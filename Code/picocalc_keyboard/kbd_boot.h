#ifndef KBD_BOOT_H
#define KBD_BOOT_H

#include <stdint.h>

// I2C bootloader support (see Code/picocalc_kbd_bootloader/README.md).
// This app must be linked at 0x08002000 when used with that bootloader.
#define KBD_APP_BASE       0x08002000UL
#define KBD_BOOT_CONFIRM   0xB0   // value to write to REG_ID_BOOT
#define KBD_BOOT_SIG       0xB0   // REG_ID_BOOT read: high nibble, so the Pico can tell this
                                  // register from another firmware's before writing to it
#define KBD_BOOT_FLAG_BL   0x01   // REG_ID_BOOT read: running above the bootloader
#define KBD_BOOT_FLAG_TRIAL 0x02  // REG_ID_BOOT read: this boot was a trial and is confirmed

void kbd_boot_request(uint8_t value);  // from the I2C receive ISR
uint8_t kbd_boot_flags(void);          // KBD_BOOT_SIG | KBD_BOOT_FLAG_*
void kbd_boot_poll(void);              // from loop(): watchdog, trial confirm, pending enter

#endif
