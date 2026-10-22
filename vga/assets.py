"""The asset contract: caller-supplied media the explainer can anchor on.

`assets.json` is the integration surface for the larger system (or any user):

    [
      {
        "id": "tweet-1",
        "kind": "tweet",            // tweet | news | clip | image
        "file": "tweet-1.png",      // optional: real screenshot / footage
        "content": "text of the post or headline",   // alternative to file
        "caption": "@handle",       // optional attribution shown in the theme
        "source": "X · Oct 21",     // optional provenance line
        "startAt": 2.5              // optional, clip start offset in seconds
      }
    ]

Rules enforced here, never trusted from the model: ids are unique and sane,
every media asset resolves to something real (a file that exists or text to
reconstruct from), and file-backed assets are copied into `public/generated/`
so a render never touches the network.
"""

from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_ROOT = REPO_ROOT / "public"

ASSET_KINDS = {"tweet", "news", "clip", "image"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
VIDEO_EXTS = {".mp4", ".webm", ".mov"}
MAX_CONTENT_CHARS = 600
MAX_SOURCE_CHARS = 60


class AssetsError(ValueError):
    pass


@dataclass
class Asset:
    id: str
    kind: str
    file: str | None = None
    content: str | None = None
    caption: str | None = None
    source: str | None = None
    start_at: float = 0.0
    staged: str | None = None  # public/-relative path once copied
    animated: bool = False
    source_url: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "file": self.file,
            "content": self.content,
            "caption": self.caption,
            "source": self.source,
            "startAt": self.start_at,
            "staged": self.staged,
            "animated": self.animated,
            "sourceUrl": self.source_url,
        }


def load_assets(spec: str) -> list[Asset]:
    """Load a manifest from an assets.json path, or a directory holding one."""
    path = Path(spec)
    if path.is_dir():
        path = path / "assets.json"
    if not path.exists():
        raise AssetsError(f"assets manifest not found: {path} (write assets.json or point at its directory)")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise AssetsError(f"{path}: invalid JSON ({error})") from error
    if not isinstance(data, list):
        raise AssetsError(f"{path}: assets.json must be a JSON array")
    base = path.parent
    assets: list[Asset] = []
    for index, item in enumerate(data):
        assets.append(_asset_from(item, base, path, index))
    _validate(assets, base)
    return assets


def _asset_from(item, base: Path, manifest: Path, index: int) -> Asset:
    if not isinstance(item, dict):
        raise AssetsError(f"{manifest}: asset #{index} must be an object")
    asset_id = str(item.get("id") or "").strip().lower()
    for key in ("file", "content", "caption", "source", "sourceUrl"):
        if item.get(key) is not None and not isinstance(item[key], str):
            raise AssetsError(f"{manifest}: asset #{index} {key} must be a string")
    if isinstance(item.get("startAt", 0), bool):
        raise AssetsError(f"{manifest}: asset #{index} startAt must be a non-negative number")
    try:
        start_at = float(item.get("startAt") or 0)
    except (TypeError, ValueError) as error:
        raise AssetsError(f"{manifest}: asset #{index} startAt must be a non-negative number") from error
    if not math.isfinite(start_at) or start_at < 0:
        raise AssetsError(f"{manifest}: asset #{index} startAt must be a finite non-negative number")
    asset = Asset(
        id=asset_id,
        kind=str(item.get("kind") or "").strip().lower(),
        file=item.get("file"),
        content=item.get("content"),
        caption=item.get("caption"),
        source=item.get("source"),
        start_at=start_at,
        animated=item.get("animated", False),
        source_url=item.get("sourceUrl"),
    )
    if asset.file:
        asset.file = str((base / asset.file).resolve())
    return asset


def _validate(assets: list[Asset], base: Path) -> None:
    seen: set[str] = set()
    for asset in assets:
        if not asset.id or not asset.id.replace("-", "").replace("_", "").isalnum():
            raise AssetsError(f"asset id {asset.id!r}: use letters, digits, dashes")
        if asset.id in seen:
            raise AssetsError(f"duplicate asset id {asset.id!r}")
        seen.add(asset.id)
        if asset.kind not in ASSET_KINDS:
            raise AssetsError(f"{asset.id}: kind must be one of {sorted(ASSET_KINDS)}")
        if asset.file:
            suffix = Path(asset.file).suffix.lower()
            expect = VIDEO_EXTS if asset.kind == "clip" else IMAGE_EXTS
            if asset.kind in ("clip",) and suffix not in VIDEO_EXTS:
                raise AssetsError(f"{asset.id}: clip needs one of {sorted(VIDEO_EXTS)}, got {suffix}")
            if asset.kind in ("tweet", "news", "image") and suffix not in expect:
                raise AssetsError(f"{asset.id}: {asset.kind} needs one of {sorted(expect)}, got {suffix}")
            if not Path(asset.file).exists():
                raise AssetsError(f"{asset.id}: file not found: {asset.file}")
        if not isinstance(asset.animated, bool):
            raise AssetsError(f"{asset.id}: animated must be true or false")
        if asset.animated and (not asset.file or Path(asset.file).suffix.lower() not in {".gif", ".webp"}):
            raise AssetsError(f"{asset.id}: animated assets need a GIF or WebP file")
        if not asset.file and not (asset.content or "").strip():
            raise AssetsError(f"{asset.id}: needs a file or content to reconstruct from")
        if asset.content and len(asset.content) > MAX_CONTENT_CHARS:
            asset.content = asset.content[:MAX_CONTENT_CHARS].rstrip() + "…"
        if asset.source and len(asset.source) > MAX_SOURCE_CHARS:
            asset.source = asset.source[:MAX_SOURCE_CHARS]
        if asset.kind == "clip" and not asset.file:
            raise AssetsError(f"{asset.id}: clip requires a file (nothing to reconstruct)")
        if asset.start_at < 0:
            raise AssetsError(f"{asset.id}: startAt must be >= 0")


def stage_assets(project_id: str, assets: list[Asset]) -> None:
    """Copy file-backed assets into public/generated/<id>/ for local-only bundling."""
    target = PUBLIC_ROOT / "generated" / project_id
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    for asset in assets:
        if not asset.file:
            continue
        suffix = Path(asset.file).suffix.lower()
        staged = target / f"{asset.id}{suffix}"
        shutil.copyfile(asset.file, staged)
        asset.staged = f"generated/{project_id}/{staged.name}"


def brief_lines(assets: list[Asset], for_code: bool = False) -> str:
    """Human-model-readable summary of what is available to anchor scenes on."""
    if not assets:
        return "No media assets were provided: every scene must be drawn animation."
    lines = []
    for asset in assets:
        kind = "animated image" if asset.animated else asset.kind
        media = (
            f' staged file (pass verbatim: asset="{asset.staged}")'
            if for_code and asset.staged
            else (f" file: {Path(asset.file).name}" if asset.file else " (no file: reconstruct as a themed card)")
        )
        head = f"- {asset.id} ({kind}: {asset.caption or 'no attribution'}){media}"
        if asset.source:
            head += f"  source: {asset.source}"
        if asset.content:
            head += f'\n  content: "{asset.content}"'
        if for_code and asset.kind == "clip":
            head += f"\n  startAt: {asset.start_at} (pass as startAt to MediaFrame)"
        lines.append(head)
    return "\n".join(lines)
