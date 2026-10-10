"""Windows backend: the keyboard through the Windows HID API.

No packages needed: hid.dll, setupapi.dll and kernel32.dll through ctypes, so
it works with the python.org Python as well as MSYS2's (for the GUI).

Windows gives every top-level collection of a HID device its own path, so the
configuration channel (Usage Page 0xFF02, Usage 2) is picked by its caps. The
keyboard's own key collections can't be opened (Windows keeps them), so the
key-release guard asks GetAsyncKeyState instead.
"""

import ctypes
import time
from ctypes import wintypes

from ..errors import AulaError
from .base import (PRODUCT_WIRED, PRODUCTS, VENDOR_USAGE, VENDOR_USAGE_PAGE, VENDOR_WIRED,
                   VENDOR_WIRELESS, Channel, KeyGuard)

# ------------------------------------------------------------ Win32 bits
GENERIC_READ, GENERIC_WRITE = 0x80000000, 0x40000000
FILE_SHARE_READ, FILE_SHARE_WRITE = 0x1, 0x2
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
DIGCF_PRESENT, DIGCF_DEVICEINTERFACE = 0x2, 0x10
ERROR_ACCESS_DENIED, ERROR_IO_PENDING = 5, 997
WAIT_OBJECT_0, WAIT_TIMEOUT = 0, 0x102
HIDP_STATUS_SUCCESS = 0x00110000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("InterfaceClassGuid", GUID),
                ("Flags", wintypes.DWORD), ("Reserved", ctypes.c_void_p)]


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Size", wintypes.ULONG), ("VendorID", wintypes.USHORT),
                ("ProductID", wintypes.USHORT), ("VersionNumber", wintypes.USHORT)]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [("Usage", wintypes.USHORT), ("UsagePage", wintypes.USHORT),
                ("InputReportByteLength", wintypes.USHORT),
                ("OutputReportByteLength", wintypes.USHORT),
                ("FeatureReportByteLength", wintypes.USHORT),
                ("Reserved", wintypes.USHORT * 17),
                ("NumberLinkCollectionNodes", wintypes.USHORT),
                ("NumberInputButtonCaps", wintypes.USHORT),
                ("NumberInputValueCaps", wintypes.USHORT),
                ("NumberInputDataIndices", wintypes.USHORT),
                ("NumberOutputButtonCaps", wintypes.USHORT),
                ("NumberOutputValueCaps", wintypes.USHORT),
                ("NumberOutputDataIndices", wintypes.USHORT),
                ("NumberFeatureButtonCaps", wintypes.USHORT),
                ("NumberFeatureValueCaps", wintypes.USHORT),
                ("NumberFeatureDataIndices", wintypes.USHORT)]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD),
                ("hEvent", wintypes.HANDLE)]


_dlls = None


def _api():
    """Load the DLLs on first use (this module is imported by tests on any OS)."""
    global _dlls
    if _dlls is not None:
        return _dlls
    hid = ctypes.WinDLL("hid")
    setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32 = ctypes.WinDLL("user32")
    H, B, P, D = wintypes.HANDLE, wintypes.BOOL, ctypes.c_void_p, wintypes.DWORD
    sigs = [
        (hid.HidD_GetHidGuid, None, [ctypes.POINTER(GUID)]),
        (hid.HidD_GetAttributes, wintypes.BOOLEAN, [H, ctypes.POINTER(HIDD_ATTRIBUTES)]),
        (hid.HidD_GetPreparsedData, wintypes.BOOLEAN, [H, ctypes.POINTER(P)]),
        (hid.HidD_FreePreparsedData, wintypes.BOOLEAN, [P]),
        (hid.HidD_GetProductString, wintypes.BOOLEAN, [H, P, wintypes.ULONG]),
        (hid.HidP_GetCaps, wintypes.LONG, [P, ctypes.POINTER(HIDP_CAPS)]),
        (setupapi.SetupDiGetClassDevsW, H, [ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, D]),
        (setupapi.SetupDiEnumDeviceInterfaces, B,
         [H, P, ctypes.POINTER(GUID), D, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)]),
        (setupapi.SetupDiGetDeviceInterfaceDetailW, B,
         [H, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA), P, D, ctypes.POINTER(D), P]),
        (setupapi.SetupDiDestroyDeviceInfoList, B, [H]),
        (kernel32.CreateFileW, H, [wintypes.LPCWSTR, D, D, P, D, D, H]),
        (kernel32.CloseHandle, B, [H]),
        (kernel32.CreateEventW, H, [P, B, B, wintypes.LPCWSTR]),
        (kernel32.ResetEvent, B, [H]),
        (kernel32.ReadFile, B, [H, P, D, ctypes.POINTER(D), ctypes.POINTER(OVERLAPPED)]),
        (kernel32.WriteFile, B, [H, P, D, ctypes.POINTER(D), ctypes.POINTER(OVERLAPPED)]),
        (kernel32.GetOverlappedResult, B, [H, ctypes.POINTER(OVERLAPPED), ctypes.POINTER(D), B]),
        (kernel32.WaitForSingleObject, D, [H, D]),
        (kernel32.CancelIo, B, [H]),
        (user32.GetAsyncKeyState, ctypes.c_short, [ctypes.c_int]),
        (user32.GetKeyboardLayoutNameW, B, [wintypes.LPWSTR]),
    ]
    for fn, res, args in sigs:
        fn.restype, fn.argtypes = res, args
    _dlls = type("Win32", (), {"hid": hid, "setupapi": setupapi, "kernel32": kernel32,
                               "user32": user32})
    return _dlls


def _last_error() -> int:
    return ctypes.get_last_error()


# ------------------------------------------------------------ discovery
def _interface_paths() -> list[str]:
    """Device paths of every HID collection present."""
    api = _api()
    guid = GUID()
    api.hid.HidD_GetHidGuid(ctypes.byref(guid))
    info = api.setupapi.SetupDiGetClassDevsW(ctypes.byref(guid), None, None,
                                             DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if info in (None, INVALID_HANDLE_VALUE):
        return []
    paths = []
    try:
        index = 0
        while True:
            iface = SP_DEVICE_INTERFACE_DATA(cbSize=ctypes.sizeof(SP_DEVICE_INTERFACE_DATA))
            if not api.setupapi.SetupDiEnumDeviceInterfaces(info, None, ctypes.byref(guid), index,
                                                            ctypes.byref(iface)):
                break  # no more interfaces
            index += 1
            need = wintypes.DWORD()
            api.setupapi.SetupDiGetDeviceInterfaceDetailW(info, ctypes.byref(iface), None, 0,
                                                          ctypes.byref(need), None)
            if not need.value:
                continue
            buf = ctypes.create_string_buffer(need.value)
            # SP_DEVICE_INTERFACE_DETAIL_DATA_W: DWORD cbSize, then the path. cbSize is the
            # size of the fixed struct: 8 on 64-bit (padding), 6 on 32-bit.
            ctypes.c_uint32.from_buffer(buf).value = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            if api.setupapi.SetupDiGetDeviceInterfaceDetailW(info, ctypes.byref(iface), buf,
                                                             need, None, None):
                paths.append(ctypes.wstring_at(ctypes.addressof(buf) + 4))
    finally:
        api.setupapi.SetupDiDestroyDeviceInfoList(info)
    return paths


def _open(path: str, access: int, flags: int = 0) -> int | None:
    h = _api().kernel32.CreateFileW(path, access, FILE_SHARE_READ | FILE_SHARE_WRITE, None,
                                    OPEN_EXISTING, flags, None)
    return None if h in (None, INVALID_HANDLE_VALUE) else h


def _caps(handle: int) -> HIDP_CAPS | None:
    api = _api()
    pp = ctypes.c_void_p()
    if not api.hid.HidD_GetPreparsedData(handle, ctypes.byref(pp)):
        return None
    try:
        caps = HIDP_CAPS()
        if api.hid.HidP_GetCaps(pp, ctypes.byref(caps)) != HIDP_STATUS_SUCCESS:
            return None
        return caps
    finally:
        api.hid.HidD_FreePreparsedData(pp)


def _describe(path: str) -> dict | None:
    """Vendor/product id, usage and name of one collection. It is opened without
    read/write access, which works even for collections Windows keeps for itself."""
    api = _api()
    h = _open(path, 0)
    if h is None:
        return None
    try:
        attrs = HIDD_ATTRIBUTES(Size=ctypes.sizeof(HIDD_ATTRIBUTES))
        if not api.hid.HidD_GetAttributes(h, ctypes.byref(attrs)):
            return None
        entry = {"path": path, "vendor_id": attrs.VendorID, "product_id": attrs.ProductID,
                 "usage_page": 0, "usage": 0, "name": ""}
        if attrs.VendorID in (VENDOR_WIRELESS, VENDOR_WIRED):
            caps = _caps(h)
            if caps is not None:
                entry["usage_page"], entry["usage"] = caps.UsagePage, caps.Usage
            name = ctypes.create_unicode_buffer(128)
            if api.hid.HidD_GetProductString(h, name, ctypes.sizeof(name)):
                entry["name"] = name.value
        return entry
    finally:
        api.kernel32.CloseHandle(h)


def pick_devices(entries: list[dict]) -> list[dict]:
    """Turn raw collection entries into find_devices() results: the configuration
    channel of each wireless F75, and a wired one (unsupported) once."""
    found, wired = [], False
    for e in entries:
        vid, pid = e["vendor_id"], e["product_id"]
        if (vid, pid) == (VENDOR_WIRED, PRODUCT_WIRED):
            if not wired:
                found.append({"path": e["path"], "mode": "wired", "supported": False,
                              "name": e["name"]})
                wired = True
        elif vid == VENDOR_WIRELESS and pid in PRODUCTS and \
                (e["usage_page"], e["usage"]) == (VENDOR_USAGE_PAGE, VENDOR_USAGE):
            found.append({"path": e["path"], "mode": PRODUCTS[pid], "supported": True,
                          "name": e["name"]})
    return found


def find_devices() -> list[dict]:
    return pick_devices([e for e in map(_describe, _interface_paths()) if e is not None])


# ------------------------------------------------------------ channel
class WindowsChannel(Channel):
    """Overlapped reads and writes on the collection's handle. A read that times
    out stays pending and is picked up by the next recv()."""

    def __init__(self, path: str):
        api = self.api = _api()
        h = _open(path, GENERIC_READ | GENERIC_WRITE, FILE_FLAG_OVERLAPPED)
        if h is None:
            err = _last_error()
            if err == ERROR_ACCESS_DENIED:
                raise AulaError("cannot open the keyboard: access denied. Close the official "
                                "AULA app (and other keyboard tools) and try again")
            raise AulaError(f"cannot open the keyboard (Windows error {err})")
        self.h = h
        caps = _caps(h)
        self.in_len = caps.InputReportByteLength if caps else 64
        self.out_len = caps.OutputReportByteLength if caps else 20
        self._rd_ev = api.kernel32.CreateEventW(None, True, False, None)
        self._wr_ev = api.kernel32.CreateEventW(None, True, False, None)
        self._rd_ov = OVERLAPPED(hEvent=self._rd_ev)
        self._rd_buf = ctypes.create_string_buffer(max(self.in_len, 1))
        self._pending = False

    def write(self, pkt: bytes) -> None:
        k = self.api.kernel32
        # Windows wants exactly the collection's output report length
        data = bytes(pkt)[:self.out_len].ljust(self.out_len, b"\0")
        buf = ctypes.create_string_buffer(data, len(data))
        k.ResetEvent(self._wr_ev)
        ov = OVERLAPPED(hEvent=self._wr_ev)
        if not k.WriteFile(self.h, buf, len(data), None, ctypes.byref(ov)):
            err = _last_error()
            if err != ERROR_IO_PENDING:
                raise AulaError(f"writing to the keyboard failed (Windows error {err})")
        if k.WaitForSingleObject(self._wr_ev, 1000) != WAIT_OBJECT_0:
            k.CancelIo(self.h)
            raise AulaError("writing to the keyboard timed out")
        done = wintypes.DWORD()
        if not k.GetOverlappedResult(self.h, ctypes.byref(ov), ctypes.byref(done), False):
            raise AulaError(f"writing to the keyboard failed (Windows error {_last_error()})")

    def recv(self, timeout: float) -> bytes | None:
        k = self.api.kernel32
        if not self._pending:
            k.ResetEvent(self._rd_ev)
            self._rd_ov = OVERLAPPED(hEvent=self._rd_ev)
            if not k.ReadFile(self.h, self._rd_buf, self.in_len, None, ctypes.byref(self._rd_ov)):
                err = _last_error()
                if err != ERROR_IO_PENDING:
                    raise AulaError(f"reading from the keyboard failed (Windows error {err})")
            self._pending = True
        if k.WaitForSingleObject(self._rd_ev, max(0, int(timeout * 1000))) == WAIT_TIMEOUT:
            return None
        self._pending = False
        got = wintypes.DWORD()
        if not k.GetOverlappedResult(self.h, ctypes.byref(self._rd_ov), ctypes.byref(got), False):
            raise AulaError(f"reading from the keyboard failed (Windows error {_last_error()})")
        return self._rd_buf.raw[:got.value]

    def close(self) -> None:
        k = self.api.kernel32
        if self._pending:
            k.CancelIo(self.h)
            got = wintypes.DWORD()
            k.GetOverlappedResult(self.h, ctypes.byref(self._rd_ov), ctypes.byref(got), True)
        for h in (self._rd_ev, self._wr_ev, self.h):
            k.CloseHandle(h)


# ------------------------------------------------------------ key guard
# Virtual keys to watch: everything but mouse buttons (a GUI click holds one)
# and the pseudo keys IME and packet input use.
GUARD_VKS = [vk for vk in range(0x08, 0xFF) if vk not in (0xE5, 0xE7)]


class WindowsKeyGuard(KeyGuard):
    def __init__(self):
        self.user32 = _api().user32
        self._last_down = time.monotonic()

    def _any_down(self) -> bool:
        state = self.user32.GetAsyncKeyState
        return any(state(vk) & 0x8000 for vk in GUARD_VKS)

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
    return WindowsChannel(path), WindowsKeyGuard()


# ------------------------------------------------------------ layout
def layout_from_klid(klid: str) -> str:
    """Keyboard layout id (e.g. '0000041F') -> macros layout name."""
    return "tr" if klid.upper() == "0000041F" else "us"  # 0001041F is Turkish F


def detect_layout() -> str:
    try:
        buf = ctypes.create_unicode_buffer(9)
        if _api().user32.GetKeyboardLayoutNameW(buf):
            return layout_from_klid(buf.value)
    except (OSError, AttributeError):
        pass
    return "us"


# ------------------------------------------------------------ recording
# PC "set 1" scan codes. Keys sent with an E0 prefix have bit 8 set, as in the
# high word of WM_KEYDOWN's lParam that GTK hands out as the scan code.
SCANCODES = {
    0x01: "esc", **{0x02 + i: str((i + 1) % 10) for i in range(10)}, 0x0C: "minus",
    0x0D: "equal", 0x0E: "backspace", 0x0F: "tab",
    **{0x10 + i: c for i, c in enumerate("qwertyuiop")}, 0x1A: "lbracket", 0x1B: "rbracket",
    0x1C: "enter", 0x1D: "lctrl", **{0x1E + i: c for i, c in enumerate("asdfghjkl")},
    0x27: "semicolon", 0x28: "quote", 0x29: "grave", 0x2A: "lshift", 0x2B: "backslash",
    **{0x2C + i: c for i, c in enumerate("zxcvbnm")}, 0x33: "comma", 0x34: "period",
    0x35: "slash", 0x36: "rshift", 0x38: "lalt", 0x39: "space", 0x3A: "capslock",
    **{0x3B + i: f"f{i + 1}" for i in range(10)}, 0x45: "pause", 0x46: "scrolllock",
    0x56: "iso_backslash", 0x57: "f11", 0x58: "f12",
    0x11D: "rctrl", 0x137: "printscreen", 0x138: "ralt", 0x147: "home", 0x148: "up",
    0x149: "pgup", 0x14B: "left", 0x14D: "right", 0x14F: "end", 0x150: "down", 0x151: "pgdn",
    0x152: "insert", 0x153: "delete", 0x15B: "lwin", 0x15C: "rwin", 0x15D: "menu",
}
# Virtual keys, only when GTK gives no scan code. Punctuation keys move with the
# layout, so they are left out.
VK_FALLBACK = {
    0x08: "backspace", 0x09: "tab", 0x0D: "enter", 0x10: "lshift", 0x11: "lctrl", 0x12: "lalt",
    0x13: "pause", 0x14: "capslock", 0x1B: "esc", 0x20: "space", 0x21: "pgup", 0x22: "pgdn",
    0x23: "end", 0x24: "home", 0x25: "left", 0x26: "up", 0x27: "right", 0x28: "down",
    0x2C: "printscreen", 0x2D: "insert", 0x2E: "delete",
    **{0x30 + i: str(i) for i in range(10)}, **{0x41 + i: chr(0x61 + i) for i in range(26)},
    0x5B: "lwin", 0x5C: "rwin", 0x5D: "menu", **{0x70 + i: f"f{i + 1}" for i in range(12)},
    0x91: "scrolllock", 0xA0: "lshift", 0xA1: "rshift", 0xA2: "lctrl", 0xA3: "rctrl",
    0xA4: "lalt", 0xA5: "ralt",
}


def key_name(event) -> str | None:
    """Position of a GTK key event. On Windows GTK's hardware_keycode is the virtual
    key, which follows the layout, so the scan code is used instead."""
    try:
        scan = event.get_scancode() & 0x1FF  # higher bits: repeat / transition flags
    except (AttributeError, TypeError):
        scan = 0
    if scan:
        return SCANCODES.get(scan)
    return VK_FALLBACK.get(event.hardware_keycode)
