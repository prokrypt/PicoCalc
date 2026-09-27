#!/usr/bin/env python3
"""Host helper for the keyboard bootloader images.

  mkimage.py check app.bin
      Check that an app .bin is linked at 0x08002000 (what kbdflash.py needs), and
      write app.bin.crc32, which kbdflash.py checks the copy on the SD card against.

  mkimage.py combined kbd_bootloader.bin app.bin -o kbd-combined.bin
      One image for the first install over USB-C with DIP switch 1 (STM32CubeProgrammer,
      start address 0x08000000): bootloader, app, and a committed info page, so the
      keyboard works immediately after the install.
"""
import argparse
import struct
import sys
import zlib

FLASH_START = 0x08000000
BL_SIZE = 0x2000
APP_BASE = FLASH_START + BL_SIZE
INFO_ADDR = FLASH_START + 0xFC00
APP_MAX = INFO_ADDR - APP_BASE
INFO_MAGIC = 0x4B424F4B
RAM_START, RAM_END = 0x20000000, 0x20005000


def pad4(b):
    return b + b'\xff' * (-len(b) % 4)


def check_app(app):
    if len(app) > APP_MAX:
        sys.exit('app is %d bytes; the app area holds %d' % (len(app), APP_MAX))
    sp, pc = struct.unpack('<II', app[:8])
    if not (RAM_START < sp <= RAM_END) or sp & 3:
        sys.exit('stack pointer 0x%08x not in RAM: not an app image' % sp)
    if (pc & ~1) < APP_BASE:
        sys.exit('reset vector 0x%08x: linked for 0x08000000. Rebuild with tools/build_app.sh' % pc)
    if not (pc & 1) or (pc & ~1) >= APP_BASE + len(app):
        sys.exit('reset vector 0x%08x outside the image' % pc)
    print('ok: %d bytes (%d padded), crc32 %08x, sp %08x, reset %08x' % (
        len(app), len(pad4(app)), zlib.crc32(pad4(app)), sp, pc))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('check')
    c.add_argument('app')
    m = sub.add_parser('combined')
    m.add_argument('bootloader')
    m.add_argument('app')
    m.add_argument('-o', '--out', required=True)
    a = ap.parse_args()

    app = open(a.app, 'rb').read()
    check_app(app)
    if a.cmd == 'check':
        with open(a.app + '.crc32', 'w') as f:
            f.write('%08x\n' % zlib.crc32(app))
        print('wrote %s.crc32 (copy it next to the .bin on the SD card)' % a.app)
        return
    bl = open(a.bootloader, 'rb').read()
    if len(bl) > BL_SIZE:
        sys.exit('bootloader is %d bytes, over %d' % (len(bl), BL_SIZE))
    app = pad4(app)
    info = struct.pack('<IIII', INFO_MAGIC, len(app), zlib.crc32(app), ~INFO_MAGIC & 0xFFFFFFFF)
    out = bl.ljust(BL_SIZE, b'\xff') + app
    out = out.ljust(INFO_ADDR - FLASH_START, b'\xff') + info
    open(a.out, 'wb').write(out)
    print('wrote %s: %d bytes, flash at 0x08000000' % (a.out, len(out)))


if __name__ == '__main__':
    main()
