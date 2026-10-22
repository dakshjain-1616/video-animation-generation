"""Offline tests for LLM usage accounting (vga.llm)."""

import json

import pytest

from vga import llm
from vga.llm import LlmConfig, chat_json, reset_usage, set_usage_sink, usage_summary

CONFIG = LlmConfig("openai", "anthropic/claude-haiku-5.5", "k", "https://x/v1")


class _Response:
    def __init__(self, data: dict):
        self._data = data

    def read(self):
        import json

        return json.dumps(self._data).encode()


def _fake_post(monkeypatch, usage: dict, calls: list):
    def fake_post(url, payload, headers, timeout=180):
        calls.append(payload)
        return {
            "choices": [{"message": {"content": '{"ok": true}'}},
                        ],
            "usage": usage,
        }

    monkeypatch.setattr(llm, "_post", fake_post)


def test_usage_captured_per_call(monkeypatch):
    reset_usage()
    calls: list = []
    _fake_post(monkeypatch, {"prompt_tokens": 3000, "completion_tokens": 1500}, calls)

    result = chat_json(CONFIG, [{"role": "user", "content": "plan"}], lambda data: data, stage="plan")
    assert result == {"ok": True}
    summary = usage_summary()
    assert summary["calls"] == 1
    assert summary["input_tokens"] == 3000
    assert summary["output_tokens"] == 1500
    # haiku-5.5: $0.10/M in, $0.50/M out.
    expected = (3000 * 0.10 + 1500 * 0.50) / 1_000_000
    assert summary["estimated_usd"] == pytest.approx(expected, rel=1e-3)
    assert summary["items"][0]["stage"] == "plan"
    assert summary["items"][0]["model"] == "anthropic/claude-haiku-5.5"


def test_usage_repair_rounds_are_separate_entries(monkeypatch):
    reset_usage()
    calls: list = []
    state = {"n": 0}

    def fake_post(url, payload, headers, timeout=180):
        state["n"] += 1
        calls.append(payload)
        content = '{"bad": 1}' if state["n"] == 1 else '{"good": true}'
        return {
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 1000 * state["n"], "completion_tokens": 500},
        }

    monkeypatch.setattr(llm, "_post", fake_post)

    def validate(data):
        if "good" not in data:
            raise ValueError("wrong shape")
        return data

    chat_json(CONFIG, [{"role": "user", "content": "x"}], validate, stage="codegen")
    summary = usage_summary()
    assert summary["calls"] == 2
    assert summary["input_tokens"] == 3000  # 1000 + 2000 (repair replays the draft)
    assert summary["estimated_usd"] is not None


def test_usage_missing_field_is_tolerated(monkeypatch):
    reset_usage()
    calls: list = []

    def fake_post(url, payload, headers, timeout=180):
        calls.append(payload)
        return {"choices": [{"message": {"content": '{"ok": 1}'}}]}

    monkeypatch.setattr(llm, "_post", fake_post)
    chat_json(CONFIG, [{"role": "user", "content": "x"}], lambda d: d)
    summary = usage_summary()
    assert summary["calls"] == 0  # nothing recorded without a usage block
    assert summary["input_tokens"] == 0


def test_price_overrides_env(monkeypatch):
    monkeypatch.setenv("VGA_PRICE_INPUT", "3.0")
    monkeypatch.setenv("VGA_PRICE_OUTPUT", "15.0")
    assert llm._prices("some/unknown-model") == (3.0, 15.0)
    assert llm._prices("anthropic/claude-haiku-5.5") == (3.0, 15.0)
    monkeypatch.delenv("VGA_PRICE_INPUT")
    monkeypatch.delenv("VGA_PRICE_OUTPUT")
    assert llm._prices("anthropic/claude-haiku-5.5") == (0.10, 0.50)
    assert llm._prices("anthropic/claude-haiku-4.5") == (1.00, 5.00)


def test_sink_persists_usage_before_the_run_finishes(monkeypatch, tmp_path):
    reset_usage()
    sink = tmp_path / "usage.json"
    set_usage_sink(sink)
    calls: list = []
    _fake_post(monkeypatch, {"prompt_tokens": 100, "completion_tokens": 20}, calls)
    chat_json(CONFIG, [{"role": "user", "content": "x"}], lambda d: d)
    written = json.loads(sink.read_text())
    assert written["calls"] == 1
    assert written["input_tokens"] == 100
    reset_usage()  # also clears the sink


def test_reset_clears(monkeypatch):
    reset_usage()
    calls: list = []
    _fake_post(monkeypatch, {"prompt_tokens": 10, "completion_tokens": 5}, calls)
    chat_json(CONFIG, [{"role": "user", "content": "x"}], lambda d: d)
    assert usage_summary()["calls"] == 1
    reset_usage()
    assert usage_summary()["calls"] == 0
