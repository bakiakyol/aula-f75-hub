"""Linux backend: the keyboard through /dev/hidraw*.

No extra libraries: plain os.read/os.write on the hidraw node, device info
from /sys. Access requires the udev rule in udev/70-aula-f75.rules.
"""

import fcntl
import glob
import os
import select
import subprocess
import time

from ..errors import AulaError
from ..protocol import WIRED_REPORT_ID
from .base import (PRODUCT_WIRED, PRODUCTS, VENDOR_WIRED, VENDOR_WIRELESS, Channel,
                   FeatureChannel, KeyGuard, NoKeyGuard)

# Report descriptor fragment: Usage Page 0xFF02, Usage 2, Collection, Report ID 0x13
_VENDOR_CHANNEL = bytes([0x06, 0x02, 0xFF, 0x09, 0x02, 0xA1, 0x01, 0x85, 0x13])


def _uevent(path: str) -> dict:
    out = {}
    try:
        with open(path) as f:
            for line in f:
                k, _, v = line.strip().partition("=")
                out[k] = v
    except OSError:
        pass
    return out


def _sibling_nodes(path: str) -> list[str]:
    """All hidraw nodes of the same device (e.g. its boot keyboard interface)."""
    want = _uevent(f"/sys/class/hidraw/{os.path.basename(path)}/device/uevent").get("HID_ID")
    return [
        "/dev/" + os.path.basename(d)
        for d in sorted(glob.glob("/sys/class/hidraw/hidraw*"))
        if want and _uevent(f"{d}/device/uevent").get("HID_ID") == want
    ]


def _has_feature_report(desc: bytes, report_id: int) -> bool:
    """Does the report descriptor declare a Feature report with this id?"""
    i, current = 0, 0
    while i < len(desc):
        prefix = desc[i]
        if prefix == 0xFE:  # long item: skip it
            i += 3 + (desc[i + 1] if i + 1 < len(desc) else 0)
            continue
        size = (0, 1, 2, 4)[prefix & 0x03]
        value = int.from_bytes(desc[i + 1:i + 1 + size], "little")
        if prefix & 0xFC == 0x84:  # Global: Report ID
            current = value
        elif prefix & 0xFC == 0xB0 and current == report_id:  # Main: Feature
            return True
        i += 1 + size
    return False


def _keys_down(report: bytes, bluetooth: bool = False) -> bool | None:
    """True/False if the report is a keyboard state report, None otherwise.

    2.4G dongle: boot keyboard interface sends 8-byte reports without an id
    ([mods, 0, key x5, vendor]); the NKRO bitmap is report 4.
    Bluetooth: everything arrives on one node; the keyboard report is id 1
    ([1, mods, 0, key x5, vendor]) and the NKRO bitmap is id 2. (Id 4 is system
    control there, so it must not be read as keys.)
    """
    if not report:
        return None
    if bluetooth:
        if report[0] == 0x01 and len(report) >= 8:
            return bool(report[1] or any(report[3:8]))
        if report[0] == 0x02:
            return any(report[1:])
        return None
    if len(report) == 8:
        return bool(report[0] or any(report[2:7]))
    if report[0] == 0x04:
        return any(report[1:])
    return None


def find_devices() -> list[dict]:
    """List connected AULA F75 configuration channels."""
    found = []
    for sys_dir in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        ev = _uevent(f"{sys_dir}/device/uevent")
        try:
            _bus, vid, pid = (int(x, 16) for x in ev.get("HID_ID", "").split(":"))
        except ValueError:
            continue
        node = "/dev/" + os.path.basename(sys_dir)
        if vid == VENDOR_WIRED and pid == PRODUCT_WIRED:
            # several nodes; the one with feature report 0x06 is the configuration channel
            try:
                with open(f"{sys_dir}/device/report_descriptor", "rb") as f:
                    desc = f.read()
            except OSError:
                continue
            if _has_feature_report(desc, WIRED_REPORT_ID):
                found.append({"path": node, "mode": "wired", "supported": True,
                              "name": ev.get("HID_NAME", "")})
            continue
        if vid != VENDOR_WIRELESS or pid not in PRODUCTS:
            continue
        try:
            with open(f"{sys_dir}/device/report_descriptor", "rb") as f:
                desc = f.read()
        except OSError:
            continue
        if _VENDOR_CHANNEL in desc:
            found.append({"path": node, "mode": PRODUCTS[pid], "supported": True,
                          "name": ev.get("HID_NAME", "")})
    return found


class LinuxChannel(Channel):
    def __init__(self, path: str):
        try:
            self.fd = os.open(path, os.O_RDWR)
        except PermissionError:
            raise AulaError(f"cannot open {path}: permission denied. "
                            "Is the udev rule installed? (see README)") from None

    def write(self, pkt: bytes) -> None:
        os.write(self.fd, pkt)

    def recv(self, timeout: float) -> bytes | None:
        if select.select([self.fd], [], [], timeout)[0]:
            return os.read(self.fd, 64)
        return None

    def drain(self) -> None:
        while select.select([self.fd], [], [], 0.02)[0]:
            os.read(self.fd, 64)

    def close(self) -> None:
        os.close(self.fd)


def _hidioc(nr: int, length: int) -> int:
    """HIDIOCSFEATURE (nr 6) / HIDIOCGFEATURE (nr 7) from linux/hidraw.h."""
    return (3 << 30) | (length << 16) | (ord("H") << 8) | nr


class LinuxFeatureChannel(FeatureChannel):
    """The wired configuration channel: feature reports through hidraw ioctls."""

    def __init__(self, path: str):
        try:
            self.fd = os.open(path, os.O_RDWR)
        except PermissionError:
            raise AulaError(f"cannot open {path}: permission denied. "
                            "Is the udev rule installed? (see README)") from None

    def set_feature(self, report: bytes) -> None:
        fcntl.ioctl(self.fd, _hidioc(6, len(report)), bytearray(report))

    def get_feature(self, report_id: int, length: int) -> bytes:
        buf = bytearray(length)
        buf[0] = report_id
        n = fcntl.ioctl(self.fd, _hidioc(7, length), buf, True)
        return bytes(buf[:n]) if n and n > 0 else bytes(buf)

    def close(self) -> None:
        os.close(self.fd)


class LinuxKeyGuard(KeyGuard):
    """Watches the keyboard's normal key reports on its other hidraw nodes."""

    def __init__(self, path: str, bluetooth: bool):
        self.bluetooth = bluetooth
        self._key_fds = []
        self._config_fd = None
        for node in _sibling_nodes(path):
            try:
                fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                continue
            self._key_fds.append(fd)
            if node == path:
                self._config_fd = fd
        self._held: dict[int, bool] = {}
        self._last_key_event = time.monotonic()

    def wait_released(self, quiet: float = 0.4, limit: float = 5.0) -> None:
        """Returns at once if nothing was typed since the last call."""
        if not self._key_fds:
            time.sleep(quiet)
            return
        start = time.monotonic()
        while True:
            for fd in select.select(self._key_fds, [], [], 0.05)[0]:
                try:
                    report = os.read(fd, 64)
                except BlockingIOError:
                    continue
                if fd == self._config_fd and report[:1] == bytes([WIRED_REPORT_ID]):
                    # wired mode: the keyboard's own notice on the configuration
                    # collection (e.g. 06 0a 07 … after a write), not a key report
                    continue
                state = _keys_down(report, self.bluetooth)
                if state is not None:
                    self._held[fd] = state
                    self._last_key_event = time.monotonic()
            now = time.monotonic()
            if not any(self._held.values()) and now - self._last_key_event >= quiet:
                return
            if now - start > limit:
                raise AulaError("a key seems to be held down; release all keys and try again")

    def close(self) -> None:
        for fd in self._key_fds:
            os.close(fd)


def open_device(path: str, mode: str) -> tuple[Channel | FeatureChannel, KeyGuard]:
    channel = LinuxFeatureChannel(path) if mode == "wired" else LinuxChannel(path)
    try:
        guard = LinuxKeyGuard(path, mode == "Bluetooth")
    except OSError:
        guard = NoKeyGuard()
    return channel, guard


def detect_layout() -> str:
    """'tr' when the computer uses the Turkish Q layout, otherwise 'us'."""
    try:
        out = subprocess.run(["setxkbmap", "-query"], capture_output=True, text=True, timeout=2).stdout
        conf = {k.strip(): v.strip() for k, _, v in (ln.partition(":") for ln in out.splitlines())}
        layout, variant = conf.get("layout", ""), conf.get("variant", "")
    except (OSError, subprocess.SubprocessError):
        layout = variant = ""
    if not layout:
        try:
            with open("/etc/default/keyboard") as f:
                conf = dict(ln.strip().partition("=")[::2] for ln in f if "=" in ln)
            layout, variant = conf.get("XKBLAYOUT", "").strip('"'), conf.get("XKBVARIANT", "").strip('"')
        except OSError:
            pass
    # several layouts are listed as "tr,us"; the first one is the default
    first = layout.split(",")[0]
    return "tr" if first == "tr" and variant.split(",")[0] in ("", "basic") else "us"


# Linux input key codes (linux/input-event-codes.h) -> names in HID or MODIFIERS,
# for recording macros. X11/GTK hardware keycodes are these plus 8.
EVDEV = {
    1: "esc", **{2 + i: str((i + 1) % 10) for i in range(10)}, 12: "minus", 13: "equal",
    14: "backspace", 15: "tab", **{16 + i: c for i, c in enumerate("qwertyuiop")},
    26: "lbracket", 27: "rbracket", 28: "enter", 29: "lctrl",
    **{30 + i: c for i, c in enumerate("asdfghjkl")}, 39: "semicolon", 40: "quote",
    41: "grave", 42: "lshift", 43: "backslash", **{44 + i: c for i, c in enumerate("zxcvbnm")},
    51: "comma", 52: "period", 53: "slash", 54: "rshift", 56: "lalt", 57: "space",
    58: "capslock", **{59 + i: f"f{i + 1}" for i in range(10)}, 70: "scrolllock",
    86: "iso_backslash", 87: "f11", 88: "f12", 97: "rctrl", 99: "printscreen", 100: "ralt",
    102: "home", 103: "up", 104: "pgup", 105: "left", 106: "right", 107: "end",
    108: "down", 109: "pgdn", 110: "insert", 111: "delete", 119: "pause",
    125: "lwin", 126: "rwin", 127: "menu",
}
GDK_KEYCODES = {code + 8: name for code, name in EVDEV.items()}  # X11 keycode = Linux key code + 8


def key_name(event) -> str | None:
    """Key name (as in keymap.HID / macros.MOD_CODES) of a GTK key event, by position."""
    return GDK_KEYCODES.get(event.hardware_keycode)
