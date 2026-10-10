"""Linux backend: the keyboard through /dev/hidraw*.

No extra libraries: plain os.read/os.write on the hidraw node, device info
from /sys. Access requires the udev rule in udev/70-aula-f75.rules.
"""

import glob
import os
import select
import subprocess
import time

from ..errors import AulaError
from .base import (PRODUCT_WIRED, PRODUCTS, VENDOR_WIRED, VENDOR_WIRELESS, Channel, KeyGuard,
                   NoKeyGuard)

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
            found.append({"path": node, "mode": "wired", "supported": False,
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


class LinuxKeyGuard(KeyGuard):
    """Watches the keyboard's normal key reports on its other hidraw nodes."""

    def __init__(self, path: str, bluetooth: bool):
        self.bluetooth = bluetooth
        self._key_fds = []
        for node in _sibling_nodes(path):
            try:
                self._key_fds.append(os.open(node, os.O_RDONLY | os.O_NONBLOCK))
            except OSError:
                pass
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
                    state = _keys_down(os.read(fd, 64), self.bluetooth)
                except BlockingIOError:
                    continue
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


def open_device(path: str, mode: str) -> tuple[Channel, KeyGuard]:
    channel = LinuxChannel(path)
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
