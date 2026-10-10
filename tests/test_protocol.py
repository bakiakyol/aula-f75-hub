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
