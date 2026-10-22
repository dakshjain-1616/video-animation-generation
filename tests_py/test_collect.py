"""Offline tests for the media-fetch stage (vga.collect).

No network: queries and downloads are faked with injectable stand-ins.
Covers query validation, caps/diversity/id assignment in collect_media, and
the graceful "nothing fetched" path.
"""

import json
from pathlib import Path

import pytest

from vga import collect
from vga.assets import Asset
from vga.collect import MediaQuery, collect_media, download_candidate, media_queries


class _FakeLlm:
    """chat_json is monkeypatched around each test; config is never used."""


def _patch_queries(monkeypatch, raw):
    def fake_chat_json(config, messages, validate, attempts=2, stage=""):
        if raw is None:
            raise ValueError("bad")
        return validate(raw)

    monkeypatch.setattr(collect, "chat_json", fake_chat_json)


def test_media_queries_parses_and_normalizes(monkeypatch):
    raw = {
        "queries": [
            {"text": "agent dashboard screenshot", "kind": "image", "animated": False},
            {"text": "datacenter b-roll", "kind": " CLIP ", "animated": False},
            {"text": "agent workflow animated GIF", "kind": "image", "animated": True},
        ]
    }
    _patch_queries(monkeypatch, raw)
    queries = media_queries("idea", _FakeLlm())
    assert [q.kind for q in queries] == ["image", "clip", "image"]
    assert queries[1].text == "datacenter b-roll"
    assert queries[2].animated


def test_media_queries_adds_animated_search_when_model_omits_it(monkeypatch):
    _patch_queries(monkeypatch, {"queries": [{"text": "plant leaves", "kind": "image"}]})
    queries = media_queries("how a plant grows", _FakeLlm())
    assert len(queries) == 2
    assert queries[0].animated
    assert queries[0].text == "plant growth GIF"


def test_media_queries_rejects_bad_shape(monkeypatch):
    _patch_queries(monkeypatch, {"queries": [{"text": "x", "kind": "podcast"}]})
    assert media_queries("idea", _FakeLlm()) == []
    _patch_queries(monkeypatch, {"queries": []})
    assert media_queries("idea", _FakeLlm()) == []


def _fake_asset(index: int, kind: str) -> Asset:
    return Asset(id=f"m{index}", kind=kind, file=f"/tmp/fake-{index}.jpg")


def test_collect_media_caps_and_ids(monkeypatch, tmp_path: Path):
    queries = [MediaQuery(text="dashboard screenshot", kind="image")]
    monkeypatch.setattr(collect, "media_queries", lambda idea, llm, attempts=2: queries)

    # Two identical urls per fetch: dedupe must collapse them.
    monkeypatch.setattr(
        collect, "fetch_images", lambda query: [{"url": "https://x/1.png", "referrer": "x.com"}] * 2
    )
    downloaded: list[str] = []

    def fake_download(candidate, target_dir, stem):  # signature matches download_candidate
        downloaded.append(candidate.url)
        return _fake_asset(len(downloaded), candidate.kind)

    monkeypatch.setattr(collect, "download_candidate", fake_download)

    assets = collect_media(tmp_path, "about dashboards", _FakeLlm(), log=lambda *_: None)
    assert len(assets) == 1  # deduped
    assert assets[0].id == "img-1"
    assert assets[0].file is not None
    assert not (tmp_path / "assets-src" / "assets.json").exists()


def test_collect_media_respects_caps(monkeypatch, tmp_path: Path):
    queries = [
        MediaQuery(text="query one", kind="image"),
        MediaQuery(text="query two", kind="image"),
        MediaQuery(text="b-roll", kind="clip"),
    ]
    monkeypatch.setattr(collect, "media_queries", lambda idea, llm, attempts=2: queries)
    monkeypatch.setattr(
        collect,
        "fetch_images",
        lambda query: [{"url": f"https://x/{query}-{i}.png", "referrer": "x.com"} for i in range(4)],
    )
    monkeypatch.setattr(
        collect, "fetch_clips", lambda query: [{"url": "https://x/clip.mp4", "referrer": "x.com"}]
    )
    kept: list[tuple[str, str]] = []

    def fake_download(candidate, target_dir, stem):
        kept.append((candidate.kind, candidate.url))
        return _fake_asset(len(kept) + 10, candidate.kind)

    monkeypatch.setattr(collect, "download_candidate", fake_download)

    assets = collect_media(tmp_path, "idea", _FakeLlm(), log=lambda *_: None)
    kinds = [a.kind for a in assets]
    # Hard caps: at most 5 assets total, exactly one clip, clip kept first so
    # image candidates can never starve it.
    assert len(assets) == 5
    assert kinds[0] == "clip"
    assert all(kind == "image" for kind in kinds[1:])
    ids = [a.id for a in assets]
    assert len(set(ids)) == 5  # unique ids


def test_collect_media_empty_is_silent_success(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(collect, "media_queries", lambda idea, llm, attempts=2: [])
    logs = []
    assert collect_media(tmp_path, "idea", _FakeLlm(), log=logs.append) == []
    assert not (tmp_path / "assets-src" / "assets.json").exists()


def test_curate_assets_drops_bad_hits_and_describes_kept_media(monkeypatch, tmp_path: Path):
    from vga.collect import curate_assets

    good = tmp_path / "good.jpg"
    bad = tmp_path / "bad.jpg"
    good.write_bytes(b"visual")
    bad.write_bytes(b"visual")
    assets = [
        Asset(id="img-1", kind="image", file=str(good)),
        Asset(id="img-2", kind="image", file=str(bad)),
    ]
    monkeypatch.setattr("vga.review.thumbnail", lambda path: f"image:{path}")

    def curated(config, messages, validate, **kwargs):
        content = messages[1]["content"]
        assert sum(row["type"] == "image_url" for row in content) == 2
        return validate({"assets": [
            {"id": "img-1", "keep": True, "caption": "Seedling roots in soil"},
            {"id": "img-2", "keep": False, "caption": "Watermarked unrelated diagram"},
        ]})

    monkeypatch.setattr(collect, "chat_json", curated)
    kept = curate_assets(assets, "How a seed grows", _FakeLlm(), log=lambda *_: None)
    assert [asset.id for asset in kept] == ["img-1"]
    assert kept[0].caption == "Seedling roots in soil"
    assert good.exists() and not bad.exists()


def test_download_candidate_writes_and_probes(monkeypatch, tmp_path: Path):
    from vga.collect import MediaCandidate

    class FakeResponse:
        def __init__(self, data: bytes):
            self.headers = {"Content-Type": "image/png"}
            self._data = data

        def read(self, limit):
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    data = b"\x89PNG\r\n\x1a\n" + b"0" * 30_000
    monkeypatch.setattr(collect.urllib.request, "urlopen", lambda request, timeout=30: FakeResponse(data))

    def fake_probe(file, kind, animated=False):
        return kind == "image" and file.suffix == ".png" and not animated

    monkeypatch.setattr(collect, "_probe", fake_probe)
    asset = download_candidate(MediaCandidate("https://cdn.example.org/a/b.png", "image", "q"), tmp_path, "m1")
    assert asset is not None
    assert asset.kind == "image" and asset.source == "cdn.example.org"
    assert (tmp_path / "m1.png").exists()


def test_download_candidate_rejects_bad_type(monkeypatch, tmp_path: Path):
    from vga.collect import MediaCandidate

    class FakeResponse:
        headers = {"Content-Type": "text/html"}

        def read(self, limit):
            return b"<html></html>"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(collect.urllib.request, "urlopen", lambda request, timeout=30: FakeResponse())
    assert download_candidate(MediaCandidate("https://x.com/page", "image", "q"), tmp_path, "m1") is None


def test_collect_rotates_image_queries_for_visual_diversity(monkeypatch, tmp_path):
    monkeypatch.setattr(collect, 'media_queries', lambda *args: [MediaQuery('product UI', 'image'), MediaQuery('motion GIF', 'image')])
    monkeypatch.setattr(collect, 'fetch_images', lambda query: [{'url': f'https://x/{query}/{i}.gif'} for i in range(5)])
    used = []
    def download(candidate, directory, stem):
        used.append(candidate.query)
        return _fake_asset(len(used), 'image')
    monkeypatch.setattr(collect, 'download_candidate', download)
    collect_media(tmp_path, 'idea', _FakeLlm(), log=lambda *_: None)
    assert used == ['product UI', 'motion GIF', 'product UI', 'motion GIF', 'product UI']


def test_gif_mime_is_supported():
    from vga.assets import IMAGE_EXTS
    assert collect.IMAGE_MIME['image/gif'] == '.gif'
    assert '.gif' in IMAGE_EXTS


def test_animated_gif_probe_rejects_static_and_accepts_multiple_frames(monkeypatch, tmp_path):
    import json
    from types import SimpleNamespace

    image = tmp_path / "motion.gif"
    image.write_bytes(b"gif")
    def probe(frame_count):
        return SimpleNamespace(stdout=json.dumps({"streams": [{
            "codec_type": "video", "width": 400, "height": 300,
            "nb_read_frames": str(frame_count),
        }]}))
    monkeypatch.setattr(collect.subprocess, "run", lambda *args, **kwargs: probe(1))
    assert not collect._probe(image, "image", animated=True)
    monkeypatch.setattr(collect.subprocess, "run", lambda *args, **kwargs: probe(2))
    assert collect._probe(image, "image", animated=True)


def test_animated_webp_probe_checks_canvas_and_frame_count(tmp_path):
    from vga.collect import _webp_info

    vp8x = b"VP8X" + (10).to_bytes(4, "little") + bytes([0, 0, 0, 0]) + (399).to_bytes(3, "little") + (299).to_bytes(3, "little")
    frame = b"ANMF" + (16).to_bytes(4, "little") + bytes(16)
    chunks = vp8x + frame + frame
    image = tmp_path / "animated.webp"
    image.write_bytes(b"RIFF" + (len(chunks) + 4).to_bytes(4, "little") + b"WEBP" + chunks)
    assert _webp_info(image) == (400, 300, 2)
    assert collect._probe(image, "image", animated=True)


def test_media_download_rejects_private_and_non_https_urls(monkeypatch, tmp_path):
    from vga.collect import MediaCandidate
    monkeypatch.setattr(collect.urllib.request, "urlopen", lambda *args, **kwargs: pytest.fail("must not request"))
    assert download_candidate(MediaCandidate("http://example.com/a.gif", "image", "q"), tmp_path, "m1") is None
    assert download_candidate(MediaCandidate("https://127.0.0.1/a.gif", "image", "q"), tmp_path, "m1") is None
