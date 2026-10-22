"""Vision review: a model looks at the rendered frames, the way an editor would.

The pixel statistics in codegen.py prove a frame is not blank or unreadable;
they cannot tell a title card from a diagram, or overlapping labels from a
clean layout. This stage shows the mid-scene stills to a vision model with a
fixed rubric and turns clear defects into repair feedback for the code stage.

Only unambiguous defects fail a scene. If enabled review cannot run, final QA
records the missing review and fails so unverified output is not marked clean.
"""

from __future__ import annotations

import base64
import subprocess
from typing import Any

from .llm import LlmConfig, chat_json
from .models import Storyboard
from .plan import Plan

THUMB_WIDTH = 720

REVIEW_SYSTEM = """You are the art director of a motion-graphics studio reviewing
stills from an animated explainer. Each image is one scene, captured at its
early, midpoint and late states when supplied. Compare paired images for visible
progress and correct action outcomes. Judge each scene against the rubric
and flag only defects a viewer would notice at a glance. Do not nitpick drawing
details beyond the rubric; at most one problem per scene.

Rubric:
1. clipped: text or shapes cut off by the frame edge, or inside the unsafe
   top/bottom bands of a vertical frame (top 9% and bottom 18%).
2. overlap: labels or shapes overlapping each other so something is hard to read.
3. title-card: a body scene has only text, with no drawn visual that shows
   the idea. Typography-led open/close scenes are allowed.
4. mismatch: the drawing does not show what the scene's intended visual says,
   or a media artifact is unrelated to the claim the scene is making.
5. tiny: text so small it is unreadable on a phone.
6. repetitive: three consecutive body scenes reuse the same composition,
   framing and visual treatment with only labels changed. Theme consistency
   alone is fine; request a concrete different composition for the repeated scene.
7. motion: paired frames show the wrong state progression, a broken
   interaction, or an action that never reaches its intended visible outcome.
   Small intentional idle motion is fine after an action has completed.
8. empty: the intended mechanism is absent or the main visual is so small
   that the action cannot be followed. Canvas layouts may use intentional
   negative space around a clear, legible subject. Do not impose BodyScene
   occupancy rules or reject a composition solely for unused space.

Return JSON only."""


def review_scenes(
    storyboard: Storyboard,
    plan: Plan,
    stills: list[str],
    llm: LlmConfig,
    assets=(),
) -> list[str]:
    """Defect descriptions, one per flawed scene; empty when the frames pass."""
    asset_by_id = {asset.id: asset for asset in assets}
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": "Scenes, in order. For each image: intended visual, then the frame.\n"
            + f"Format: {storyboard.width}x{storyboard.height}.\n"
            'Return {"scenes": [{"id": "<scene id>", "verdict": "ok" | "fix", "problem": "<one sentence, '
            'naming the element and what to change; empty when ok>"}]}',
        }
    ]
    count = len(storyboard.scenes)
    if not count or len(stills) not in (count, 2 * count, 3 * count):
        raise ValueError("review requires one, two or three stills per scene")
    stride = len(stills) // count
    midpoint_stills = stills[1::3] if stride == 3 else stills[::stride]
    for index, (scene, planned, still) in enumerate(zip(storyboard.scenes, plan.scenes, midpoint_stills)):
        text = f'Scene {scene.id} ({scene.kind}, layout {planned.layout}) — "{scene.title}". Intended: {planned.visual or "n/a"}'
        if planned.motion:
            text += (f". Motion starts: {planned.motion['start']}. "
                     f"Required action: {planned.motion['action']}. "
                     f"Expected completed end by 75% (must be visible in the late frame): {planned.motion['end']}")
        asset = asset_by_id.get(scene.asset or "")
        if asset is not None:
            kind = "animated image" if asset.animated else asset.kind
            text += (
                f". Media artifact: {kind}"
                + (f' described as "{asset.caption}"' if asset.caption else "")
                + (f' from {asset.source}' if asset.source else "")
                + (f' — "{asset.content}"' if asset.content else "")
                + ". The artifact must be the large, legible protagonist."
            )
        content.append({"type": "text", "text": text})
        if stride == 3:
            content.append({"type": "text", "text": "Early state, at 15% of the scene:"})
            content.append({"type": "image_url", "image_url": {"url": thumbnail(stills[index * stride])}})
        content.append({"type": "text", "text": "Midpoint state:"})
        content.append({"type": "image_url", "image_url": {"url": thumbnail(still)}})
        if stride >= 2:
            content.append({"type": "text", "text": "Same scene near 85% of its duration:"})
            content.append({"type": "image_url", "image_url": {"url": thumbnail(stills[index * stride + stride - 1])}})

    ids = {scene.id for scene in storyboard.scenes}

    def validate(data: Any) -> list[str]:
        rows = data.get("scenes") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise ValueError('expected {"scenes": [...]}')
        problems = []
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or row.get("id") not in ids:
                raise ValueError("every row needs an id from the scene list")
            if row["id"] in seen or row.get("verdict") not in ("ok", "fix"):
                raise ValueError("each scene needs exactly one ok/fix verdict")
            seen.add(row["id"])
            if row.get("verdict") == "fix" and not str(row.get("problem", "")).strip():
                raise ValueError("fix verdict needs an actionable problem")
            if row.get("verdict") == "fix" and str(row.get("problem", "")).strip():
                problems.append(f"scene {row['id']} (art director): {str(row['problem']).strip()}")
        if seen != ids:
            raise ValueError("review must cover every scene exactly once")
        return problems

    messages = [{"role": "system", "content": REVIEW_SYSTEM}, {"role": "user", "content": content}]
    return chat_json(llm, messages, validate, attempts=2, stage="review")


def thumbnail(path: str) -> str:
    """A small JPEG data URL for a still: enough to judge layout, cheap to send."""
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-vf", f"scale={THUMB_WIDTH}:-2", "-frames:v", "1",
         "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "4", "-"],
        capture_output=True, check=True,
    )
    return "data:image/jpeg;base64," + base64.b64encode(result.stdout).decode("ascii")
