"""LLM access.

OpenAI-compatible chat completions covers OpenAI, OpenRouter and most gateways.
Two request shapes share one loop:

- `chat_json`: structured planning output, validated by a callback, repaired
  once by feeding the validation error back to the model.
- `chat_text`: raw text (generated scene code). The same loop, without JSON
  extraction; the validator is the code contract plus a typecheck.

A failed model output never reaches disk or the renderer.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

INPUT_PRICE_OVERRIDES = ("VGA_PRICE_INPUT", "VGA_PRICE_OUTPUT")


class ProviderNotConfigured(RuntimeError):
    pass


class TruncatedOutput(RuntimeError):
    """The provider exhausted the output budget; request a compact full rewrite."""


@dataclass(frozen=True)
class LlmConfig:
    provider: str
    model: str
    api_key: str
    base_url: str
    max_tokens: int = 16000
    temperature: float = 0.6

    def describe(self) -> str:
        return f"{self.provider}:{self.model} via {self.base_url}"


def resolve_llm_config(env: dict[str, str] | None = None) -> LlmConfig | None:
    env = env or os.environ

    if env.get("VGA_LLM_API_KEY") and env.get("VGA_LLM_BASE_URL") and env.get("VGA_LLM_MODEL"):
        return LlmConfig(
            "openai",
            env["VGA_LLM_MODEL"],
            env["VGA_LLM_API_KEY"],
            env["VGA_LLM_BASE_URL"],
            int(env.get("VGA_LLM_MAX_TOKENS", 16000)),
            float(env.get("VGA_LLM_TEMPERATURE", 0.6)),
        )
    if env.get("OPENROUTER_API_KEY"):
        return LlmConfig(
            "openai",
            env.get("VGA_MODEL", "anthropic/claude-sonnet-5.5"),
            env["OPENROUTER_API_KEY"],
            "https://openrouter.ai/api/v1",
        )
    if env.get("OPENAI_API_KEY"):
        return LlmConfig(
            "openai",
            env.get("VGA_MODEL", "gpt-4.1"),
            env["OPENAI_API_KEY"],
            env.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )
    return None


def stage_config(config: LlmConfig, env_name: str, env: dict[str, str] | None = None) -> LlmConfig:
    """Use a stronger/cheaper model for one stage without changing the rest.

    Planning is cheap; codegen and vision review are where quality and repair
    cost concentrate. `VGA_CODEGEN_MODEL` / `VGA_REVIEW_MODEL` let a caller
    route only those stages without paying the stronger model on every call.
    """
    env = env or os.environ
    override = (env.get(env_name) or "").strip()
    return replace(config, model=override) if override else config


def extract_json(raw: str) -> Any:
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    candidate = fenced.group(1) if fenced else raw.strip()
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"No JSON object in model output: {candidate[:200]}")
    return json.loads(candidate[start : end + 1])


def chat_json(
    config: LlmConfig,
    messages: list[dict[str, str]],
    validate: Callable[[Any], Any],
    attempts: int = 2,
    stage: str = "",
) -> Any:
    return _loop(config, messages, validate, attempts, extract_json, "Return corrected JSON only. No prose, no fences.", stage)


def chat_text(
    config: LlmConfig,
    messages: list[dict[str, str]],
    validate: Callable[[str], Any],
    attempts: int = 3,
    stage: str = "",
) -> str:
    return _loop(config, messages, validate, attempts, lambda raw: raw, "Return the full corrected file content only. No prose, no fences.", stage)


class InfraError(RuntimeError):
    """An environment failure (missing file, render service, tooling).

    Not a model-output problem: the repair loop must abort, not retry.
    """


def _loop(
    config: LlmConfig,
    messages: list[dict[str, str]],
    validate: Callable[[Any], Any],
    attempts: int,
    parse: Callable[[str], Any],
    repair_note: str,
    stage: str = "",
) -> Any:
    history = list(messages)
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            raw = _chat(config, history, retry=attempt > 1, stage=stage)
        except TruncatedOutput as error:
            last_error = error
            history.append({"role": "user", "content":
                "The previous response exhausted the output budget. Return a complete, "
                "more compact response. For scene code, reuse local helpers, reduce "
                "decorative detail, and keep the full file below 500 lines. " + repair_note})
            continue
        try:
            return validate(parse(raw))
        except InfraError:
            raise  # environment failure: retrying a fresh draft cannot fix it
        except Exception as error:  # validation failure: repair with feedback
            last_error = error
            history = history + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"That response was rejected:\n{error}\n{repair_note}"},
            ]

    raise RuntimeError(f"Model output failed validation after {attempts} attempts: {last_error}")


def _post(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int = 180) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"LLM {error.code}: {body}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"LLM request failed: {error.reason}") from error


# --- usage accounting -------------------------------------------------------
#
# Every chat completion reports a `usage` object; the ledger keeps one entry
# per HTTP call (including repair attempts, which replay the conversation).
# run_project resets it and stores the usage summary in run.json.
#
# Prices are USD per MILLION tokens. The table is a convenience estimate keyed
# by model-id substring; VGA_PRICE_INPUT / VGA_PRICE_OUTPUT override the guess
# for any model (also per million).

_USAGE: list[dict[str, Any]] = []
# Run projects can point the ledger at an incremental sink so a mid-run failure
# still leaves the token/cost record on disk.
_USAGE_SINK: "Path | Callable[[dict[str, Any]], None] | None" = None

_PRICES: tuple[tuple[str, float, float], ...] = (
    ("haiku-5.5", 0.10, 0.50),
    ("haiku-4.5", 1.00, 5.00),
    ("sonnet-5", 2.00, 10.00),
    ("sonnet-4.5", 3.00, 15.00),
    ("opus-5", 5.00, 25.00),
    ("gpt-4.1", 2.00, 8.00),
    ("gpt-4o", 2.50, 10.00),
)


def _prices(model: str, env: dict[str, str] | None = None) -> tuple[float | None, float | None]:
    env = env or os.environ
    custom = env.get(INPUT_PRICE_OVERRIDES[0]), env.get(INPUT_PRICE_OVERRIDES[1])
    if custom[0] and custom[1]:
        return float(custom[0]), float(custom[1])
    for key, price_in, price_out in _PRICES:
        if key in model:
            return price_in, price_out
    return None, None


def _record_usage(config: LlmConfig, stage: str, usage: dict[str, Any]) -> None:
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    if prompt == 0 and completion == 0:
        return
    price_in, price_out = _prices(config.model)
    cost = (price_in * prompt + price_out * completion) / 1_000_000 if price_in is not None else None
    _USAGE.append(
        {
            "stage": stage,
            "model": config.model,
            "input_tokens": prompt,
            "output_tokens": completion,
            "reasoning_tokens": int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0),
            "cost_usd": round(cost, 6) if cost is not None else None,
        }
    )
    _flush_usage()


def set_usage_sink(path: "Path | Callable[[dict[str, Any]], None] | None") -> None:
    """Persist the ledger after every call (used by a project run)."""
    global _USAGE_SINK
    _USAGE_SINK = path


def _flush_usage() -> None:
    if _USAGE_SINK is None:
        return
    summary = usage_summary()
    payload = {"model": _USAGE[-1]["model"] if _USAGE else "", **summary}
    if callable(_USAGE_SINK):
        _USAGE_SINK(payload)
        return
    _USAGE_SINK.parent.mkdir(parents=True, exist_ok=True)
    _USAGE_SINK.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def reset_usage() -> None:
    _USAGE.clear()
    set_usage_sink(None)


def usage_summary() -> dict[str, Any]:
    total_in = sum(entry["input_tokens"] for entry in _USAGE)
    total_out = sum(entry["output_tokens"] for entry in _USAGE)
    costs = [entry["cost_usd"] for entry in _USAGE if entry.get("cost_usd") is not None]
    return {
        "calls": len(_USAGE),
        "input_tokens": total_in,
        "output_tokens": total_out,
        "estimated_usd": round(sum(costs), 5) if len(costs) == len(_USAGE) and _USAGE else None,
        "items": list(_USAGE),
    }


RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


def _chat(config: LlmConfig, messages: list[dict[str, str]], retry: bool, stage: str = "") -> str:
    temperature = 0.2 if retry else config.temperature
    payload = {
        "model": config.model,
        "messages": messages,
        "max_tokens": config.max_tokens,
        "temperature": temperature,
    }
    # Sonnet 5.5 defaults to high reasoning, which can consume the code budget.
    if "openrouter.ai" in config.base_url and config.model.startswith(("anthropic/claude-sonnet-5.5", "anthropic/claude-haiku-5.5")):
        payload["reasoning"] = {"effort": "medium"}
    data = _post_with_retry(
        f"{config.base_url}/chat/completions",
        payload,
        {"authorization": f"Bearer {config.api_key}"},
    )
    if isinstance(data.get("usage"), dict):
        _record_usage(config, stage, data["usage"])
    choice = data["choices"][0]
    content = (choice.get("message") or {}).get("content")
    if choice.get("finish_reason") == "length":
        raise TruncatedOutput(
            f"LLM response was truncated at max_tokens={config.max_tokens}; "
            "raise the stage token budget or reduce the scene count."
        )
    if not isinstance(content, str) or not content.strip():
        finish = choice.get("finish_reason") or "unknown"
        raise RuntimeError(
            f"LLM returned no text (finish_reason={finish}); "
            f"max_tokens={config.max_tokens}. Raise the stage token budget or reduce the scene count."
        )
    return content


def _post_with_retry(url: str, payload: dict[str, Any], headers: dict[str, str], attempts: int = 3) -> dict[str, Any]:
    """Retry only transient upstream failures; a bad key or request fails once."""
    for attempt in range(1, attempts + 1):
        try:
            return _post(url, payload, headers)
        except RuntimeError as error:
            if attempt == attempts or not _transient_http_error(str(error)):
                raise
            time.sleep(0.8 * 2 ** (attempt - 1))


def _transient_http_error(message: str) -> bool:
    status = re.search(r"LLM (\d{3})", message)
    if status is not None:
        return int(status.group(1)) in RETRYABLE_STATUS
    return "LLM request failed" in message
