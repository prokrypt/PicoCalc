#!/usr/bin/env python3
"""Host test: drive micropython/kbdflash.py against the real bl_core.c protocol code.

    make hosttest            (or: python3 tools/sim_test.py build/libblcore.so)

bl_core.c is compiled for the host with tools/host_hal.c as its flash (STM32F1
programming rules). A fake I2C bus plays the keyboard app until kbdflash asks for
the bootloader, then passes traffic to bl_core the way bl_main.c's poll loop does.
The STM32 register code in bl_main.c and the Arduino app are NOT covered.
"""
import ctypes
import os
import random
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'micropython'))
import kbdflash  # noqa: E402

kbdflash.sleep_ms = lambda ms: None
lib = ctypes.CDLL(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'build', 'libblcore.so'))
lib.host_flash.restype = ctypes.POINTER(ctypes.c_uint8)
lib.bl_crc32.restype = ctypes.c_uint32
lib.bl_crc32.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32]
lib.bl_on_write.argtypes = [ctypes.c_char_p, ctypes.c_uint32, ctypes.c_int]
boot_reason = ctypes.c_uint8.in_dll(lib, 'bl_boot_reason')
reset_req = ctypes.c_uint8.in_dll(lib, 'bl_reset_requested')
fail_at = ctypes.c_int.in_dll(lib, 'host_fail_program_at')

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
        if self.mode == 'app':
            if data == bytes((0x8E, 0xB0)):
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
        if self.mode == 'app':
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
                return bytes((reg, 1))
            if reg == kbdflash.REG_BAT:
                return bytes((reg, 0x80 | 60))
            return bytes((0, 0))
        self.writeto(addr, bytes((reg,)))
        return self.readfrom(addr, n)


def make_image(size, linked_at=kbdflash.APP_BASE, seed=7):
    rng = random.Random(seed)
    body = bytes(rng.randrange(256) for _ in range(size - 8))
    return struct.pack('<II', 0x20005000, linked_at + 0x101) + body


def flash_region(n):
    p = lib.host_flash()
    return ctypes.string_at(ctypes.addressof(p.contents) + APP_OFF, n)


def poke(off, value):
    p = lib.host_flash()
    p[APP_OFF + off] = value


def write_file(d, name, data):
    path = os.path.join(d, name)
    with open(path, 'wb') as f:
        f.write(data)
    return path


def run_flash(bus, path, **kw):
    try:
        kbdflash.flash(path, i2c=bus, **kw)
    except PowerCycle:
        return True
    return False


def main():
    tmp = tempfile.mkdtemp()
    kbdflash.KBD_DIR = tmp
    kbdflash.APP_BIN = os.path.join(tmp, 'app.bin')
    kbdflash.LAST_GOOD = os.path.join(tmp, 'last_good.bin')
    kbdflash.PENDING = os.path.join(tmp, 'pending.bin')
    lib.host_flash_blank()
    passed = 0

    # 1. clean flash from the running app, odd-sized image
    img = make_image(34001)
    path = write_file(tmp, 'app.bin', img)
    bus = FakeBus('app')
    assert run_flash(bus, path), 'expected the Pico to power-cycle at the end'
    padded = img + b'\xff' * (-len(img) % 4)
    assert flash_region(len(padded)) == padded
    assert lib.bl_app_valid() == 1
    assert os.path.exists(kbdflash.PENDING)
    passed += 1

    # 2. autorecover sees the app running and promotes pending -> last_good
    assert kbdflash.autorecover(i2c=bus) == 'promoted'
    assert os.path.exists(kbdflash.LAST_GOOD) and not os.path.exists(kbdflash.PENDING)
    assert kbdflash.autorecover(i2c=bus) == 'ok'
    passed += 1

    # 3. noisy bus: lost writes, lost acks, bit flips, read timeouts
    img2 = make_image(20000, seed=9)
    path2 = write_file(tmp, 'app2.bin', img2)
    bus = FakeBus('app', noise=0.08, seed=3)
    assert run_flash(bus, path2)
    assert flash_region(len(img2)) == img2 and lib.bl_app_valid() == 1
    passed += 1

    # 4. image linked for 0x08000000 is refused before anything is touched
    bad = write_file(tmp, 'bad.bin', make_image(4000, linked_at=0x08000000))
    try:
        kbdflash.flash(bad, i2c=FakeBus('app'))
        raise AssertionError('bad image accepted')
    except kbdflash.KbdFlashError as e:
        assert 'linked for 0x08000000' in str(e), e
    assert lib.bl_app_valid() == 1
    passed += 1

    # 5. flash fault mid-write: commit refused, app invalid, bootloader keeps answering
    bus = FakeBus('app')
    fail_at.value = APP_OFF + 5000
    try:
        run_flash(bus, path)
        raise AssertionError('flash fault not reported')
    except kbdflash.KbdFlashError as e:
        assert 'flash controller' in str(e), e
    fail_at.value = -1
    assert lib.bl_app_valid() == 0 and bus.mode == 'bl'
    passed += 1

    # 6. stray keyboard-driver traffic does not disturb the bootloader's status
    s0 = kbdflash.Link(bus).status()
    bus.writeto(0x1F, bytes((0x04,)))
    bus.writeto(0x1F, bytes((0x85, 16)))
    assert kbdflash.Link(bus).status().seq == s0.seq
    passed += 1

    # 7. autorecover restores last_good while stuck in the bootloader
    try:
        kbdflash.autorecover(i2c=bus)
        raise AssertionError('expected power cycle')
    except PowerCycle:
        pass
    assert flash_region(len(padded)) == padded and lib.bl_app_valid() == 1
    passed += 1

    # 8. flash() while the bootloader is already running; CRC mismatch detected
    bus = FakeBus('bl')
    orig = kbdflash.Link.commit

    def commit_after_rot(self, length, crc, progress=None):
        poke(100, flash_region(101)[100] & 0x0F)  # a bit that went bad after programming
        return orig(self, length, crc, progress)
    kbdflash.Link.commit = commit_after_rot
    try:
        run_flash(bus, path2)
        raise AssertionError('crc mismatch not reported')
    except kbdflash.KbdFlashError as e:
        assert 'CRC mismatch' in str(e), e
    kbdflash.Link.commit = orig
    assert lib.bl_app_valid() == 0
    passed += 1

    # 9. BOOT with nothing committed is refused (keyboard would stay dead otherwise)
    try:
        kbdflash.Link(bus).boot()
        raise AssertionError('boot without app accepted')
    except kbdflash.KbdFlashError as e:
        assert 'no valid app' in str(e), e
    passed += 1

    # 10. crc32 fallback matches zlib
    import zlib
    kbdflash._crc32 = None
    assert kbdflash.crc32(img) == zlib.crc32(img)
    passed += 1

    print('sim_test: %d/10 passed' % passed)


if __name__ == '__main__':
    main()
