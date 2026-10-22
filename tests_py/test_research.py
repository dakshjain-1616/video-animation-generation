import json

import pytest

from vga import research


@pytest.mark.parametrize("url", ["http://example.com", "https://localhost", "https://127.0.0.1/a", "https://169.254.169.254", "https://user:pass@example.com", "https://example.local", "https://[::1]", "https://example.com:8080", "file:///tmp/a"])
def test_private_or_invalid_references_rejected(url):
    assert not research.public_reference_url(url)


def test_public_reference():
    assert research.public_reference_url("https://developer.example.com/docs")


def test_missing_key_persisted_without_model_call(monkeypatch, tmp_path):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr(research, "_queries", lambda *_: pytest.fail("unexpected model call"))
    report = research.research_visuals(tmp_path, "video idea", None)
    assert report["status"] == "unavailable"
    assert json.loads((tmp_path / "research.json").read_text()) == report
    assert "no reference material" in research.research_brief(report)


def test_search_normalizes_deduplicates_and_reports_partial(monkeypatch, tmp_path):
    monkeypatch.setenv("TAVILY_API_KEY", "fake")
    monkeypatch.setattr(research, "_queries", lambda *_: ["ui reference", "motion reference", "visual metaphor"])
    def search(query, key):
        if query == "motion reference":
            raise OSError("offline")
        return [{"url": "https://example.com/ref", "title": "x" * 500, "content": "y" * 2000},
                {"url": "https://127.0.0.1", "title": "local", "content": "no"}]
    monkeypatch.setattr(research, "_search", search)
    report = research.research_visuals(tmp_path, "video idea", None)
    assert report["status"] == "partial"
    assert len(report["sources"]) == 1
    assert len(report["sources"][0]["content"]) == 900
    assert len(report["sources"][0]["title"]) == 180
    assert "UNTRUSTED" in research.research_brief(report)


def test_network_request_and_size_cap(monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, size):
            assert size == research.MAX_RESPONSE_BYTES + 1
            return b"x" * size
    def open_request(request, timeout):
        assert request.full_url == "https://api.tavily.com/search"
        assert json.loads(request.data)["max_results"] == 3
        return Response()
    monkeypatch.setattr(research.urllib.request, "urlopen", open_request)
    with pytest.raises(ValueError, match="size limit"):
        research._search("query", "fake")


def test_query_validation(monkeypatch):
    def chat(config, messages, validate, **kwargs):
        assert kwargs["stage"] == "research-queries"
        with pytest.raises(ValueError): validate({"queries": ["one"]})
        with pytest.raises(ValueError): validate({"queries": ["duplicate query"] * 3})
        return validate({"queries": ["topic UI reference", "topic motion reference", "topic visual metaphor"]})
    monkeypatch.setattr(research, "chat_json", chat)
    assert len(research._queries("video idea", None)) == 3


def test_successful_network_results(monkeypatch, tmp_path):
    monkeypatch.setenv("TAVILY_API_KEY", "fake")
    monkeypatch.setattr(research, "_queries", lambda *_: ["one query", "two query", "three query"])
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, size):
            return json.dumps({"results": [{"url": "https://example.com/ref", "title": "A", "content": "A UI reference"}]}).encode()
    monkeypatch.setattr(research.urllib.request, "urlopen", lambda *a, **kw: Response())
    report = research.research_visuals(tmp_path, "video idea", None)
    assert report["status"] == "ok"
    assert len(report["sources"]) == 1
