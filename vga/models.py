"""Typed artifacts and the storyboard contract.

The JSON these dataclasses emit is the integration contract with the Node
render service, so field names match the renderer schema exactly.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

Surface = Literal["paper", "night"]
Category = Literal["explainer"]

# Output formats: aspect -> (width, height). Shorts are vertical.
FORMATS = {"9:16": (1080, 1920), "16:9": (1920, 1080)}
DEFAULT_ASPECT = "9:16"

DURATION_TOLERANCE = 2.0
PLATFORM_MIN = 20.0
PLATFORM_MAX = 60.0

SCENE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,23}$")
# These collide with the exports and helpers of the generated code.
RESERVED_SCENE_IDS = {"scenes", "default", "sceneprops"}


@dataclass
class Scene:
    id: str
    title: str
    kind: Literal["open", "body", "close"]
    surface: Surface
    seconds: float
    frames: int = 0
    asset: str | None = None
    narration: str | None = None

    def to_dict(self) -> dict[str, Any]:
        scene: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "surface": self.surface,
            "seconds": round(self.seconds, 3),
            "frames": self.frames,
        }
        if self.asset:
            scene["asset"] = self.asset
        if self.narration:
            scene["narration"] = self.narration
        return scene


@dataclass
class Storyboard:
    id: str
    title: str
    category: Category
    target: float
    fps: int
    width: int
    height: int
    entry: str
    scenes: list[Scene]
    pack: str | None = None

    def to_dict(self) -> dict[str, Any]:
        storyboard: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "pack": self.pack or "editorial-ink",
            "target": self.target,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "entry": self.entry,
            "scenes": [scene.to_dict() for scene in self.scenes],
        }
        return storyboard

    def write(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2)
            handle.write("\n")

    def seconds(self) -> float:
        return sum(scene.frames / self.fps if scene.frames else scene.seconds for scene in self.scenes)

    def frames(self) -> int:
        return sum(scene.frames for scene in self.scenes)


def allowed_window(target: float) -> tuple[float, float]:
    return (max(PLATFORM_MIN, target - DURATION_TOLERANCE), min(PLATFORM_MAX, target + DURATION_TOLERANCE))


def duration_pass(actual: float, target: float) -> bool:
    low, high = allowed_window(target)
    return low <= actual <= high and abs(actual - target) <= DURATION_TOLERANCE


def storyboard_issues(storyboard: Storyboard) -> list[str]:
    """Structural checks that can fail before a frame is rendered."""
    issues: list[str] = []
    scenes = storyboard.scenes

    seen: set[str] = set()
    for i, scene in enumerate(scenes):
        if not SCENE_ID_RE.match(scene.id) or scene.id in RESERVED_SCENE_IDS:
            issues.append(f'{scene.id}: scene id must match [a-z][a-z0-9_]{{0,23}} and not be reserved')
        if scene.id in seen:
            issues.append(f"{scene.id}: duplicate scene id")
        seen.add(scene.id)
        if not 2.0 <= scene.seconds <= 5.0:
            issues.append(f"{scene.id}: duration {scene.seconds}s outside 2.0-5.0s")
        if scene.frames <= 0:
            issues.append(f"{scene.id}: frames must be positive")
        expected = "open" if i == 0 else ("close" if i == len(scenes) - 1 else "body")
        if scene.kind != expected:
            issues.append(
                f'{scene.id}: kind "{scene.kind}" should be "{expected}" for position {i + 1} of {len(scenes)}'
            )
        if i and scenes[i - 1].surface == "night" and scene.surface == "night":
            issues.append(f"{scene.id}: two night surfaces back to back")

    total = storyboard.seconds()
    if not duration_pass(total, storyboard.target):
        issues.append(f"storyboard totals {total:.2f}s, outside tolerance for target {storyboard.target:g}s")
    return issues
