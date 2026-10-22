import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vga import review, voice
from vga.models import FORMATS, Scene, Storyboard
from vga.plan import Plan, PlannedScene
from vga.prompts import format_rules


def tone(path: Path, seconds: float) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", str(path)],
        check=True,
    )


class BudgetTests(unittest.TestCase):
    def test_budget_scales_with_scene_length(self):
        self.assertLess(voice.word_budget(2.0), voice.word_budget(5.0))
        self.assertGreaterEqual(voice.word_budget(2.0), 4)

    def test_speedup_only_when_speech_overruns(self):
        self.assertEqual(voice.speedup_needed(1.0, 3.0), 1.0)
        self.assertGreater(voice.speedup_needed(3.0, 3.0), 1.0)


class FitTests(unittest.TestCase):
    def test_line_is_padded_to_exactly_the_scene_length(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, out = Path(tmp, "raw.mp3"), Path(tmp, "out.wav")
            tone(raw, 1.5)
            voice.fit_to_scene(raw, 4.0, out)
            self.assertAlmostEqual(voice.probe_duration(out), 4.0, delta=0.05)

    def test_line_far_too_long_is_refused_not_rushed(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp, "raw.mp3")
            tone(raw, 5.0)
            with self.assertRaises(voice.VoiceError):
                voice.fit_to_scene(raw, 3.0, Path(tmp, "out.wav"))

    def test_mux_keeps_the_video_length(self):
        with tempfile.TemporaryDirectory() as tmp:
            video, audio = Path(tmp, "v.mp4"), Path(tmp, "a.m4a")
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=3:r=30",
                 "-pix_fmt", "yuv420p", str(video)], check=True)
            tone(audio, 5.0)
            length = voice.mux(video, audio)
            self.assertAlmostEqual(length, 3.0, delta=0.1)
            streams = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(video)],
                capture_output=True, text=True).stdout.split()
            self.assertEqual(sorted(streams), ["audio", "video"])


def board_and_plan():
    scenes = [Scene(f"s{i}", f"T{i}", "body", "paper", 3.0, 90) for i in range(2)]
    board = Storyboard("p", "t", "explainer", 20, 30, 1080, 1920, "e", scenes)
    plan = Plan("idea", 20, "t", "a", "u", [PlannedScene(s.id, s.title, "body", "paper", 3.0, visual="a wave") for s in scenes])
    return board, plan


class TrackTests(unittest.TestCase):
    def test_lines_are_synthesized_and_joined_in_scene_order(self):
        board, _plan = board_and_plan()

        def fake_synth(text, out, voice_id, key, model=None):
            tone(out, 0.4)

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(voice, "synthesize", fake_synth):
            track = voice.build_track(board, ["first", "second"], Path(tmp), "v", "k")
            self.assertAlmostEqual(voice.probe_duration(track), 6.0, delta=0.1)

    def test_transient_tts_failure_is_retried(self):
        calls: list[str] = []

        def flaky(text, out, voice_id, key, model=None):
            calls.append(text)
            if len(calls) == 1:
                raise voice.VoiceError("TTS 503: busy")
            tone(out, 0.2)

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(voice, "synthesize", flaky), \
                mock.patch.object(voice.time, "sleep", lambda _s: None):
            voice._synthesize_with_retry("line", Path(tmp, "out.mp3"), "v", "k")
        self.assertEqual(len(calls), 2)

    def test_auth_failure_is_not_retried(self):
        calls: list[str] = []

        def unauthorized(text, out, voice_id, key, model=None):
            calls.append(text)
            raise voice.VoiceError("TTS 401: bad key")

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(voice, "synthesize", unauthorized):
            with self.assertRaises(voice.VoiceError):
                voice._synthesize_with_retry("line", Path(tmp, "out.mp3"), "v", "k")
        self.assertEqual(len(calls), 1)


class ScriptTests(unittest.TestCase):
    def run_script(self, data):
        board, plan = board_and_plan()

        def fake_chat(_llm, _messages, validate, **_kw):
            return validate(data)

        with mock.patch.object(voice, "chat_json", fake_chat):
            return voice.write_script(board, plan, mock.Mock())

    def test_accepts_one_line_per_scene(self):
        self.assertEqual(self.run_script({"narration": ["Hello there.", "And so on."]}), ["Hello there.", "And so on."])

    def test_rejects_wrong_count_and_over_budget(self):
        with self.assertRaises(ValueError):
            self.run_script({"narration": ["only one"]})
        with self.assertRaises(ValueError):
            self.run_script({"narration": ["word " * 30, "ok"]})


class ReviewTests(unittest.TestCase):
    def run_review(self, data):
        board, plan = board_and_plan()

        def fake_chat(_llm, _messages, validate, **_kw):
            return validate(data)

        with mock.patch.object(review, "chat_json", fake_chat), mock.patch.object(review, "thumbnail", lambda _p: "data:,"):
            return review.review_scenes(board, plan, ["a.png", "b.png"], mock.Mock())

    def test_only_fix_verdicts_become_feedback(self):
        rows = {"scenes": [{"id": "s0", "verdict": "ok", "problem": ""},
                           {"id": "s1", "verdict": "fix", "problem": "label overlaps the plot"}]}
        self.assertEqual(self.run_review(rows), ["scene s1 (art director): label overlaps the plot"])

    def test_unknown_scene_id_is_rejected(self):
        with self.assertRaises(ValueError):
            self.run_review({"scenes": [{"id": "nope", "verdict": "ok"}]})


class FormatTests(unittest.TestCase):
    def test_formats_and_stage_rules(self):
        self.assertEqual(FORMATS["9:16"], (1080, 1920))
        self.assertIn("PORTRAIT", format_rules(1080, 1920))
        self.assertIn("LANDSCAPE", format_rules(1920, 1080))


if __name__ == "__main__":
    unittest.main()
