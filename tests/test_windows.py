"""Windows backend: pure logic everywhere, real Win32 calls on Windows (no keyboard needed)."""

import os
import subprocess
import sys
import unittest

from aula import keymap as K
from aula import macros as M
from aula.backends import linux, windows as W

ON_WINDOWS = sys.platform == "win32"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def entry(pid, page=0xFF02, usage=2, vid=0x3554, path=None):
    return {"path": path or f"\\\\?\\hid#{vid:04x}_{pid:04x}_{page:x}_{usage}", "vendor_id": vid,
            "product_id": pid, "usage_page": page, "usage": usage, "name": "Compx 2.4G Wireless Receiver"}


class FakeEvent:
    def __init__(self, scan, vk=0):
        self.scan, self.hardware_keycode = scan, vk

    def get_scancode(self):
        return self.scan


class PickTests(unittest.TestCase):
    def test_vendor_collection_only(self):
        found = W.pick_devices([
            entry(0xFA09, page=0x01, usage=6),      # boot keyboard
            entry(0xFA09, page=0x0C, usage=1),      # consumer keys
            entry(0xFA09),                          # configuration channel
            entry(0x1234, vid=0x046D),              # someone else's device
        ])
        self.assertEqual([(d["mode"], d["supported"]) for d in found], [("2.4G dongle", True)])

    def test_bluetooth_and_wired(self):
        found = W.pick_devices([entry(0xFA07), entry(0x010C, vid=0x258A, page=0xFF00, usage=1),
                                entry(0x010C, vid=0x258A, page=0x01, usage=6)])
        self.assertEqual([(d["mode"], d["supported"]) for d in found],
                         [("Bluetooth", True), ("wired", False)])


class LayoutTests(unittest.TestCase):
    def test_klid(self):
        self.assertEqual(W.layout_from_klid("0000041F"), "tr")
        self.assertEqual(W.layout_from_klid("0000041f"), "tr")
        self.assertEqual(W.layout_from_klid("0001041F"), "us")   # Turkish F isn't supported
        self.assertEqual(W.layout_from_klid("00000409"), "us")


class RecordingTests(unittest.TestCase):
    def test_names_are_known(self):
        names = set(K.HID) | set(M.MOD_CODES)
        self.assertLessEqual(set(W.SCANCODES.values()), names)
        self.assertLessEqual(set(W.VK_FALLBACK.values()), names)

    def test_set1_matches_linux_codes(self):
        # Linux key codes 1-88 are the PC set-1 scan codes
        for code, name in linux.EVDEV.items():
            if code <= 0x58:
                self.assertEqual(W.SCANCODES.get(code), name, hex(code))

    def test_key_name(self):
        self.assertEqual(W.key_name(FakeEvent(0x1E)), "a")
        self.assertEqual(W.key_name(FakeEvent(0x1E | 0xC000)), "a")  # key-up flags in the high bits
        self.assertEqual(W.key_name(FakeEvent(0x11D)), "rctrl")
        self.assertEqual(W.key_name(FakeEvent(0x1D)), "lctrl")
        self.assertEqual(W.key_name(FakeEvent(0x14B)), "left")
        self.assertEqual(W.key_name(FakeEvent(0, vk=0x70)), "f1")    # no scan code: virtual key
        self.assertIsNone(W.key_name(FakeEvent(0, vk=0xBA)))         # punctuation VK: unknown


@unittest.skipUnless(ON_WINDOWS, "needs Windows")
class Win32Tests(unittest.TestCase):
    def test_enumeration_runs(self):
        devices = W.find_devices()          # no keyboard on CI: an empty list, but no crash
        self.assertIsInstance(devices, list)

    def test_some_hid_paths(self):
        self.assertIsInstance(W._interface_paths(), list)

    def test_key_guard(self):
        W.WindowsKeyGuard().wait_released(quiet=0.05, limit=2.0)

    def test_layout(self):
        self.assertIn(W.detect_layout(), ("us", "tr"))

    def test_aula_cmd(self):
        # the launcher runs from any folder and finds Python; 'effects' needs no keyboard
        r = subprocess.run(["cmd", "/c", os.path.join(ROOT, "aula.cmd"), "effects"],
                           capture_output=True, text=True, cwd=os.environ.get("TEMP", ROOT))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("rainbow-wheel", r.stdout)

    def test_aula_cmd_passes_errors_on(self):
        r = subprocess.run(["cmd", "/c", os.path.join(ROOT, "aula.cmd"), "no-such-command"],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)

    def test_install_ps1_parses(self):
        script = os.path.join(ROOT, "install.ps1")
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            f"$null = [ScriptBlock]::Create((Get-Content -Raw '{script}'))"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
