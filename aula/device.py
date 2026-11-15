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

# Safety rules (see docs/protocol.md, "Safety"). Every packet to the keyboard goes
# through this class, so this is the one place they are enforced.
#
# Only these commands may ever be sent. Anything else (0x06 reset, 0x07, 0x0b, 0x8e,
# firmware reads/writes...) is refused before it reaches the keyboard.
READ_COMMANDS = {P.CMD_SET_MATRIX, P.CMD_SET_CUSTOM, P.CMD_SET_MACRO, P.CMD_SET_LED,
                 P.CMD_SET_PALETTE, P.CMD_PROFILE}
WRITE_COMMANDS = {P.CMD_SET_MATRIX, P.CMD_SET_CUSTOM, P.CMD_SET_MACRO, P.CMD_SET_LED,
                  P.CMD_SET_PALETTE}
# Settings are written over the USB cable only, like the official app and the other
# open-source F75 tools: over the radio packets get lost, and a radio write is known
# to have left another F75 unable to type until its firmware was reflashed.
WIRELESS_WRITE_REFUSED = (
    "Settings are only written over the USB cable (wired mode), never over the 2.4G "
    "dongle or Bluetooth. Reading, backups and live animations over the dongle still work.")
WIRED_WRITE_MISSING = ("Over the cable only the lighting/settings block can be written "
                       "so far; this table can't be written yet.")
LIVE_MIN_INTERVAL = 1 / 20  # s between live frames: faster starves the keyboard's key scan


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
        # The cable wins: with the switch on wired the keyboard isn't on the radio,
        # even when the dongle is still plugged in.
        wired = [d for d in devs if d["mode"] == "wired"]
        if wired or len(devs) == 1:
            d = (wired or devs)[0]
            self._open(d["path"], d["mode"])
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
        self._last_live = 0.0

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
        if cmd not in READ_COMMANDS:
            raise AulaError(f"refused: 0x{cmd:02x} is not a known read command")
        if self.mode == "wired":
            return self._wired_read(cmd, sub)
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

    def _wired_read(self, cmd: int, sub: int = 0) -> bytes:
        """Read a table over the cable (see P.WIRED_READS): request, then reply."""
        if cmd not in P.WIRED_READS:
            raise AulaError(f"0x{cmd:02x} can't be read over the cable yet")
        wcmd, asked = P.WIRED_READS[cmd]
        length = {P.CMD_SET_LED: P.LED_LEN, P.CMD_SET_MATRIX: P.MATRIX_BYTES,
                  P.CMD_SET_PALETTE: P.PALETTE_LEN, P.CMD_SET_CUSTOM: P.CUSTOM_LEN}[cmd]
        magic = P.LED_LEN - 2 if cmd == P.CMD_SET_LED else None
        return self._wired_get(wcmd, sub, asked, length, magic)

    def _wired_get(self, wcmd: int, sub: int, asked: int, length: int,
                   magic_at: int | None = None) -> bytes:
        """One wired read; with magic_at the reply must carry 5a a5 there."""
        for _ in range(3):
            self.wait_keys_released()
            self._ch.set_feature(P.wired_request(wcmd, sub, asked))
            time.sleep(0.02)
            reply = self._ch.get_feature(P.WIRED_REPORT_ID, P.WIRED_REPORT_LEN)
            data = P.wired_reply(reply, wcmd, sub, length)
            # while busy the firmware can answer with a truncated, mostly-zero block
            if data is not None and (magic_at is None
                                     or data[magic_at:magic_at + 2] == P.LED_MAGIC):
                return data
            time.sleep(0.1)
        raise AulaError(f"read 0x{wcmd:02x} over the cable got no matching reply; try again")

    def _wired_put(self, wcmd: int, data: bytes, read_back) -> None:
        """Send one wired write, wait, then read back: it has to match byte for byte."""
        self.wait_keys_released()
        self._ch.set_feature(P.wired_write_report(wcmd, 0, data))
        self._last_write = time.monotonic()
        time.sleep(P.WIRED_SETTLE)
        try:
            back = read_back()
        except AulaError as e:
            raise AulaError(f"write 0x{wcmd:02x} was sent but couldn't be checked ({e}); "
                            "run 'aula info' to see what the keyboard has now") from None
        if back != data:
            raise AulaError(f"the keyboard didn't keep write 0x{wcmd:02x} "
                            "(the read-back differs)")

    def can_read(self, cmd: int) -> bool:
        """Whether this table can be read on the current connection."""
        return cmd in READ_COMMANDS and (self.mode != "wired" or cmd in P.WIRED_READS)

    def write(self, cmd: int, data: bytes, sub: int = 0) -> None:
        """Store data on the keyboard. Refused unless the command is a known write and
        the keyboard is on the cable (see WIRELESS_WRITE_REFUSED).

        The old packet writes over the dongle and Bluetooth were removed on purpose.
        Over the cable the LED block, the effect palettes and the per-key colors can be
        written so far.
        """
        if cmd not in WRITE_COMMANDS:
            raise AulaError(f"refused: 0x{cmd:02x} is not a known write command")
        if self.mode != "wired":
            raise AulaError(WIRELESS_WRITE_REFUSED)
        if cmd == P.CMD_SET_LED and sub == 0:
            return self._wired_write_led(bytes(data))
        if cmd == P.CMD_SET_PALETTE and sub == 0:
            return self._wired_write_palette(bytes(data))
        if cmd == P.CMD_SET_CUSTOM and sub == 0:
            return self._wired_write_custom(bytes(data))
        raise AulaError(WIRED_WRITE_MISSING)

    def _wired_write_led(self, raw: bytes) -> None:
        """Write the LED block over the cable, changing only bytes whose meaning is known.

        The block is read over the cable first and only the bytes in P.LED_WRITABLE
        (plus the new effect's own slot) may differ from it: a block read over another
        connection, or a damaged one, is refused. Afterwards it is read back and has
        to match byte for byte.
        """
        current = self._wired_read(P.CMD_SET_LED)
        allowed = set(P.LED_WRITABLE)
        try:
            slot = P.LedConfig(raw)._off(raw[P.LED_EFFECT_OFFSET])
            allowed |= {slot, slot + 1}
        except ValueError:  # an effect without a settings slot
            pass
        changed = [i for i in range(P.LED_LEN) if raw[i] != current[i]]
        unknown = [i for i in changed if i not in allowed]
        if unknown:
            raise AulaError(f"refused: the write would change LED bytes {unknown}, "
                            "whose meaning is unknown")
        if changed:
            self._wired_put(P.WIRED_WRITE_LED, raw, lambda: self._wired_read(P.CMD_SET_LED))

    def _wired_write_palette(self, raw: bytes) -> None:
        """Write the effect palettes over the cable (command 0x0a, Dahuum/aula-studio).

        The whole 512-byte page is read first; only the 490 palette bytes may change,
        the rest (padding, the 5a a5 at 506 and what follows it) is sent back as read.
        After the page, the unchanged LED block is sent once more, as the official app
        does to apply it. Both are read back.
        """
        if len(raw) != P.PALETTE_LEN:
            raise ValueError(f"effect palettes must be {P.PALETTE_LEN} bytes")
        wcmd, asked = P.WIRED_READS[P.CMD_SET_PALETTE]
        read_page = lambda: self._wired_get(wcmd, 0, asked, P.WIRED_PAGE, P.WIRED_PALETTE_MAGIC)
        page = read_page()
        new = raw + page[P.PALETTE_LEN:]
        if new == page:
            return
        led = self._wired_read(P.CMD_SET_LED)
        self._wired_put(P.WIRED_WRITE_PALETTE, new, read_page)
        self._wired_put(P.WIRED_WRITE_LED, led, lambda: self._wired_read(P.CMD_SET_LED))

    def _wired_write_custom(self, raw: bytes) -> None:
        """Write the per-key color table over the cable; it is read back.

        The official app commits the unchanged LED block afterwards, but that isn't
        needed: the colors show at once without it (tested on a real keyboard), and
        every LED block write makes the keyboard blink once.
        """
        if len(raw) != P.CUSTOM_LEN:
            raise ValueError("per-key color table must be 378 bytes")
        if raw == self._wired_read(P.CMD_SET_CUSTOM):
            return
        self._wired_put(P.WIRED_WRITE_CUSTOM, raw, lambda: self._wired_read(P.CMD_SET_CUSTOM))

    # ----------------------------------------------------------- high level
    def get_led(self) -> P.LedConfig:
        return P.LedConfig(self.read(P.CMD_SET_LED))

    def set_led(self, cfg: P.LedConfig) -> None:
        raw = cfg.to_bytes()
        if len(raw) != P.LED_LEN or raw[-2:] != P.LED_MAGIC:
            raise AulaError("refused: the LED block is damaged (it has to end in 5a a5)")
        if cfg.sleep == 0:
            # A keyboard that never sleeps drains its battery with the lights on
            # (docs/protocol.md, "Safety"); the old keyboard ran like this for ~39 h.
            raise AulaError("refused: sleep 'never' is not allowed; pick a sleep time")
        self.write(P.CMD_SET_LED, raw)

    def get_custom(self) -> bytes:
        return self.read(P.CMD_SET_CUSTOM)

    def set_custom(self, raw: bytes) -> None:
        if len(raw) != P.CUSTOM_LEN:
            raise ValueError("per-key color table must be 378 bytes")
        self.write(P.CMD_SET_CUSTOM, raw)

    def send_live(self, frame: bytes) -> None:
        """Show a real-time frame (P.live_frame) until the next one arrives.

        Nothing is stored and nothing is acknowledged, so a lost packet silently
        loses the frame; P.LIVE_GAP keeps that rare. Without a new frame the
        keyboard returns to its own effect after about 2 seconds. Typing keeps
        working while frames stream (tested).

        Over the cable the same frame goes out as one feature report
        (P.wired_live_report) with a fixed header.

        Not over Bluetooth (too slow, packets get lost), at most 20 frames a second
        (faster starves the keyboard's key scanning) and at most P.LIVE_MAX bytes,
        the longest frame the official app sends.
        """
        if self.bluetooth:
            raise AulaError("live animations don't run over Bluetooth; use the 2.4G dongle")
        if len(frame) > P.LIVE_MAX:
            raise AulaError(f"refused: live frame of {len(frame)} bytes "
                            f"(at most {P.LIVE_MAX})")
        wait = self._last_live + LIVE_MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_live = time.monotonic()
        if self.mode == "wired":
            report = P.wired_live_report(frame)
            if report[:P.WIRED_HEADER] != P.WIRED_LIVE_HEADER:   # never another command
                raise AulaError("refused: wrong header for a live frame")
            self._ch.set_feature(report)
            return
        for pkt in P.split_packets(P.CMD_LIVE, P.LIVE_KEYS, frame):
            self._ch.write(pkt)
            time.sleep(P.LIVE_GAP)
        self._drain()

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
        if not self.can_read(P.CMD_PROFILE):
            return None
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
        if len(raw) != P.PALETTE_LEN:
            raise ValueError(f"effect palettes must be {P.PALETTE_LEN} bytes")
        self.write(P.CMD_SET_PALETTE, raw)
