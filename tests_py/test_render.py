"""Renderer client behavior that can be tested without Chromium."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vga import render


def completed(returncode: int, stdout: str = "", stderr: str = ""):
    return mock.Mock(returncode=returncode, stdout=stdout, stderr=stderr)


class RunTests(unittest.TestCase):
    def test_keeps_the_report_when_the_duration_gate_fails(self):
        report = {"ok": True, "actual": 19.0, "target": 20.0, "pass": False}
        with mock.patch("vga.render.subprocess.run", return_value=completed(1, json.dumps(report))):
            self.assertEqual(render._run([]), report)

    def test_hard_failure_without_json_raises(self):
        with mock.patch("vga.render.subprocess.run", return_value=completed(1, stderr="boom")):
            with self.assertRaises(render.RenderError):
                render._run([])

    def test_last_json_is_used_even_after_log_lines(self):
        stdout = 'log line\n{"ok": true, "stills": []}\n'
        with mock.patch("vga.render.subprocess.run", return_value=completed(0, stdout)):
            self.assertEqual(render._run([])["stills"], [])


class DimensionTests(unittest.TestCase):
    def test_wrong_composition_dimensions_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "storyboard.json"
            path.write_text(json.dumps({
                "id": "p", "title": "t", "category": "explainer", "pack": "editorial-ink",
                "target": 20, "fps": 30, "width": 1920, "height": 1080,
                "entry": "src/generated/nc-vertical-1/entry.tsx", "scenes": [],
            }), encoding="utf-8")
            report = {"ok": True, "width": 1080, "height": 1920, "fps": 30}
            with mock.patch("vga.render._run", return_value=report):
                with self.assertRaises(render.RenderError):
                    render.render_storyboard(str(path), str(Path(tmp) / "out.mp4"))

    def test_matching_dimensions_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "storyboard.json"
            path.write_text(json.dumps({
                "id": "p", "title": "t", "category": "explainer", "pack": "editorial-ink",
                "target": 20, "fps": 30, "width": 1920, "height": 1080,
                "entry": "src/generated/nc-vertical-1/entry.tsx", "scenes": [],
            }), encoding="utf-8")
            report = {"ok": True, "width": 1920, "height": 1080, "fps": 30}
            with mock.patch("vga.render._run", return_value=report):
                self.assertIs(render.render_storyboard(str(path), str(Path(tmp) / "out.mp4")), report)


if __name__ == "__main__":
    unittest.main()
