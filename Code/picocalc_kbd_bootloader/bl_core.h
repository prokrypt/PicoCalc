/*
 * PicoCalc keyboard MCU (STM32F103R8) I2C bootloader: protocol core.
 *
 * Hardware-independent: all flash access goes through the hal_* functions,
 * which bl_main.c implements for the STM32 and tools/host_hal.c implements
 * for the host-side test harness.
 *
 * Flash map (64 KB part, 1 KB pages):
 *   0x08000000 - 0x08001FFF  bootloader (8 KB)
 *   0x08002000 - 0x0800FBFF  keyboard app (55 KB)
 *   0x0800FC00 - 0x0800FFFF  info page: {magic, len, crc32, ~magic}
 *
 * The protocol is documented in README.md.
 */
#ifndef BL_CORE_H
#define BL_CORE_H

#include <stdint.h>

#define BL_VERSION        1u
#define BL_MARKER         0xB1u   /* status byte 0; never a valid app reply */

#define FLASH_START       0x08000000u
#define FLASH_PAGE        1024u
#define BL_SIZE           0x2000u
#define APP_BASE          (FLASH_START + BL_SIZE)
#define INFO_ADDR         (FLASH_START + 0xFC00u)
#define APP_MAX           (INFO_ADDR - APP_BASE)
#define RAM_START         0x20000000u
#define RAM_END           0x20005000u   /* 20 KB */

#define INFO_MAGIC        0x4B424F4Bu   /* "KOBK" little-endian */

#define I2C_ADDR          0x1Fu         /* same address as the keyboard app */
#define WRITE_MAX         128u
#define RX_MAX            (1u + 4u + 1u + WRITE_MAX + 2u)
#define STATUS_LEN        24u

/* BKP_DR1 value the app writes before resetting into the bootloader */
#define BKP_ENTER_MAGIC   0xB007u
/* BKP_DR2: trial boot of a freshly flashed app. CMD_BOOT arms it, the next
 * reset turns ARM into TRIAL and starts the watchdog, and the app clears it
 * once it has run for a moment (kbd_boot.ino). Still TRIAL at reset = the new
 * app never got going, so the bootloader stays. */
#define BKP_TRIAL_ARM     0x7E51u
#define BKP_TRIAL         0x7E57u

/* why the bootloader is running (status byte 20) */
#define WHY_ASKED   1u   /* the app asked (REG 0x0E)                  */
#define WHY_NO_APP  2u   /* nothing committed, or it failed its check */
#define WHY_TRIAL   3u   /* the last flashed app never confirmed      */

/* commands (first byte of an I2C write) */
#define CMD_INFO    0x01u  /* -> OK                                          */
#define CMD_ERASE   0x10u  /* u32 len -> BUSY (value=pages done) -> OK       */
#define CMD_WRITE   0x20u  /* u32 off, u8 n, n bytes, u16 sum -> OK          */
#define CMD_CRC     0x30u  /* u32 len -> BUSY -> OK (value=crc32)            */
#define CMD_COMMIT  0x40u  /* u32 len, u32 crc -> BUSY -> OK                 */
#define CMD_BOOT    0x50u  /* -> OK, then reset into the app 20 ms later     */
#define CMD_PING    0x51u  /* -> OK; resets the idle timeout                 */

/* states */
#define ST_IDLE 0u
#define ST_BUSY 1u
#define ST_OK   2u
#define ST_ERR  3u

/* errors */
#define E_NONE        0u
#define E_LEN         2u   /* frame length wrong for the command        */
#define E_ARG         3u   /* offset/length out of range or misaligned  */
#define E_SUM         4u   /* WRITE checksum mismatch                   */
#define E_NOT_ERASED  5u   /* WRITE before ERASE, or target not blank   */
#define E_FLASH       6u   /* flash controller reported an error        */
#define E_VERIFY      7u   /* read-back differs after programming       */
#define E_CRC         8u   /* COMMIT crc differs from flash contents    */
#define E_VECTORS     9u   /* image SP/reset vector not plausible       */
#define E_OVERFLOW   11u   /* I2C write longer than RX_MAX              */
#define E_NO_APP     12u   /* BOOT with no valid committed app          */

/* implemented by the platform */
uint32_t hal_read32(uint32_t addr);
uint16_t hal_read16(uint32_t addr);
int      hal_erase_page(uint32_t addr);          /* 0 ok, -1 error */
int      hal_program16(uint32_t addr, uint16_t v); /* 0 ok, -1 error */

/* implemented by bl_core.c */
void     bl_init(void);
void     bl_on_write(const uint8_t *buf, uint32_t n, int overflow);
void     bl_status(uint8_t out[STATUS_LEN]);
int      bl_step(void);           /* run one job slice; 1 while a job is active */
int      bl_app_valid(void);      /* committed info page + vectors + crc */
uint32_t bl_crc32(uint32_t crc, uint32_t addr, uint32_t n);

extern volatile uint32_t bl_activity;        /* bumped on every accepted command */
extern volatile uint8_t  bl_reset_requested; /* set by CMD_BOOT */
extern uint8_t bl_boot_reason;               /* WHY_* */

#endif
