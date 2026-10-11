"""What every platform backend provides.

A backend finds the keyboard's configuration channel, opens it as a Channel
(raw 20-byte reports in and out) and gives a KeyGuard that can tell when no
key is held. Everything above that (packets, retries, acks) lives in
aula.device.Keyboard and is the same on every platform.

Device entries returned by find_devices() are dicts:
    {"path": str, "mode": "2.4G dongle" | "Bluetooth" | "wired",
     "supported": bool, "name": str}
"""

import collections
import time

VENDOR_WIRELESS = 0x3554
PRODUCTS = {0xFA09: "2.4G dongle", 0xFA07: "Bluetooth"}
VENDOR_WIRED = 0x258A
PRODUCT_WIRED = 0x010C
# The configuration channel: Usage Page 0xFF02, Usage 2, report id 0x13
VENDOR_USAGE_PAGE = 0xFF02
VENDOR_USAGE = 0x02


MODIFIER_USAGE = 0xE0   # HID usage of left Ctrl; the 8 modifier bits are usages 0xE0-0xE7


def keys_in_report(report: bytes, bluetooth: bool = False) -> frozenset[int] | None:
    """The HID usages a keyboard report holds down, or None if it isn't one.

    2.4G dongle: the boot keyboard interface sends 8-byte reports without an id
    ([mods, 0, key x5, vendor]); the NKRO bitmap is report 4 (bit n = usage n,
    0x00-0x9F per its report descriptor; modifiers only come in the boot report).
    Bluetooth: everything arrives on one node; the keyboard report is id 1
    ([1, mods, 0, key x5, vendor]) and the NKRO bitmap is id 2. (Id 4 is system
    control there, so it must not be read as keys.) Usages 1-3 are error codes:
    after every key release the board sends three ErrorRollOver (1) reports.
    """
    if not report:
        return None
    if bluetooth:
        if report[0] == 0x01 and len(report) >= 8:
            return _boot_keys(report[1], report[3:8])
        if report[0] == 0x02:
            return _bitmap_keys(report[1:])
        return None
    if len(report) == 8:
        return _boot_keys(report[0], report[2:7])
    if report[0] == 0x04:
        return _bitmap_keys(report[1:])
    return None


def _boot_keys(mods: int, keys: bytes) -> frozenset[int]:
    return frozenset({MODIFIER_USAGE + b for b in range(8) if mods >> b & 1} | {k for k in keys if k > 3})


def _bitmap_keys(bits: bytes) -> frozenset[int]:
    return frozenset(i * 8 + b for i, byte in enumerate(bits) for b in range(8)
                     if byte >> b & 1 and i * 8 + b > 3)


class KeyTracker:
    """Turns the keyboard's reports into key presses.

    The board reports its keys in more than one report (boot interface and NKRO
    bitmap), so a key is held while any source holds it, and pressed when it
    becomes held.
    """

    def __init__(self):
        self._held: dict[object, frozenset[int]] = {}
        self._presses: collections.deque[int] = collections.deque(maxlen=64)

    def feed(self, source, keys: frozenset[int]) -> None:
        """The keys one source (a node and report kind) holds now."""
        before = self.held()
        self._held[source] = keys
        self._presses.extend(sorted(self.held() - before))

    def held(self) -> frozenset[int]:
        return frozenset().union(*self._held.values())

    def take_presses(self) -> list[int]:
        """HID usages pressed since the last call, oldest first."""
        out = list(self._presses)
        self._presses.clear()
        return out


class Channel:
    """The open configuration channel."""

    def write(self, pkt: bytes) -> None:
        """Send one 20-byte report (report id 0x13 first)."""
        raise NotImplementedError

    def recv(self, timeout: float) -> bytes | None:
        """One incoming report, or None if nothing came within `timeout` seconds."""
        raise NotImplementedError

    def drain(self) -> None:
        """Throw away whatever is waiting to be read."""
        while self.recv(0.02) is not None:
            pass

    def close(self) -> None:
        pass


class KeyGuard:
    """Knows whether a key on the keyboard is held down.

    While the keyboard is busy with configuration traffic it can drop a key
    release report, and the OS then auto-repeats that key forever. So the
    keyboard is only talked to while no key is held.
    """

    def wait_released(self, quiet: float = 0.4, limit: float = 5.0) -> None:
        """Block until no key is held and none has been for `quiet` seconds;
        raise AulaError after `limit` seconds."""
        raise NotImplementedError

    def presses(self) -> list[int]:
        """HID usages of the keys pressed since the last call (none if unknown)."""
        return []

    def close(self) -> None:
        pass


class NoKeyGuard(KeyGuard):
    """Fallback when key state can't be read: just leave a short pause."""

    def wait_released(self, quiet: float = 0.4, limit: float = 5.0) -> None:
        time.sleep(quiet)
