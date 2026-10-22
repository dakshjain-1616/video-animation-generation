"""Renderer client.

The Node side is a service, not a dependency of the agent's logic: hand it a
storyboard file (whose `entry` names the generated Remotion component) and it
returns an MP4 plus a duration report on stdout.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .llm import InfraError

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDERER = REPO_ROOT / "renderer" / "render.mjs"


class ServiceMissing(InfraError):
    """The render service itself is unusable: not a generated-code failure."""

    pass


class RenderError(RuntimeError):
    """The composition failed while rendering: usually generated-code bugs."""


def _run(args: list[str], timeout: int = 1800) -> dict:
    if shutil.which("npx") is None:
        raise ServiceMissing("npx not found: the renderer needs Node installed")
    if not RENDERER.exists():
        raise ServiceMissing(f"renderer entry missing: {RENDERER}")

    result = subprocess.run(
        ["npx", "tsx", str(RENDERER), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    report = _last_json(result.stdout)
    # A duration-gate failure exits nonzero but still writes the full report;
    # keep it so the caller can persist duration and QA instead of losing
    # the measurement behind a generic render error.
    if report is not None and report.get("ok"):
        return report
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()[-6:]
        raise RenderError("render failed: " + " | ".join(detail))
    raise ServiceMissing(f"renderer produced no JSON: {result.stdout[-300:]}")


def _last_json(stdout: str) -> dict | None:
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
    return None


def _storyboard_args(storyboard_path: str) -> list[str]:
    entry = read_entry(storyboard_path)
    return ["--storyboard", str(storyboard_path), "--entry", entry]


def read_entry(storyboard_path: str) -> str:
    """The generated Remotion entry for a storyboard, asserted to exist."""
    data = json.loads(Path(storyboard_path).read_text(encoding="utf-8"))
    entry = str(data.get("entry", "")).strip()
    if not entry:
        raise ServiceMissing(f"{storyboard_path} has no entry field")
    if not (REPO_ROOT / entry).exists():
        raise ServiceMissing(f"entry {entry} is missing; run the codegen stage again")
    return entry


def render_storyboard(storyboard_path: str, out: str, crf: int | None = None) -> dict:
    args = [*_storyboard_args(storyboard_path), "--out", str(out)]
    if crf:
        args += ["--crf", str(crf)]
    result = _run(args)
    board = json.loads(Path(storyboard_path).read_text(encoding="utf-8"))
    for key in ("width", "height", "fps"):
        expected = board.get(key)
        actual = result.get(key)
        if expected is not None and actual is not None and abs(float(actual) - float(expected)) > 0.01:
            raise RenderError(
                f"render {key} {actual} does not match storyboard {expected}; "
                "the entry points at the wrong composition"
            )
    return result


def render_stills(storyboard_path: str, frames: list[int], stills_dir: str) -> list[str]:
    args = [*_storyboard_args(storyboard_path), "--frames", ",".join(str(frame) for frame in frames), "--stills-dir", str(stills_dir)]
    return _run(args, timeout=900).get("stills", [])


def renderer_available() -> tuple[bool, str]:
    if shutil.which("npx") is None:
        return False, "npx not found"
    if not RENDERER.exists():
        return False, f"missing {RENDERER}"
    return True, "node renderer ready"
