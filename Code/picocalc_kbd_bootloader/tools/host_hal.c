/* Host-side flash model for testing bl_core.c (see sim_test.py). Mimics STM32F1
 * rules: erase sets a 1 KB page to 0xFF, a halfword can only be programmed from
 * 0xFFFF (or to 0x0000), and the bootloader's own 8 KB is off limits. */
#include <string.h>
#include "bl_core.h"

#define FLASH_SIZE 0x10000u
static uint8_t flash[FLASH_SIZE];
int host_fail_program_at = -1;   /* test hook: make this offset's program fail */

uint8_t *host_flash(void) { return flash; }
void host_flash_blank(void) { memset(flash, 0xFF, sizeof flash); }

static int ok_addr(uint32_t a) { return a >= APP_BASE && a < FLASH_START + FLASH_SIZE; }

uint32_t hal_read32(uint32_t a) {
  uint32_t o = a - FLASH_START, v;
  memcpy(&v, flash + o, 4);
  return v;
}

uint16_t hal_read16(uint32_t a) {
  uint32_t o = a - FLASH_START;
  return (uint16_t)(flash[o] | (flash[o + 1] << 8));
}

int hal_erase_page(uint32_t a) {
  if (!ok_addr(a) || (a % FLASH_PAGE)) return -1;
  memset(flash + (a - FLASH_START), 0xFF, FLASH_PAGE);
  return 0;
}

int hal_program16(uint32_t a, uint16_t v) {
  if (!ok_addr(a) || (a & 1u)) return -1;
  uint32_t o = a - FLASH_START;
  if ((int)o == host_fail_program_at) return -1;
  if (hal_read16(a) != 0xFFFFu && v != 0) return -1;  /* PGERR */
  flash[o] = (uint8_t)v;
  flash[o + 1] = (uint8_t)(v >> 8);
  return 0;
}
