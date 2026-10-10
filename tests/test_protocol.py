"""Packet tests: expected values were captured from real keyboard traffic."""

import os
import unittest

from aula import keymap as K
from aula import protocol as P

BACKUP = os.path.join(os.path.dirname(__file__), "..", "backup")


def _backup(name):
    with open(os.path.join(BACKUP, name)) as f:
        return bytes.fromhex(f.read().strip())


class PacketTests(unittest.TestCase):
    def test_read_request_matches_capture(self):
        self.assertEqual(P.read_request(P.CMD_SET_LED).hex(" "),
                         "13 44 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 58")
        self.assertEqual(P.read_request(P.CMD_PROFILE)[-1], 0x5E)

    def test_led_write_packets_match_capture(self):
        led = _backup("cmd_44.hex")
        pkts = P.split_packets(P.CMD_SET_LED, 0, led)
        self.assertEqual(len(pkts), 10)
        self.assertEqual(pkts[0][:5].hex(" "), "13 04 0a 00 0e")
        self.assertEqual(pkts[9][:7].hex(" "), "13 04 0a 09 02 5a a5")
        for p in pkts:
            self.assertEqual(P.checksum(p), p[19])

    def test_parse_reply(self):
        r = bytes.fromhex("13 44 0a 09 02 5a a5" + " 00" * 12 + " 6b")
        rep = P.parse_packet(r)
        self.assertEqual((rep.cmd, rep.total, rep.index, rep.data), (0x44, 10, 9, b"\x5a\xa5"))
        self.assertIsNone(P.parse_packet(r[:-1] + b"\x00"))  # bad checksum


class LedConfigTests(unittest.TestCase):
    def test_slot_roundtrip(self):
        led = P.LedConfig(_backup("cmd_44.hex"))
        s = led.slot(1)
        s.color = 0
        led.set_slot(1, s)
        self.assertEqual(led.slot(1).color, 0)
        self.assertEqual(led.to_bytes()[-2:], P.LED_MAGIC)

    def test_side_mode(self):
        led = P.LedConfig(_backup("cmd_44.hex"))
        self.assertEqual(P.SIDE_MODES[led.side_mode], "static")  # original setting
        led.side_mode = P.SIDE_MODES.index("off")
        self.assertEqual(led.to_bytes()[18], 0)
        with self.assertRaises(ValueError):
            led.side_mode = 4

    def test_knob_mode(self):
        led = P.LedConfig(_backup("cmd_44.hex"))
        self.assertEqual(P.KNOB_MODES[led.knob_mode], "media")  # original setting
        led.knob_mode = P.KNOB_MODES.index("lighting")
        self.assertEqual(led.to_bytes()[26], 1)

    def test_os_and_win_lock(self):
        led = P.LedConfig(_backup("cmd_44.hex"))
        self.assertEqual(P.OS_MODES[led.os_mode], "windows")  # original settings
        self.assertFalse(led.win_lock)
        led.os_mode = P.OS_MODES.index("mac")
        led.win_lock = True
        self.assertEqual((led.to_bytes()[27], led.to_bytes()[15]), (2, 1))

    def test_sleep(self):
        from aula.cli import parse_duration
        led = P.LedConfig(_backup("cmd_44.hex"))
        self.assertEqual(led.sleep, 60)  # factory: 2 x 30 s, timed on hardware
        led.sleep = 300
        self.assertEqual(led.to_bytes()[24], 10)  # what the official app writes for 5 min
        self.assertEqual(P.sleep_text(90), "1.5 min")
        self.assertEqual([parse_duration(t) for t in ("5", "5m", "90s", "1.5m", "off")], [300, 300, 90, 90, 0])
        for bad in (45, 1230):
            with self.assertRaises(ValueError):
                led.sleep = bad

    def test_bad_values(self):
        led = P.LedConfig(_backup("cmd_44.hex"))
        with self.assertRaises(ValueError):
            led.set_slot(1, P.EffectSlot(10, 0, 0))


class CustomTableTests(unittest.TestCase):
    def test_planar_layout_matches_live_test(self):
        # Live test: ESC lit red, A green, W blue
        raw = P.custom_from_colors({K.key_index("esc"): (255, 0, 0),
                                    K.key_index("a"): (0, 255, 0),
                                    K.key_index("w"): (0, 0, 255)})
        self.assertEqual(len(raw), 378)
        self.assertEqual(raw[0], 0xFF)
        self.assertEqual(raw[126 + 9], 0xFF)
        self.assertEqual(raw[252 + 14], 0xFF)
        self.assertEqual(sum(raw), 3 * 0xFF)


class KeyReportTests(unittest.TestCase):
    def test_dongle_reports(self):
        from aula.device import _keys_down
        self.assertTrue(_keys_down(bytes([0, 0, 0x28, 0, 0, 0, 0, 0])))     # Enter on boot iface
        self.assertFalse(_keys_down(bytes(8)))
        self.assertTrue(_keys_down(bytes([4, 0, 0, 0, 0, 0, 1] + [0] * 14)))  # NKRO bit set
        self.assertIsNone(_keys_down(bytes([0x13] + [0] * 19)))             # config reply

    def test_bluetooth_reports(self):
        from aula.device import _keys_down
        self.assertTrue(_keys_down(bytes([1, 0, 0, 0x28, 0, 0, 0, 0, 0]), True))
        self.assertFalse(_keys_down(bytes([1] + [0] * 8), True))
        self.assertTrue(_keys_down(bytes([2, 0, 0, 0, 0, 0, 1] + [0] * 14), True))
        self.assertIsNone(_keys_down(bytes([4, 1]), True))  # system control, not keys


class MacroTests(unittest.TestCase):
    def test_factory_macro(self):
        from aula import macros as M
        raw = _backup("cmd_43.hex")
        ms = M.parse_store(raw)
        self.assertEqual(len(ms), 1)
        self.assertEqual(ms[0].name, "M1")
        self.assertEqual([e.describe() for e in ms[0].events],
                         ["lctrl↓10ms", "grave↓10ms", "lctrl↑10ms", "grave↑10ms"])
        self.assertEqual(M.build_store(ms), raw)          # byte-for-byte round trip

    def test_steps(self):
        from aula import macros as M
        ev = M.parse_steps(["ctrl+c", "wait:100", "text:Hi"], delay=15)
        self.assertEqual([e.describe() for e in ev[:4]],
                         ["lctrl↓15ms", "c↓15ms", "c↑15ms", "lctrl↑115ms"])
        self.assertEqual(ev[4].describe(), "lshift↓15ms")  # capital H
        self.assertEqual(len(ev), 4 + 4 + 2)

    def test_store_layout_and_entry(self):
        from aula import macros as M
        store = M.build_store([M.Macro("a", M.parse_steps(["x"])), M.Macro("b", M.parse_steps(["y"]))])
        self.assertEqual(store[:4], bytes([8, 0, 11, 0]))  # 2 entries -> first macro at 8
        self.assertEqual(len(M.parse_store(store)), 2)
        self.assertEqual(M.macro_entry(1, M.REPEAT_TIMES, 3), bytes([3, 1, 3, 1]))
        with self.assertRaises(ValueError):
            M.parse_steps(["text:ç"])

    def test_store_skips_reserved_bytes(self):
        from aula import macros as M
        ms = [M.Macro("a", M.parse_steps(["text:" + "a" * 14])), M.Macro("b", M.parse_steps(["x"]))]
        store = M.build_store(ms)
        first = int.from_bytes(store[4:6], "little")
        self.assertEqual(first, 128)              # a: 8..123, b (11 bytes) would cross 126
        self.assertEqual(store[126:128], b"\0\0")
        self.assertEqual([m.name for m in M.parse_store(store)], ["a", "b"])

    def test_down_up_steps(self):
        from aula import macros as M
        ev = M.parse_steps(["down:shift", "a", "up:shift"])
        self.assertEqual([e.describe() for e in ev], ["lshift↓20ms", "a↓20ms", "a↑20ms", "lshift↑20ms"])

    def test_recording_to_steps(self):
        from aula import macros as M

        def rec(*keys, gap=30):
            out, t = [], 0
            for k in keys:
                name, down = k[1:], k[0] == "+"
                out.append((name, down, t))
                t += gap
            return out

        def tap(*names):
            return [x for n in names for x in (f"+{n}", f"-{n}")]

        # "Selam, iyi" + Enter on Turkish Q, then Ctrl+C and the Win key alone
        typed = rec("+lshift", *tap("s"), "-lshift", *tap("e", "l", "a", "m", "backslash", "space",
                                                           "quote", "y", "quote", "enter"),
                    "+lctrl", *tap("c"), "-lctrl", "+lwin", "-lwin")
        steps = M.steps_from_recording(typed, "tr")
        self.assertEqual(steps, ["text:Selam, iyi", "enter", "ctrl+c", "win"])
        self.assertEqual(M.steps_from_recording(typed, "us"), ["text:Selam\\ 'y'", "enter", "ctrl+c", "win"])

        def keys(events):
            return [(e.kind, e.code, e.down) for e in events]

        # replaying the steps gives the same characters (Shift released between letters is fine)
        replay = M.parse_steps(steps, layout="tr")
        self.assertEqual(sum(e.down for e in replay if e.kind == M.KIND_KEY), 12)

        # fast typing overlaps keys: still plain text (as recorded on hardware)
        fast = rec("+lshift", "+m", "-m", "-lshift", "+e", "+r", "-e", "-r", "+rshift", "+1", "-rshift", "-1")
        self.assertEqual(M.steps_from_recording(fast, "tr"), ["text:Mer!"])

        # a key really held while others are pressed falls back to down:/up:
        held = rec("+w", "+space", "-space", "-w", gap=200)
        steps = M.steps_from_recording(held)
        self.assertEqual(steps, ["down:w", "down:space", "up:space", "up:w"])
        self.assertEqual(keys(M.parse_steps(steps)), [(0, 0x1A, True), (0, 0x2C, True), (0, 0x2C, False), (0, 0x1A, False)])

        # pauses
        slow = [("a", True, 0), ("a", False, 30), ("b", True, 530), ("b", False, 560)]
        self.assertEqual(M.steps_from_recording(slow), ["text:ab"])
        self.assertEqual(M.steps_from_recording(slow, pauses=True), ["text:a", "wait:500", "text:b"])
        # spaces at the ends stay separate steps
        self.assertEqual(M.steps_from_recording(rec(*tap("space", "a", "space"))), ["space", "text:a", "space"])

    def test_text_layouts(self):
        from aula import macros as M

        def typed(text, layout):
            return [e.describe()[:-5] for e in M.parse_steps([f"text:{text}"], layout=layout) if e.down]

        self.assertEqual(typed("bilgi", "us"), ["b", "i", "l", "g", "i"])
        self.assertEqual(typed("bilgi", "tr"), ["b", "quote", "l", "g", "quote"])
        self.assertEqual(typed("ıİ", "tr"), ["i", "lshift", "quote"])
        self.assertEqual(typed("ğüşöç", "tr"), ["lbracket", "rbracket", "semicolon", "comma", "period"])
        self.assertEqual(typed(",.:", "tr"), ["backslash", "slash", "lshift", "slash"])
        self.assertEqual(typed("@<", "tr"), ["ralt", "q", "iso_backslash"])
        with self.assertRaises(ValueError):
            M.parse_steps(["text:ğ"], layout="us")


class PresetTests(unittest.TestCase):
    def test_synthwave(self):
        from aula import presets as T
        c = T.render(T.PRESET_BY_NAME["synthwave"])
        self.assertEqual(len(c), 80)                          # every key with a position
        self.assertEqual(c[K.key_index("esc")], (0xFF, 0x50, 0x00))
        self.assertEqual(c[K.key_index("w")], (0xFF, 0xFF, 0xFF))
        r, g, b = c[K.key_index("grave")]                      # left edge: purple
        self.assertTrue(r < 0x70 and g == 0 and b == 0xFF)
        self.assertEqual(c[K.key_index("pgup")], (0x00, 0xD5, 0xFF))    # rightmost: cyan


class MatrixTests(unittest.TestCase):
    def test_backup_matches_keymap(self):
        m = _backup("cmd_41.hex")
        self.assertEqual(P.matrix_entry(m, K.key_index("esc")), P.key_entry(hid=K.HID["esc"]))
        self.assertEqual(P.matrix_entry(m, K.key_index("q")), P.key_entry(hid=K.HID["q"]))
        self.assertEqual(P.matrix_entry(m, K.key_index("lshift")),
                         P.key_entry(modifiers=K.MODIFIERS["lshift"]))
        self.assertEqual(P.matrix_entry(m, K.key_index("ralt")),
                         P.key_entry(modifiers=K.MODIFIERS["ralt"]))

    def test_tr_alias(self):
        self.assertEqual(K.key_index("ğ"), K.key_index("lbracket"))
        self.assertEqual(K.key_index("#53"), 53)


if __name__ == "__main__":
    unittest.main()
