"""Preflight: everything that can fail before a frame is rendered."""

from __future__ import annotations

from . import assets as assets_module
from .models import Storyboard, storyboard_issues
from .plan import MAX_TITLE_CHARS, Plan


def preflight(plan: Plan, storyboard: Storyboard, code_report: dict, assets=()) -> dict:
    errors: list[str] = list(storyboard_issues(storyboard))
    asset_list = list(assets or ())
    asset_ids = {asset.id for asset in asset_list}

    if not plan.title or not plan.angle:
        errors.append("plan: missing title or angle")
    for scene in plan.scenes:
        if not scene.title:
            errors.append(f"{scene.id}: empty scene title")
        elif len(scene.title) > MAX_TITLE_CHARS:
            errors.append(f"{scene.id}: scene title is {len(scene.title)} chars (max {MAX_TITLE_CHARS})")

    # Asset anchors resolve, and file-backed assets actually staged.
    for scene in storyboard.scenes:
        if scene.asset and scene.asset not in asset_ids:
            errors.append(f'{scene.id}: scene anchors on unknown asset "{scene.asset}"')
    for asset in asset_list:
        if asset.file and not asset.staged:
            errors.append(f"{asset.id}: file-backed asset was not staged for the render")
        elif asset.staged and not (assets_module.PUBLIC_ROOT / asset.staged).is_file():
            errors.append(f"{asset.id}: staged file is missing from public/ ({asset.staged})")

    frames_total = storyboard.frames()
    expected = round(storyboard.seconds() * storyboard.fps)
    if abs(frames_total - expected) > storyboard.fps // 2:
        errors.append(f"frames {frames_total} vs seconds*fps {expected} disagree by more than half a frame")

    scope = code_report or {}
    if not scope.get("pass"):
        errors.append("generated scene code did not pass its checks")

    notes: list[str] = []
    if scope.get("attempts", 0) > 1:
        notes.append(f"scene code was repaired on attempt {scope['attempts']}")
    notes.extend(scope.get("notes", []))
    used = {scene.asset for scene in storyboard.scenes if scene.asset}
    unused = sorted(asset_ids - used)
    if unused:
        notes.append("assets provided but not used: " + ", ".join(unused))

    return {"errors": sorted(set(errors)), "warnings": notes, "pass": not errors}
