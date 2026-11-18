import unittest

from akki.hotkey import MOD_ALT, MOD_CONTROL, MOD_SHIFT, HotkeyError, parse_hotkey


class HotkeyTests(unittest.TestCase):
    def test_parse_ctrl_space(self) -> None:
        self.assertEqual(parse_hotkey("ctrl+space"), (MOD_CONTROL, 0x20))

    def test_parse_multiple_modifiers_and_key(self) -> None:
        modifiers, key = parse_hotkey("Ctrl+Alt+Shift+F9")
        self.assertEqual(modifiers, MOD_CONTROL | MOD_ALT | MOD_SHIFT)
        self.assertEqual(key, 0x78)

    def test_parse_requires_modifier_and_key(self) -> None:
        with self.assertRaises(HotkeyError):
            parse_hotkey("space")
        with self.assertRaises(HotkeyError):
            parse_hotkey("ctrl")
        with self.assertRaises(HotkeyError):
            parse_hotkey("ctrl+nope")


if __name__ == "__main__":
    unittest.main()
