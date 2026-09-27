"""kbdflash: update the PicoCalc keyboard chip (STM32F103) from MicroPython, over I2C.

Needs the keyboard firmware from prokrypt/PicoCalc branch claude/kbd-i2c-bootloader,
installed once over USB-C with DIP switch 1 (see Code/picocalc_kbd_bootloader/README.md).
After that:

    import kbdflash
    kbdflash.status()                  # what is answering at 0x1F
    kbdflash.plan('/sd/kbd/app.bin')   # how many flash pages an update would erase (no I2C)
    kbdflash.flash('/sd/kbd/app.bin')  # the Pico power-cycles at the end
    kbdflash.autorecover()             # for main.py: see README

The keyboard stops working while this runs, and the keyboard chip controls the Pico's
power, so the Pico restarts when the new keyboard firmware starts. If anything fails
after the first erase, the keyboard chip stays in its bootloader (Pico powered, screen
lit) until a good image is written, so running flash() or recover() again always works.

Flash wear: the STM32F103 is rated for about 10,000 erase cycles per page. Only
flash() and recover() ever erase or program it, and only pages whose content
differs from the image; re-flashing the same image erases nothing. The image must
come with a .crc32 sidecar (tools/mkimage.py writes it) and is checked against it,
read twice, before anything is touched.
"""
import struct

try:
    from time import sleep_ms, ticks_ms, ticks_diff
except ImportError:  # CPython, for tools/sim_test.py
    import time as _t

    def sleep_ms(ms):
        _t.sleep(ms / 1000)

    def ticks_ms():
        return int(_t.monotonic() * 1000)

    def ticks_diff(a, b):
        return a - b

try:
    from binascii import crc32 as _crc32
except ImportError:
    _crc32 = None

# Must match bl_core.h
ADDR = 0x1F
MARKER = 0xB1
APP_BASE = 0x08002000
APP_MAX = 0xDC00
PAGE = 1024
RAM_START = 0x20000000
RAM_END = 0x20005000
WRITE_MAX = 128
STATUS_LEN = 24

BL_VERSION = 2
CMD_INFO, CMD_ERASE_PAGE, CMD_WRITE, CMD_CRC, CMD_COMMIT, CMD_BOOT, CMD_PING = (
    0x01, 0x11, 0x20, 0x30, 0x40, 0x50, 0x51)
ST_IDLE, ST_BUSY, ST_OK, ST_ERR = 0, 1, 2, 3
REG_BAT = 0x0B
REG_BOOT = 0x0E
BOOT_CONFIRM = 0xB0

ERRORS = {
    2: 'bad frame length', 3: 'offset or length out of range', 4: 'checksum mismatch (I2C noise?)',
    5: 'page not erased in this session', 6: 'flash controller error', 7: 'read-back differs',
    8: 'CRC mismatch after writing', 9: 'image vectors not plausible', 11: 'I2C write too long',
    12: 'no valid app to boot',
}
WHY = {1: 'asked by the keyboard firmware', 2: 'no valid keyboard firmware in flash',
       3: 'the last flashed firmware did not start'}

KBD_DIR = '/sd/kbd'
APP_BIN = KBD_DIR + '/app.bin'          # default image to flash
LAST_GOOD = KBD_DIR + '/last_good.bin'  # last image seen running (autorecover restores it)
PENDING = KBD_DIR + '/pending.bin'      # just flashed, not yet seen running
MIN_BATTERY = 25     # percent; below this, refuse unless charging or force=True
DEFAULT_FREQ = 50000


class KbdFlashError(Exception):
    pass


def _say(msg):
    print('[kbd] ' + msg)


def crc32(data, crc=0):
    if _crc32:
        return _crc32(data, crc) & 0xFFFFFFFF
    c = ~crc & 0xFFFFFFFF
    for b in data:
        c ^= b
        for _ in range(8):
            c = (c >> 1) ^ (0xEDB88320 & -(c & 1))
    return ~c & 0xFFFFFFFF


def _sum16(b):
    s = 0
    for x in b:
        s += x
    return s & 0xFFFF


def _make_i2c(freq):
    from machine import I2C, Pin
    try:
        # timeout covers clock stretching while the bootloader erases a page (~20 ms)
        return I2C(1, scl=Pin(7), sda=Pin(6), freq=freq, timeout=200000)
    except TypeError:
        return I2C(1, scl=Pin(7), sda=Pin(6), freq=freq)


class _Parked:
    """Stands in for the keyboard driver's I2C object while we flash, so timers and the
    terminal's key polling fail fast (they already treat OSError as 'no data')."""

    def __getattr__(self, name):
        def dead(*a, **k):
            raise OSError(19)
        return dead


def _park_keyboard():
    try:
        import glob
        kb = glob.pc_keyboard
    except Exception:
        return None
    if kb is None or not hasattr(kb, 'i2c'):
        return None
    saved = kb.i2c
    kb.i2c = _Parked()
    return kb, saved


def _unpark_keyboard(parked, restore_freq):
    if not parked:
        return
    kb, saved = parked
    try:
        kb.i2c = _make_i2c(restore_freq)  # our I2C(1) re-init changed the bus speed
    except Exception:
        kb.i2c = saved


class Status:
    def __init__(self, raw):
        (self.marker, self.version, self.state, self.seq, self.cmd, self.err, self.page,
         self.value, self.app_base, self.app_max, self.why) = struct.unpack('<BBBBBBHIIIB', raw[:21])

    def __repr__(self):
        return 'Status(v%d state=%d seq=%d cmd=0x%02x err=%d value=%d why=%d)' % (
            self.version, self.state, self.seq, self.cmd, self.err, self.value, self.why)


class Link:
    def __init__(self, i2c, addr=ADDR):
        self.i2c = i2c
        self.addr = addr

    # --- bootloader side ---

    def probe(self):
        """What answers at 0x1F, using only a 2-byte register read, which is safe for
        every firmware (reading past what the app offers can stretch SCL forever):
        'bl' bootloader, 'app+bl' app above the bootloader, 'app' any other keyboard
        firmware, None nothing answered."""
        r = self.app_reg(REG_BOOT)  # the bootloader ignores 0x0E and answers with its marker
        if r is None:
            return None
        if r[0] == MARKER:
            return 'bl'
        if r[0] == REG_BOOT and r[1] & 1:
            return 'app+bl'
        return 'app'

    def status(self, tries=3):
        """Bootloader Status. Call only once probe() said 'bl'. None if no valid status
        came back (a byte left over from a short read can shift one read; retry)."""
        for i in range(tries):
            try:
                raw = self.i2c.readfrom(self.addr, STATUS_LEN)
            except OSError:
                sleep_ms(5 * (i + 1))
                continue
            if raw[0] == MARKER:
                s = Status(raw)
                if s.app_base == APP_BASE:
                    return s
            sleep_ms(2)
        return None

    def command(self, frame, timeout_ms=2000, progress=None):
        """Send one command and wait for its result. Retries are safe: a command the
        bootloader already took shows up as the next sequence number, and WRITE skips
        halfwords that already hold the right value."""
        before = self.status(tries=5)
        if before is None:
            raise KbdFlashError('bootloader stopped answering')
        want = (before.seq + 1) & 0xFF
        t0 = ticks_ms()
        sent = 0
        while True:
            if sent < 4:
                try:
                    self.i2c.writeto(self.addr, frame)
                except OSError:
                    pass
                sent += 1
            s = None
            while True:
                s = self.status(tries=5)
                if s is None:
                    raise KbdFlashError('bootloader stopped answering')
                if s.seq != want or s.state != ST_BUSY:
                    break
                if progress:
                    progress(s.value)
                if ticks_diff(ticks_ms(), t0) > timeout_ms:
                    raise KbdFlashError('command 0x%02x timed out while busy' % frame[0])
                sleep_ms(10)
            if s.seq == want:
                if s.state == ST_OK:
                    return s.value
                raise KbdFlashError('command 0x%02x failed: %s' % (frame[0], ERRORS.get(s.err, 'error %d' % s.err)))
            if s.seq != before.seq:
                raise KbdFlashError('lost track of the bootloader (another I2C user?)')
            if sent >= 4 or ticks_diff(ticks_ms(), t0) > timeout_ms:
                raise KbdFlashError('command 0x%02x was never accepted' % frame[0])
            sleep_ms(5)

    def erase_page(self, offset):
        """Erase one app page (the bootloader first invalidates the committed app).
        Returns 1 if an erase cycle was spent, 0 if the page was already blank."""
        return self.command(struct.pack('<BI', CMD_ERASE_PAGE, offset), timeout_ms=1000)

    def write(self, offset, data):
        frame = struct.pack('<BIB', CMD_WRITE, offset, len(data)) + bytes(data)
        frame += struct.pack('<H', _sum16(frame))
        return self.command(frame, timeout_ms=1000)

    def commit(self, length, crc, progress=None):
        return self.command(struct.pack('<BII', CMD_COMMIT, length, crc), timeout_ms=5000, progress=progress)

    def crc(self, offset, length):
        return self.command(struct.pack('<BII', CMD_CRC, offset, length), timeout_ms=5000)

    def boot(self):
        return self.command(bytes((CMD_BOOT,)), timeout_ms=1000)

    # --- app side ---

    def app_reg(self, reg):
        for _ in range(3):
            try:
                return self.i2c.readfrom_mem(self.addr, reg, 2)
            except OSError:
                sleep_ms(2)
        return None

    def enter_bootloader(self, wait_ms=3000):
        """Ask the app to restart into the bootloader; returns the bootloader Status or None."""
        r = self.app_reg(REG_BOOT)
        if r is None or r[0] != REG_BOOT or not (r[1] & 1):
            return None  # old firmware, or not linked above the bootloader
        try:
            self.i2c.writeto(self.addr, bytes((REG_BOOT | 0x80, BOOT_CONFIRM)))
        except OSError:
            pass
        t0 = ticks_ms()
        sleep_ms(100)
        while ticks_diff(ticks_ms(), t0) < wait_ms:
            if self.probe() == 'bl':
                return self.status()
            sleep_ms(50)
        return None


def _read(path):
    with open(path, 'rb') as f:
        return f.read()


def load_image(path, expect_crc=None):
    """Read, check and pad an image. The crc32 of the file as built must match
    expect_crc or the '<path>.crc32' sidecar, and two reads must agree, so an SD
    card glitch or a truncated copy is caught before anything is erased."""
    raw = _read(path)
    if expect_crc is None:
        try:
            expect_crc = int(_read(path + '.crc32').decode().split()[0], 16)
        except (OSError, ValueError, IndexError):
            raise KbdFlashError('no %s.crc32 sidecar: copy it with the .bin (tools/mkimage.py writes it), '
                                'or pass expect_crc=' % path)
    got = crc32(raw)
    if got != expect_crc:
        raise KbdFlashError('%s crc32 is %08x, expected %08x: the file is damaged or not the one built'
                            % (path, got, expect_crc))
    if crc32(_read(path)) != got:
        raise KbdFlashError('%s reads back differently each time: SD card problem' % path)
    img = raw
    if len(img) % 4:
        img += b'\xff' * (4 - len(img) % 4)
    check_image(img)
    return img


def _pages(img):
    return [(off, img[off:off + PAGE]) for off in range(0, len(img), PAGE)]


def plan(path=None, against=None, expect_crc=None):
    """Host-only dry run: check the image and show how many pages an update would
    erase, compared with `against` (default: last_good.bin, the image believed to
    be in the keyboard chip). Touches no hardware."""
    path = path or APP_BIN
    img = load_image(path, expect_crc)
    against = against or LAST_GOOD
    try:
        old = _read(against)
        old += b'\xff' * (-len(old) % 4)  # as it was written
    except OSError:
        old = None
    pages = _pages(img)
    if old is None:
        changed = len(pages)
        _say('%s: %d bytes, %d pages; no %s to compare, so up to %d page erases'
             % (path, len(img), len(pages), against, changed))
    else:
        changed = sum(1 for off, p in pages if old[off:off + len(p)] != p)
        _say('%s: %d bytes, %d pages; %d differ from %s, so %d page erases (+1 info record)'
             % (path, len(img), len(pages), changed, against, changed))
    return changed


def check_image(img):
    """Refuse images that can't run at APP_BASE, before anything is erased."""
    if len(img) < 8:
        raise KbdFlashError('image too small (%d bytes)' % len(img))
    if len(img) > APP_MAX:
        raise KbdFlashError('image is %d bytes; the app area holds %d' % (len(img), APP_MAX))
    sp, pc = struct.unpack('<II', img[:8])
    if not (RAM_START < sp <= RAM_END) or sp & 3:
        raise KbdFlashError('initial stack pointer 0x%08x is not in RAM: not a keyboard app image' % sp)
    if not (pc & 1) or not (APP_BASE + 8 <= (pc & ~1) < APP_BASE + len(img)):
        if (pc & ~1) < APP_BASE:
            raise KbdFlashError('reset vector 0x%08x is below 0x%08x: this build is linked for 0x08000000. '
                                'Rebuild with tools/build_app.sh (flash offset 0x2000).' % (pc, APP_BASE))
        raise KbdFlashError('reset vector 0x%08x is outside the image' % pc)


def estimate_s(length, freq=DEFAULT_FREQ):
    chunks = (length + WRITE_MAX - 1) // WRITE_MAX
    pages = (length + PAGE - 1) // PAGE + 1
    per_chunk = ((WRITE_MAX + 8) + 2 * (STATUS_LEN + 1)) * 9 / freq + 0.006
    return 1 + pages * 0.03 + chunks * per_chunk + 0.5


def _bar(done, total, width=20):
    n = done * width // total if total else width
    return '[' + '#' * n + '.' * (width - n) + '] %3d%%' % (done * 100 // total if total else 100)


def _save_copy(img, path, sidecar=False):
    try:
        import os
        try:
            os.mkdir(KBD_DIR)
        except OSError:
            pass
        with open(path, 'wb') as f:
            f.write(img)
        if sidecar:  # images kept for recover() carry their crc like any other
            with open(path + '.crc32', 'w') as f:
                f.write('%08x\n' % crc32(img))
        return True
    except Exception as e:
        _say('note: could not save %s (%s)' % (path, e))
        return False


def status(i2c=None, freq=DEFAULT_FREQ):
    """Print and return what is answering at 0x1F."""
    parked = _park_keyboard()
    try:
        link = Link(i2c or _make_i2c(freq))
        what = link.probe()
        if what == 'bl':
            s = link.status()
            if s:
                _say('bootloader v%d is running (%s)' % (s.version, WHY.get(s.why, 'reason %d' % s.why)))
            return s
        if what is None:
            _say('nothing answered at 0x1F')
        elif what == 'app+bl':
            _say('keyboard firmware is running above the bootloader: kbdflash.flash() will work')
        else:
            _say('keyboard firmware is running without the bootloader: install it over USB first (README)')
        return what
    finally:
        _unpark_keyboard(parked, 12000)


def flash(path=None, i2c=None, force=False, freq=DEFAULT_FREQ, restore_freq=12000, reboot=True,
          expect_crc=None):
    """Write a keyboard app image (raw .bin linked at 0x08002000) and restart into it.
    Only pages that differ from what the chip holds are erased and written."""
    t_start = ticks_ms()
    path = path or APP_BIN
    img = load_image(path, expect_crc)
    crc = crc32(img)
    est = estimate_s(len(img), freq)
    _say('Keyboard firmware update: %s, %d bytes, crc %08x (file checked)' % (path, len(img), crc))
    _say('This takes up to %d s. The keyboard stops responding until it is done; then the '
         'keyboard chip restarts and the Pico power-cycles with it. Keep power on.' % int(est + 0.5))

    parked = _park_keyboard()
    entered = False
    try:
        link = Link(i2c or _make_i2c(freq))
        what = link.probe()
        if what is None:
            raise KbdFlashError('nothing answered at 0x1F. Nothing was changed.')
        s = link.status() if what == 'bl' else None
        if what == 'bl' and s is None:
            raise KbdFlashError('the bootloader answered but its status did not read back cleanly')
        if s is None:
            bat = link.app_reg(REG_BAT)
            if bat is not None and bat[0] == REG_BAT:
                pct, charging = bat[1] & 0x7F, bat[1] & 0x80
                _say('Battery %d%%%s' % (pct, ', charging' if charging else ''))
                if pct < MIN_BATTERY and not charging and not force:
                    raise KbdFlashError('battery below %d%% and not charging: plug in USB-C, or pass force=True'
                                        % MIN_BATTERY)
            _say('1/5 Asking the keyboard firmware to restart into its bootloader...')
            s = link.enter_bootloader()
            if s is None:
                raise KbdFlashError('no bootloader answered. Either this keyboard firmware predates the '
                                    'bootloader (install it once over USB with DIP 1, see README) or the request '
                                    'was lost. Nothing was changed; the keyboard still works.')
        else:
            _say('1/5 Keyboard is already in its bootloader (%s).' % WHY.get(s.why, 'reason %d' % s.why))
        entered = True
        if s.version != BL_VERSION:
            raise KbdFlashError('bootloader protocol v%d, this kbdflash speaks v%d: nothing was changed. '
                                'Use the kbdflash.py from the same build as the bootloader.' % (s.version, BL_VERSION))
        if s.app_max < len(img):
            raise KbdFlashError('bootloader reports only %d bytes of app space' % s.app_max)

        pages = _pages(img)
        _say('2/5 Comparing %d pages with the chip (reads only)...' % len(pages))
        todo = [(off, p) for off, p in pages if link.crc(off, len(p)) != crc32(p)]
        _say('    %d of %d pages differ.' % (len(todo), len(pages)))

        erased = 0
        if todo:
            nbytes = sum(len(p) for _, p in todo)
            _say('3/5 Rewriting %d pages (%d bytes)...' % (len(todo), nbytes))
            done = 0
            for off, p in todo:
                erased += link.erase_page(off)
                for o in range(0, len(p), WRITE_MAX):
                    chunk = p[o:o + WRITE_MAX]
                    for attempt in range(3):
                        try:
                            link.write(off + o, chunk)
                            break
                        except KbdFlashError as e:
                            if attempt == 2 or 'not erased' in str(e) or 'controller' in str(e):
                                raise
                            _say('retrying block at %d: %s' % (off + o, e))
                done += len(p)
                print('\r[kbd]     ' + _bar(done, nbytes), end='')
            print()
        else:
            _say('3/5 Nothing to rewrite.')

        _say('4/5 Verifying crc %08x on the keyboard chip...' % crc)
        link.commit(len(img), crc)
        _say('    verified and committed; %d erase cycles used.' % erased)

        if path != LAST_GOOD and todo:
            _save_copy(img, PENDING, sidecar=True)  # autorecover() promotes it once it is seen running
        took = ticks_diff(ticks_ms(), t_start) / 1000
        if not reboot:
            _say('5/5 Done in %.1f s. Staying in the bootloader (reboot=False); run kbdflash.boot() to start it.' % took)
            return erased
        _say('5/5 Done in %.1f s. Starting the keyboard firmware: the Pico restarts now.' % took)
        sleep_ms(300)  # let the message reach the screen
        entered = False  # past this point a failure leaves a valid, committed app
        link.boot()
        sleep_ms(2000)  # normally the power cut arrives first
        _say('still running: the keyboard firmware did not cut Pico power (expected with some builds).')
        return erased
    except BaseException as e:
        if entered:
            _say('FAILED: %s' % e)
            _say('The keyboard chip stays in its bootloader with the Pico powered until a good image is written.')
            _say('Run kbdflash.flash() again (pages already right are not erased again), or '
                 'kbdflash.recover() for the last good image. Last resort: DIP 1 + USB-C (README).')
        raise
    finally:
        _unpark_keyboard(parked, restore_freq)


def boot(i2c=None, freq=DEFAULT_FREQ):
    """Leave the bootloader and start the committed app (the Pico restarts)."""
    Link(i2c or _make_i2c(freq)).boot()


def recover(i2c=None, force=True):
    """Reflash the last image that was seen running."""
    return flash(LAST_GOOD, i2c=i2c, force=force)


def autorecover(i2c=None, allow_flash=False):
    """For main.py. Cheap when all is well (one 2-byte register read), and writes no
    flash unless allow_flash=True. If a freshly flashed image is running, promote it
    to last_good. If the keyboard chip sits in its bootloader with its app intact,
    start the app (no writes). Otherwise say what to do; with allow_flash=True,
    restore last_good.bin once (a marker file stops a second automatic attempt)."""
    import os
    link = Link(i2c or _make_i2c(12000))
    what = link.probe()
    if what is None:
        return None
    if what != 'bl':
        try:
            os.remove(KBD_DIR + '/autorecover.tried')  # a restore that ended in a reboot worked
        except OSError:
            pass
        try:
            os.stat(PENDING)
        except OSError:
            return 'ok'
        try:
            for ext in ('', '.crc32'):
                try:
                    os.remove(LAST_GOOD + ext)
                except OSError:
                    pass
                os.rename(PENDING + ext, LAST_GOOD + ext)
            _say('new keyboard firmware is running; kept it as ' + LAST_GOOD)
        except OSError as e:
            _say('could not promote %s: %s' % (PENDING, e))
        return 'promoted'
    s = link.status()
    _say('keyboard chip is in its bootloader (%s)' % (WHY.get(s.why, '?') if s else '?'))
    if s is not None and s.why == 1:
        # The app asked for the bootloader and then nobody flashed (the Pico restarted?).
        # If the committed app is still intact, just start it again.
        try:
            _say('starting the keyboard firmware that is already in flash')
            link.boot()
            return 'booted'
        except KbdFlashError as e:
            _say('cannot start it (%s); reflashing' % e)
    if s is not None and s.why == 3:
        try:
            os.remove(PENDING)  # the image that failed its trial
            os.remove(PENDING + '.crc32')
            _say('removed %s: it did not start' % PENDING)
        except OSError:
            pass
    try:
        os.stat(LAST_GOOD)
    except OSError:
        _say('no %s to restore. Copy a keyboard .bin there, or use DIP 1 + USB-C (README).' % LAST_GOOD)
        return 'stuck'
    marker = KBD_DIR + '/autorecover.tried'
    if not allow_flash:
        _say('the keyboard firmware needs restoring. Run kbdflash.recover() (over WiFi or USB serial).')
        return 'needs-recover'
    try:
        os.stat(marker)
        _say('automatic restore already tried once; run kbdflash.recover() by hand, then delete ' + marker)
        return 'needs-recover'
    except OSError:
        pass
    _save_copy(b'1', marker)
    flash(LAST_GOOD, i2c=link.i2c, force=True)
    try:
        os.remove(marker)
    except OSError:
        pass
    return 'recovered'
