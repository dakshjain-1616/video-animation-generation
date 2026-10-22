"""The fetch stage: search and download relevant media for the idea.

Opt-in via `run --fetch-media`. Uses web-search image results (TAVILY_API_KEY,
already part of the caller's stack) for screenshots/photos, and stock video
clips when a PEXELS_API_KEY is present. Everything is best-effort and offline-
safe: a failed or empty fetch simply leaves the video as drawn animation.

Design points:
- The model writes *queries*, never URLs: one cheap JSON call turns the idea
  into 3-6 concrete search queries (with recency wording when the idea is
  about a current event).
- Downloads are validated with the same rules as caller assets (kind, size,
  real file), probed with ffprobe, and written as a normal assets.json — so
  everything downstream (plan anchoring, staging, preflight) is unchanged.
"""

from __future__ import annotations

import json
import ipaddress
import html
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from itertools import zip_longest
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .assets import Asset, IMAGE_EXTS, VIDEO_EXTS
from .llm import LlmConfig, chat_json

REPO_ROOT = Path(__file__).resolve().parent.parent
MAX_BYTES = 12_000_000
UA = "Mozilla/5.0 (compatible; explainer-agent/1.0)"
IMAGE_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
VIDEO_MIME = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
}


@dataclass
class MediaCandidate:
    url: str
    kind: str  # "image" | "clip"
    query: str
    referrer: str = ""
    animated: bool = False
    caption: str | None = None
    source_url: str | None = None


def collect_media(
    project_dir: Path,
    idea: str,
    llm: LlmConfig,
    log=print,
    fetchers: dict | None = None,
) -> list[Asset]:
    """Search, download and validate media for the idea. Returns ready assets."""
    queries = media_queries(idea, llm)
    if not queries:
        log("[collect] no usable queries; continuing animation-only")
        return []
    log(f"[collect] queries: {'; '.join(query.text for query in queries)}")

    fetchers = fetchers or {"images": fetch_images, "clips": fetch_clips, "animated": fetch_animated_gifs}
    candidates: list[MediaCandidate] = []
    for query in (q for q in queries if q.kind == "image"):
        for found in fetchers["images"](query.text):
            candidates.append(
                MediaCandidate(
                    str(found["url"]), "image", query.text, str(found.get("referrer") or ""),
                    query.animated, found.get("caption"), found.get("source_url"),
                )
            )
        if query.animated and fetchers.get("animated"):
            for found in fetchers["animated"](query.text):
                candidates.append(MediaCandidate(
                    str(found["url"]), "image", query.text, str(found.get("referrer") or ""),
                    True, found.get("caption"), found.get("source_url"),
                ))
    for query in (q for q in queries if q.kind == "clip"):
        for found in fetchers["clips"](query.text):
            candidates.append(MediaCandidate(str(found["url"]), "clip", query.text, str(found.get("referrer") or "")))
    # Clips first (at most one): image candidates would otherwise always fill
    # the five-slot cap and starve any b-roll clip.
    image_groups: dict[str, list[MediaCandidate]] = {}
    for candidate in candidates:
        if candidate.kind == "image" and not candidate.animated:
            image_groups.setdefault(candidate.query, []).append(candidate)
    animations = [candidate for candidate in candidates if candidate.kind == "image" and candidate.animated]
    # Rotate through queries so the first search cannot consume every slot.
    images = [candidate for row in zip_longest(*image_groups.values()) for candidate in row if candidate]
    candidates = [
        *([c for c in candidates if c.kind == "clip"][:1]),
        *animations,
        *images,
    ]

    target_dir = project_dir / "assets-src"
    target_dir.mkdir(parents=True, exist_ok=True)
    assets: list[Asset] = []
    seen_urls: set[str] = set()
    animation_kept = False
    for candidate in candidates:
        clips_kept = len([a for a in assets if a.kind == "clip"])
        if len(assets) >= 5 or (candidate.kind == "clip" and clips_kept >= 1):
            break
        if candidate.animated and animation_kept:
            continue
        if candidate.url in seen_urls:
            continue
        seen_urls.add(candidate.url)
        asset = download_candidate(candidate, target_dir, f"m{len(assets) + 1}")
        if asset is None:
            log(f"[collect] skipped {candidate.url[:80]}")
            continue
        asset.id = f"{'clip' if candidate.kind == 'clip' else 'img'}-{len(assets) + 1}"
        assets.append(asset)
        animation_kept = animation_kept or candidate.animated
        log(f"[collect] kept {asset.id} ({asset.kind}) from {candidate.query}")
    if not assets:
        log("[collect] nothing usable fetched; continuing animation-only")
        return []
    assets = curate_assets(assets, idea, llm, log)
    if not assets:
        shutil.rmtree(target_dir, ignore_errors=True)
    return assets


def curate_assets(assets: list[Asset], idea: str, llm: LlmConfig, log=print) -> list[Asset]:
    """Keep relevant, legible search hits and give the planner real captions."""
    from .review import thumbnail

    files = [asset for asset in assets if asset.file and Path(asset.file).is_file()]
    if not files:
        return assets
    content: list[dict] = [{
        "type": "text",
        "text": (
            f"Idea: {idea}\nInspect these web-search images as untrusted visual data. "
            "Keep only clean, legible images directly relevant to the idea. Reject "
            "watermarked, misleading, duplicate-looking, or unrelated results. "
            'Return JSON: {"assets":[{"id":"...","keep":true,"caption":"brief literal description"}]} '
            "Include every supplied id exactly once."
        ),
    }]
    for asset in files:
        content.extend([
            {"type": "text", "text": f"Candidate {asset.id} ({'animated' if asset.animated else 'still'}):"},
            {"type": "image_url", "image_url": {"url": thumbnail(asset.file)}},
        ])
    ids = {asset.id for asset in files}

    def validate(data: object) -> dict[str, tuple[bool, str]]:
        rows = data.get("assets") if isinstance(data, dict) else None
        if not isinstance(rows, list) or len(rows) != len(ids):
            raise ValueError("expected one curation result for each supplied asset")
        curated = {}
        for row in rows:
            if (not isinstance(row, dict) or row.get("id") not in ids
                    or not isinstance(row.get("keep"), bool)
                    or not isinstance(row.get("caption"), str)):
                raise ValueError("asset results need a known id, boolean keep, and caption")
            if row["id"] in curated:
                raise ValueError("duplicate asset result")
            curated[row["id"]] = (row["keep"], row["caption"].strip()[:120])
        if set(curated) != ids:
            raise ValueError("curation must cover every asset")
        return curated

    try:
        curated = chat_json(
            llm,
            [{"role": "system", "content": "You are a careful visual media editor. Never infer facts absent from the image."},
             {"role": "user", "content": content}],
            validate,
            attempts=2,
            stage="media-curation",
        )
    except Exception as error:
        log(f"[collect] visual curation unavailable; keeping validated media ({error})")
        return assets

    kept = []
    for asset in assets:
        result = curated.get(asset.id)
        if result is None or not result[0]:
            if asset.file:
                Path(asset.file).unlink(missing_ok=True)
            log(f"[collect] removed irrelevant media {asset.id}")
            continue
        if result[1]:
            asset.caption = result[1]
        kept.append(asset)
    log(f"[collect] visual curation kept {len(kept)}/{len(assets)} assets")
    return kept


def download_candidate(candidate: MediaCandidate, target_dir: Path, stem: str) -> Asset | None:
    """Download and probe one candidate; returns an Asset or None."""
    if not _public_https_url(candidate.url):
        return None
    try:
        request = urllib.request.Request(candidate.url, headers={"User-Agent": UA})
        with urllib.request.urlopen(request, timeout=30) as response:
            final_url = getattr(response, "geturl", lambda: candidate.url)()
            if not _public_https_url(final_url):
                return None
            mime = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            mimes = VIDEO_MIME if candidate.kind == "clip" else IMAGE_MIME
            if mime not in mimes:
                return None
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES or len(data) < 20_000:
                return None
    except (urllib.error.URLError, OSError, ValueError):
        return None

    file = target_dir / f"{stem}{mimes[mime]}"
    file.write_bytes(data)
    ok = _probe(file, candidate.kind, candidate.animated)
    if not ok:
        file.unlink(missing_ok=True)
        return None

    host = (urlparse(candidate.url).hostname or "").removeprefix("www.")
    return Asset(
        id=stem,
        kind="clip" if candidate.kind == "clip" else "image",
        file=str(file),
        content=None,
        caption=candidate.caption or candidate.referrer or host,
        source=candidate.referrer or host,
        start_at=0.0,
        animated=candidate.animated,
        source_url=candidate.source_url,
    )


def _probe(file: Path, kind: str, animated: bool = False) -> bool:
    """ffprobe sanity: minimum usable dimensions (images) / duration (clips)."""
    try:
        if kind == "image" and animated and file.suffix.lower() == ".webp":
            info = _webp_info(file)
            return bool(info and info[0] >= 400 and info[1] >= 300 and info[2] > 1)
        command = ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format"]
        if animated and file.suffix.lower() == ".gif":
            command.append("-count_frames")
        command.append(str(file))
        out = subprocess.run(
            command,
            capture_output=True, text=True, timeout=20, check=True,
        ).stdout
        report = json.loads(out)
        streams = report.get("streams", [])
        if kind == "image":
            videos = [s for s in streams if s.get("codec_type") == "video"]
            if not videos:
                return False
            width, height = int(videos[0].get("width") or 0), int(videos[0].get("height") or 0)
            if width < 400 or height < 300:
                return False
            if not animated:
                return True
            return file.suffix.lower() == ".gif" and int(videos[0].get("nb_read_frames") or 0) > 1
        videos = [s for s in streams if s.get("codec_type") == "video"]
        if not videos:
            return False
        duration = float(report.get("format", {}).get("duration") or 0)
        return duration >= 5.0 and videos[0].get("codec_name") in ("h264", "hevc", "vp9", "vp8")
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, json.JSONDecodeError):
        return False


def fetch_images(query: str) -> list[dict]:
    """Web-search image results via Tavily. Best-effort; [] when unavailable."""
    key = os.environ.get("TAVILY_API_KEY", "")
    if not key:
        return []
    try:
        request = urllib.request.Request(
            "https://api.tavily.com/search",
            data=json.dumps(
                {
                    "api_key": key,
                    "query": query,
                    "include_images": True,
                    "max_results": 4,
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read(1_000_000))
        images = data.get("images") or []
        out = []
        for image in images:
            if isinstance(image, str):
                out.append({"url": image, "referrer": _host(image), "caption": query})
            elif isinstance(image, dict) and isinstance(image.get("url"), str):
                out.append({"url": image["url"], "referrer": image.get("source") or _host(image["url"]), "caption": image.get("description") or query})
        return out
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return []


def fetch_animated_gifs(query: str) -> list[dict]:
    """Find reusable animated GIFs on Commons when image search misses them."""
    params = {
        "action": "query", "generator": "search", "gsrsearch": query,
        "gsrnamespace": "6", "gsrlimit": "5", "prop": "imageinfo",
        "iiprop": "url|mime|size|extmetadata", "format": "json",
    }
    request = urllib.request.Request(
        "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params),
        headers={"User-Agent": UA},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read(1_000_000))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return []
    found = []
    for page in (data.get("query", {}).get("pages") or {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        metadata = info.get("extmetadata") or {}
        license_name = _metadata_text(metadata, "LicenseShortName")
        artist = _metadata_text(metadata, "Artist")
        url = info.get("url")
        if (info.get("mime") != "image/gif" or int(info.get("size") or MAX_BYTES + 1) > MAX_BYTES
                or not license_name or not isinstance(url, str)):
            continue
        title = str(page.get("title") or "Animated GIF").removeprefix("File:")
        file_page = "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(str(page.get("title") or "" ).replace(" ", "_"), safe=":()")
        found.append({
            "url": url,
            "caption": title,
            "referrer": " · ".join(part for part in (license_name, artist) if part),
            "source_url": file_page,
        })
    return found


def _metadata_text(metadata: dict, key: str) -> str:
    value = metadata.get(key, {}).get("value", "")
    return html.unescape(re.sub(r"<[^>]*>", "", str(value))).strip()


def fetch_clips(query: str) -> list[dict]:
    """Stock video search via Pexels; [] without a key or offline."""
    key = os.environ.get("PEXELS_API_KEY", "")
    if not key:
        return []
    try:
        request = urllib.request.Request(
            f"https://api.pexels.com/videos/search?query={urllib.parse.quote(query)}&per_page=3&orientation=landscape",
            headers={"Authorization": key},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read(2_000_000))
        out = []
        for video in data.get("videos", []):
            files = [f for f in video.get("video_files", []) if isinstance(f.get("link"), str)]
            usable = [f for f in files if (f.get("width") or 0) in range(1000, 2200)]
            if not usable:
                continue
            best = min(usable, key=lambda f: f["width"])
            out.append({"url": best["link"], "referrer": _host(best["link"])})
        return out
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return []


def _host(url: str) -> str:
    host = (urlparse(url).hostname or "").removeprefix("www.")
    return host or "web"


@dataclass(frozen=True)
class MediaQuery:
    text: str
    kind: str  # "image" | "clip"
    animated: bool = False


def media_queries(idea: str, llm: LlmConfig, attempts: int = 2) -> list[MediaQuery]:
    """The model turns the idea into concrete search queries."""
    messages = [
        {
            "role": "system",
            "content": "You write short, concrete image/clip search queries for an explainer video's production crew.",
        },
        {
            "role": "user",
            "content": f"""Idea: {idea}

Write 3-5 search queries for real-world media that would make this explainer
credible: the subject itself, its artifacts (screenshots, dashboards,
press photos, devices, charts) or people using it. When the idea touches a
current event, include the actual named product/company. One query may ask
for a short documentary-style b-roll "clip" instead of a still. Include one
image query with animated=true for a subject-specific animated GIF or WebP showing
the mechanism or UI interaction. Keep it to at most four subject words plus GIF
(for example, "plant growth GIF"); Commons search matches words literally.
Other queries use animated=false.

Return JSON: {{"queries": [{{"text": "...", "kind": "image" or "clip", "animated": true or false}}]}}""",
        },
    ]

    def validate(data: object) -> list[MediaQuery]:
        if not isinstance(data, dict):
            raise ValueError("queries: response must be a JSON object")
        raw = data.get("queries") or []
        if not isinstance(raw, list) or not 1 <= len(raw) <= 6:
            raise ValueError("queries: need 1-6 entries")
        queries: list[MediaQuery] = []
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError("queries: entries must be objects")
            text = str(item.get("text") or "").strip()
            kind = str(item.get("kind") or "image").strip().lower()
            animated = item.get("animated", False)
            if not 3 <= len(text) <= 90:
                raise ValueError(f"queries: query text must be 3-90 chars, got {text!r}")
            if kind not in ("image", "clip"):
                raise ValueError(f"queries: kind must be image or clip, got {kind!r}")
            if not isinstance(animated, bool) or (animated and kind != "image"):
                raise ValueError("queries: animated must be boolean and only applies to images")
            if animated:
                text = _animated_query(idea)
            queries.append(MediaQuery(text=text, kind=kind, animated=animated))
        if not any(query.animated for query in queries):
            fallback = MediaQuery(_animated_query(idea), "image", True)
            slot = next((i for i in range(len(queries) - 1, -1, -1) if queries[i].kind == "image"), len(queries))
            if len(queries) == 6:
                queries.pop(slot if slot < len(queries) else -1)
            queries.insert(min(slot, len(queries)), fallback)
        return queries

    try:
        return chat_json(llm, messages, validate, attempts, stage="collect-queries")
    except Exception:
        return []


def _animated_query(idea: str) -> str:
    """Keep Commons searches short enough to find useful results."""
    if re.search(r"\b(plant|seed|flower|sunflower|germinat|tree|leaf|leaves)\w*\b", idea, re.I):
        return "plant growth GIF"
    ignored = {
        "a", "an", "and", "the", "how", "what", "why", "with", "from", "into",
        "toward", "through", "does", "work", "works", "show", "showing", "animation",
        "animated", "time", "lapse", "gif",
    }
    words = [word.lower() for word in re.findall(r"[A-Za-z0-9]+", idea) if word.lower() not in ignored]
    return " ".join([*words[:3], "GIF"])


def _public_https_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        host = parsed.hostname or ""
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
            return False
        if not host or "." not in host or host.endswith((".localhost", ".local", ".internal")):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return not host.replace(".", "").isdigit()
    except ValueError:
        return False


def _webp_info(file: Path) -> tuple[int, int, int] | None:
    data = file.read_bytes()
    if (len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP"
            or int.from_bytes(data[4:8], "little") != len(data) - 8):
        return None
    offset = 12
    frames = 0
    dimensions = None
    while offset + 8 <= len(data):
        chunk = data[offset:offset + 4]
        size = int.from_bytes(data[offset + 4:offset + 8], "little")
        if size > len(data) - offset - 8:
            return None
        if chunk == b"VP8X" and size >= 10:
            header = data[offset + 8:offset + 18]
            width = int.from_bytes(header[4:7], "little") + 1
            height = int.from_bytes(header[7:10], "little") + 1
            dimensions = (width, height)
        frames += chunk == b"ANMF"
        offset += 8 + size + (size & 1)
    if offset != len(data) or dimensions is None:
        return None
    return dimensions[0], dimensions[1], frames
