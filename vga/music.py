"""Optional background music: a supplied track or a generated, license-free bed.

Music is off by default. `run --music` (or `--music auto`) uses the first track
in the local library (`data/music/`, or `VGA_MUSIC_DIR`) and falls back to a
deterministic procedural cue. `--music path/to/track.mp3` uses that file.

The stage is deliberately small and local, like the rest of the agent: no
streaming service, no keys, no extra Python dependency. The bed is cut or
looped to the storyboard's exact length, normalized, and mixed once with the
voice track (ducked) before the video is muxed with `-c:v copy`. The duration
gate therefore still measures the same video, unchanged.

    --music -> bed.wav -> audio/mix.m4a -> muxed under final.mp4
"""

from __future__ import annotations

import math
import os
import random
import subprocess
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path

from .models import Storyboard

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LIBRARY = REPO_ROOT / "data" / "music"
MUSIC_EXTS = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus")

# The generated cue is pad-heavy and band-limited, so 22.05 kHz is transparent
# enough and keeps pure-Python synthesis fast. Files are prepared at 44.1 kHz
# and the final mix resamples everything to 48 kHz.
SAMPLE_RATE = 44_100
COMPOSE_RATE = 22_050
CHANNELS = 2
FADE_IN = 1.2
FADE_OUT = 2.0
DEFAULT_VOLUME = 0.16

# Loudness targets (EBU R128). Music sits well under the narrator; a music-only
# bed is louder because it is the whole soundtrack.
VOICE_LUFS = -16.0
MUSIC_LUFS_UNDER_VOICE = -24.0
MUSIC_LUFS_ALONE = -18.0
TRUE_PEAK = -1.5

# Per-pack musical settings. Packs are tokens only, so the cue follows the same
# idea: a slow minor-key editorial theme or a cooler, slightly quicker slate.
_CUES = {
    "editorial-ink": {
        "key": "D minor",
        "tempo": 72,
        "chords": [
            ([62, 65, 69], 38),  # Dm
            ([58, 62, 65], 34),  # Bb
            ([57, 60, 65], 41),  # F
            ([55, 60, 64], 36),  # C
            ([62, 65, 69, 72], 38),  # Dm (open voicing)
        ],
        "arp": [74, 77, 81, 77, 74, 72],
    },
    "clinical-slate": {
        "key": "A minor",
        "tempo": 84,
        "chords": [
            ([57, 60, 64], 45),  # Am
            ([53, 57, 60], 41),  # F
            ([48, 52, 55], 36),  # C
            ([55, 59, 62], 43),  # G
            ([57, 60, 64, 67], 45),  # Am (open voicing)
        ],
        "arp": [69, 72, 76, 79, 76, 72],
    },
    "sunset-paper": {
        "key": "F major",
        "tempo": 76,
        "chords": [
            ([65, 69, 72], 41),  # F
            ([62, 65, 69], 38),  # Dm
            ([58, 62, 65], 34),  # Bb
            ([60, 64, 67], 36),  # C
            ([65, 69, 72, 77], 41),  # F (open)
        ],
        "arp": [77, 81, 84, 81, 77, 72],
    },
    "forest-ink": {
        "key": "G major",
        "tempo": 68,
        "chords": [
            ([67, 71, 74], 43),  # G
            ([64, 67, 71], 40),  # Em
            ([60, 64, 67], 36),  # C
            ([62, 66, 69], 38),  # D
            ([67, 71, 74, 79], 43),  # G (open)
        ],
        "arp": [79, 83, 86, 83, 79, 74],
    },
    "mono-graphite": {
        "key": "C minor",
        "tempo": 80,
        "chords": [
            ([60, 63, 67], 36),  # Cm
            ([56, 60, 63], 32),  # Ab
            ([51, 55, 58], 39),  # Eb
            ([58, 62, 65], 34),  # Bb
            ([60, 63, 67, 70], 36),  # Cm (open)
        ],
        "arp": [72, 75, 79, 82, 79, 75],
    },
}

_DEFAULT_CUE = _CUES["editorial-ink"]

# Sine table: every sample is two lookups instead of a transcendental call.
_TABLE_BITS = 12
_TABLE_SIZE = 1 << _TABLE_BITS
_TABLE_MASK = _TABLE_SIZE - 1
_SINE = [math.sin(2 * math.pi * i / _TABLE_SIZE) for i in range(_TABLE_SIZE)]


class MusicError(RuntimeError):
    pass


@dataclass(frozen=True)
class MusicRequest:
    """What to use as the bed: a caller file or the built-in composer."""

    source: str  # "file" | "procedural"
    file: Path | None = None


def resolve_request(spec: str | None, pack: str) -> MusicRequest | None:
    """Resolve a CLI/environment music spec, or None when music is off.

    `auto` prefers a local library track named after the pack, then any audio
    file in the library, and only then the procedural cue. A path is validated
    here so a bad choice fails before any LLM or render work.
    """
    if spec is None or spec.strip().lower() in ("", "off", "none", "no"):
        return None
    value = spec.strip()
    if value.lower() == "auto":
        track = find_library_track(pack)
        return MusicRequest("file", track) if track else MusicRequest("procedural")
    path = Path(os.path.expanduser(value))
    if path.is_dir():
        path = _first_audio(path)
        if path is None:
            raise MusicError(f"no audio files in {value}")
    if not path.is_file():
        raise MusicError(f"music file not found: {value}")
    if path.suffix.lower() not in MUSIC_EXTS:
        raise MusicError(f"music file must be one of {', '.join(MUSIC_EXTS)}: {value}")
    if not has_audio_stream(path):
        raise MusicError(f"music file has no readable audio stream: {value}")
    return MusicRequest("file", path.resolve())


def library_dir() -> Path:
    override = os.environ.get("VGA_MUSIC_DIR")
    return Path(os.path.expanduser(override)).resolve() if override else DEFAULT_LIBRARY


def find_library_track(pack: str) -> Path | None:
    """Deterministic library lookup: <pack>.<ext> first, then the first track.

    Files without a readable audio stream are skipped, so one stray document in
    the folder cannot break `--music auto`.
    """
    root = library_dir()
    if not root.is_dir():
        return None
    for extension in MUSIC_EXTS:
        exact = root / f"{pack}{extension}"
        if exact.is_file() and has_audio_stream(exact):
            return exact
    direct = sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() in MUSIC_EXTS)
    for candidate in direct:
        if has_audio_stream(candidate):
            return candidate
    nested = root / pack
    if nested.is_dir():
        return _first_audio(nested)
    return None


def _first_audio(directory: Path) -> Path | None:
    tracks = sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in MUSIC_EXTS)
    return next((track for track in tracks if has_audio_stream(track)), None)


def has_audio_stream(path: Path) -> bool:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and "audio" in result.stdout


def build_bed(request: MusicRequest, storyboard: Storyboard, directory: Path) -> Path:
    """Write music/bed.wav at exactly the storyboard length."""
    seconds = storyboard.frames() / storyboard.fps
    music_dir = directory / "music"
    music_dir.mkdir(parents=True, exist_ok=True)
    bed = music_dir / "bed.wav"
    if request.source == "file":
        if request.file is None:  # guarded by resolve_request
            raise MusicError("music request has no file")
        prepare_file(request.file, seconds, bed)
    else:
        compose(storyboard, bed)
    return bed


def prepare_file(source: Path, seconds: float, out: Path) -> None:
    """Loop/trim an arbitrary track to the video length, with safe fades."""
    fade_out_start = max(0.0, seconds - FADE_OUT)
    filters = (
        f"aresample={SAMPLE_RATE},"
        "aformat=sample_fmts=s16:channel_layouts=stereo,"
        f"afade=t=in:st=0:d={min(FADE_IN, seconds / 4):.3f},"
        f"afade=t=out:st={fade_out_start:.3f}:d={min(FADE_OUT, seconds / 3):.3f}"
    )
    result = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-i", str(source),
         "-t", f"{seconds:.3f}", "-af", filters, "-ar", str(SAMPLE_RATE), "-ac", "2", str(out)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise MusicError(f"could not prepare music {source.name}: {result.stderr.strip()[-300:]}")


def build_mix(
    storyboard: Storyboard,
    directory: Path,
    voice_track: Path | None,
    music_track: Path | None,
) -> Path | None:
    """One normalized, ducked stereo mix at exactly the video length."""
    if voice_track is None and music_track is None:
        return None
    seconds = storyboard.frames() / storyboard.fps
    audio_dir = directory / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    out = audio_dir / "mix.m4a"

    inputs: list[str] = []
    filters: list[str] = []
    voice_index = music_index = None
    if voice_track is not None:
        voice_index = len(inputs) // 2
        inputs += ["-i", str(voice_track)]
    if music_track is not None:
        music_index = len(inputs) // 2
        inputs += ["-i", str(music_track)]

    if voice_index is not None:
        filters.append(
            f"[{voice_index}:a]aresample=48000,"
            "aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"loudnorm=I={VOICE_LUFS}:TP={TRUE_PEAK}:LRA=9,aresample=48000[voice]"
        )
        if music_index is not None:
            # The narrator needs two consumers: the ducker's key and the mix.
            filters.append("[voice]asplit=2[vmain][vsc]")
    if music_index is not None:
        # Under narration the bed is quiet and sidechain-ducked; alone it is the
        # soundtrack. Both are normalized, never guessed at with a volume knob.
        target = MUSIC_LUFS_UNDER_VOICE if voice_index is not None else MUSIC_LUFS_ALONE
        filters.append(
            f"[{music_index}:a]aresample=48000,"
            "aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"loudnorm=I={target}:TP=-2:LRA=7,aresample=48000[m]"
        )

    if voice_index is not None and music_index is not None:
        filters.append(
            "[m][vsc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=350[ducked]"
        )
        filters.append(
            "[ducked][vmain]amix=inputs=2:duration=longest:normalize=0,"
            "alimiter=limit=0.95:level=disabled[mix]"
        )
    elif music_index is not None:
        filters.append("[m]anull[mix]")
    else:
        filters.append("[voice]anull[mix]")

    fade_out_start = max(0.0, seconds - min(FADE_OUT, seconds / 3))
    filters.append(
        f"[mix]atrim=0:{seconds:.3f},"
        f"afade=t=out:st={fade_out_start:.3f}:d={min(FADE_OUT, seconds / 3):.3f},"
        "aresample=48000[a]"
    )

    result = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", *inputs,
         "-filter_complex", ";".join(filters), "-map", "[a]",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
         "-t", f"{seconds:.3f}", str(out)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise MusicError(f"could not build the audio mix: {result.stderr.strip()[-400:]}")
    return out


def mux(video: Path, track: Path) -> float:
    """Put the mix under the video in place, keeping the video's exact length."""
    length = probe_duration(video)
    muxed = video.with_name("mixed.mp4")
    result = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(track),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", "-t", f"{length:.3f}", str(muxed)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise MusicError(f"could not mux audio: {result.stderr.strip()[-300:]}")
    muxed.replace(video)
    return probe_duration(video)


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError as error:
        raise MusicError(f"ffprobe could not read {path}: {result.stderr.strip()[-200:]}") from error


# --- procedural cue ---------------------------------------------------------


def compose(storyboard: Storyboard, out: Path, volume: float = DEFAULT_VOLUME) -> None:
    """Write a deterministic ambient cue shaped by the storyboard's scene arc.

    No samples, no model, no license: pads, a soft bass and sparse plucks in a
    slow minor progression. It is intentionally a bed, not a song: the picture
    and voice carry the video.
    """
    seconds = storyboard.frames() / storyboard.fps
    cue = _CUES.get(storyboard.pack or "editorial-ink", _DEFAULT_CUE)
    rate = COMPOSE_RATE
    frames = max(1, int(round(seconds * rate)))
    left = [0.0] * frames
    right = [0.0] * frames
    rng = random.Random(11 + sum(ord(char) for char in cue["key"]))

    chord_len = max(3.5, min(7.0, seconds / 6.0))
    boundaries = _scene_boundaries(storyboard)
    chord_index = 0
    start = 0.0
    while start < seconds:
        notes, bass = cue["chords"][chord_index % len(cue["chords"])]
        end = min(seconds, start + chord_len)
        energy = _energy_at((start + end) / 2, boundaries, storyboard)
        # The final chord is the tonic and resolves the cue.
        if seconds - end < 0.05:
            notes, bass = cue["chords"][0]
        _pad(left, right, notes, start, end, energy, chord_len, rate)
        _bass(left, right, bass, start, min(seconds, end + 0.4), energy, rate)
        if energy > 0.5:
            _arp(left, right, cue, start, end, energy, rng, rate)
        start = end
        chord_index += 1

    _swells(left, right, boundaries, seconds, rng, rate)
    _reverb(left, right, rate)
    _finish(left, right, seconds, rate, volume)
    write_wav(out, left, right, rate)


def _scene_boundaries(storyboard: Storyboard) -> list[float]:
    boundaries: list[float] = []
    elapsed = 0.0
    for scene in storyboard.scenes:
        elapsed += scene.frames / storyboard.fps
        boundaries.append(elapsed)
    return boundaries[:-1]  # the end is not a transition


def _energy_at(t: float, boundaries: list[float], storyboard: Storyboard) -> float:
    """0.35..0.9 energy: the opening is sparse, the body builds, the close rests."""
    index = 0
    for boundary in boundaries:
        if t > boundary:
            index += 1
    scene = storyboard.scenes[min(index, len(storyboard.scenes) - 1)]
    if scene.kind == "open":
        return 0.42
    if scene.kind == "close":
        return 0.38
    position = index / max(1, len(storyboard.scenes) - 1)
    return 0.58 + 0.28 * math.sin(position * math.pi)


def _pad(left: list[float], right: list[float], notes: list[int], start: float, end: float,
         energy: float, chord_len: float, rate: int) -> None:
    duration = max(0.4, end - start)
    for index, midi in enumerate(notes):
        frequency = _hz(midi)
        attack = min(1.4, duration * 0.35)
        release = min(1.8, duration * 0.45)
        gain = (0.048 + 0.02 * energy) / (1 + index * 0.22)
        pan = -0.35 if index % 2 == 0 else 0.35
        _note(left, right, start, duration, [frequency, frequency * 1.003],
              gain, attack, release, pan, decay=False, detune_gain=0.55, rate=rate)
    # A quiet octave shimmer marks the chord change in the body.
    if energy > 0.6 and notes:
        _note(left, right, start + 0.2, min(1.6, chord_len),
              [_hz(notes[-1] + 12)], 0.018 * energy, 0.6, 1.2, 0.15, decay=False, rate=rate)


def _bass(left: list[float], right: list[float], midi: int, start: float, end: float,
          energy: float, rate: int) -> None:
    duration = max(0.4, end - start)
    _note(left, right, start, duration, [_hz(midi), _hz(midi) * 2],
          0.055 + 0.02 * energy, 0.5, 0.9, 0.0, decay=False, detune_gain=0.12, rate=rate)


def _arp(left: list[float], right: list[float], cue: dict, start: float, end: float,
         energy: float, rng: random.Random, rate: int) -> None:
    step = 60.0 / cue["tempo"] * 2  # half-note plucks: unhurried
    notes = cue["arp"]
    index = 0
    t = start + 0.15
    while t < end - 0.1:
        midi = notes[(index + rng.randrange(0, 2)) % len(notes)]
        pan = 0.5 if index % 2 == 0 else -0.5
        _note(left, right, t, min(1.4, end - t), [_hz(midi)],
              0.028 * energy, 0.012, 0.35, pan, decay=True, rate=rate)
        t += step
        index += 1


def _swells(left: list[float], right: list[float], boundaries: list[float], seconds: float,
            rng: random.Random, rate: int) -> None:
    """A soft airy rise into each cut, so scene changes do not feel pasted on."""
    for boundary in boundaries:
        if boundary < 1.0 or boundary > seconds - 1.0:
            continue
        _noise_note(left, right, boundary - 0.55, 1.1, 0.012, rng, rate)


def _note(left: list[float], right: list[float], start: float, duration: float,
          frequencies: list[float], gain: float, attack: float, release: float,
          pan: float, decay: bool, detune_gain: float = 1.0, rate: int = COMPOSE_RATE) -> None:
    begin = max(0, int(round(start * rate)))
    length = min(len(left) - begin, int(round(duration * rate)))
    if length <= 0:
        return
    angle = (pan + 1) * math.pi / 4
    gain_left, gain_right = math.cos(angle), math.sin(angle)
    divisor = max(1.0, len(frequencies) * detune_gain)
    for offset in range(length):
        t = offset / rate
        if decay:
            envelope = math.exp(-t / 0.45) * min(1.0, t / max(attack, 1e-3))
        else:
            envelope = min(1.0, t / max(attack, 1e-3), (length / rate - t) / max(release, 1e-3))
            envelope = max(0.0, envelope)
        sample = 0.0
        for index, frequency in enumerate(frequencies):
            phase = (t * frequency) % 1.0
            sample += _SINE[int(phase * _TABLE_SIZE) & _TABLE_MASK] * (detune_gain if index else 1.0)
        sample *= gain * envelope / divisor
        position = begin + offset
        left[position] += sample * gain_left
        right[position] += sample * gain_right


def _noise_note(left: list[float], right: list[float], start: float, duration: float,
                gain: float, rng: random.Random, rate: int) -> None:
    begin = max(0, int(round(start * rate)))
    length = min(len(left) - begin, int(round(duration * rate)))
    if length <= 0:
        return
    smoothed = 0.0
    for offset in range(length):
        t = offset / rate
        envelope = math.sin(math.pi * min(1.0, t / duration)) ** 2
        smoothed = smoothed * 0.86 + rng.uniform(-1, 1) * 0.14
        sample = smoothed * gain * envelope
        left[begin + offset] += sample * 0.8
        right[begin + offset] += sample * 0.6


def _reverb(left: list[float], right: list[float], rate: int) -> None:
    """Cheap multi-tap space: one dry copy per channel, four decaying taps."""
    dry_left, dry_right = left[:], right[:]
    for dry, channel, taps in (
        (dry_left, left, [(97, 0.20), (151, 0.14), (211, 0.09), (307, 0.06)]),
        (dry_right, right, [(113, 0.20), (173, 0.14), (239, 0.09), (331, 0.06)]),
    ):
        for milliseconds, gain in taps:
            delay = int(rate * milliseconds / 1000)
            for index in range(delay, len(channel)):
                channel[index] += dry[index - delay] * gain


def _finish(left: list[float], right: list[float], seconds: float, rate: int,
            volume: float = DEFAULT_VOLUME) -> None:
    peak = max(max(abs(value) for value in left), max(abs(value) for value in right), 1e-9)
    scale = (0.72 / peak) * (volume / DEFAULT_VOLUME)
    fade_in_end = min(len(left), int(FADE_IN * rate))
    fade_out_start = max(0, len(left) - int(min(FADE_OUT, seconds / 3) * rate))
    for index in range(len(left)):
        value = scale
        if index < fade_in_end:
            value *= index / fade_in_end
        if index >= fade_out_start:
            value *= max(0.0, (len(left) - index) / (len(left) - fade_out_start))
        left[index] *= value
        right[index] *= value


def write_wav(path: Path, left: list[float], right: list[float], rate: int) -> None:
    data = array("h")
    append = data.append
    for lvalue, rvalue in zip(left, right):
        append(_pcm(lvalue))
        append(_pcm(rvalue))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(CHANNELS)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(data.tobytes())


def _pcm(value: float) -> int:
    return max(-32768, min(32767, int(value * 32767)))


def _hz(midi: int) -> float:
    return 440.0 * (2 ** ((midi - 69) / 12))


def metadata(request: MusicRequest, storyboard: Storyboard, bed: Path, mix: Path | None,
             voice: bool) -> dict:
    cue = _CUES.get(storyboard.pack or "editorial-ink", _DEFAULT_CUE)
    data = {
        "source": request.source,
        "pack": storyboard.pack or "editorial-ink",
        "seconds": round(storyboard.frames() / storyboard.fps, 3),
        "bed": str(bed.relative_to(bed.parent.parent)),
        "mix": str(mix.relative_to(mix.parent.parent)) if mix else None,
        "voice": voice,
        "ducked": bool(voice),
    }
    if request.file is not None:
        data["file"] = str(request.file)
    else:
        data.update({
            "key": cue["key"],
            "tempo": cue["tempo"],
            "license": "generated in-repo (no external samples)",
        })
    return data


