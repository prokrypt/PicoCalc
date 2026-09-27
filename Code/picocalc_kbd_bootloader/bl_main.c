/*
 * PicoCalc keyboard MCU (STM32F103R8) I2C bootloader: hardware side.
 *
 * Bare metal, no HAL, no interrupts: runs on the 8 MHz HSI and polls I2C1
 * (remapped to PB8/PB9, the same pins and address 0x1F the keyboard app uses).
 *
 * Boot decision, taken before any peripheral is touched:
 *   BKP_DR1 == BKP_ENTER_MAGIC  -> clear it, stay (the app asked for this)
 *   BKP_DR2 == BKP_TRIAL        -> the freshly flashed app never confirmed: stay
 *   app committed and valid     -> jump to the app at APP_BASE; if CMD_BOOT
 *                                  armed a trial, start the watchdog first
 *   otherwise                   -> stay (nothing valid to run)
 *
 * While staying: Pico power (PA13) held on, LCD backlight (PA8) full on so the
 * Pico's progress messages are readable, audio amp (PA14) off, LED (PC13)
 * blinks. If we were asked in by the app and nothing talks to us for
 * IDLE_TIMEOUT_MS while a valid app is still present, reset back into it.
 *
 * The ROM bootloader (DIP switch 1 + USB-C, STM32CubeProgrammer) is untouched
 * and stays the recovery path for everything, including this bootloader.
 */
#include "bl_core.h"

#define REG32(a) (*(volatile uint32_t *)(a))
#define REG16(a) (*(volatile uint16_t *)(a))

/* RCC */
#define RCC_APB1RSTR  REG32(0x40021010u)
#define RCC_APB2ENR   REG32(0x40021018u)
#define RCC_APB1ENR   REG32(0x4002101Cu)
#define APB2_AFIO     (1u << 0)
#define APB2_IOPA     (1u << 2)
#define APB2_IOPB     (1u << 3)
#define APB2_IOPC     (1u << 4)
#define APB1_I2C1     (1u << 21)
#define APB1_BKP      (1u << 27)
#define APB1_PWR      (1u << 28)

/* GPIO */
#define GPIOA 0x40010800u
#define GPIOB 0x40010C00u
#define GPIOC 0x40011000u
#define GPIO_CRH(p)  REG32((p) + 0x04u)
#define GPIO_BSRR(p) REG32((p) + 0x10u)
#define GPIO_BRR(p)  REG32((p) + 0x14u)
#define OUT_PP_2MHZ  0x2u
#define AF_OD_2MHZ   0xEu

/* AFIO */
#define AFIO_MAPR       REG32(0x40010004u)
#define MAPR_I2C1_REMAP (1u << 1)
#define MAPR_SWJ_OFF    (4u << 24)   /* JTAG+SWD off: PA13/PA14 become GPIO, as in the app */

/* PWR / BKP */
#define PWR_CR   REG32(0x40007000u)
#define PWR_DBP  (1u << 8)
#define BKP_DR1  REG16(0x40006C04u)
#define BKP_DR2  REG16(0x40006C08u)

/* IWDG */
#define IWDG_KR   REG32(0x40003000u)
#define IWDG_PR   REG32(0x40003004u)
#define IWDG_RLR  REG32(0x40003008u)
#define IWDG_SR   REG32(0x4000300Cu)

/* I2C1 */
#define I2C_CR1   REG32(0x40005400u)
#define I2C_CR2   REG32(0x40005404u)
#define I2C_OAR1  REG32(0x40005408u)
#define I2C_DR    REG32(0x40005410u)
#define I2C_SR1   REG32(0x40005414u)
#define I2C_SR2   REG32(0x40005418u)
#define CR1_PE    (1u << 0)
#define CR1_ACK   (1u << 10)
#define CR1_SWRST (1u << 15)
#define SR1_ADDR  (1u << 1)
#define SR1_BTF   (1u << 2)
#define SR1_STOPF (1u << 4)
#define SR1_RXNE  (1u << 6)
#define SR1_TXE   (1u << 7)
#define SR1_BERR  (1u << 8)
#define SR1_ARLO  (1u << 9)
#define SR1_AF    (1u << 10)
#define SR1_OVR   (1u << 11)
#define SR2_BUSY  (1u << 1)
#define SR2_TRA   (1u << 2)

/* FLASH */
#define FLASH_KEYR REG32(0x40022004u)
#define FLASH_SR   REG32(0x4002200Cu)
#define FLASH_CR   REG32(0x40022010u)
#define FLASH_AR   REG32(0x40022014u)
#define FSR_BSY    (1u << 0)
#define FSR_PGERR  (1u << 2)
#define FSR_WRPRT  (1u << 4)
#define FSR_EOP    (1u << 5)
#define FCR_PG     (1u << 0)
#define FCR_PER    (1u << 1)
#define FCR_STRT   (1u << 6)
#define FCR_LOCK   (1u << 7)

/* core */
#define SCB_VTOR   REG32(0xE000ED08u)
#define SCB_AIRCR  REG32(0xE000ED0Cu)
#define SYST_CSR   REG32(0xE000E010u)
#define SYST_RVR   REG32(0xE000E014u)
#define SYST_CVR   REG32(0xE000E018u)

#define IDLE_TIMEOUT_MS 30000u
#define BOOT_DELAY_MS   20u

/* ---- flash HAL for bl_core.c ---- */

uint32_t hal_read32(uint32_t addr) { return REG32(addr); }
uint16_t hal_read16(uint32_t addr) { return REG16(addr); }

static int flash_allowed(uint32_t addr) {
  return addr >= APP_BASE && addr < INFO_ADDR + FLASH_PAGE;  /* never ourselves */
}

static int flash_wait(void) {
  while (FLASH_SR & FSR_BSY) {}
  uint32_t sr = FLASH_SR;
  FLASH_SR = FSR_EOP | FSR_PGERR | FSR_WRPRT;  /* write 1 to clear */
  return (sr & (FSR_PGERR | FSR_WRPRT)) ? -1 : 0;
}

static void flash_unlock(void) {
  if (FLASH_CR & FCR_LOCK) {
    FLASH_KEYR = 0x45670123u;
    FLASH_KEYR = 0xCDEF89ABu;
  }
}

int hal_erase_page(uint32_t addr) {
  if (!flash_allowed(addr) || (addr % FLASH_PAGE)) return -1;
  flash_unlock();
  flash_wait();
  FLASH_CR |= FCR_PER;
  FLASH_AR = addr;
  FLASH_CR |= FCR_STRT;
  int r = flash_wait();
  FLASH_CR &= ~FCR_PER;
  FLASH_CR |= FCR_LOCK;
  return r;
}

int hal_program16(uint32_t addr, uint16_t v) {
  if (!flash_allowed(addr) || (addr & 1u)) return -1;
  flash_unlock();
  flash_wait();
  FLASH_CR |= FCR_PG;
  REG16(addr) = v;
  int r = flash_wait();
  FLASH_CR &= ~FCR_PG;
  FLASH_CR |= FCR_LOCK;
  return r;
}

/* ---- time: SysTick polled, no interrupt ---- */

static uint32_t now_ms;

static void tick_init(void) {
  SYST_RVR = 8000u - 1u;   /* 1 ms at 8 MHz HSI */
  SYST_CVR = 0;
  SYST_CSR = 5u;           /* core clock, enabled, no interrupt */
}

static void tick_poll(void) {
  if (SYST_CSR & (1u << 16)) now_ms++;  /* COUNTFLAG clears on read; ticks lost during flash stalls are fine */
}

/* ---- I2C1 slave, polled ---- */

static uint8_t rx_buf[RX_MAX];
static uint32_t rx_len;
static uint8_t rx_active, rx_overflow;
static uint8_t tx_buf[STATUS_LEN];
static uint32_t tx_idx;
static uint8_t tx_active;
static uint8_t tx_flush;   /* a byte the master never took is left in DR */
static uint32_t stall_since;

static void i2c_init(void) {
  RCC_APB1ENR |= APB1_I2C1;
  RCC_APB1RSTR |= APB1_I2C1;
  RCC_APB1RSTR &= ~APB1_I2C1;
  I2C_CR1 = CR1_SWRST;
  I2C_CR1 = 0;
  I2C_CR2 = 8u;                                  /* PCLK1 = 8 MHz */
  I2C_OAR1 = (1u << 14) | (I2C_ADDR << 1);        /* bit 14 must be kept at 1 */
  I2C_CR1 = CR1_PE;
  I2C_CR1 = CR1_PE | CR1_ACK;                     /* ACK only sticks once PE is set */
}

static void i2c_end_write(void) {
  if (rx_active) {
    rx_active = 0;
    bl_on_write(rx_buf, rx_len, rx_overflow);
  }
}

static void i2c_poll(void) {
  uint32_t sr1 = I2C_SR1;

  if (sr1 & (SR1_BERR | SR1_ARLO | SR1_OVR)) {
    I2C_SR1 = ~(SR1_BERR | SR1_ARLO | SR1_OVR) & 0xFFFFu;
    rx_active = 0;
    tx_active = 0;
  }

  if (sr1 & SR1_AF) {                     /* master NACKed: end of a read */
    I2C_SR1 = ~SR1_AF & 0xFFFFu;
    tx_active = 0;
    /* After a short read (e.g. a 2-byte register read) the next status byte may
     * already sit in DR and would go out first on the next read. DR can only be
     * emptied by disabling the peripheral, and PE=0 only takes effect once the
     * bus is idle (RM0008 I2C_CR1.PE), so do it after the master's STOP. */
    if (!(I2C_SR1 & SR1_TXE)) tx_flush = 1;
  }

  if (tx_flush) {
    uint32_t s1 = I2C_SR1;
    if (!(s1 & SR1_ADDR)) {
      uint32_t s2 = I2C_SR2;               /* SR1 (no ADDR) then SR2: see the stall guard below */
      if (!(s2 & SR2_BUSY)) {
        I2C_CR1 = 0;                       /* also clears ACK */
        I2C_CR1 = CR1_PE;
        I2C_CR1 = CR1_PE | CR1_ACK;
        tx_flush = 0;
      }
    }
  }

  if (sr1 & SR1_RXNE) {
    uint8_t b = (uint8_t)I2C_DR;
    if (rx_active) {
      if (rx_len < RX_MAX) rx_buf[rx_len++] = b;
      else rx_overflow = 1;
    }
  }

  if (sr1 & SR1_ADDR) {
    i2c_end_write();                       /* repeated start after a write */
    uint32_t sr2 = I2C_SR2;                /* SR1 then SR2 read clears ADDR */
    if (sr2 & SR2_TRA) {
      bl_status(tx_buf);
      tx_idx = 0;
      tx_active = 1;
    } else {
      rx_len = 0;
      rx_overflow = 0;
      rx_active = 1;
    }
    sr1 = I2C_SR1;
  }

  /* Stall guard: if an address match was cleared behind our back (it could land
   * between the SR1 and SR2 reads of the flush check), the master sits in a read
   * with SCL stretched and we'd never answer. Between a NACK and the master's
   * STOP the same flags show for microseconds only, so wait 5 ms before acting. */
  if (!tx_active && (sr1 & SR1_TXE) && !(sr1 & (SR1_AF | SR1_BTF))) {
    if (!stall_since) stall_since = now_ms + 1u;
    else if (now_ms + 1u - stall_since > 5u && (I2C_SR2 & (SR2_TRA | SR2_BUSY)) == (SR2_TRA | SR2_BUSY)) {
      bl_status(tx_buf);
      tx_idx = 0;
      tx_active = 1;
      stall_since = 0;
    }
  } else {
    stall_since = 0;
  }

  if (tx_active && (sr1 & SR1_TXE)) {
    if (tx_idx < STATUS_LEN)
      I2C_DR = tx_buf[tx_idx++];
    else if (sr1 & SR1_BTF)
      I2C_DR = 0xFFu;  /* master wants more than the status: pad rather than stretch forever */
  }

  if (sr1 & SR1_STOPF) {
    I2C_CR1 = I2C_CR1;                     /* SR1 read then CR1 write clears STOPF */
    i2c_end_write();
    tx_active = 0;
  }
}

/* ---- boot ---- */

static void system_reset(void) {
  __asm volatile ("dsb");
  SCB_AIRCR = 0x05FA0004u;                 /* SYSRESETREQ */
  for (;;) {}
}

static void jump_to_app(void) {
  uint32_t sp = REG32(APP_BASE);
  uint32_t pc = REG32(APP_BASE + 4u);
  SYST_CSR = 0;
  RCC_APB1ENR = 0;                         /* back to reset values for the app */
  RCC_APB2ENR = 0;
  SCB_VTOR = APP_BASE;                     /* in case the app's SystemInit leaves VTOR alone */
  __asm volatile (
    "msr msp, %0\n"
    "bx  %1\n"
    :: "r"(sp), "r"(pc));
  for (;;) {}
}

static void bkp_write(volatile uint16_t *reg, uint16_t v) {
  PWR_CR |= PWR_DBP;
  *reg = v;
  PWR_CR &= ~PWR_DBP;
}

/* Watchdog for the trial boot: LSI ~40 kHz / 64 * 2500 = ~4 s. The app feeds it
 * from loop() (kbd_boot.ino). A reset stops it again, so it only runs after a
 * trial boot until the next reset or power cycle. */
static void iwdg_start(void) {
  /* Start first: that forces the LSI on, and PR/RLR only update (PVU/RVU clear)
   * while the LSI runs (RM0008 19.3, same order as the ST HAL). */
  IWDG_KR = 0xCCCCu;
  IWDG_KR = 0x5555u;
  IWDG_PR = 4u;
  IWDG_RLR = 2500u;
  for (uint32_t n = 0; (IWDG_SR & 3u) && n < 200000u; n++) {}  /* ~5 LSI cycles; never hang here */
  IWDG_KR = 0xAAAAu;
}

/* Returns a WHY_* reason to stay, or 0 to try the app. */
static uint8_t boot_flags(int *trial) {
  RCC_APB1ENR |= APB1_PWR | APB1_BKP;
  (void)RCC_APB1ENR;                        /* let the clock enable land before BKP reads */
  *trial = 0;
  if (BKP_DR1 == BKP_ENTER_MAGIC) {
    bkp_write(&BKP_DR1, 0);                 /* one-shot: the next reset goes to the app */
    return WHY_ASKED;
  }
  uint16_t t = BKP_DR2;
  if (t == BKP_TRIAL) {
    bkp_write(&BKP_DR2, 0);                 /* new app never confirmed */
    return WHY_TRIAL;
  }
  if (t == BKP_TRIAL_ARM) {
    bkp_write(&BKP_DR2, BKP_TRIAL);
    *trial = 1;
  }
  return 0;
}

static void pins_init(void) {
  RCC_APB2ENR |= APB2_AFIO | APB2_IOPA | APB2_IOPB | APB2_IOPC;
  AFIO_MAPR = MAPR_SWJ_OFF | MAPR_I2C1_REMAP;

  /* PA13 Pico enable HIGH first, then PA8 LCD backlight HIGH, PA14 amp LOW */
  GPIO_BSRR(GPIOA) = (1u << 13) | (1u << 8);
  GPIO_BRR(GPIOA) = (1u << 14);
  uint32_t crh = GPIO_CRH(GPIOA);
  crh &= ~((0xFu << 20) | (0xFu << 24) | 0xFu);
  crh |= (OUT_PP_2MHZ << 20) | (OUT_PP_2MHZ << 24) | OUT_PP_2MHZ;
  GPIO_CRH(GPIOA) = crh;

  /* PC13 indicator LED (active low) */
  GPIO_CRH(GPIOC) = (GPIO_CRH(GPIOC) & ~(0xFu << 20)) | (OUT_PP_2MHZ << 20);

  /* PB8 SCL, PB9 SDA: alternate function open drain */
  GPIO_CRH(GPIOB) = (GPIO_CRH(GPIOB) & ~0xFFu) | (AF_OD_2MHZ << 4) | AF_OD_2MHZ;
}

int main(void) {
  int trial;
  uint8_t why = boot_flags(&trial);
  if (!why) {
    if (bl_app_valid()) {
      if (trial) iwdg_start();
      jump_to_app();
    }
    if (trial) bkp_write(&BKP_DR2, 0);
    why = WHY_NO_APP;
  }
  int asked = why == WHY_ASKED;

  pins_init();
  tick_init();
  bl_init();
  bl_boot_reason = why;
  i2c_init();

  uint32_t seen_activity = bl_activity;
  uint32_t last_activity_ms = 0;
  uint32_t led_ms = 0;
  uint32_t reset_at = 0;
  uint8_t led = 0;

  for (;;) {
    i2c_poll();
    int busy = bl_step();
    tick_poll();

    if (bl_activity != seen_activity) {
      seen_activity = bl_activity;
      last_activity_ms = now_ms;
    }

    if (bl_reset_requested && !reset_at) reset_at = now_ms + BOOT_DELAY_MS;  /* let the Pico read OK */
    if (reset_at && (int32_t)(now_ms - reset_at) >= 0) {
      bkp_write(&BKP_DR2, BKP_TRIAL_ARM);  /* first run of the new app is a trial */
      system_reset();
    }

    if (asked && !busy && now_ms - last_activity_ms > IDLE_TIMEOUT_MS) {
      if (bl_app_valid()) system_reset();  /* Pico went away; give the keyboard back */
      asked = 0;                            /* no valid app: wait here for good */
    }

    /* LED: fast blink while working, slow while waiting */
    uint32_t period = (now_ms - last_activity_ms < 1000u) ? 100u : 500u;
    if (now_ms - led_ms >= period) {
      led_ms = now_ms;
      led ^= 1u;
      if (led) GPIO_BRR(GPIOC) = 1u << 13; else GPIO_BSRR(GPIOC) = 1u << 13;
    }
  }
}

/* ---- startup ---- */

extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss, _estack;

void Reset_Handler(void) {
  uint32_t *src = &_sidata, *dst = &_sdata;
  while (dst < &_edata) *dst++ = *src++;
  for (dst = &_sbss; dst < &_ebss;) *dst++ = 0;
  main();
  system_reset();
}

void Default_Handler(void) {
  system_reset();  /* any fault: start over; the app is still there if it was valid */
}

__attribute__((section(".isr_vector"), used))
const void *const vector_table[16] = {
  &_estack,
  (const void *)Reset_Handler,
  (const void *)Default_Handler,  /* NMI */
  (const void *)Default_Handler,  /* HardFault */
  (const void *)Default_Handler,  /* MemManage */
  (const void *)Default_Handler,  /* BusFault */
  (const void *)Default_Handler,  /* UsageFault */
  0, 0, 0, 0,
  (const void *)Default_Handler,  /* SVC */
  (const void *)Default_Handler,  /* DebugMon */
  0,
  (const void *)Default_Handler,  /* PendSV */
  (const void *)Default_Handler,  /* SysTick */
};
