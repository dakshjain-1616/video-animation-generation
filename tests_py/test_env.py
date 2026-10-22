from __future__ import annotations

import os
import unittest
from pathlib import Path

from vga.env import load_env


class LoadEnvTest(unittest.TestCase):
    def setUp(self) -> None:
        self.saved = {key: os.environ.get(key) for key in ("VGA_TEST_KEY", "VGA_TEST_KEPT")}

    def tearDown(self) -> None:
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _load(self, content: str) -> list[str]:
        path = Path(__file__).resolve().parent / ".env.tmp"
        path.write_text(content, encoding="utf-8")
        try:
            return load_env(path)
        finally:
            path.unlink()

    def test_sets_missing_values_and_strips_quotes(self) -> None:
        os.environ.pop("VGA_TEST_KEY", None)
        set_keys = self._load('# comment\nVGA_TEST_KEY="hello world"\nexported=no\n')
        self.assertIn("VGA_TEST_KEY", set_keys)
        self.assertEqual(os.environ["VGA_TEST_KEY"], "hello world")

    def test_existing_environment_wins(self) -> None:
        os.environ["VGA_TEST_KEPT"] = "real"
        set_keys = self._load("VGA_TEST_KEPT=from-file\n")
        self.assertNotIn("VGA_TEST_KEPT", set_keys)
        self.assertEqual(os.environ["VGA_TEST_KEPT"], "real")

    def test_missing_file_and_blanks(self) -> None:
        self.assertEqual(load_env(Path(__file__).parent / ".env.missing"), [])
        self.assertEqual(self._load("\n## nothing here\n"), [])


if __name__ == "__main__":
    unittest.main()
