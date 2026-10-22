"""Pipeline configuration helpers that do not need an LLM or a renderer."""

import json
import os
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

from vga import music
from vga import pipeline
from vga.pipeline import PACK_IDS, _codegen_attempts, _codegen_token_budget


class ThemeTests(unittest.TestCase):
    def test_every_selectable_theme_has_a_pack_and_a_music_cue(self):
        root = Path(__file__).resolve().parent.parent
        for pack in PACK_IDS:
            with self.subTest(pack):
                self.assertTrue((root / "src" / "packs" / f"{pack}.ts").is_file())
                self.assertIn(pack, music._CUES)


class CodegenTokenTests(unittest.TestCase):
    def test_default_has_room_for_a_long_scene_file(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertGreaterEqual(_codegen_token_budget(), 24_000)

    def test_override_is_bounded(self):
        with mock.patch.dict(os.environ, {"VGA_CODEGEN_MAX_TOKENS": "40000"}):
            self.assertEqual(_codegen_token_budget(), 40_000)
        for bad in ("1000", "70000", "lots"):
            with self.subTest(bad), mock.patch.dict(os.environ, {"VGA_CODEGEN_MAX_TOKENS": bad}):
                with self.assertRaises(ValueError):
                    _codegen_token_budget()


class CodegenAttemptTests(unittest.TestCase):
    def test_default_is_four(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_codegen_attempts(), 4)

    def test_override_is_bounded(self):
        with mock.patch.dict(os.environ, {"VGA_CODEGEN_ATTEMPTS": "5"}):
            self.assertEqual(_codegen_attempts(), 5)
        for bad in ("0", "7", "many", "-1"):
            with self.subTest(bad), mock.patch.dict(os.environ, {"VGA_CODEGEN_ATTEMPTS": bad}):
                with self.assertRaises(ValueError):
                    _codegen_attempts()


class RunCheckpointTests(unittest.TestCase):
    def test_failure_records_stage_and_rejects_unsafe_project_ids(self):
        with self.assertRaises(ValueError):
            pipeline.project_dir("../../outside")
        with tempfile.TemporaryDirectory() as root, mock.patch.object(pipeline, "PROJECTS", Path(root)):
            project = Path(root) / "sample"
            project.mkdir()
            started = datetime.now(timezone.utc) - timedelta(seconds=1)
            record = {
                "status": "running",
                "startedAt": datetime.now(timezone.utc).isoformat(),
                "activeStage": "render",
            }
            (project / "run.json").write_text(json.dumps(record))
            pipeline._mark_run_failed("sample", started, RuntimeError("renderer crashed"))
            saved = json.loads((project / "run.json").read_text())
            self.assertEqual(saved["status"], "failed")
            self.assertEqual(saved["error"], {"stage": "render", "message": "renderer crashed"})

    def test_rerun_clears_stale_project_artifacts(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(pipeline, "REPO_ROOT", Path(root)):
            project = Path(root) / "data" / "projects" / "sample"
            for relative in (
                "assets/old.jpg", "assets-src/old.jpg", "qa/visual/old.png",
                "code/scenes.tsx", "render/final.mp4", "assets.json", "storyboard.json",
            ):
                path = project / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("stale")
            for relative in ("src/generated/sample/scenes.tsx", "public/generated/sample/old.jpg"):
                path = Path(root) / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("stale")
            pipeline._clear_run_outputs(project)
            self.assertFalse((project / "assets").exists())
            self.assertFalse((project / "assets.json").exists())
            self.assertFalse((project / "storyboard.json").exists())
            self.assertFalse((project / "render/final.mp4").exists())
            self.assertFalse((Path(root) / "src/generated/sample").exists())
            self.assertFalse((Path(root) / "public/generated/sample").exists())


if __name__ == "__main__":
    unittest.main()
