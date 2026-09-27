/*
 * PicoCalc keyboard MCU I2C bootloader: protocol core. See bl_core.h.
 *
 * Long operations (erase, crc, commit) run as jobs, one slice per bl_step()
 * call, so the main loop keeps servicing I2C between slices and the Pico sees
 * at most one page erase (~20 ms) of clock stretching.
 */
#include "bl_core.h"

volatile uint32_t bl_activity;
volatile uint8_t  bl_reset_requested;
uint8_t bl_boot_reason;

enum { JOB_NONE, JOB_ERASE, JOB_CRC, JOB_COMMIT };

static uint8_t  st_state, st_seq, st_cmd, st_err;
static uint32_t st_value;

static uint8_t  job;
static uint32_t job_len;      /* bytes the job covers                     */
static uint32_t job_pos;      /* erase: pages done; crc: bytes done       */
static uint32_t job_crc;      /* running crc                              */
static uint32_t job_want;     /* commit: crc the host expects             */
static uint32_t erased_len;   /* bytes of app area known blank since ERASE */
static uint8_t  info_erased;  /* erase job: info page done                */

#define CRC_SLICE 256u

static const uint32_t crc_tab[16] = {
  0x00000000, 0x1DB71064, 0x3B6E20C8, 0x26D930AC,
  0x76DC4190, 0x6B6B51F4, 0x4DB26158, 0x5005713C,
  0xEDB88320, 0xF00F9344, 0xD6D6A3E8, 0xCB61B38C,
  0x9B64C2B0, 0x86D3D2D4, 0xA00AE278, 0xBDBDF21C,
};

/* zlib/binascii-compatible crc32 over flash, chainable like zlib.crc32(data, crc) */
uint32_t bl_crc32(uint32_t crc, uint32_t addr, uint32_t n) {
  uint32_t c = ~crc;
  while (n) {
    uint32_t w = hal_read16(addr & ~1u);
    uint8_t b = (addr & 1u) ? (uint8_t)(w >> 8) : (uint8_t)w;
    c ^= b;
    c = (c >> 4) ^ crc_tab[c & 15u];
    c = (c >> 4) ^ crc_tab[c & 15u];
    addr++;
    n--;
  }
  return ~c;
}

static uint32_t get32(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static void put32(uint8_t *p, uint32_t v) {
  p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}

static void ok(uint32_t value) { st_state = ST_OK; st_err = E_NONE; st_value = value; }
static void fail(uint8_t e)    { st_state = ST_ERR; st_err = e; job = JOB_NONE; }

static int vectors_ok(uint32_t len) {
  uint32_t sp = hal_read32(APP_BASE);
  uint32_t pc = hal_read32(APP_BASE + 4u);
  if (sp <= RAM_START || sp > RAM_END || (sp & 3u)) return 0;
  if (!(pc & 1u)) return 0;
  pc &= ~1u;
  return pc >= APP_BASE + 8u && pc < APP_BASE + len;
}

int bl_app_valid(void) {
  uint32_t magic = hal_read32(INFO_ADDR);
  uint32_t len   = hal_read32(INFO_ADDR + 4u);
  uint32_t crc   = hal_read32(INFO_ADDR + 8u);
  uint32_t inv   = hal_read32(INFO_ADDR + 12u);
  if (magic != INFO_MAGIC || inv != ~INFO_MAGIC) return 0;
  if (len < 8u || len > APP_MAX) return 0;
  if (!vectors_ok(len)) return 0;
  return bl_crc32(0, APP_BASE, len) == crc;
}

static int program_words(uint32_t addr, const uint32_t *w, uint32_t count) {
  for (uint32_t i = 0; i < count; i++) {
    for (uint32_t h = 0; h < 2u; h++) {
      uint32_t a = addr + i * 4u + h * 2u;
      uint16_t v = (uint16_t)(w[i] >> (16u * h));
      if (hal_program16(a, v)) return E_FLASH;
      if (hal_read16(a) != v) return E_VERIFY;
    }
  }
  return E_NONE;
}

static void cmd_write(const uint8_t *buf, uint32_t n) {
  if (n < 1u + 4u + 1u + 2u) { fail(E_LEN); return; }
  uint32_t off = get32(buf + 1);
  uint32_t cnt = buf[5];
  if (n != 1u + 4u + 1u + cnt + 2u) { fail(E_LEN); return; }

  uint16_t sum = 0;
  for (uint32_t i = 0; i < n - 2u; i++) sum = (uint16_t)(sum + buf[i]);
  if (sum != (uint16_t)(buf[n - 2u] | (buf[n - 1u] << 8))) { fail(E_SUM); return; }

  if (cnt == 0u || cnt > WRITE_MAX || (cnt & 1u) || (off & 1u) || off > APP_MAX - cnt) {
    fail(E_ARG);
    return;
  }
  if (off + cnt > erased_len) { fail(E_NOT_ERASED); return; }

  const uint8_t *d = buf + 6;
  for (uint32_t i = 0; i < cnt; i += 2u) {
    uint32_t a = APP_BASE + off + i;
    uint16_t v = (uint16_t)(d[i] | (d[i + 1u] << 8));
    uint16_t cur = hal_read16(a);
    if (cur == v) continue;               /* already written: retries are harmless */
    if (cur != 0xFFFFu) { fail(E_NOT_ERASED); return; }
    if (hal_program16(a, v)) { fail(E_FLASH); return; }
    if (hal_read16(a) != v) { fail(E_VERIFY); return; }
  }
  ok(off + cnt);
}

void bl_init(void) {
  st_state = ST_IDLE;
  st_seq = st_cmd = st_err = 0;
  st_value = 0;
  job = JOB_NONE;
  erased_len = 0;
  bl_reset_requested = 0;
}

void bl_on_write(const uint8_t *buf, uint32_t n, int overflow) {
  if (n == 0u) return;
  uint8_t c = buf[0];
  switch (c) {
    case CMD_INFO: case CMD_ERASE: case CMD_WRITE: case CMD_CRC:
    case CMD_COMMIT: case CMD_BOOT: case CMD_PING:
      break;
    default:
      return;  /* stray keyboard-driver traffic: leave the status alone */
  }
  if (job != JOB_NONE) return;  /* host must wait for BUSY to clear */

  st_seq++;
  st_cmd = c;
  st_err = E_NONE;
  st_value = 0;
  bl_activity++;
  if (overflow) { fail(E_OVERFLOW); return; }

  switch (c) {
    case CMD_INFO:
    case CMD_PING:
      if (n != 1u) { fail(E_LEN); return; }
      ok(0);
      break;

    case CMD_ERASE: {
      if (n != 5u) { fail(E_LEN); return; }
      uint32_t len = get32(buf + 1);
      if (len == 0u || len > APP_MAX) { fail(E_ARG); return; }
      erased_len = 0;
      job = JOB_ERASE;
      job_len = (len + FLASH_PAGE - 1u) / FLASH_PAGE;  /* pages */
      job_pos = 0;
      info_erased = 0;
      st_state = ST_BUSY;
    } break;

    case CMD_WRITE:
      cmd_write(buf, n);
      break;

    case CMD_CRC:
    case CMD_COMMIT: {
      if (n != (c == CMD_CRC ? 5u : 9u)) { fail(E_LEN); return; }
      uint32_t len = get32(buf + 1);
      if (len == 0u || len > APP_MAX) { fail(E_ARG); return; }
      if (c == CMD_COMMIT) {
        if (len < 8u || len > erased_len) { fail(E_ARG); return; }
        job_want = get32(buf + 5);
      }
      job = (c == CMD_CRC) ? JOB_CRC : JOB_COMMIT;
      job_len = len;
      job_pos = 0;
      job_crc = 0;
      st_state = ST_BUSY;
    } break;

    case CMD_BOOT:
      if (n != 1u) { fail(E_LEN); return; }
      if (!bl_app_valid()) { fail(E_NO_APP); return; }
      ok(0);
      bl_reset_requested = 1;
      break;
  }
}

int bl_step(void) {
  switch (job) {
    case JOB_ERASE:
      if (!info_erased) {
        /* invalidate the app first, so a power loss mid-flash leaves us in the bootloader */
        if (hal_erase_page(INFO_ADDR) || hal_read32(INFO_ADDR) != 0xFFFFFFFFu) { fail(E_FLASH); return 0; }
        info_erased = 1;
        st_value = 1u;  /* value = pages erased, info page included */
        return 1;
      }
      if (job_pos < job_len) {
        uint32_t a = APP_BASE + job_pos * FLASH_PAGE;
        if (hal_erase_page(a) || hal_read32(a) != 0xFFFFFFFFu ||
            hal_read32(a + FLASH_PAGE - 4u) != 0xFFFFFFFFu) {
          fail(E_FLASH);
          return 0;
        }
        job_pos++;
        erased_len = job_pos * FLASH_PAGE;
        st_value = 1u + job_pos;
        return 1;
      }
      job = JOB_NONE;
      ok(job_pos);
      return 0;

    case JOB_CRC:
    case JOB_COMMIT: {
      if (job_pos < job_len) {
        uint32_t n = job_len - job_pos;
        if (n > CRC_SLICE) n = CRC_SLICE;
        job_crc = bl_crc32(job_crc, APP_BASE + job_pos, n);
        job_pos += n;
        st_value = job_pos;
        return 1;
      }
      uint8_t j = job;
      job = JOB_NONE;
      if (j == JOB_CRC) { ok(job_crc); return 0; }

      if (job_crc != job_want) { st_value = job_crc; fail(E_CRC); return 0; }
      if (!vectors_ok(job_len)) { fail(E_VECTORS); return 0; }
      if (hal_read32(INFO_ADDR) != 0xFFFFFFFFu) { fail(E_NOT_ERASED); return 0; }
      uint32_t info[4] = { INFO_MAGIC, job_len, job_crc, ~INFO_MAGIC };
      uint8_t e = (uint8_t)program_words(INFO_ADDR, info, 4u);
      if (e) { fail(e); return 0; }
      erased_len = 0;  /* committed: no more writes until the next ERASE */
      ok(job_crc);
      return 0;
    }
  }
  return 0;
}

void bl_status(uint8_t out[STATUS_LEN]) {
  out[0] = BL_MARKER;
  out[1] = BL_VERSION;
  out[2] = job != JOB_NONE ? ST_BUSY : st_state;
  out[3] = st_seq;
  out[4] = st_cmd;
  out[5] = st_err;
  out[6] = (uint8_t)FLASH_PAGE;
  out[7] = (uint8_t)(FLASH_PAGE >> 8);
  put32(out + 8, st_value);
  put32(out + 12, APP_BASE);
  put32(out + 16, APP_MAX);
  out[20] = bl_boot_reason;
  out[21] = out[22] = out[23] = 0;
}
