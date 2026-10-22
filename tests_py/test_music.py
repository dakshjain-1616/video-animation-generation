"""Offline tests for the optional music stage (vga.music).

No network: a generated tone stands in for a caller track, and the procedural
cue is composed directly. ffmpeg/ffprobe are already required by the suite.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vga import music
from vga.models import Scene, Storyboard


def tone(path: Path, seconds: float, frequency: int = 220) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", f"sine=frequency={frequency}:duration={seconds}", str(path)],
        check=True,
    )


def board(seconds: float = 2.0) -> Storyboard:
    frames = int(seconds * 30 / 2)
    return Storyboard(
        id="p",
        title="t",
        category="explainer",
        pack="editorial-ink",
        target=20.0,
        fps=30,
        width=1080,
        height=1920,
        entry="src/generated/p/entry.tsx",
        scenes=[
            Scene("s1", "OPEN", "open", "night", seconds / 2, frames),
            Scene("s2", "CLOSE", "close", "night", seconds / 2, frames),
        ],
    )


class TempDir(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)


class ResolveTests(TempDir):
    def test_off_by_default(self):
        self.assertIsNone(music.resolve_request(None, "editorial-ink"))
        self.assertIsNone(music.resolve_request("off", "editorial-ink"))

    def test_auto_falls_back_to_procedural(self):
        with mock.patch.object(music, "library_dir", lambda: self.dir / "missing"):
            request = music.resolve_request("auto", "editorial-ink")
        self.assertEqual(request, music.MusicRequest("procedural"))

    def test_auto_prefers_named_library_track(self):
        library = self.dir / "music"
        library.mkdir()
        (library / "other.mp3").write_bytes(b"x")
        chosen = library / "editorial-ink.mp3"
        tone(chosen, 0.4)
        with mock.patch.object(music, "library_dir", lambda: library):
            request = music.resolve_request("auto", "editorial-ink")
        self.assertEqual(request.file, chosen)

    def test_explicit_file_is_validated(self):
        track = self.dir / "track.wav"
        tone(track, 0.4)
        request = music.resolve_request(str(track), "editorial-ink")
        self.assertEqual(request.source, "file")
        self.assertEqual(request.file, track)
        with self.assertRaises(music.MusicError):
            music.resolve_request(str(self.dir / "nope.mp3"), "editorial-ink")

    def test_file_without_audio_is_rejected(self):
        broken = self.dir / "broken.mp3"
        broken.write_bytes(b"not audio")
        with self.assertRaises(music.MusicError):
            music.resolve_request(str(broken), "editorial-ink")


class ComposeTests(TempDir):
    def test_exact_length_stereo_and_deterministic(self):
        first, second = self.dir / "a.wav", self.dir / "b.wav"
        music.compose(board(2.0), first)
        music.compose(board(2.0), second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=channels,sample_rate",
             "-of", "default=noprint_wrappers=1", str(first)],
            capture_output=True, text=True, check=True,
        ).stdout
        self.assertIn("channels=2", probe)
        self.assertIn(f"sample_rate={music.COMPOSE_RATE}", probe)
        self.assertAlmostEqual(music.probe_duration(first), 2.0, delta=0.01)

    def test_bed_is_not_silent_and_does_not_clip(self):
        bed = self.dir / "bed.wav"
        music.compose(board(2.0), bed)
        stats = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", str(bed), "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True,
        ).stderr
        self.assertIn("mean_volume", stats)
        mean = float(stats.split("mean_volume:")[1].split("dB")[0])
        peak = float(stats.split("max_volume:")[1].split("dB")[0])
        self.assertGreater(mean, -40.0)
        self.assertLess(peak, 0.0)


class PrepareTests(TempDir):
    def test_short_track_loops_to_video_length(self):
        source, out = self.dir / "short.wav", self.dir / "bed.wav"
        tone(source, 0.5)
        music.prepare_file(source, 3.0, out)
        self.assertAlmostEqual(music.probe_duration(out), 3.0, delta=0.05)

    def test_long_track_is_trimmed(self):
        source, out = self.dir / "long.wav", self.dir / "bed.wav"
        tone(source, 6.0)
        music.prepare_file(source, 2.5, out)
        self.assertAlmostEqual(music.probe_duration(out), 2.5, delta=0.05)


class MixTests(TempDir):
    def test_music_only_mix_is_exact(self):
        bed = self.dir / "bed.wav"
        music.compose(board(2.0), bed)
        mix = music.build_mix(board(2.0), self.dir, None, bed)
        self.assertIsNotNone(mix)
        self.assertAlmostEqual(music.probe_duration(mix), 2.0, delta=0.02)

    def test_voice_is_ducked_under_music(self):
        voice, bed = self.dir / "voice.wav", self.dir / "bed.wav"
        tone(voice, 2.0, 440)
        music.compose(board(2.0), bed)
        mix = music.build_mix(board(2.0), self.dir, voice, bed)
        self.assertIsNotNone(mix)
        self.assertAlmostEqual(music.probe_duration(mix), 2.0, delta=0.02)
        streams = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(mix)],
            capture_output=True, text=True, check=True,
        ).stdout.split()
        self.assertEqual(streams, ["audio"])

    def test_voice_only_mix_exists(self):
        voice = self.dir / "voice.wav"
        tone(voice, 2.0, 440)
        mix = music.build_mix(board(2.0), self.dir, voice, None)
        self.assertAlmostEqual(music.probe_duration(mix), 2.0, delta=0.02)

    def test_silent_inputs_need_no_mix(self):
        self.assertIsNone(music.build_mix(board(2.0), self.dir, None, None))


class MuxTests(TempDir):
    def test_mux_keeps_video_length_and_adds_audio(self):
        video, audio = self.dir / "v.mp4", self.dir / "a.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=2:r=30",
             "-pix_fmt", "yuv420p", str(video)],
            check=True,
        )
        tone(audio, 5.0)
        length = music.mux(video, audio)
        self.assertAlmostEqual(length, 2.0, delta=0.1)
        streams = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(video)],
            capture_output=True, text=True, check=True,
        ).stdout.split()
        self.assertEqual(sorted(streams), ["audio", "video"])


if __name__ == "__main__":
    unittest.main()
