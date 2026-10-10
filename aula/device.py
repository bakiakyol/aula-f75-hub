"""Talking to the AULA F75 over its configuration channel.

Packets, retries and acks live here and are the same on every platform; how
the channel is found and opened comes from aula.backends (hidraw on Linux).
"""

import random
import time

from . import protocol as P
from .backends import find_devices, open_device
from .errors import AulaError

__all__ = ["AulaError", "Keyboard", "find_devices"]


class Keyboard:
    def __init__(self, path: str | None = None, timeout: float = 1.0):
        self.timeout = timeout
        if path is not None:
            known = next((d for d in find_devices() if d["path"] == path), None)
            self._open(path, known["mode"] if known else "?")
            return
        devs = [d for d in find_devices() if d["supported"]]
        if not devs:
            if find_devices():
                raise AulaError("The keyboard is connected by cable. Wired mode is not "
                                "supported yet; use the 2.4G dongle or Bluetooth.")
            raise AulaError("AULA F75 not found (is the dongle plugged in and the keyboard on?)")
        if len(devs) == 1:
            self._open(devs[0]["path"], devs[0]["mode"])
            return
        # Several candidates (e.g. dongle plugged in while the keyboard is on Bluetooth):
        # use the one the keyboard actually answers on.
        for d in devs:
            self._open(d["path"], d["mode"])
            if self._probe():
                return
            self.close()
        raise AulaError("the keyboard didn't answer. It may be asleep: press any key "
                        "to wake it, then try again")

    def _open(self, path: str, mode: str) -> None:
        self.path = path
        self.mode = mode
        self.bluetooth = mode == "Bluetooth"
        # The guard watches the keyboard's normal key reports so we never talk to it
        # while a key is held (see wait_keys_released).
        self._ch, self._guard = open_device(path, mode)
        self._last_write = 0.0

    def _probe(self, timeout: float = 0.6) -> bool:
        """Quick single read: does the keyboard answer on this channel?"""
        self.wait_keys_released()
        self._drain()
        self._ch.write(P.read_request(P.CMD_PROFILE))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            r = self._recv(0.1)
            rep = P.parse_packet(r) if r else None
            if rep is not None and rep.cmd == P.CMD_PROFILE | P.READ:
                return True
        return False

    def close(self) -> None:
        self._guard.close()
        self._ch.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------ low level
    def wait_keys_released(self, quiet: float = 0.4, limit: float = 5.0) -> None:
        """Block until no key is held and the keyboard has been idle for `quiet` seconds.

        While the keyboard is busy with configuration traffic it can drop a key
        release report, and the OS then auto-repeats that key forever (e.g. the
        Enter used to launch this command).
        """
        self._guard.wait_released(quiet, limit)

    def _drain(self) -> None:
        self._ch.drain()

    def _recv(self, timeout: float) -> bytes | None:
        return self._ch.recv(timeout)

    def read(self, cmd: int, sub: int = 0, retries: int | None = None) -> bytes:
        """Send a read command and reassemble the multi-packet reply by index.

        Packets get lost (over Bluetooth roughly every other one after the first
        few, at random), and the keyboard always resends the whole reply. So the
        request is repeated and the parts are collected across attempts.
        """
        rcmd = cmd | P.READ
        if retries is None:
            retries = 15 if self.bluetooth else 4
        parts: dict[int, bytes] = {}
        total = None
        if self.bluetooth:  # right after a write the keyboard is busy saving
            settle = self._last_write + 0.5 - time.monotonic()
            if settle > 0:
                time.sleep(settle)
        for _ in range(retries):
            self.wait_keys_released()
            self._drain()
            if self.bluetooth:  # shift the burst against the radio's timing slots
                time.sleep(random.uniform(0, 0.05))
            self._ch.write(P.read_request(cmd, sub))
            deadline = time.monotonic() + 2 * self.timeout
            last = None
            while time.monotonic() < deadline:
                if last is not None and time.monotonic() - last > 0.25:
                    break  # this burst is over
                r = self._recv(0.05)
                rep = P.parse_packet(r) if r else None
                if rep is None or rep.cmd != rcmd:
                    continue
                if rep.error:
                    raise AulaError(f"keyboard rejected read 0x{rcmd:02x}")
                last = time.monotonic()
                total = rep.total
                if rep.index < total:
                    parts[rep.index] = rep.data
                if len(parts) == total:
                    return b"".join(parts[i] for i in range(total))
        if total is None:
            raise AulaError("the keyboard didn't answer. It may be asleep: press any key "
                            "to wake it, then try again")
        missing = sorted(set(range(total)) - set(parts))
        raise AulaError(f"read 0x{rcmd:02x} incomplete, packets {missing} never arrived; try again")

    def write(self, cmd: int, data: bytes, sub: int = 0, retries: int = 3) -> None:
        """Write data in 14-byte packets; the keyboard echoes each one back as an ack."""
        self.wait_keys_released()
        self._drain()
        for pkt in P.split_packets(cmd, sub, data):
            for _ in range(retries):
                self._ch.write(pkt)
                if self._wait_ack(pkt):
                    break
            else:
                raise AulaError(f"write 0x{cmd:02x} not acknowledged (packet {pkt[3]})")
            time.sleep(0.015)
        self._last_write = time.monotonic()

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

    def get_macro_store(self) -> bytes:
        return self.read(P.CMD_SET_MACRO, 0)

    def set_macro_store(self, raw: bytes) -> None:
        if len(raw) != 512:
            raise ValueError("macro store block must be 512 bytes")
        self.write(P.CMD_SET_MACRO, raw, 0)

    def get_palette(self) -> bytes:
        return self.read(P.CMD_SET_PALETTE)

    def set_palette(self, raw: bytes) -> None:
        self.write(P.CMD_SET_PALETTE, raw)
