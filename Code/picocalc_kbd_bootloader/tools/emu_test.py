#!/usr/bin/env python3
"""Run the real bootloader binary in an STM32F103 model and drive it with kbdflash.py.

    python3 tools/emu_test.py build/kbd_bootloader.bin APP.bin [--quick]

Needs the `unicorn` Python package (Cortex-M3 CPU emulation). Around the CPU this
file models the parts of the STM32F103 the bootloader touches, following RM0008:
the flash controller (unlock keys, PG/PER/STRT, the F1 programming rules, per-page
erase counters), BKP/PWR (DBP write protection, contents kept across resets), IWDG
(including that PR/RLR only update while the LSI runs), SysTick, GPIO and the I2C1
slave (ADDR/RXNE/TXE/BTF/STOPF/AF, clock stretching, DR/shift register, PE=0 only
taking effect when the bus is idle). The master side of the bus is kbdflash.py
itself, talking through FakeI2C.

The keyboard app is not emulated: when the bootloader jumps to it, a Python stand-in
takes over (answers registers 0x0B/0x0F, enters the bootloader on request, confirms
or fails a trial boot), and "power-cycles the Pico" the way the real app does.

Checks: no flash write on any boot path, never booting a half-written image, power
loss at every flash operation of an update (erase and program), with and without the
backup domain surviving, then recovery; bad images; retries; erase cycles per page.
"""
import os
import random
import struct
import sys
import tempfile
import zlib

from unicorn import Uc, UcError, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_PROT_ALL, \
    UC_HOOK_MEM_WRITE, UC_HOOK_CODE, UC_HOOK_BLOCK
from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_PC, UC_CPU_ARM_CORTEX_M3

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'micropython'))
import kbdflash  # noqa: E402

FLASH, FLASH_SIZE, PAGE = 0x08000000, 0x10000, 1024
APP_BASE = kbdflash.APP_BASE
INFO_ADDR = FLASH + 0xFC00
RAM, RAM_SIZE = 0x20000000, 0x5000
CPU_HZ = 8_000_000
INSTR_PER_MS = CPU_HZ // 1000       # ~1 instruction per cycle is close enough here


class PowerLoss(Exception):
    pass


class PicoPowerCycle(Exception):
    """The keyboard app started: it drops PA13, so the Pico (and kbdflash) restarts."""


class Violation(AssertionError):
    pass


class Chip:
    """Persistent state (flash, backup registers, wear counters) plus one power-on at a time."""

    def __init__(self, flash_image, bkp_on_vbat=True):
        self.flash = bytearray(b'\xff' * FLASH_SIZE)
        self.flash[:len(flash_image)] = flash_image
        self.bkp = {1: 0, 2: 0}
        self.bkp_on_vbat = bkp_on_vbat   # backup domain survives a power loss
        self.erases = [0] * (FLASH_SIZE // PAGE)
        self.clock_base = 0.0            # ms from earlier power-ons, for kbdflash's ticks_ms
        self.pico_live = False           # a kbdflash run is attached (the app start power-cycles it)
        self.pending_fix = []
        self.programs = 0
        self.flash_ops = 0               # erase + program operations, for power-loss injection
        self.op_log = []
        self.cut_at = None               # power loss during this flash op number
        self.boot_log = []
        self.app_bad = False             # stand-in app fails its trial boot
        self.app_v16 = False             # stand-in is upstream firmware v1.6 (0x0E = power off)
        self.app_writes = []             # I2C writes the app received
        self.retires = 0                 # info-page programs on the failed-trial boot path
        self.power_on(cold=True)

    # ---- power ----

    def power_on(self, cold=False):
        if hasattr(self, 'instr'):
            self.clock_base += self.now_ms()
        if cold and not self.bkp_on_vbat:
            self.bkp = {1: 0, 2: 0}
        # the one boot path allowed to write flash: retiring an image that failed its trial
        self.retire_ok = self.bkp[2] == 0x7E57
        self.mode = 'bl'
        self.uc = uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        uc.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M3)
        uc.mem_map(FLASH, FLASH_SIZE, UC_PROT_ALL)
        uc.mem_write(FLASH, bytes(self.flash))
        uc.mem_map(RAM, RAM_SIZE)
        uc.mem_write(RAM, os.urandom(RAM_SIZE))   # RAM is garbage at power-on
        uc.mmio_map(0x40000000, 0x24000, self._rd, None, self._wr, None)
        uc.mmio_map(0xE000E000, 0x1000, self._ppb_rd, None, self._ppb_wr, None)
        uc.hook_add(UC_HOOK_MEM_WRITE, self._flash_write, begin=FLASH, end=FLASH + FLASH_SIZE - 1)
        uc.hook_add(UC_HOOK_BLOCK, self._count)
        uc.hook_add(UC_HOOK_CODE, self._entered_app, begin=APP_BASE, end=FLASH + FLASH_SIZE - 1)
        self.instr = 0                   # instructions run this power-on
        self.extra_ms = 0.0              # time the CPU spent stalled on flash
        self.last_tick_ms = 0
        self.stop_reason = None
        self.waiting = None
        self.in_boot_path = True         # until the first I2C command is accepted
        # peripherals
        self.rcc = {'apb1': 0, 'apb2': 0}
        self.pwr_dbp = False
        self.flash_locked, self.flash_keys, self.flash_cr, self.flash_ar, self.flash_sr = True, 0, 0, 0, 0
        self.iwdg = {'running': False, 'unlocked': False, 'pr': 0, 'rlr': 0xFFF, 'sr': 0, 'fed_ms': 0}
        self.vtor = 0
        self.gpio = {}
        self.pa13_low_ever = False
        self.mapr = 0
        self.systick_csr = 0
        self.i2c = I2CSlave(self)
        sp, pc = struct.unpack('<II', bytes(self.flash[:8]))
        uc.reg_write(UC_ARM_REG_SP, sp)
        self.pc = pc | 1
        self.run_ms(300)                 # boot decision (the app crc check takes ~100 ms at 8 MHz)

    def _count(self, uc, address, size, _):
        self.instr += max(1, size * 2 // 5)   # mix of 16- and 32-bit Thumb instructions

    def total_ms(self):
        return self.clock_base + self.now_ms()

    def _fix_flash(self):
        # A CPU store to flash only reaches the array through the controller; undo what
        # unicorn wrote and show the modelled result (applied before the next MMIO access,
        # which the bootloader always makes (BSY poll) before reading flash back).
        while self.pending_fix:
            a = self.pending_fix.pop()
            self.uc.mem_write(a, bytes(self.flash[a - FLASH:a - FLASH + 4]))

    def now_ms(self):
        return self.instr / INSTR_PER_MS + self.extra_ms

    def run(self, count):
        """Run up to `count` instructions; stops early on emu_stop()."""
        if self.mode != 'bl':
            return
        iw = self.iwdg
        if iw['running']:
            timeout = 4 * (1 << iw['pr']) * (iw['rlr'] + 1) / 40.0
            if self.now_ms() - iw['fed_ms'] > timeout:
                self.boot_log.append('iwdg reset (bootloader)')
                self.power_on()
                return
        start = self.pc
        try:
            self.uc.emu_start(start, 0xFFFFFFFF, count=count)
        except UcError as e:
            raise Violation('CPU fault at %08x: %s' % (self.uc.reg_read(UC_ARM_REG_PC), e))
        self._fix_flash()
        self.pc = self.uc.reg_read(UC_ARM_REG_PC) | 1
        reason, self.stop_reason = self.stop_reason, None
        if reason == 'reset':
            self.system_reset()
        elif reason == 'app':
            self.start_app()
        elif reason == 'powerloss':
            raise PowerLoss()

    def run_until(self, cond, max_ms):
        deadline = self.now_ms() + max_ms
        self.waiting = cond
        try:
            while not cond():
                if self.mode != 'bl':
                    return cond()
                if self.now_ms() > deadline:
                    return False
                self.run(64)
            return True
        finally:
            self.waiting = None

    def run_ms(self, ms):
        end = self.now_ms() + ms
        while self.mode == 'bl' and self.now_ms() < end:
            self.run(min(INSTR_PER_MS * 5, max(64, int((end - self.now_ms()) * INSTR_PER_MS))))
        if self.mode == 'app':
            self.app_tick(ms)

    def _poke_waiter(self):
        # No emu_stop() from MMIO callbacks: unicorn then reports the PC of the start
        # of the translation block and re-runs its first instructions. run_until()
        # polls in small instruction counts instead, which stop on exact boundaries.
        pass

    def system_reset(self):
        self.boot_log.append('reset')
        self.power_on()

    # ---- app stand-in ----

    def _entered_app(self, uc, address, size, _):
        if self.mode == 'bl':
            self.stop_reason = 'app'
            uc.emu_stop()

    def start_app(self):
        self.mode = 'app'
        self.app_ms = 0
        sp = struct.unpack('<I', bytes(self.flash[APP_BASE - FLASH:APP_BASE - FLASH + 4]))[0]
        if self.vtor != APP_BASE:
            raise Violation('jumped to the app with VTOR=%08x' % self.vtor)
        if self.uc.reg_read(UC_ARM_REG_SP) != sp:
            raise Violation('jumped to the app with the wrong MSP')
        rec = live_record(self.flash)
        if rec is None or zlib.crc32(bytes(self.flash[APP_BASE - FLASH:APP_BASE - FLASH + rec[0]])) != rec[1]:
            raise Violation('jumped into an app whose flash does not match a committed record')
        self.boot_log.append('app' + (' (trial)' if self.iwdg['running'] else ''))
        self.trial = self.iwdg['running'] and self.bkp[2] == 0x7E57
        if self.pico_live:
            raise PicoPowerCycle()        # setup() pulses PA13: the Pico loses power here

    def app_tick(self, ms):
        self.app_ms += ms
        if self.iwdg['running'] and self.app_bad and self.app_ms > 4000:
            self.boot_log.append('iwdg reset')
            self.power_on()               # IWDG reset: BKP kept, like a system reset
            return
        if self.trial and not self.app_bad and self.app_ms > 500:
            self.bkp[2] = 0
            self.trial = False

    # ---- flash ----

    def _flash_op(self, kind, addr):
        self.flash_ops += 1
        self.op_log.append((kind, addr))
        if self.cut_at is not None and self.flash_ops == self.cut_at:
            return True
        return False

    def _flash_write(self, uc, access, address, size, value, _):
        if not (self.flash_cr & 1) or self.flash_locked:
            raise Violation('write to flash %08x without PG/unlock' % address)
        self.pending_fix.append(address & ~3)
        if size == 4:
            self.pending_fix.append((address & ~3) + 4)
        if size != 2 or address & 1:
            self.flash_sr |= 1 << 2
            return True
        off = address - FLASH
        if off < 0x2000:
            raise Violation('bootloader area written at %08x' % address)
        if self.in_boot_path:
            if not (self.retire_ok and value == 0 and INFO_ADDR <= address < INFO_ADDR + PAGE):
                raise Violation('flash programmed on a boot path (%08x)' % address)
            self.retires += 1
        cur = self.flash[off] | self.flash[off + 1] << 8
        cut = self._flash_op('program', address)
        if cur != 0xFFFF and value != 0:
            self.flash_sr |= 1 << 2       # PGERR, nothing written (RM0008 3.3.3)
            return True
        new = value
        if cut:
            new = cur & random.getrandbits(16)   # interrupted program: some bits only
        self.flash[off:off + 2] = struct.pack('<H', new)
        self.programs += 1
        self.extra_ms += 0.05
        self.flash_sr |= 1 << 5           # EOP
        if cut:
            self.stop_reason = 'powerloss'
            uc.emu_stop()
        return True

    def _flash_erase(self):
        page = (self.flash_ar - FLASH) // PAGE
        if page < 8:
            raise Violation('bootloader page %d erased' % page)
        if self.in_boot_path:
            raise Violation('flash erased on a boot path (page %d)' % page)
        cut = self._flash_op('erase', self.flash_ar)
        base = page * PAGE
        if cut:  # interrupted erase: a mix of erased and old bits
            data = bytes(b | random.getrandbits(8) for b in self.flash[base:base + PAGE])
        else:
            data = b'\xff' * PAGE
        self.flash[base:base + PAGE] = data
        self.uc.mem_write(FLASH + base, data)
        self.erases[page] += 1
        self.extra_ms += 20
        self.flash_sr |= 1 << 5
        if cut:
            self.stop_reason = 'powerloss'
            self.uc.emu_stop()

    # ---- MMIO ----

    def _rd(self, uc, off, size, _):
        self._fix_flash()
        a = 0x40000000 + off
        if 0x40005400 <= a < 0x40005800:
            return self.i2c.read(a - 0x40005400)
        if a == 0x4002101C:
            return self.rcc['apb1']
        if a == 0x40021018:
            return self.rcc['apb2']
        if a in (0x40006C04, 0x40006C08):
            if not (self.rcc['apb1'] & (1 << 27)):
                return 0                  # BKP clock off: reads don't see the register
            return self.bkp[1 if a == 0x40006C04 else 2]
        if a == 0x40007000:
            return self.pwr_dbp << 8
        if a == 0x4002200C:
            return self.flash_sr
        if a == 0x40022010:
            return self.flash_cr | (0x80 if self.flash_locked else 0)
        if a == 0x4000300C:
            if self.iwdg['sr'] and self.iwdg['running'] and self.now_ms() - self.iwdg['sr_at'] > 0.2:
                self.iwdg['sr'] = 0       # updates complete a few LSI cycles later
            return self.iwdg['sr']
        if 0x40010800 <= a < 0x40011400:
            return self.gpio.get(a, 0)
        if a == 0x40010004:
            return self.mapr & ~(7 << 24)  # SWJ_CFG is write-only
        return 0

    def _wr(self, uc, off, size, v, _):
        self._fix_flash()
        a = 0x40000000 + off
        if 0x40005400 <= a < 0x40005800:
            self.i2c.write(a - 0x40005400, v)
        elif a == 0x4002101C:
            self.rcc['apb1'] = v
        elif a == 0x40021018:
            self.rcc['apb2'] = v
        elif a in (0x40006C04, 0x40006C08):
            if not self.pwr_dbp:
                raise Violation('BKP written without DBP')
            self.bkp[1 if a == 0x40006C04 else 2] = v & 0xFFFF
        elif a == 0x40007000:
            self.pwr_dbp = bool(v & (1 << 8))
        elif a == 0x40022004:           # KEYR
            self.flash_keys = (self.flash_keys << 32 | v) & 0xFFFFFFFFFFFFFFFF
            if self.flash_keys == 0x45670123CDEF89AB:
                self.flash_locked = False
        elif a == 0x40022008:
            raise Violation('option byte key written')
        elif a == 0x4002200C:
            self.flash_sr &= ~(v & 0x34)
        elif a == 0x40022010:
            if self.flash_locked and v & 0x7F:
                raise Violation('FLASH_CR written while locked')
            if v & (1 << 4) or v & (1 << 5):
                raise Violation('option byte program/erase')
            if v & 0x80:
                self.flash_locked = True
            if v & (1 << 6) and v & (1 << 1):
                self._flash_erase()
                v &= ~(1 << 6)
            self.flash_cr = v & 0x7F
        elif a == 0x40022014:
            self.flash_ar = v
        elif a == 0x40003000:
            iw = self.iwdg
            if v == 0xCCCC:
                iw['running'] = True
                iw['fed_ms'] = self.now_ms()
            elif v == 0x5555:
                iw['unlocked'] = True
            elif v == 0xAAAA:
                iw['fed_ms'] = self.now_ms()
                iw['unlocked'] = False
        elif a in (0x40003004, 0x40003008):
            iw = self.iwdg
            if iw['unlocked']:
                iw['pr' if a == 0x40003004 else 'rlr'] = v
                iw['sr'] |= 1 if a == 0x40003004 else 2
                iw['sr_at'] = self.now_ms() if iw['running'] else float('inf')  # never completes without LSI
        elif 0x40010800 <= a < 0x40011400:
            self._gpio_write(a, v)
        elif a == 0x40010004:
            self.mapr = v

    def _gpio_write(self, a, v):
        port = a & ~0x3FF
        reg = a & 0x3FF
        odr = self.gpio.get(port + 0x0C, 0)
        if reg == 0x10:
            odr = (odr | (v & 0xFFFF)) & ~(v >> 16)
        elif reg == 0x14:
            odr &= ~(v & 0xFFFF)
        elif reg == 0x0C:
            odr = v
        else:
            self.gpio[a] = v
        self.gpio[port + 0x0C] = odr
        crh = self.gpio.get(0x40010804, 0)
        if port == 0x40010800 and ((crh >> 20) & 3) and not (odr & (1 << 13)):
            self.pa13_low_ever = True     # Pico power enable driven low

    def _ppb_rd(self, uc, off, size, _):
        a = 0xE000E000 + off
        if a == 0xE000E010:
            v = self.systick_csr
            now = int(self.now_ms())
            if now > self.last_tick_ms:
                self.last_tick_ms += 1
                v |= 1 << 16
            return v
        if a == 0xE000ED08:
            return self.vtor
        return 0

    def _ppb_wr(self, uc, off, size, v, _):
        a = 0xE000E000 + off
        if a == 0xE000E010:
            self.systick_csr = v & 7
        elif a == 0xE000ED08:
            self.vtor = v
        elif a == 0xE000ED0C and (v >> 16) == 0x05FA and v & 4:
            self.stop_reason = 'reset'
            uc.emu_stop()


class I2CSlave:
    """RM0008 I2C slave behaviour, as far as the bootloader relies on it."""

    def __init__(self, chip):
        self.chip = chip
        self.cr1 = self.cr2 = self.oar1 = 0
        self.addr = self.rxne = self.txe = self.btf = self.stopf = self.af = False
        self.tra = self.busy = False
        self.dr_rx = 0
        self.dr_tx = None       # byte written by firmware, waiting to go out
        self.sr1_read = False
        self.pe_off_pending = False

    @property
    def pe(self):
        return bool(self.cr1 & 1)

    @property
    def ack(self):
        return bool(self.cr1 & (1 << 10))

    def sr1(self):
        return (self.addr << 1 | self.btf << 2 | self.stopf << 4 | self.rxne << 6 |
                self.txe << 7 | self.af << 10)

    def read(self, off):
        if off == 0x14:
            self.sr1_read = True
            return self.sr1()
        if off == 0x18:
            if self.sr1_read and self.addr:
                self.addr = False
                self.chip._poke_waiter()
            self.sr1_read = False
            return self.tra << 2 | self.busy << 1
        if off == 0x10:
            v = self.dr_rx
            self.rxne = False
            self.btf = False
            self.chip._poke_waiter()
            return v
        return {0x00: self.cr1, 0x04: self.cr2, 0x08: self.oar1}.get(off, 0)

    def write(self, off, v):
        if off == 0x00:
            if v & (1 << 15):
                self.__init__(self.chip)
                return
            if self.sr1_read and self.stopf:
                self.stopf = False
            self.sr1_read = False
            if self.pe and not (v & 1):
                if self.busy:
                    self.pe_off_pending = True   # takes effect at the end of the transfer
                    self.cr1 = v | 1
                    return
                self._disable()
            self.cr1 = v
            if not self.pe:
                self.cr1 &= ~(1 << 10)            # ACK can't be set while PE=0
            self.chip._poke_waiter()
        elif off == 0x04:
            self.cr2 = v
        elif off == 0x08:
            self.oar1 = v
        elif off == 0x10:
            if self.tra or True:
                self.dr_tx = v & 0xFF
                self.txe = False
                self.btf = False
                self.chip._poke_waiter()
        elif off == 0x14:
            if not (v & (1 << 10)):
                self.af = False

    def _disable(self):
        self.cr1 &= ~1
        self.cr1 &= ~(1 << 10)
        self.addr = self.rxne = self.txe = self.btf = self.stopf = self.af = self.tra = False
        self.dr_tx = None

    def _stop(self):
        self.busy = False
        self.tra = False
        self.txe = False                  # cleared by hardware on STOP; DR content stays
        if self.pe_off_pending:
            self.pe_off_pending = False
            self._disable()


class FakeI2C:
    """machine.I2C stand-in: kbdflash's master side, against the modelled slave."""

    TIMEOUT_MS = 200    # kbdflash sets timeout=200000 us

    def __init__(self, chip, noise=0.0, seed=1):
        self.chip = chip
        self.rng = random.Random(seed)
        self.noise = noise
        self.stuck = 0

    def _wait(self, cond):
        if not self.chip.run_until(cond, self.TIMEOUT_MS):
            if self.chip.mode != 'bl':
                raise PicoPowerCycle()
            self.stuck += 1
            raise OSError(110)

    def _gap(self):
        self.chip.run(200)                # bus idle between transactions (~25 us)
        if self.chip.mode == 'app':
            self.chip.app_tick(0)

    def _address(self, tra):
        s = self.chip.i2c
        if not (s.pe and s.ack) or (s.oar1 >> 1) & 0x7F != 0x1F:
            raise OSError(5)              # address NACK
        s.busy = True
        s.tra = tra
        s.addr = True
        if tra:
            s.txe = s.dr_tx is None
        self._wait(lambda: not s.addr)

    def _send(self, data):
        s = self.chip.i2c
        for b in data:
            self._wait(lambda: not s.rxne)   # DR full + next byte in: BTF, SCL stretched
            s.dr_rx = b
            s.rxne = True
            self.chip._poke_waiter()
            self.chip.run(120)            # ~one byte time at 8 MHz vs 50 kHz, scaled down
            if not s.ack:
                raise OSError(5)

    def _recv(self, n):
        s = self.chip.i2c
        out = bytearray()
        for i in range(n):
            if s.dr_tx is None:
                s.btf = i > 0
                self._wait(lambda: s.dr_tx is not None)
            out.append(s.dr_tx)
            s.dr_tx = None
            s.txe = True                  # DR moved to the shift register
            s.btf = False
            self.chip.run(120)            # firmware may refill DR while the byte shifts out
        s.af = True                       # master NACKs the last byte
        return bytes(out)

    def _check_app(self):
        if self.chip.mode == 'app':
            return True
        return False

    def writeto(self, addr, data, stop=True):
        assert addr == 0x1F
        data = bytes(data)
        if self.noise and self.rng.random() < self.noise:
            raise OSError(5)
        if self._check_app():
            return self.chip_app_write(data)
        self._address(False)
        self._send(data)
        self.chip.in_boot_path = False    # a command arrived: flash writes are allowed from here
        if stop:
            s = self.chip.i2c
            s.stopf = True
            s._stop()
            self._gap()

    def readfrom(self, addr, n):
        assert addr == 0x1F
        if self.noise and self.rng.random() < self.noise:
            raise OSError(110)
        if self._check_app():
            if n > 2:
                raise Violation('read %d bytes from the keyboard app: over-read would hold SCL' % n)
            return bytes(n)
        self._address(True)
        data = self._recv(n)
        self.chip.i2c._stop()
        self._gap()
        return data

    def readfrom_mem(self, addr, reg, n):
        if self._check_app():
            if self.chip.app_v16:          # upstream v1.6: 0x0E = REG_ID_OFF, 0x0F unknown
                return bytes((reg, 1 if reg == 0x0E else 60)) if reg in (0x0E, 0x0B) else bytes(2)
            if reg == 0x0F:
                return bytes((0x0F, 0xB1))    # signature 0xB0 | running above the bootloader
            if reg == 0x0B:
                return bytes((0x0B, 60))
            return bytes(2)
        self.writeto(addr, bytes((reg,)), stop=False)   # repeated start
        self._address(True)
        data = self._recv(n)
        self.chip.i2c._stop()
        self._gap()
        return data

    def chip_app_write(self, data):
        self.chip.app_writes.append(data)
        if self.chip.app_v16:
            if data[:1] == b'\x8e':
                self.chip.boot_log.append('v1.6 app: power off requested')
            return
        if data == bytes((0x8F, 0xB0)):
            ch = self.chip
            ch.bkp[1] = 0xB007
            ch.boot_log.append('app asks for bootloader')
            ch.power_on()                  # NVIC_SystemReset: BKP kept


def live_record(flash):
    for i in range(63, -1, -1):
        a = INFO_ADDR - FLASH + i * 16
        magic, ln, crc, inv = struct.unpack('<IIII', bytes(flash[a:a + 16]))
        if magic == 0x4B424F4B and inv == (~0x4B424F4B & 0xFFFFFFFF):
            return ln, crc
    return None


def combined(bl, app):
    img = bytearray(b'\xff' * FLASH_SIZE)
    img[:len(bl)] = bl
    app = app + b'\xff' * (-len(app) % 4)
    img[0x2000:0x2000 + len(app)] = app
    rec = struct.pack('<IIII', 0x4B424F4B, len(app), zlib.crc32(app), ~0x4B424F4B & 0xFFFFFFFF)
    img[0xFC00:0xFC10] = rec
    return bytes(img)


def write_img(d, name, data):
    p = os.path.join(d, name)
    with open(p, 'wb') as f:
        f.write(data)
    with open(p + '.crc32', 'w') as f:
        f.write('%08x\n' % zlib.crc32(data))
    return p


def attach(chip):
    kbdflash.sleep_ms = lambda ms: chip.run_ms(ms)
    kbdflash.ticks_ms = lambda: int(chip.total_ms())


def do_flash(chip, path, **kw):
    """kbdflash.flash() until the Pico power-cycles; returns erase cycles used."""
    attach(chip)
    before = sum(chip.erases)
    chip.pico_live = True
    try:
        kbdflash.flash(path, i2c=FakeI2C(chip, **kw))
    except PicoPowerCycle:
        pass
    finally:
        chip.pico_live = False
    return sum(chip.erases) - before


def app_is(chip, img):
    img = img + b'\xff' * (-len(img) % 4)
    rec = live_record(chip.flash)
    return rec == (len(img), zlib.crc32(img)) and bytes(chip.flash[0x2000:0x2000 + len(img)]) == img


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    quick = '--quick' in sys.argv
    bl = open(args[0], 'rb').read()
    app_a = open(args[1], 'rb').read()
    # B: the same app with a few bytes changed in two places (a real update touches few pages)
    b = bytearray(app_a)
    for off in (len(b) // 3, len(b) - 100):
        b[off] ^= 0x5A
    app_b = bytes(b)
    assert kbdflash.APP_MARKER in app_a and kbdflash.APP_MARKER in app_b, 'app built without kbd_boot.ino'
    tmp = tempfile.mkdtemp()
    kbdflash.KBD_DIR = tmp
    kbdflash.LAST_GOOD = os.path.join(tmp, 'last_good.bin')
    kbdflash.PENDING = os.path.join(tmp, 'pending.bin')
    kbdflash._say = lambda m: None
    import builtins
    real_print = builtins.print
    kbdflash.print = lambda *a, **k: None
    pa, pb = write_img(tmp, 'a.bin', app_a), write_img(tmp, 'b.bin', app_b)
    results = []

    def ok(name, cond, detail=''):
        if not cond:
            raise AssertionError('%s %s' % (name, detail))
        results.append((name, detail))
        real_print('  ok  %-58s %s' % (name, detail), flush=True)

    # 1. cold boot with a committed app: jumps, writes nothing, no trial watchdog
    chip = Chip(combined(bl, app_a))
    ok('cold boot jumps to the committed app', chip.mode == 'app' and chip.boot_log[-1] == 'app')
    ok('boot path: no flash writes, Pico enable never driven low',
       sum(chip.erases) == 0 and chip.programs == 0 and not chip.pa13_low_ever)
    boots = 50
    for _ in range(boots):
        chip.power_on(cold=True)
    ok('%d more cold boots: still no flash writes' % boots, sum(chip.erases) == 0 and chip.programs == 0)

    # 2. update A -> B through the app's enter-bootloader request
    e = do_flash(chip, pb)
    ok('update A->B: app runs B', chip.mode == 'app' and app_is(chip, app_b), 'erase cycles %d' % e)
    chip.app_tick(1000)
    ok('update A->B: trial boot under the watchdog, confirmed after 500 ms',
       chip.boot_log[-1] == 'app (trial)' and chip.bkp[2] == 0 and chip.mode == 'app', repr(chip.boot_log[-3:]))
    pages_changed = sum(1 for o in range(0, len(app_a), PAGE) if app_a[o:o + PAGE] != app_b[o:o + PAGE])
    ok('update A->B: erases only the changed pages', e == pages_changed, '%d of %d pages' % (e, -(-len(app_a) // PAGE)))

    # 3. same image again: no writes at all
    p0, e0 = chip.programs, sum(chip.erases)
    do_flash(chip, pb)
    ok('re-flash of the same image: zero erases, zero programs',
       chip.programs == p0 and sum(chip.erases) == e0 and app_is(chip, app_b))

    # 4. a bad app that never confirms its trial: back in the bootloader, then restore
    chip.app_bad = True
    do_flash(chip, pa)
    chip.app_tick(5000)
    ok('bad app: watchdog brings the chip back to the bootloader',
       chip.mode == 'bl' and 'iwdg reset' in chip.boot_log, repr(chip.boot_log[-3:]))
    st = kbdflash.Link(FakeI2C(chip)).status()
    ok('bootloader reports why: trial failed', st is not None and st.why == 3)
    ok('failed trial: its record is retired on the way in (2 programs, no erase)',
       live_record(chip.flash) is None and chip.retires == 2, 'retire programs %d' % chip.retires)
    chip.power_on(cold=True)
    st = kbdflash.Link(FakeI2C(chip)).status()
    ok('power cycle after a failed trial: stays in the bootloader, Pico powered',
       chip.mode == 'bl' and st is not None and st.why == 2 and chip.retires == 2, repr(chip.boot_log[-3:]))
    chip.app_bad = False
    do_flash(chip, pb)
    ok('restore after a failed trial', chip.mode == 'app' and app_is(chip, app_b))

    # 4b. power loss while the failed image is being retired: still never runs again
    for vbat in (True, False):
        c = Chip(combined(bl, app_b), bkp_on_vbat=vbat)
        c.app_bad = True
        do_flash(c, pa)
        c.cut_at = c.flash_ops + 1
        try:
            c.app_tick(5000)
            raise AssertionError('retire never cut')
        except PowerLoss:
            pass
        c.cut_at = None
        rec = live_record(c.flash)
        c.power_on(cold=True)
        # a cut program clears some bits of the magic: dead record. If by chance it cleared
        # none, only a kept backup domain (DR2 still TRIAL) can retire it again.
        ok('power loss during the retire (BKP %s): stays in the bootloader' % ('kept' if vbat else 'lost'),
           c.mode == 'bl' or (not vbat and rec is not None), 'record %s after the cut' % ('live' if rec else 'dead'))
        c.app_bad = False
        do_flash(c, pb)
        ok('... then restore works (BKP %s)' % ('kept' if vbat else 'lost'), c.mode == 'app' and app_is(c, app_b))

    # 4c. power lost inside the 500 ms trial window with BKP kept: the unconfirmed image is
    # retired too; flash() again only re-commits it (no page erases)
    c = Chip(combined(bl, app_a))
    do_flash(c, pb)
    c.power_on(cold=True)
    ok('power loss during a trial: image retired, bootloader waits', c.mode == 'bl' and live_record(c.flash) is None)
    e = do_flash(c, pb)
    ok('... flash() again: 0 erases, runs B', e == 0 and c.mode == 'app' and app_is(c, app_b))

    # 5. power loss during an update (B -> A), with and without the backup domain kept.
    # Every erase and every info-page write is a cut point, plus the first and last
    # halfword of each page and every 16th (--quick: a sample).
    def cut_sweep(name, start_img, path, img):
        probe = Chip(start_img)
        do_flash(probe, path)
        log = probe.op_log
        cuts = set()
        for i, (kind, addr) in enumerate(log, 1):
            first_last = i == 1 or i == len(log) or log[i - 2][1] // PAGE != addr // PAGE \
                or i == len(log) or log[i][1] // PAGE != addr // PAGE
            if kind == 'erase' or addr >= INFO_ADDR or first_last or i % (97 if quick else 16) == 0:
                cuts.add(i)
        if quick:
            cuts = set(sorted(cuts)[::3]) | {1, len(log)}
        worst, mixed = 0, 0
        for vbat in (True, False):
            for k in sorted(cuts):
                c = Chip(start_img, bkp_on_vbat=vbat)
                c.cut_at = k
                try:
                    do_flash(c, path)
                    raise AssertionError('%s: cut at op %d never happened' % (name, k))
                except PowerLoss:
                    pass
                c.cut_at = None
                c.power_on(cold=True)         # power comes back
                if c.mode == 'app' and not app_is(c, img):
                    mixed += 1                # start_app() already checks it matches a record
                do_flash(c, path)             # run the update again
                if not (c.mode == 'app' and app_is(c, img)):
                    raise AssertionError('%s: cut %d (vbat=%s): recovery failed' % (name, k, vbat))
                worst = max(worst, max(c.erases))
        ok('%s: power loss at %d of %d flash ops x 2 BKP cases: never a mixed image, always recovers'
           % (name, len(cuts), len(log)), True, 'worst wear on any page, cut + retry: %d erases' % worst)

    cut_sweep('update B->A', combined(bl, app_b), pa, app_a)

    # 5b. the same with the info-page log full, so this commit has to erase the info page
    full = bytearray(combined(bl, app_b))
    rec = bytes(full[0xFC00:0xFC10])
    for i in range(63):
        full[0xFC00 + i * 16:0xFC10 + i * 16] = b'\0\0\0\0' + rec[4:]   # invalidated records
    full[0xFC00 + 63 * 16:0xFC10 + 63 * 16] = rec
    c = Chip(bytes(full))
    ok('info log full: chip still boots the last record', c.mode == 'app' and app_is(c, app_b))
    cut_sweep('update with a full info log', bytes(full), pa, app_a)

    # 6. retries on a noisy bus
    c = Chip(combined(bl, app_a))
    e = do_flash(c, pb, noise=0.05, seed=5)
    ok('noisy bus (5% transfer errors): update completes', c.mode == 'app' and app_is(c, app_b),
       'erase cycles %d' % e)

    # 7. bad images never reach the chip
    c = Chip(combined(bl, app_a))
    p_bad = write_img(tmp, 'bad.bin', struct.pack('<II', 0x20005000, 0x08000101) + app_a[8:])
    try:
        do_flash(c, p_bad)
        raise AssertionError('bad image accepted')
    except kbdflash.KbdFlashError:
        pass
    ok('image linked at 0x08000000: refused, chip untouched',
       c.programs == 0 and sum(c.erases) == 0 and c.mode == 'app')
    i = app_a.find(kbdflash.APP_MARKER)
    p_nomark = write_img(tmp, 'nomark.bin', app_a[:i] + bytes(8) + app_a[i + 8:])
    try:
        do_flash(c, p_nomark)
        raise AssertionError('image without marker accepted')
    except kbdflash.KbdFlashError:
        pass
    ok('image without the kbd_boot.ino marker: refused, chip untouched',
       c.programs == 0 and sum(c.erases) == 0 and c.mode == 'app' and not c.app_writes)

    # 7b. upstream v1.6 keyboard firmware, where 0x0E powers the device off: kbdflash
    # must not write to it at all
    c = Chip(combined(bl, app_a))
    c.app_v16 = True
    ok('v1.6 keyboard: status() says other firmware', kbdflash.status(i2c=FakeI2C(c)) == 'app')
    try:
        do_flash(c, pb)
        raise AssertionError('flash() went ahead on a v1.6 keyboard')
    except kbdflash.KbdFlashError:
        pass
    ok('v1.6 keyboard: flash() refuses, no I2C write reaches it',
       c.app_writes == [] and c.programs == 0 and sum(c.erases) == 0, repr(c.app_writes))

    # 8. the app asks for the bootloader and nobody flashes: back to the app after 30 s, no writes
    c = Chip(combined(bl, app_a))
    FakeI2C(c).writeto(0x1F, bytes((0x8F, 0xB0)))
    ok('app -> bootloader request lands in the bootloader', c.mode == 'bl')
    c.run_ms(31000)
    ok('idle 30 s in the bootloader: back to the app, no flash writes',
       c.mode == 'app' and c.programs == 0 and sum(c.erases) == 0, repr(c.boot_log[-2:]))

    real_print('emu_test: %d checks passed' % len(results))


if __name__ == '__main__':
    main()
