# PicoCalc keyboard I2C bootloader

Lets MicroPython on the Pico update the keyboard chip (STM32F103R8, I2C 0x1F)
without DIP switches or a USB cable, after one install over USB.

**Status: untested on hardware.** What has been checked:
- The bootloader builds with the STM32 core's arm-none-eabi-gcc 14.2 (2.8 KB) and with clang/lld.
- The app builds with arduino-cli 1.3.1 and STM32 core 2.10.0 at 0x08002000: 40,744 bytes, ending at
  0x0800BF28. The vector table is at 0x08002000, and `SystemInit()` sets VTOR to 0x08002000.
- `mkimage.py combined` output passes the bootloader's own validity check (`bl_app_valid`).
- `make hosttest` runs `kbdflash.py` against the real protocol code (`bl_core.c`), with a simulated
  flash, a noisy bus, stale bytes after short reads, and an app that must never be over-read.
- `bl_main.c` was reviewed against RM0008 for flash, IWDG, BKP and the I2C slave.

Not exercised: anything on a real PicoCalc.

## Why a bootloader is needed

- The STM32F103's ROM bootloader only speaks UART1 (PA9/PA10), which goes to the
  onboard CH340 USB-serial chip, not the Pico. It has no I2C mode.
- BOOT0 is DIP switch 1, which the Pico can't reach.
- The stock keyboard firmware has no update command.

So the first install is over USB-C with DIP 1 (as the Clockwork wiki describes), and
after that the Pico can flash the keyboard chip itself over the I2C bus it already uses.

## Flash map

| Range | Size | Contents |
|---|---|---|
| 0x08000000–0x08001FFF | 8 KB | this bootloader |
| 0x08002000–0x0800FBFF | 55 KB | keyboard app (`Code/picocalc_keyboard`, linked here) |
| 0x0800FC00–0x0800FFFF | 1 KB | info page: magic, length, crc32, ~magic |

## Boot flow

At reset, before touching any peripheral, the bootloader:

1. `BKP_DR1 == 0xB007` (the app asked): clear it and stay.
2. `BKP_DR2 == TRIAL`: the last flashed app never confirmed, so stay.
3. The info page is committed, the vectors are plausible, and the crc matches: jump to the app.
   If `CMD_BOOT` armed a trial boot, it starts a ~4 s watchdog first.
4. Otherwise it stays.

While it stays, the bootloader:
- holds Pico power on (PA13);
- turns the LCD backlight fully on so the Pico's progress text is readable;
- turns the audio amp off;
- blinks the LED on PC13;
- answers on I2C 0x1F.

If the app asked for the bootloader and nothing talks to it for 30 s while the app
is still intact, it resets back into the app.

The app (`kbd_boot.ino`) feeds the watchdog from `loop()`. After 500 ms of running it
clears the trial flag. A new image that hangs or faults before then comes back to the
bootloader instead of leaving the keyboard (and the Pico's power) dead.

## I2C protocol (address 0x1F, Pico is master)

A write is `[cmd, args...]`. A read returns this 24-byte status:

| Byte | Field |
|---|---|
| 0 | 0xB1 marker (the app never answers this) |
| 1 | bootloader version |
| 2 | state: 0 idle, 1 busy, 2 ok, 3 error |
| 3 | sequence number, bumped once per accepted command |
| 4 | last command |
| 5 | error code |
| 6–7 | page size |
| 8–11 | value (progress while busy, then the result) |
| 12–15 | app base |
| 16–19 | app max |
| 20 | why the bootloader is running: 1 asked, 2 no app, 3 trial failed |

| Cmd | Args | Result |
|---|---|---|
| 0x01 INFO | | ok |
| 0x10 ERASE | u32 len | busy (erases the info page first, then the app pages), then ok |
| 0x20 WRITE | u32 off, u8 n ≤ 128 (even), n bytes, u16 sum of all previous bytes | ok, value = off+n |
| 0x30 CRC | u32 len | busy, then ok, value = crc32 |
| 0x40 COMMIT | u32 len, u32 crc32 | busy, then ok (checks the crc and vectors, then writes the info page) |
| 0x50 BOOT | | ok, then reset into the app 20 ms later (refused if nothing is committed) |
| 0x51 PING | | ok, resets the idle timeout |

Details:
- Unknown bytes are ignored and leave the status alone, so stray keyboard-driver reads can't clobber it.
- A command sent while busy is ignored.
- WRITE skips halfwords that already hold the right value, so retrying after a lost ack is safe.
- crc32 matches zlib and `binascii.crc32`.

New app register: **0x0E REG_ID_BOOT**.
- Read it to get `[0x0E, flags]`: bit 0 means the app is running above the bootloader, and bit 1 means this boot was a trial and has been confirmed.
- Write 0xB0 to restart into the bootloader.

## Install once (USB-C + DIP 1)

1. `make` (or `make clang`), which gives `build/kbd_bootloader.bin`.
2. `tools/build_app.sh`, which builds the app at 0x08002000. This is the fork at 3444552
   plus the charging fix and `kbd_boot.ino`.
3. `tools/mkimage.py combined build/kbd_bootloader.bin build/app/picocalc_keyboard.ino.bin -o kbd-combined.bin`
4. DIP 1 on, connect USB-C, long-press power, and flash `kbd-combined.bin` at 0x08000000
   with STM32CubeProgrammer (UART). Then set DIP 1 off.
5. Copy the app .bin to `/sd/kbd/last_good.bin` and `kbdflash.py` to the Pico.

## Updating from MicroPython

```python
import kbdflash
kbdflash.status()                  # bootloader? app above the bootloader? old app?
kbdflash.flash('/sd/kbd/app.bin')  # ~10-15 s at 50 kHz; the Pico power-cycles at the end
```

What `flash()` does:
- It checks the image before touching anything: size, stack pointer, and that the reset vector is linked at 0x08002000.
- It refuses to run below 25 % battery unless charging or `force=True`.
- It parks the keyboard driver so timers can't interleave I2C traffic.
- It prints each step with a progress bar.

The Pico restarts at the end because the app's `setup()` drives PA13 (Pico enable) low
then high. That has always been true of this firmware.

For `main.py`, before `PicoKeyboard()` is created:

```python
import kbdflash; kbdflash.autorecover()
```

This costs one 2-byte read when all is well. It promotes `/sd/kbd/pending.bin` to
`last_good.bin` once a new image is seen running. If the keyboard chip is sitting in
its bootloader, it restarts the intact app, or reflashes `last_good.bin`.

## Register review notes (RM0008)

- **Flash.**
  - Unlock with KEYR 0x45670123 then 0xCDEF89AB.
  - Page erase: PER, AR, STRT, then wait for BSY.
  - Program: PG, one halfword write, then wait for BSY.
  - Every operation checks PGERR and WRPRTERR, relocks, and reads back.
  - Erases and writes are refused below 0x08002000. Option bytes (OPTKEYR) are never touched.
  - Runs on HSI at 8 MHz, as programming requires, with 0 wait states.
- **IWDG.** Started with 0xCCCC before writing PR/RLR. That forces the LSI on; otherwise PVU/RVU never clear, and the old order hung forever here (fixed). The wait is also bounded now.
- **BKP.** DR1 and DR2 are read after the PWR and BKP clocks are enabled, and written only with DBP set.
- **I2C1.**
  - Remapped to PB8/PB9, with SWJ off, as the app does.
  - FREQ=8, OAR1 bit 14 set, ACK written after PE.
  - ADDR cleared by an SR1 read then an SR2 read. STOPF cleared by an SR1 read then a CR1 write.
  - AF (the master's NACK) ends a read. Padding goes out only when BTF shows the master wants more.
  - Clock stretching stays on, so the page-erase stalls (~20 ms) stretch SCL instead of dropping bytes.

## Recovery ladder

1. Any failure after the erase leaves the chip in the bootloader, with the Pico powered, until a good image is committed. Run `flash()` or `recover()` again, from push.py/WiFi or USB serial, since the keyboard is down.
2. A new image that dies within 500 ms is caught by the trial watchdog, and `autorecover()` restores `last_good.bin`.
3. Last resort, always available: DIP 1 + USB-C + STM32CubeProgrammer. The ROM bootloader is untouched, and this also re-installs the bootloader itself.

## Known risks (check on hardware first)

- **Reset glitch on PA13.** During the microseconds of reset into the bootloader, PA13 is an input with a pull-up before the bootloader drives it high. If the Pico still browns out, it reboots with the bootloader waiting. The 30 s idle timeout then returns to the app, and nothing is lost.
- **Flash size.** Assumes 64 KB flash (F103R8). The info page sits at 0x0800FC00.
- **Wrong link address.** Checked with core 2.10.0 (see Status). Both `build_app.sh` (via `mkimage.py check`) and `kbdflash.py` still refuse an image linked at the wrong address.
- **I2C slave edge cases.** The F1 I2C slave is driven by polling. After a short read, one status byte can be left in DR. The bootloader flushes it once the bus is idle, and `kbdflash` retries a status read that comes back shifted. A 5 ms stall guard answers a read whose address event was missed.
- **Never over-read the app.** The stm32duino Wire slave only has the 2 bytes `requestEvent()` queued, so a longer read can hold SCL low. `kbdflash` therefore identifies the firmware with a 2-byte read of register 0x0E, and only reads the 24-byte status once the bootloader has answered.
- **Power key not serviced.** The bootloader doesn't handle the AXP2101 power key. The PMU's own hardware long-press power-off still applies.
- **Late crashes.** The trial window is 500 ms, so an app that crashes later than that isn't caught, and needs DIP 1.
- **Bus speed.** `kbdflash` uses 50 kHz. The Pico driver currently runs the bus at 12 kHz. 100 kHz should work (the fork dropped the 10 kHz limit) but is unconfirmed.
