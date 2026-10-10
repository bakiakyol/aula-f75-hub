"""What every platform backend provides.

A backend finds the keyboard's configuration channel, opens it as a Channel
(raw 20-byte reports in and out) and gives a KeyGuard that can tell when no
key is held. Everything above that (packets, retries, acks) lives in
aula.device.Keyboard and is the same on every platform.

Device entries returned by find_devices() are dicts:
    {"path": str, "mode": "2.4G dongle" | "Bluetooth" | "wired",
     "supported": bool, "name": str}
"""

import time

VENDOR_WIRELESS = 0x3554
PRODUCTS = {0xFA09: "2.4G dongle", 0xFA07: "Bluetooth"}
VENDOR_WIRED = 0x258A
PRODUCT_WIRED = 0x010C
# The configuration channel: Usage Page 0xFF02, Usage 2, report id 0x13
VENDOR_USAGE_PAGE = 0xFF02
VENDOR_USAGE = 0x02


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

    def close(self) -> None:
        pass


class NoKeyGuard(KeyGuard):
    """Fallback when key state can't be read: just leave a short pause."""

    def wait_released(self, quiet: float = 0.4, limit: float = 5.0) -> None:
        time.sleep(quiet)
