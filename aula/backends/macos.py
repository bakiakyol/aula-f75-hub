"""macOS backend: the keyboard through hidapi (`pip install hidapi`).

hidapi lists every top-level collection of a device separately, so the
configuration channel is the entry with Usage Page 0xFF02 / Usage 2. The key
collections are the system's, so the key-release guard asks Quartz
(CGEventSourceKeyState) whether a key is down instead.
"""

import ctypes
import subprocess
import time

from ..errors import AulaError
from .base import (PRODUCT_WIRED, PRODUCTS, VENDOR_USAGE, VENDOR_USAGE_PAGE, VENDOR_WIRED,
                   VENDOR_WIRELESS, Channel, KeyGuard, NoKeyGuard)


def _hid():
    try:
        import hid
    except ImportError:
        raise AulaError("the 'hidapi' Python package is missing: run install-macos.sh, "
                        "or pip install hidapi") from None
    return hid


# ------------------------------------------------------------ discovery
def pick_devices(entries: list[dict]) -> list[dict]:
    """hid.enumerate() entries -> find_devices() results: the configuration channel
    of each wireless F75, and a wired one (unsupported) once."""
    found, wired = [], False
    for e in entries:
        vid, pid = e["vendor_id"], e["product_id"]
        path = e["path"].decode() if isinstance(e["path"], bytes) else e["path"]
        name = e.get("product_string") or ""
        if (vid, pid) == (VENDOR_WIRED, PRODUCT_WIRED):
            if not wired:
                found.append({"path": path, "mode": "wired", "supported": False, "name": name})
                wired = True
        elif vid == VENDOR_WIRELESS and pid in PRODUCTS and \
                (e["usage_page"], e["usage"]) == (VENDOR_USAGE_PAGE, VENDOR_USAGE):
            found.append({"path": path, "mode": PRODUCTS[pid], "supported": True, "name": name})
    return found


def find_devices() -> list[dict]:
    hid = _hid()
    return pick_devices(hid.enumerate(VENDOR_WIRELESS) + hid.enumerate(VENDOR_WIRED, PRODUCT_WIRED))


# ------------------------------------------------------------ channel
def open_shared(hid) -> None:
    """Make hidapi open devices shared instead of seized.

    On macOS hidapi seizes every device it opens (kIOHIDOptionsTypeSeizeDevice),
    and macOS refuses to let a normal program seize a keyboard, so every open
    failed. The setter is in hidapi 0.12+; the key reports that a shared open
    also delivers are dropped by protocol.parse_packet (wrong report id).
    """
    try:
        ctypes.CDLL(hid.__file__).hid_darwin_set_open_exclusive(0)
    except (OSError, AttributeError):
        pass


class MacChannel(Channel):
    def __init__(self, path: str):
        hid = _hid()
        open_shared(hid)
        self.dev = hid.device()
        try:
            self.dev.open_path(path.encode())
        except OSError:
            raise AulaError("cannot open the keyboard. Close the official AULA app if it runs; "
                            "if it still fails, allow your terminal (or AULA F75) under System "
                            "Settings > Privacy & Security > Input Monitoring") from None

    def write(self, pkt: bytes) -> None:
        try:
            n = self.dev.write(bytes(pkt))
        except OSError as e:
            raise AulaError(f"writing to the keyboard failed ({e})") from None
        if n < 0:
            raise AulaError("writing to the keyboard failed")

    def recv(self, timeout: float) -> bytes | None:
        try:
            data = self.dev.read(64, max(1, int(timeout * 1000)))
        except OSError as e:
            raise AulaError(f"reading from the keyboard failed ({e})") from None
        return bytes(data) if data else None

    def close(self) -> None:
        self.dev.close()


# ------------------------------------------------------------ key guard
HID_SYSTEM_STATE = 1  # kCGEventSourceStateHIDSystemState: the hardware's own key state
# Virtual key codes 0-126, without Caps Lock (its state may read as its lock) and Fn
GUARD_KEYCODES = [kc for kc in range(0x7F) if kc not in (0x39, 0x3F)]


def _quartz():
    lib = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
    lib.CGEventSourceKeyState.restype = ctypes.c_bool
    lib.CGEventSourceKeyState.argtypes = [ctypes.c_int32, ctypes.c_uint16]
    return lib


class MacKeyGuard(KeyGuard):
    def __init__(self):
        self.quartz = _quartz()
        self._last_down = time.monotonic()

    def _any_down(self) -> bool:
        state = self.quartz.CGEventSourceKeyState
        return any(state(HID_SYSTEM_STATE, kc) for kc in GUARD_KEYCODES)

    def wait_released(self, quiet: float = 0.4, limit: float = 5.0) -> None:
        start = time.monotonic()
        while True:
            now = time.monotonic()
            if self._any_down():
                self._last_down = now
            elif now - self._last_down >= quiet:
                return
            if now - start > limit:
                raise AulaError("a key seems to be held down; release all keys and try again")
            time.sleep(0.02)


def open_device(path: str, mode: str) -> tuple[Channel, KeyGuard]:
    channel = MacChannel(path)
    try:
        guard = MacKeyGuard()
    except (OSError, AttributeError):
        guard = NoKeyGuard()
    return channel, guard


# ------------------------------------------------------------ layout
def layout_from_source_id(source: str) -> str:
    """Input source id (e.g. com.apple.keylayout.Turkish-QWERTY-PC) -> macros layout name.

    Apple's "Turkish Q - PC" matches the PC layout except for the AltGr level;
    Apple's own "Turkish Q" has the Turkish letters in the same places but other
    punctuation. Turkish F ("Turkish", "Turkish-Standard") isn't supported.
    """
    name = source.rsplit(".", 1)[-1]
    return {"Turkish-QWERTY-PC": "tr_mac_pc", "Turkish-QWERTY": "tr_mac"}.get(name, "us")


def detect_layout() -> str:
    try:
        out = subprocess.run(["defaults", "read", "com.apple.HIToolbox",
                              "AppleCurrentKeyboardLayoutInputSourceID"],
                             capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return "us"
    return layout_from_source_id(out.strip())


# ------------------------------------------------------------ recording
# GTK's hardware_keycode on macOS is the virtual key code (kVK_*), which names
# the key's position on an ANSI keyboard.
KEYCODES = {
    0x00: "a", 0x01: "s", 0x02: "d", 0x03: "f", 0x04: "h", 0x05: "g", 0x06: "z", 0x07: "x",
    0x08: "c", 0x09: "v", 0x0A: "iso_backslash", 0x0B: "b", 0x0C: "q", 0x0D: "w", 0x0E: "e",
    0x0F: "r", 0x10: "y", 0x11: "t", 0x12: "1", 0x13: "2", 0x14: "3", 0x15: "4", 0x16: "6",
    0x17: "5", 0x18: "equal", 0x19: "9", 0x1A: "7", 0x1B: "minus", 0x1C: "8", 0x1D: "0",
    0x1E: "rbracket", 0x1F: "o", 0x20: "u", 0x21: "lbracket", 0x22: "i", 0x23: "p",
    0x24: "enter", 0x25: "l", 0x26: "j", 0x27: "quote", 0x28: "k", 0x29: "semicolon",
    0x2A: "backslash", 0x2B: "comma", 0x2C: "slash", 0x2D: "n", 0x2E: "m", 0x2F: "period",
    0x30: "tab", 0x31: "space", 0x32: "grave", 0x33: "backspace", 0x35: "esc",
    0x36: "rwin", 0x37: "lwin", 0x38: "lshift", 0x39: "capslock", 0x3A: "lalt", 0x3B: "lctrl",
    0x3C: "rshift", 0x3D: "ralt", 0x3E: "rctrl",
    0x60: "f5", 0x61: "f6", 0x62: "f7", 0x63: "f3", 0x64: "f8", 0x65: "f9", 0x67: "f11",
    0x69: "printscreen", 0x6B: "scrolllock", 0x6D: "f10", 0x6E: "menu", 0x6F: "f12",
    0x71: "pause", 0x72: "insert", 0x73: "home", 0x74: "pgup", 0x75: "delete", 0x76: "f4",
    0x77: "end", 0x78: "f2", 0x79: "pgdn", 0x7A: "f1", 0x7B: "left", 0x7C: "right",
    0x7D: "down", 0x7E: "up",
}


def key_name(event) -> str | None:
    return KEYCODES.get(event.hardware_keycode)
