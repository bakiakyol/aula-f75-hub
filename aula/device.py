"""Finding and talking to the AULA F75 through /dev/hidraw*.

No extra libraries: plain os.read/os.write on the Linux hidraw node.
Access requires the udev rule in udev/70-aula-f75.rules.
"""

import glob
import os
import select
import time

from . import protocol as P

VENDOR_WIRELESS = 0x3554
PRODUCTS = {0xFA09: "2.4G dongle", 0xFA07: "Bluetooth"}
VENDOR_WIRED = 0x258A
PRODUCT_WIRED = 0x010C

# Report descriptor fragment: Usage Page 0xFF02, Usage 2, Collection, Report ID 0x13
_VENDOR_CHANNEL = bytes([0x06, 0x02, 0xFF, 0x09, 0x02, 0xA1, 0x01, 0x85, 0x13])


class AulaError(Exception):
    pass


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


def _keys_down(report: bytes) -> bool | None:
    """True/False if the report is a keyboard state report, None otherwise."""
    if len(report) == 8:                       # boot keyboard: [mods, 0, key x5, vendor]
        return bool(report[0] or any(report[2:7]))
    if report and report[0] == 0x04:           # NKRO bitmap report (id 4)
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


class Keyboard:
    def __init__(self, path: str | None = None, timeout: float = 1.0):
        if path is None:
            devs = [d for d in find_devices() if d["supported"]]
            if not devs:
                if any(not d["supported"] for d in find_devices()):
                    raise AulaError("The keyboard is connected by cable. Wired mode is not "
                                    "supported yet; use the 2.4G dongle or Bluetooth.")
                raise AulaError("AULA F75 not found (is the dongle plugged in and the keyboard on?)")
            path = devs[0]["path"]
            self.mode = devs[0]["mode"]
        else:
            self.mode = "?"
        self.path = path
        self.timeout = timeout
        try:
            self.fd = os.open(path, os.O_RDWR)
        except PermissionError:
            raise AulaError(f"cannot open {path}: permission denied. "
                            "Is the udev rule installed? (see README)")
        # Watch the keyboard's normal key reports so we never talk to it while a key
        # is held (see wait_keys_released).
        self._key_fds = []
        for node in _sibling_nodes(path):
            try:
                self._key_fds.append(os.open(node, os.O_RDONLY | os.O_NONBLOCK))
            except OSError:
                pass
        self._held: dict[int, bool] = {}
        self._last_key_event = time.monotonic()

    def close(self) -> None:
        for fd in self._key_fds:
            os.close(fd)
        os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------ low level
    def wait_keys_released(self, quiet: float = 0.4, limit: float = 5.0) -> None:
        """Block until no key is held and the keyboard has been idle for `quiet` seconds.

        While the keyboard is busy with configuration traffic it can drop a key
        release report, and the OS then auto-repeats that key forever (e.g. the
        Enter used to launch this command). Returns at once if nothing was typed
        since the last call.
        """
        if not self._key_fds:
            time.sleep(quiet)
            return
        start = time.monotonic()
        while True:
            for fd in select.select(self._key_fds, [], [], 0.05)[0]:
                try:
                    state = _keys_down(os.read(fd, 64))
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

    def _drain(self) -> None:
        while select.select([self.fd], [], [], 0.02)[0]:
            os.read(self.fd, 64)

    def _recv(self, timeout: float) -> bytes | None:
        if select.select([self.fd], [], [], timeout)[0]:
            return os.read(self.fd, 64)
        return None

    def read(self, cmd: int, sub: int = 0, retries: int = 3) -> bytes:
        """Send a read command and reassemble the multi-packet reply by index."""
        rcmd = cmd | P.READ
        for _ in range(retries):
            self.wait_keys_released()
            self._drain()
            os.write(self.fd, P.read_request(cmd, sub))
            parts: dict[int, bytes] = {}
            total = None
            deadline = time.monotonic() + 2 * self.timeout
            while time.monotonic() < deadline:
                r = self._recv(0.3)
                rep = P.parse_packet(r) if r else None
                if rep is None or rep.cmd != rcmd:
                    continue
                if rep.error:
                    raise AulaError(f"keyboard rejected read 0x{rcmd:02x}")
                total = rep.total
                parts[rep.index] = rep.data
                if len(parts) == total:
                    return b"".join(parts[i] for i in range(total))
        raise AulaError("the keyboard didn't answer. It may be asleep: press any key "
                        "to wake it, then try again")

    def write(self, cmd: int, data: bytes, sub: int = 0, retries: int = 3) -> None:
        """Write data in 14-byte packets; the keyboard echoes each one back as an ack."""
        self.wait_keys_released()
        self._drain()
        for pkt in P.split_packets(cmd, sub, data):
            for _ in range(retries):
                os.write(self.fd, pkt)
                if self._wait_ack(pkt):
                    break
            else:
                raise AulaError(f"write 0x{cmd:02x} not acknowledged (packet {pkt[3]})")
            time.sleep(0.015)

    def _wait_ack(self, pkt: bytes) -> bool:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            r = self._recv(0.3)
            if not r:
                continue
            rep = P.parse_packet(r)
            if rep is None or rep.cmd != pkt[1] or rep.index != pkt[3]:
                continue
            if rep.error:
                raise AulaError(f"keyboard rejected command 0x{pkt[1]:02x}")
            return True
        return False

    # ----------------------------------------------------------- high level
    def get_led(self) -> P.LedConfig:
        return P.LedConfig(self.read(P.CMD_SET_LED))

    def set_led(self, cfg: P.LedConfig) -> None:
        self.write(P.CMD_SET_LED, cfg.to_bytes())

    def get_custom(self) -> bytes:
        return self.read(P.CMD_SET_CUSTOM)

    def set_custom(self, raw: bytes) -> None:
        if len(raw) != P.CUSTOM_LEN:
            raise ValueError("per-key color table must be 378 bytes")
        self.write(P.CMD_SET_CUSTOM, raw)

    def get_matrix(self, layer: int = 0) -> bytes:
        return self.read(P.CMD_SET_MATRIX, layer)

    def set_matrix(self, raw: bytes, layer: int = 0) -> None:
        if len(raw) != P.MATRIX_BYTES:
            raise ValueError("keymap must be 504 bytes")
        self.write(P.CMD_SET_MATRIX, raw, layer)

    def get_battery(self) -> int | None:
        """Battery percentage (experimental: first byte of the 0x4a reply).

        Read 100 while the keyboard's own Fn+B gauge showed 10/10; needs to be
        confirmed at a lower charge.
        """
        data = self.read(P.CMD_PROFILE)
        return data[0] if data and data[0] <= 100 else None

    def get_palette(self) -> bytes:
        return self.read(P.CMD_SET_PALETTE)

    def set_palette(self, raw: bytes) -> None:
        self.write(P.CMD_SET_PALETTE, raw)
