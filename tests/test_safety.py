"""The safety rules in aula/device.py, checked against a fake channel (no keyboard)."""

import time
import unittest

from aula import device as D
from aula import protocol as P
from aula.backends.base import NoKeyGuard
from aula.errors import AulaError


class FakeChannel:
    def __init__(self):
        self.sent = []

    def write(self, pkt):
        self.sent.append(bytes(pkt))

    def recv(self, timeout):
        return None

    def drain(self):
        pass

    def close(self):
        pass


def keyboard(mode):
    kb = D.Keyboard.__new__(D.Keyboard)
    kb.timeout = 0.05
    kb.path, kb.mode, kb.bluetooth = "/dev/fake", mode, mode == "Bluetooth"
    kb._ch, kb._guard = FakeChannel(), NoKeyGuard()
    kb._last_write = kb._last_live = 0.0
    return kb


def led(sleep=300):
    raw = bytearray(P.LED_LEN)
    raw[-2:] = P.LED_MAGIC
    cfg = P.LedConfig(bytes(raw))
    cfg.sleep = sleep
    return cfg


class WriteRules(unittest.TestCase):
    def test_no_writes_over_the_radio(self):
        for mode in ("2.4G dongle", "Bluetooth"):
            kb = keyboard(mode)
            for call in (lambda: kb.set_led(led()),
                         lambda: kb.set_custom(bytes(P.CUSTOM_LEN)),
                         lambda: kb.set_matrix(bytes(P.MATRIX_BYTES)),
                         lambda: kb.set_macro_store(bytes(512)),
                         lambda: kb.set_palette(bytes(P.PALETTE_LEN))):
                with self.assertRaises(AulaError):
                    call()
            self.assertEqual(kb._ch.sent, [], mode)


    def test_unknown_commands_refused(self):
        kb = keyboard("2.4G dongle")
        for cmd in (P.CMD_RESET, 0x07, 0x0B, 0x0A, 0x08):
            with self.assertRaises(AulaError):
                kb.write(cmd, b"\0" * 14)
        for cmd in (P.CMD_RESET, 0x07, 0x0B, 0x08, 0x48):
            with self.assertRaises(AulaError):
                kb.read(cmd)
        self.assertEqual(kb._ch.sent, [])

    def test_reset_number_refused_on_the_cable_too(self):
        kb = keyboard("wired")
        kb._ch = FakeFeature({})
        with self.assertRaises(AulaError):
            kb.write(P.CMD_RESET, bytes(P.CUSTOM_LEN))
        self.assertEqual(kb._ch.sets, [])

    def test_sleep_never_refused(self):
        with self.assertRaisesRegex(AulaError, "never"):
            keyboard("wired").set_led(led(sleep=0))

    def test_damaged_led_block_refused(self):
        cfg = led()
        cfg.raw[-1] = 0
        with self.assertRaisesRegex(AulaError, "5a a5"):
            keyboard("wired").set_led(cfg)


class LiveRules(unittest.TestCase):
    frame = P.live_frame({(255, 0, 0): [1, 2, 3]})

    def test_not_over_bluetooth(self):
        kb = keyboard("Bluetooth")
        with self.assertRaises(AulaError):
            kb.send_live(self.frame)
        self.assertEqual(kb._ch.sent, [])

    def test_over_cable_one_report_with_the_fixed_header(self):
        kb = keyboard("wired")
        kb._ch = FakeFeature({})
        kb.send_live(self.frame)
        self.assertEqual(len(kb._ch.sets), 1)
        report = kb._ch.sets[0]
        self.assertEqual(len(report), P.WIRED_REPORT_LEN)
        self.assertEqual(report[:8], bytes.fromhex("0608000001007a01"))
        for idx in range(P.WIRED_LIVE_KEYS):
            want = (255, 0, 0) if idx in (1, 2, 3) else (0, 0, 0)
            self.assertEqual(tuple(report[8 + 3 * idx:11 + 3 * idx]), want)
        self.assertEqual(set(report[8 + 3 * P.WIRED_LIVE_KEYS:]), {0})

    def test_size_limit_over_cable_too(self):
        kb = keyboard("wired")
        kb._ch = FakeFeature({})
        with self.assertRaises(AulaError):
            kb.send_live(b"\x01" * (P.LIVE_MAX + 1))
        self.assertEqual(kb._ch.sets, [])

    def test_frame_size_limit(self):
        kb = keyboard("2.4G dongle")
        with self.assertRaises(AulaError):
            kb.send_live(b"\x01" * (P.LIVE_MAX + 1))
        self.assertEqual(kb._ch.sent, [])

    def test_at_most_20_frames_a_second(self):
        kb = keyboard("2.4G dongle")
        start = time.monotonic()
        for _ in range(5):
            kb.send_live(self.frame)
        self.assertGreaterEqual(time.monotonic() - start, 4 * D.LIVE_MIN_INTERVAL - 0.005)
        self.assertTrue(all(p[1] == P.CMD_LIVE for p in kb._ch.sent))



class FakeFeature:
    """A fake wired keyboard: answers a read request with a table on the next get."""

    def __init__(self, tables):
        self.tables, self.sets, self.reply, self.keeps = tables, [], None, True

    def set_feature(self, report):
        self.sets.append(bytes(report))
        if report[1] in (P.WIRED_WRITE_LED, P.WIRED_WRITE_PALETTE, P.WIRED_WRITE_CUSTOM):
            read, n = {P.WIRED_WRITE_LED: (0x84, P.LED_LEN),
                       P.WIRED_WRITE_PALETTE: (0x8A, P.WIRED_PAGE),
                       P.WIRED_WRITE_CUSTOM: (0x86, P.CUSTOM_LEN)}[report[1]]
            if self.keeps:
                self.tables[(read, 0)] = bytes(report[P.WIRED_HEADER:P.WIRED_HEADER + n])
            return
        table = self.tables.get((report[1], report[2]))
        self.reply = report[:P.WIRED_HEADER] + table + bytes(P.WIRED_REPORT_LEN - P.WIRED_HEADER - len(table)) \
            if table is not None else bytes(P.WIRED_REPORT_LEN)

    def get_feature(self, report_id, length):
        return self.reply

    def close(self):
        pass


class WiredReads(unittest.TestCase):
    def setUp(self):
        led_raw = bytearray(P.LED_LEN)
        led_raw[-2:] = P.LED_MAGIC
        led_raw[P.LED_EFFECT_OFFSET] = 12
        self.led = bytes(led_raw)
        self.matrix = bytes(range(256)) * 2
        self.kb = keyboard("wired")
        self.kb._ch = FakeFeature({(0x84, 0): self.led, (0x83, 1): self.matrix,
                                   (0x8A, 0): palette_page()})

    def test_reads(self):
        self.assertEqual(self.kb.get_led().effect, 12)
        self.assertEqual(self.kb.get_matrix(1), self.matrix[:P.MATRIX_BYTES])
        self.assertEqual(self.kb.get_palette(), palette_page()[:P.PALETTE_LEN])
        self.assertEqual(self.kb._ch.sets[0][:8], bytes.fromhex("0684000001008000"))
        self.assertEqual(self.kb._ch.sets[1][:8], bytes.fromhex("0683010001000002"))

    def test_unknown_tables_not_tried(self):
        for get in (self.kb.get_macro_store,):
            with self.assertRaises(AulaError):
                get()
        self.assertIsNone(self.kb.get_battery())
        self.assertEqual(self.kb._ch.sets, [])

    def test_wrong_reply_is_an_error(self):
        self.kb._ch = FakeFeature({})
        with self.assertRaises(AulaError):
            self.kb.get_led()


class WiredWrites(unittest.TestCase):
    def setUp(self):
        self.stored = led(sleep=300)
        self.stored.effect = 12
        self.kb = keyboard("wired")
        self.kb._ch = FakeFeature({(0x84, 0): self.stored.to_bytes()})
        P.WIRED_SETTLE, self._settle = 0, P.WIRED_SETTLE

    def tearDown(self):
        P.WIRED_SETTLE = self._settle

    def writes(self):
        return [r for r in self.kb._ch.sets if r[1] == P.WIRED_WRITE_LED]

    def test_read_modify_write_and_read_back(self):
        cfg = self.kb.get_led()
        cfg.effect = 3
        cfg.sleep = 600
        self.kb.set_led(cfg)
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(self.writes()[0][:8], bytes.fromhex("0604000001008000"))
        self.assertEqual(self.kb.get_led().effect, 3)

    def test_unknown_byte_refused(self):
        cfg = self.kb.get_led()
        cfg.raw[14] = 1  # e.g. a block read over the dongle
        with self.assertRaisesRegex(AulaError, r"\[14\]"):
            self.kb.set_led(cfg)
        self.assertEqual(self.writes(), [])

    def test_change_not_kept(self):
        self.kb._ch.keeps = False
        cfg = self.kb.get_led()
        cfg.effect = 3
        with self.assertRaisesRegex(AulaError, "read-back"):
            self.kb.set_led(cfg)

    def test_nothing_changed_nothing_written(self):
        self.kb.set_led(self.kb.get_led())
        self.assertEqual(self.writes(), [])

    def test_other_tables_not_written_over_cable(self):
        for call in (lambda: self.kb.set_matrix(bytes(P.MATRIX_BYTES)),
                     lambda: self.kb.set_macro_store(bytes(512))):
            with self.assertRaises(AulaError):
                call()
        self.assertEqual(self.kb._ch.sets, [])

    def test_per_key_without_led_commit(self):
        # an LED block write makes the keyboard blink, and the colors show without it
        self.kb._ch.tables[(0x86, 0)] = bytes(P.CUSTOM_LEN)
        table = P.custom_from_colors({0: (255, 0, 0)})
        self.kb.set_custom(table)
        w = [r for r in self.kb._ch.sets if r[1] in (P.WIRED_WRITE_CUSTOM, P.WIRED_WRITE_LED)]
        self.assertEqual([r[1] for r in w], [P.WIRED_WRITE_CUSTOM])
        self.assertEqual(w[0][:8], bytes.fromhex("060600000100" "7a01"))
        self.assertEqual(self.kb.get_custom(), table)


def palette_page():
    page = bytearray(range(256)) * 2
    page[P.PALETTE_LEN:] = bytes(P.WIRED_PAGE - P.PALETTE_LEN)
    page[506:512] = bytes.fromhex("5aa500100000")
    return bytes(page)


class WiredPalette(unittest.TestCase):
    def setUp(self):
        self.page = palette_page()
        self.led = led(sleep=300).to_bytes()
        self.kb = keyboard("wired")
        self.kb._ch = FakeFeature({(0x8A, 0): self.page, (0x84, 0): self.led})
        P.WIRED_SETTLE, self._settle = 0, P.WIRED_SETTLE

    def tearDown(self):
        P.WIRED_SETTLE = self._settle

    def written(self):
        return [r for r in self.kb._ch.sets if r[1] in (P.WIRED_WRITE_LED, P.WIRED_WRITE_PALETTE)]

    def test_palette_then_led_commit(self):
        pal = P.set_palette_color(self.kb.get_palette(), 1, 0, (1, 2, 3))
        self.kb.set_palette(pal)
        w = self.written()
        self.assertEqual([r[1] for r in w], [P.WIRED_WRITE_PALETTE, P.WIRED_WRITE_LED])
        self.assertEqual(w[0][:8], bytes.fromhex("060a000001000002"))
        self.assertEqual(w[0][8 + P.PALETTE_LEN:8 + P.WIRED_PAGE], self.page[P.PALETTE_LEN:])
        self.assertEqual(w[1][8:8 + P.LED_LEN], self.led)  # the LED block unchanged
        self.assertEqual(self.kb.get_palette(), pal)

    def test_page_without_signature_refused(self):
        self.kb._ch.tables[(0x8A, 0)] = bytes(P.WIRED_PAGE)
        with self.assertRaises(AulaError):
            self.kb.set_palette(bytes(P.PALETTE_LEN))
        self.assertEqual(self.written(), [])

    def test_unchanged_palette_not_written(self):
        self.kb.set_palette(self.kb.get_palette())
        self.assertEqual(self.written(), [])

    def test_not_kept(self):
        self.kb._ch.keeps = False
        with self.assertRaisesRegex(AulaError, "0x0a"):
            self.kb.set_palette(P.set_palette_color(self.kb.get_palette(), 1, 0, (1, 2, 3)))
        self.assertEqual([r[1] for r in self.written()], [P.WIRED_WRITE_PALETTE])


class WiredDescriptor(unittest.TestCase):
    def test_feature_report_detection(self):
        from aula.backends.linux import _has_feature_report
        # Report ID 6, Report Size 8, Report Count 519, Feature (Data,Var,Abs)
        desc = bytes([0x06, 0x01, 0xFF, 0x09, 0x01, 0xA1, 0x01, 0x85, 0x06, 0x75, 0x08,
                      0x96, 0x07, 0x02, 0xB1, 0x02, 0xC0])
        self.assertTrue(_has_feature_report(desc, 6))
        self.assertFalse(_has_feature_report(desc, 5))
        # Report ID 6 only as an Input report
        self.assertFalse(_has_feature_report(bytes([0x85, 0x06, 0x81, 0x02]), 6))


if __name__ == "__main__":
    unittest.main()
