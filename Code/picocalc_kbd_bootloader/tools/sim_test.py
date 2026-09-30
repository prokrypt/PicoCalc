#!/usr/bin/env python3
"""Host test: drive micropython/kbdflash.py against the real bl_core.c protocol code.

    make hosttest            (or: python3 tools/sim_test.py build/libblcore.so)

bl_core.c is compiled for the host with tools/host_hal.c as its flash (STM32F1
programming rules). A fake I2C bus plays the keyboard app until kbdflash asks for
the bootloader, then passes traffic to bl_core the way bl_main.c's poll loop does.
Also counts erase cycles per page. The STM32 register code in bl_main.c is covered by
tools/emu_test.py instead.
"""
import ctypes
import os
import random
import struct
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'micropython'))
import kbdflash  # noqa: E402

kbdflash.sleep_ms = lambda ms: None
lib = ctypes.CDLL(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'build', 'libblcore.so'))
lib.host_flash.restype = ctypes.POINTER(ctypes.c_uint8)
lib.bl_on_write.argtypes = [ctypes.c_char_p, ctypes.c_uint32, ctypes.c_int]
boot_reason = ctypes.c_uint8.in_dll(lib, 'bl_boot_reason')
reset_req = ctypes.c_uint8.in_dll(lib, 'bl_reset_requested')
fail_at = ctypes.c_int.in_dll(lib, 'host_fail_program_at')
erase_count = (ctypes.c_uint32 * 64).in_dll(lib, 'host_erase_count')
program_count = ctypes.c_uint32.in_dll(lib, 'host_program_count')

APP_OFF = kbdflash.APP_BASE - 0x08000000
RX_MAX = 1 + 4 + 1 + kbdflash.WRITE_MAX + 2


class PowerCycle(Exception):
    """The keyboard app started and cut Pico power."""


class FakeBus:
    def __init__(self, mode='app', noise=0.0, seed=1):
        self.mode = mode
        self.noise = noise
        self.rng = random.Random(seed)
        self.stray = 0
        self.stale = None  # a status byte left in DR by a short read (if not flushed in time)
        self.app_writes = []  # writes the keyboard app received
        if mode == 'bl':
            self.enter_bl(2)

    def enter_bl(self, why):
        lib.bl_init()
        boot_reason.value = why
        self.mode = 'bl'

    def _noise(self):
        return self.noise and self.rng.random() < self.noise

    def _steps(self):
        for _ in range(4):  # the poll loop runs job slices between transactions
            lib.bl_step()

    def writeto(self, addr, data):
        assert addr == 0x1F
        data = bytes(data)
        if self._noise():
            raise OSError(5)  # lost before the slave saw it
        if self.mode in ('app', 'v16'):
            self.app_writes.append(data)
            if self.mode == 'app' and data == bytes((0x80 | kbdflash.REG_BOOT, kbdflash.BOOT_CONFIRM)):
                self.enter_bl(1)
            return
        if self._noise() and len(data) > 8:  # flip a bit on the wire
            i = self.rng.randrange(1, len(data))
            data = data[:i] + bytes((data[i] ^ 0x10,)) + data[i + 1:]
        lib.bl_on_write(data[:RX_MAX], min(len(data), RX_MAX), int(len(data) > RX_MAX))
        self._steps()
        if reset_req.value:
            assert lib.bl_app_valid() == 1
            self.mode = 'app'
            reset_req.value = 0
            raise PowerCycle()
        if self._noise():
            raise OSError(5)  # delivered, but the master saw an error

    def readfrom(self, addr, n):
        if self._noise():
            raise OSError(110)
        if self.mode in ('app', 'v16'):
            # the stm32duino slave only has the 2 bytes requestEvent() queued; reading
            # more stretches SCL indefinitely on the real chip
            assert n <= 2, 'over-read of the keyboard app (%d bytes)' % n
            return bytes([0, 0])[:n]
        self._steps()
        buf = ctypes.create_string_buffer(kbdflash.STATUS_LEN)
        lib.bl_status(buf)
        raw = buf.raw + b'\xff' * n
        if self.stale is not None:
            raw = bytes((self.stale,)) + raw
            self.stale = None
        if n < kbdflash.STATUS_LEN and self.rng.random() < 0.5:
            self.stale = raw[n]  # worst case: the bootloader's flush didn't happen before the next read
        return raw[:n]

    def readfrom_mem(self, addr, reg, n):
        if self.mode == 'app':
            if self._noise():
                raise OSError(5)
            if reg == kbdflash.REG_BOOT:
                return bytes((reg, kbdflash.BOOT_SIG | 1))
            if reg == kbdflash.REG_BAT:
                return bytes((reg, 0x80 | 60))
            return bytes((0, 0))
        if self.mode == 'v16':
            # upstream keyboard firmware v1.6: 0x0E is REG_ID_OFF (a write powers the
            # device off), unknown registers such as 0x0F read [0, 0]
            if reg in (0x0E, kbdflash.REG_BAT):
                return bytes((reg, 1 if reg == 0x0E else 60))
            return bytes((0, 0))
        self.writeto(addr, bytes((reg,)))
        return self.readfrom(addr, n)


def make_image(size, linked_at=kbdflash.APP_BASE, seed=7, marker=kbdflash.APP_MARKER):
    rng = random.Random(seed)
    body = bytes(rng.randrange(256) for _ in range(size - 8 - len(marker)))
    return struct.pack('<II', 0x20005000, linked_at + 0x101) + body + marker


def flash_region(n):
    p = lib.host_flash()
    return ctypes.string_at(ctypes.addressof(p.contents) + APP_OFF, n)


def poke(off, value):
    p = lib.host_flash()
    p[APP_OFF + off] = value


def write_file(d, name, data, crc=None):
    path = os.path.join(d, name)
    with open(path, 'wb') as f:
        f.write(data)
    with open(path + '.crc32', 'w') as f:
        f.write('%08x\n' % (zlib.crc32(data) if crc is None else crc))
    return path


def run_flash(bus, path, **kw):
    try:
        kbdflash.flash(path, i2c=bus, **kw)
    except PowerCycle:
        return True
    return False


def wear():
    """(app page erases, info page erases, halfword programs) since the last reset_counts()"""
    info = (kbdflash.APP_BASE - 0x08000000 + kbdflash.APP_MAX) // 1024
    app = sum(erase_count[i] for i in range(8, info))
    return app, erase_count[info], program_count.value


def padded(b):
    return b + b'\xff' * (-len(b) % 4)


RESULTS = []


def check(name, cond, detail=''):
    assert cond, '%s: %s' % (name, detail)
    RESULTS.append((name, detail))


def main():
    tmp = tempfile.mkdtemp()
    kbdflash.KBD_DIR = tmp
    kbdflash.APP_BIN = os.path.join(tmp, 'app.bin')
    kbdflash.LAST_GOOD = os.path.join(tmp, 'last_good.bin')
    kbdflash.PENDING = os.path.join(tmp, 'pending.bin')
    lib.host_flash_blank()
    say = kbdflash._say
    kbdflash._say = lambda m: None  # keep the output to the results table

    # 1. first flash into blank app flash, from the running app, odd-sized image
    img = make_image(34001)
    path = write_file(tmp, 'app.bin', img)
    lib.host_reset_counts()
    bus = FakeBus('app')
    check('first flash reboots into the app', run_flash(bus, path))
    check('first flash: content and commit', flash_region(len(padded(img))) == padded(img) and lib.bl_app_valid() == 1)
    w = wear()
    check('first flash into blank pages: no erase cycles', w[:2] == (0, 0), 'erases app/info %d/%d' % w[:2])

    # 2. autorecover promotes pending -> last_good once the app runs
    check('autorecover promotes', kbdflash.autorecover(i2c=bus) == 'promoted' and os.path.exists(kbdflash.LAST_GOOD))
    check('autorecover idle when all is well', kbdflash.autorecover(i2c=bus) == 'ok')

    # 3. re-flashing the same image writes nothing at all
    lib.host_reset_counts()
    run_flash(FakeBus('app'), path)
    check('same image again: zero erases, zero programs', wear() == (0, 0, 0), 'wear %r' % (wear(),))

    # 4. one changed byte: one page erased
    img4 = bytearray(img)
    img4[10 * 1024 + 5] ^= 0xFF
    path4 = write_file(tmp, 'app4.bin', bytes(img4))
    check('plan() predicts 1 erase', kbdflash.plan(path4, against=path) == 1)
    lib.host_reset_counts()
    run_flash(FakeBus('app'), path4)
    w = wear()
    check('one byte changed: 1 page erase, no info erase', w[:2] == (1, 0) and lib.bl_app_valid() == 1,
          'erases app/info %d/%d, programs %d' % w)

    # 5. noisy bus: lost writes, lost acks, bit flips, timeouts, stale bytes
    img5 = make_image(20000, seed=9)
    path5 = write_file(tmp, 'app5.bin', img5)
    lib.host_reset_counts()
    check('noisy bus flash', run_flash(FakeBus('app', noise=0.08, seed=3), path5))
    w = wear()
    check('noisy bus: content right, each page erased at most once',
          flash_region(len(img5)) == img5 and lib.bl_app_valid() == 1 and max(erase_count) <= 1,
          'erases app/info %d/%d' % w[:2])

    # 6. image linked for 0x08000000 is refused before any I2C traffic
    bad = write_file(tmp, 'bad.bin', make_image(4000, linked_at=0x08000000))
    lib.host_reset_counts()
    try:
        kbdflash.flash(bad, i2c=FakeBus('app'))
        raise AssertionError('bad image accepted')
    except kbdflash.KbdFlashError as e:
        check('wrong link address refused', 'linked for 0x08000000' in str(e) and wear() == (0, 0, 0))

    # 6b. image built without kbd_boot.ino (no marker) is refused before any I2C traffic
    nomark = write_file(tmp, 'nomark.bin', make_image(4000, marker=b''))
    bus = FakeBus('app')
    try:
        kbdflash.flash(nomark, i2c=bus)
        raise AssertionError('image without marker accepted')
    except kbdflash.KbdFlashError as e:
        check('image without kbd_boot.ino marker refused', 'marker' in str(e) and wear() == (0, 0, 0)
              and not bus.app_writes)

    # 6c. upstream v1.6 keyboard firmware (0x0E = power off): probe says 'app', flash()
    # stops before writing anything to it
    bus = FakeBus('v16')
    check('v1.6 keyboard: probe says other firmware', kbdflash.Link(bus).probe() == 'app')
    try:
        kbdflash.flash(path, i2c=bus)
        raise AssertionError('flash() went ahead on a v1.6 keyboard')
    except kbdflash.KbdFlashError as e:
        check('v1.6 keyboard: flash() refuses, nothing written to it',
              'no bootloader answered' in str(e) and bus.app_writes == [], repr(bus.app_writes))

    # 7. damaged copy on SD (sidecar mismatch) refused before any I2C traffic
    dmg = write_file(tmp, 'dmg.bin', img5, crc=zlib.crc32(img5) ^ 1)
    try:
        kbdflash.flash(dmg, i2c=FakeBus('app'))
        raise AssertionError('damaged image accepted')
    except kbdflash.KbdFlashError as e:
        check('crc sidecar mismatch refused', 'damaged' in str(e) and wear() == (0, 0, 0))
    os.remove(path5 + '.crc32')
    try:
        kbdflash.flash(path5, i2c=FakeBus('app'))
        raise AssertionError('image without sidecar accepted')
    except kbdflash.KbdFlashError as e:
        check('missing sidecar refused', 'sidecar' in str(e) and wear() == (0, 0, 0))
    path5 = write_file(tmp, 'app5.bin', img5)

    # 8. flash fault mid-write: app invalid, bootloader keeps answering, retry finishes
    bus = FakeBus('app')
    lib.host_reset_counts()
    fail_at.value = APP_OFF + 5000
    try:
        run_flash(bus, path)
        raise AssertionError('flash fault not reported')
    except kbdflash.KbdFlashError as e:
        check('flash fault reported, app invalidated', 'controller' in str(e) and lib.bl_app_valid() == 0 and bus.mode == 'bl')
    fail_at.value = -1
    check('retry after fault finishes', run_flash(bus, path))
    twice = [i for i in range(64) if erase_count[i] > 1]
    check('fault + retry: only the faulted page erased twice', twice == [(APP_OFF + 5000) // 1024],
          'app erases %d, pages erased twice %r' % (wear()[0], twice))

    # 9. stray keyboard-driver traffic leaves the status alone
    bus = FakeBus('bl')
    s0 = kbdflash.Link(bus).status()
    bus.writeto(0x1F, bytes((0x04,)))
    bus.writeto(0x1F, bytes((0x85, 16)))
    check('stray traffic ignored', kbdflash.Link(bus).status().seq == s0.seq)

    # 10. autorecover writes nothing unless allowed, and tries a restore only once
    kbdflash.Link(bus).erase_page(0)  # knock the app out
    check('app knocked out', lib.bl_app_valid() == 0)
    lib.host_reset_counts()
    check('autorecover default: no flash writes', kbdflash.autorecover(i2c=bus) == 'needs-recover' and wear() == (0, 0, 0))
    marker = os.path.join(tmp, 'autorecover.tried')
    with open(marker, 'w') as f:
        f.write('1')
    check('autorecover(allow_flash) respects the tried marker',
          kbdflash.autorecover(i2c=bus, allow_flash=True) == 'needs-recover' and wear() == (0, 0, 0))
    os.remove(marker)
    try:
        kbdflash.autorecover(i2c=bus, allow_flash=True)
        raise AssertionError('expected power cycle')
    except PowerCycle:
        pass
    check('autorecover(allow_flash) restores last_good', lib.bl_app_valid() == 1)

    # 11. bit rot after programming: commit refuses
    bus = FakeBus('bl')
    orig = kbdflash.Link.commit

    def commit_after_rot(self, length, crc, progress=None):
        poke(100, flash_region(101)[100] ^ 0x01)
        return orig(self, length, crc, progress)
    kbdflash.Link.commit = commit_after_rot
    try:
        run_flash(bus, path5)
        raise AssertionError('crc mismatch not reported')
    except kbdflash.KbdFlashError as e:
        check('commit catches a bad byte', 'CRC mismatch' in str(e) and lib.bl_app_valid() == 0)
    kbdflash.Link.commit = orig

    # 12. BOOT with nothing committed is refused
    try:
        kbdflash.Link(bus).boot()
        raise AssertionError('boot without app accepted')
    except kbdflash.KbdFlashError as e:
        check('boot without an app refused', 'no valid app' in str(e))

    # 13. info page is a log: 70 alternating updates erase it once
    small_a, small_b = make_image(1500, seed=21), make_image(1500, seed=22)
    pa, pb = write_file(tmp, 'a.bin', small_a), write_file(tmp, 'b.bin', small_b)
    lib.host_reset_counts()
    for i in range(70):
        run_flash(FakeBus('bl'), pa if i % 2 else pb)
    w = wear()
    check('70 updates: info page erased once', w[1] == 1 and lib.bl_app_valid() == 1,
          'app erases %d (2 pages x 70), info erases %d' % w[:2])

    kbdflash._say = say
    for name, detail in RESULTS:
        print('  ok  %-52s %s' % (name, detail))
    print('sim_test: %d checks passed' % len(RESULTS))


if __name__ == '__main__':
    main()
