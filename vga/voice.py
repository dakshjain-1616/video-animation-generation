"""Optional voice-over: script -> speech -> one audio track -> muxed into the video.

Off by default (`run --voice` turns it on). The script is written after timing,
so every scene's line is budgeted in words for its real length, and each line is
synthesized, measured and fitted into its scene. The track is exactly as long as
the video, so the duration gate is unaffected.

    storyboard (timed) -> script (LLM, word budgets) -> TTS per scene
                       -> fit + pad to scene length -> voice.m4a -> mux
"""

from __future__ import annotations

import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .llm import LlmConfig, chat_json
from .models import Storyboard
from .plan import Plan

# Conservative pace (typical speech is ~2.5 words/s) so lines fit without rushing.
WORDS_PER_SECOND = 2.2
LEAD_IN = 0.15  # silence before a line starts, seconds
TAIL = 0.25  # silence kept after a line, seconds
MAX_SPEEDUP = 1.15  # past this a line sounds rushed: shorten the script instead

DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
DEFAULT_TTS_MODEL = "eleven_multilingual_v2"
TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128"

SCRIPT_SYSTEM = """You write the voice-over for a short animated explainer. A calm,
clear narrator speaks over the picture; the picture shows what the words say.

Rules:
- One short line per scene, in scene order, as spoken language: contractions,
  short sentences, no lists, no stage directions, no emoji.
- The line says what the viewer is looking at and why it matters; it does not
  repeat the on-screen title word for word.
- Scene 1 is a hook, the last scene is the payoff the viewer would repeat.
- Never invent precise numbers or facts the idea did not provide.
- Hard word budget per scene (given in the brief). Stay under it.

Return JSON only."""


class VoiceError(RuntimeError):
    pass


def word_budget(seconds: float) -> int:
    return max(4, int((seconds - LEAD_IN - TAIL) * WORDS_PER_SECOND))


def api_key() -> str | None:
    return os.environ.get("ELEVENLABS_API_KEY") or None


def write_script(storyboard: Storyboard, plan: Plan, llm: LlmConfig) -> list[str]:
    """One spoken line per scene, each inside its word budget."""
    budgets = [word_budget(scene.seconds) for scene in storyboard.scenes]
    lines = "\n".join(
        f'{i + 1}. [{scene.kind}] on-screen: "{scene.title}" · picture: {planned.visual or "n/a"}'
        f" · {scene.seconds:.1f}s · max {budgets[i]} words"
        for i, (scene, planned) in enumerate(zip(storyboard.scenes, plan.scenes))
    )
    messages = [
        {"role": "system", "content": SCRIPT_SYSTEM},
        {
            "role": "user",
            "content": f"""Idea: {plan.idea}
Angle: {plan.angle}
Audience: {plan.audience}

Scenes:
{lines}

Return JSON: {{"narration": ["<line for scene 1>", "<line for scene 2>", ...]}}
with exactly {len(budgets)} lines.""",
        },
    ]

    def validate(data: Any) -> list[str]:
        narration = data.get("narration") if isinstance(data, dict) else None
        if not isinstance(narration, list) or len(narration) != len(budgets):
            raise ValueError(f'"narration" must be a list of exactly {len(budgets)} strings')
        for i, (line, budget) in enumerate(zip(narration, budgets), start=1):
            if not isinstance(line, str) or not line.strip():
                raise ValueError(f"line {i} is empty")
            words = len(line.split())
            if words > budget:
                raise ValueError(f"line {i} has {words} words, the budget for that scene is {budget}")
        return [line.strip() for line in narration]

    return chat_json(llm, messages, validate, stage="script")


def synthesize(text: str, out: Path, voice_id: str, key: str, model: str = DEFAULT_TTS_MODEL) -> None:
    """One line of text to an mp3 file, through ElevenLabs."""
    import json

    request = urllib.request.Request(
        TTS_URL.format(voice=voice_id),
        data=json.dumps({"text": text, "model_id": model}).encode("utf-8"),
        headers={"content-type": "application/json", "xi-api-key": key, "accept": "audio/mpeg"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            out.write_bytes(response.read())
    except urllib.error.HTTPError as error:
        raise VoiceError(f"TTS {error.code}: {error.read().decode('utf-8', 'replace')[:300]}") from error
    except urllib.error.URLError as error:
        raise VoiceError(f"TTS request failed: {error.reason}") from error


RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


def _synthesize_with_retry(text: str, out: Path, voice_id: str, key: str, attempts: int = 3) -> None:
    """One line, retried only for transient upstream failures (not bad keys)."""
    for attempt in range(1, attempts + 1):
        try:
            synthesize(text, out, voice_id, key)
            return
        except VoiceError as error:
            status = re.search(r"TTS (\d{3})", str(error))
            transient = status is not None and int(status.group(1)) in RETRYABLE_STATUS
            if attempt == attempts or not (transient or "request failed" in str(error)):
                raise
            time.sleep(0.5 * attempt)


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError as error:
        raise VoiceError(f"ffprobe could not read {path}: {result.stderr.strip()[-200:]}") from error


def speedup_needed(speech: float, seconds: float) -> float:
    """Tempo factor that makes `speech` fit inside a scene (1.0 = untouched)."""
    room = seconds - LEAD_IN - TAIL
    return max(1.0, speech / room)


def fit_to_scene(raw: Path, seconds: float, out: Path) -> None:
    """Lead-in silence, optional gentle speed-up, padded to exactly the scene length."""
    speed = speedup_needed(probe_duration(raw), seconds)
    if speed > MAX_SPEEDUP:
        raise VoiceError(
            f"{raw.name}: speech runs {speed:.2f}x too long for a {seconds:.1f}s scene; shorten the line"
        )
    filters = [f"atempo={speed:.4f}"] if speed > 1.0 else []
    filters += [f"adelay={int(LEAD_IN * 1000)}:all=1", "apad"]
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", ",".join(filters),
         "-ar", "44100", "-ac", "1", "-t", f"{seconds:.3f}", str(out)],
        check=True, capture_output=True,
    )


def build_track(storyboard: Storyboard, script: list[str], directory: Path, voice_id: str, key: str) -> Path:
    """Synthesize every line and join them into voice/voice.m4a, scene-aligned.

    Lines are independent, so synthesis runs in parallel (bounded) while the
    order of the joined track stays exactly the scene order.
    """
    voice_dir = directory / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)

    def one(item: tuple) -> Path:
        scene, line = item
        raw, fitted = voice_dir / f"{scene.id}.mp3", voice_dir / f"{scene.id}.wav"
        _synthesize_with_retry(line, raw, voice_id, key)
        fit_to_scene(raw, scene.frames / storyboard.fps, fitted)
        return fitted

    jobs = list(zip(storyboard.scenes, script))
    with ThreadPoolExecutor(max_workers=max(1, min(4, len(jobs)))) as pool:
        parts: list[Path] = list(pool.map(one, jobs))

    listing = voice_dir / "parts.txt"
    listing.write_text("".join(f"file '{part.name}'\n" for part in parts), encoding="utf-8")
    track = voice_dir / "voice.m4a"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-c:a", "aac", "-b:a", "160k", str(track)],
        check=True, capture_output=True,
    )
    return track


def mux(video: Path, track: Path) -> float:
    """Put the track under the video in place, keeping the video's exact length."""
    length = probe_duration(video)
    muxed = video.with_name("voiced.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(track),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-t", f"{length:.3f}", str(muxed)],
        check=True, capture_output=True,
    )
    muxed.replace(video)
    return probe_duration(video)
