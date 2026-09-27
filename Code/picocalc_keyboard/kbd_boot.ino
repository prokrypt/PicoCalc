#include "kbd_boot.h"

// Must match Code/picocalc_kbd_bootloader/bl_core.h
#define BKP_ENTER_MAGIC 0xB007
#define BKP_TRIAL       0x7E57
#define TRIAL_CONFIRM_MS 500   // loop() has run this long: the new image is good

static volatile uint8_t boot_pending = 0;
static unsigned long boot_pending_at = 0;
static uint8_t trial_confirmed = 0;

static void bkp_enable(void) {
  RCC->APB1ENR |= RCC_APB1ENR_PWREN | RCC_APB1ENR_BKPEN;
  PWR->CR |= PWR_CR_DBP;
}

static bool above_bootloader(void) {
  return SCB->VTOR == KBD_APP_BASE;
}

void kbd_boot_request(uint8_t value) {
  // Only with the confirm byte, and only if there is a bootloader to go to:
  // on a board without one, BKP_DR1 would do nothing and the reset would just
  // power-cycle the Pico.
  if (value == KBD_BOOT_CONFIRM && above_bootloader() && !boot_pending) {
    boot_pending_at = millis();
    boot_pending = 1;
  }
}

uint8_t kbd_boot_flags(void) {
  uint8_t f = 0;
  if (above_bootloader()) f |= KBD_BOOT_FLAG_BL;
  if (trial_confirmed == 1) f |= KBD_BOOT_FLAG_TRIAL;
  return f;
}

void kbd_boot_poll(void) {
  IWDG->KR = 0xAAAA;  // feed; harmless when the bootloader didn't start the watchdog

  if (!trial_confirmed && millis() > TRIAL_CONFIRM_MS) {
    bkp_enable();
    if (BKP->DR2 == BKP_TRIAL) {
      BKP->DR2 = 0;
      trial_confirmed = 1;
    }
    if (!trial_confirmed) trial_confirmed = 0xFF;  // not a trial boot; don't check again
  }

  // Give the Pico time to finish the I2C write that asked for this.
  if (boot_pending && millis() - boot_pending_at > 20) {
    bkp_enable();
    BKP->DR1 = BKP_ENTER_MAGIC;
    NVIC_SystemReset();
  }
}
