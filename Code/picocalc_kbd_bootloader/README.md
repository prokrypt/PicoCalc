# PicoCalc keyboard I2C bootloader

Lets MicroPython on the Pico update the keyboard chip (STM32F103R8, I2C 0x1F)
without DIP switches or a USB cable, after one install over USB.

**Status: untested on hardware.** What has been checked:
- The bootloader builds with the STM32 core's arm-none-eabi-gcc 14.2.1 (xpack 14.2.1-1.1, 3.1 KB) and with clang/lld.
- Reproducible: that gcc and arduino-cli 1.3.1 + core 2.10.0 rebuild the published bins byte for byte
  (arduino-cli also needs Arduino's own ctags 5.8; Universal Ctags mangles the .ino prototypes).
- The app builds with arduino-cli 1.3.1 and STM32 core 2.10.0 at 0x08002000: 40,760 bytes, ending at
  0x0800BF38. The vector table is at 0x08002000, and `SystemInit()` sets VTOR to 0x08002000.
- `mkimage.py combined` output passes the bootloader's own validity check (`bl_app_valid`).
- `make hosttest` (27 checks) runs `kbdflash.py` against the real protocol code (`bl_core.c`), with a simulated
  flash, a noisy bus, stale bytes after short reads, and an app that must never be over-read.
- `make emutest` (31 checks) runs the **built bootloader binary** in an STM32F103 model (unicorn Cortex-M3 plus
  modelled flash controller, BKP, IWDG, SysTick, GPIO and I2C slave), driven by the unmodified `kbdflash.py`.
  See "Emulator results" below.
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
| 0x0800FC00–0x0800FFFF | 1 KB | info page: a log of 64 records {magic, length, crc32, ~magic} |

## Boot flow

At reset, before touching any peripheral, the bootloader:

1. `BKP_DR1 == 0xB007` (the app asked): clear it and stay.
2. `BKP_DR2 == TRIAL`: the last flashed app never confirmed. Invalidate its record (two halfword
   programs, no erase), then clear DR2 and stay. A later power cycle can't start that image again.
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
is still intact, it resets back into the app as a trial boot, so an image committed
without a BOOT (e.g. `flash(reboot=False)`, or the Pico died first) still gets the watchdog.

The app (`kbd_boot.ino`) feeds the watchdog from `loop()`. After 500 ms of running it
clears the trial flag. A new image that hangs or faults before then comes back to the
bootloader instead of leaving the keyboard (and the Pico's power) dead, and stays there until a good
image is committed.

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
| 0x01 INFO | | ok, value = committed length (0 if none) |
| 0x11 ERASE_PAGE | u32 off (page aligned) | busy, then ok, value 1 = erased, 0 = was already blank. Invalidates the committed record first. |
| 0x20 WRITE | u32 off, u8 n ≤ 128 (even), n bytes, u16 sum of all previous bytes | ok, value = off+n. Only into a page passed to ERASE_PAGE since the bootloader started. |
| 0x30 CRC | u32 off, u32 len | busy, then ok, value = crc32 of that range |
| 0x40 COMMIT | u32 len, u32 crc32 | busy, then ok (checks the crc and vectors, then appends a record; no write if that record is already live) |
| 0x50 BOOT | | ok, then reset into the app 20 ms later (refused if nothing is committed) |
| 0x51 PING | | ok, resets the idle timeout |

Details:
- Unknown bytes are ignored and leave the status alone, so stray keyboard-driver reads can't clobber it.
- A command sent while busy is ignored.
- WRITE skips halfwords that already hold the right value, so retrying after a lost ack is safe.
- crc32 matches zlib and `binascii.crc32`.
- Error codes: 2 length, 3 argument, 4 checksum, 5 page not erased this session, 6 flash controller,
  7 read-back, 8 crc, 9 vectors, 11 overflow, 12 no app.

New app register: **0x0F REG_ID_BOOT** (bootloader v3; v2 used 0x0E, which is power off in upstream firmware v1.6).
- Read it to get `[0x0F, 0xB0 | flags]`: the 0xB0 high nibble is a signature, bit 0 means the app is running above the
  bootloader, and bit 1 means this boot was a trial and has been confirmed.
- Write 0xB0 to restart into the bootloader.
- `kbdflash` writes to 0x1F only after a read shows the echo, the signature and bit 0. Other firmware (stock, v1.6)
  reads `[0, 0]` or its own value there and gets no write at all.

Image marker: `kbd_boot.ino` puts `KBDBOOT\x03` (last byte = protocol version) in the app. `kbdflash` and
`mkimage.py` refuse an image without it, because such an app never confirms its trial and can't be asked into
the bootloader.

## Flash wear

The F103 is rated for 10,000 erase cycles per page (RM0008 / datasheet), so writes are kept to what an update needs:

- **Nothing writes flash except an explicit update** (`kbdflash.flash()` / `recover()`, or `autorecover(allow_flash=True)`,
  which tries once and then needs a person), and the retire after a failed trial (2 halfword programs, no erase). Checked three ways:
  - the bootloader's boot paths only touch BKP registers, except that retire (the emulator fails the run on any other flash
    write before a command);
  - the app binary contains no flash unlock keys or FLASH_KEYR/CR accesses, and uses no EEPROM emulation;
  - `kbdflash` writes only inside `flash()`.
- Boot state (enter request, trial arm/in-progress) lives in BKP_DR1/DR2, never in flash.
- `flash()` first reads a CRC of every page from the chip and only erases and rewrites the pages that differ.
  A page that is already blank isn't erased. Re-flashing the same image erases and programs nothing.
- The info page is a log of 64 records. A commit programs the next blank record, and the old one is invalidated by programming
  0x0000 over its magic (allowed on the F1 without an erase). The page is erased once every 64 updates.
- The bootloader and the ROM/option bytes are never erased: writes below 0x08002000 are refused in `bl_main.c`,
  and OPTKEYR is never written.
- The image is checked before the first erase: `.crc32` sidecar, two reads of the file agree, link address, stack pointer, size,
  `kbd_boot.ino` marker.

Typical cost of an update that changes a few functions: 2–5 page erases. Interrupting one and running it again costs at most one more erase of the page that was in progress.

## Emulator results

`tools/emu_test.py` on the gcc build of the bootloader (3,148 bytes) and the real app (40,760 bytes, 40 pages):

| Scenario | Result |
|---|---|
| 51 cold boots with a committed app | jumps to the app every time; 0 flash writes; PA13 (Pico power) never driven low |
| Update A→B (2 pages changed) | 2 erases; trial boot under the ~4 s watchdog, confirmed after 500 ms |
| Same image again | 0 erases, 0 programs |
| New app that hangs in its trial | watchdog reset, its record retired (2 programs), bootloader reports "trial failed", restore works |
| Power cycle after that failed trial | stays in the bootloader with the Pico powered (v2 ran the bad image without the watchdog) |
| Power loss during the retire, BKP kept or lost | stays in the bootloader; restore works |
| Power loss inside the 500 ms trial (BKP kept) | image retired; `flash()` again re-commits it with 0 erases |
| Power loss at every erase, every info-page write, first/last halfword of each page and every 16th halfword, with and without BKP surviving | never boots a mixed image; running `flash()` again always recovers; worst page wear across cut + retry: 2 erases |
| Same, with the info-page log full (the commit erases the info page) | same |
| 5 % of I2C transfers fail | update completes, no extra erases |
| Image linked at 0x08000000, or without the `kbd_boot.ino` marker | refused before anything is sent |
| Upstream v1.6 keyboard firmware (0x0E = power off) | `status()` says other firmware; `flash()` refuses; no I2C write reaches it |
| App asks for the bootloader, nothing follows | back to the app after 30 s as a confirmed trial, no writes |
| Image committed, BOOT never sent, image bad | the idle reset starts it under the watchdog; retired, chip waits (also after a power cycle) |

Power loss is modelled as a half-done operation: an interrupted erase leaves random bits set, an interrupted program
clears random bits. What the model can't show: real I2C timing and electrical glitches, the brown-out behaviour of PA13
during reset, and the app itself (a Python stand-in replaces it after the jump).

## Pre-flash checklist (the one-time USB install)

This is the only step that can't be undone from the Pico, so check each item before step 4 of "Install once".

1. **Know the rollback.** Read the current firmware out first (STM32CubeProgrammer, UART, "Read" 0x08000000, 64 KB)
   and keep that file. If the chip is read-protected, stop: the readout would need a mass erase.
2. **Confirm the part.** CubeProgrammer should show STM32F101/F102/F103 medium-density, 64 KB flash. The info page at
   0x0800FC00 assumes 64 KB.
3. **Check the image.**
   - `sha256sum kbd-combined-*.bin` matches `SHA256SUMS`.
   - `python3 tools/mkimage.py check <app>.bin` passes (link address 0x08002000, SP in RAM).
   - `make hosttest` and `make emutest` pass on the build you are about to flash.
4. **Power.** Battery charged or USB power attached; don't flash on a low battery.
5. **Write once.** In CubeProgrammer: "Full chip erase" off, "Verify programming" on, start address 0x08000000.
   One write of the combined image is one erase cycle per page used, the same as any stock update.
6. **Set DIP 1 back off** before the first boot.
7. **First boot checks, before any `kbdflash.flash()`:**
   - the keyboard types, backlight and battery reading work;
   - `kbdflash.status()` says "running above the bootloader";
   - copy the app .bin and its `.crc32` to `/sd/kbd/last_good.bin` (+ `.crc32`).
8. **First I2C update:** try `kbdflash.plan('/sd/kbd/app.bin')` (reads only) first; it prints how many pages would be erased.

## Install once (USB-C + DIP 1)

1. `make` (or `make clang`), which gives `build/kbd_bootloader.bin`.
2. `tools/build_app.sh`, which builds the app at 0x08002000. This is the fork at 3444552
   plus the charging fix and `kbd_boot.ino`.
3. `tools/mkimage.py combined build/kbd_bootloader.bin build/app/picocalc_keyboard.ino.bin -o kbd-combined.bin`
4. DIP 1 on, connect USB-C, long-press power, and flash `kbd-combined.bin` at 0x08000000
   with STM32CubeProgrammer (UART). Then set DIP 1 off.
5. Copy the app .bin and its `.crc32` sidecar to `/sd/kbd/last_good.bin` (+ `.crc32`), and `kbdflash.py` to the Pico.

## Updating from MicroPython

```python
import kbdflash
kbdflash.status()                  # bootloader? app above the bootloader? old app?
kbdflash.plan('/sd/kbd/app.bin')   # dry run on the Pico's files: how many pages would be erased
kbdflash.flash('/sd/kbd/app.bin')  # needs app.bin.crc32 next to it; the Pico power-cycles at the end
```

What `flash()` does:
- It checks the image before touching anything: the `.crc32` sidecar, two reads agree, size, stack pointer, and that the reset vector is linked at 0x08002000.
- It compares page CRCs with the chip and rewrites only the pages that differ. It returns the number of erase cycles used.
- It refuses to run below 25 % battery unless charging or `force=True`.
- It parks the keyboard driver so timers can't interleave I2C traffic.
- It prints each step with a progress bar.

The Pico restarts at the end because the app's `setup()` drives PA13 (Pico enable) low
then high. That has always been true of this firmware.

For `main.py`, before `PicoKeyboard()` is created:

```python
import kbdflash; kbdflash.autorecover()
```

This costs one 2-byte read when all is well, and never writes keyboard flash by default. It promotes
`/sd/kbd/pending.bin` to `last_good.bin` once a new image is seen running. If the keyboard chip sits
in its bootloader with its app intact (it was asked and nobody flashed), it starts the app again.
Otherwise it returns `'needs-recover'` and leaves the choice to a person. With `allow_flash=True`
it reflashes `last_good.bin` once; a marker file stops it from trying again on every boot.

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
2. A new image that dies within 500 ms is caught by the trial watchdog; its record is retired, so the chip waits in its bootloader (across power cycles too) and `recover()` restores `last_good.bin` (or `autorecover(allow_flash=True)`, once).
3. Last resort, always available: DIP 1 + USB-C + STM32CubeProgrammer. The ROM bootloader is untouched, and this also re-installs the bootloader itself.

## Known risks (check on hardware first)

- **Reset glitch on PA13.** During the microseconds of reset into the bootloader, PA13 is an input with a pull-up before the bootloader drives it high. If the Pico still browns out, it reboots with the bootloader waiting. The 30 s idle timeout then returns to the app, and nothing is lost.
- **Flash size.** Assumes 64 KB flash (F103R8). The info page sits at 0x0800FC00.
- **Wrong link address.** Checked with core 2.10.0 (see Status). Both `build_app.sh` (via `mkimage.py check`) and `kbdflash.py` still refuse an image linked at the wrong address.
- **I2C slave edge cases.** The F1 I2C slave is driven by polling. After a short read, one status byte can be left in DR. The bootloader flushes it once the bus is idle, and `kbdflash` retries a status read that comes back shifted. A 5 ms stall guard answers a read whose address event was missed.
- **Never over-read the app.** The stm32duino Wire slave only has the 2 bytes `requestEvent()` queued, so a longer read can hold SCL low. `kbdflash` therefore identifies the firmware with a 2-byte read of register 0x0F, and only reads the 24-byte status once the bootloader has answered.
- **Power key not serviced.** The bootloader doesn't handle the AXP2101 power key. The PMU's own hardware long-press power-off still applies.
- **Late crashes.** The trial window is 500 ms, so an app that crashes later than that isn't caught, and needs DIP 1.
- **Power loss inside the trial window.** If BKP survives (VBAT), the unconfirmed image is retired: run `flash()` again
  (0 erases). If BKP is lost, the image boots normally, without the watchdog.
- **Bus speed.** `kbdflash` uses 50 kHz. The Pico driver currently runs the bus at 12 kHz. 100 kHz should work (the fork dropped the 10 kHz limit) but is unconfirmed.
