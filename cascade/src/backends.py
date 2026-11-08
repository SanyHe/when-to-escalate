"""
Backend adapters for the cascade demo.

Two implementations share one interface:

  MockBackend            deterministic, offline, used by M1 and the web replay
  OpenAICompatibleBackend real HTTP client for vLLM (small) and any
                          OpenAI-compatible frontier endpoint

Both return a schema-valid ``model_response`` dict and never raise on
transport errors: a failed call is a ``success: false`` response so the
engine can escalate and the ledger can count the wasted spend.

Configuration comes from environment variables only (no secrets in the repo):

  CASCADE_SMALL_BASE_URL       e.g. http://127.0.0.1:6006/v1
  CASCADE_SMALL_MODEL          e.g. wte-small
  CASCADE_SMALL_API_KEY        optional; falls back to DASHSCOPE_API_KEY
  CASCADE_FRONTIER_BASE_URL    e.g. https://api.example.com/v1
  CASCADE_FRONTIER_MODEL       e.g. frontier-model
  CASCADE_FRONTIER_API_KEY     secret; falls back to DASHSCOPE_API_KEY

Alibaba Bailian (DashScope) shortcut: set DASHSCOPE_API_KEY and call
``bailian_backends()`` — both roles then use the OpenAI-compatible
endpoint https://dashscope.aliyuncs.com/compatible-mode/v1 with
qwen-turbo (small) and qwen-max (frontier) by default.
"""
from __future__ import annotations

import hashlib
import math
import os
import time
from typing import Any, Dict, List, Optional

import httpx

from schema import validate_model_response

# Mock behaviour knobs. These are MOCK probabilities, not measured metrics.
SUCCESS_PROBABILITY = {
    "small": {"low": 0.97, "medium": 0.76, "high": 0.38},
    "frontier": {"low": 0.995, "medium": 0.97, "high": 0.92},
}

# Base token estimates by (model, difficulty).
TOKEN_ESTIMATES = {
    "small": {
        "low": {"prompt": 180, "completion": 60},
        "medium": {"prompt": 350, "completion": 110},
        "high": {"prompt": 650, "completion": 160},
    },
    "frontier": {
        "low": {"prompt": 180, "completion": 70},
        "medium": {"prompt": 350, "completion": 130},
        "high": {"prompt": 650, "completion": 220},
    },
}

BASE_LATENCY_MS = {
    "small": {"low": 180, "medium": 320, "high": 520},
    "frontier": {"low": 520, "medium": 900, "high": 1500},
}


def _draw(*parts: str) -> float:
    """Stable pseudo-random value in [0, 1) for the given key parts."""
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _jitter(*parts: str, spread: float) -> float:
    return 1.0 + (_draw(*parts) - 0.5) * spread


def _zero_usage() -> Dict[str, int]:
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def confidence_from_logprobs(logprobs: Any) -> Optional[float]:
    """Average per-token probability from an OpenAI-style ``logprobs`` object.

    The score is ``exp(mean(token logprob))`` over all generated tokens, i.e.
    the geometric mean token probability, clamped to [0, 1]. Both the current
    ``content`` list and the legacy ``token_logprobs`` list are supported.
    Returns ``None`` when the provider did not return usable log-probabilities,
    so the engine can fall back to the rule-based prior.
    """
    if not isinstance(logprobs, dict):
        return None
    values: List[float] = []
    for entry in logprobs.get("content") or []:
        if isinstance(entry, dict) and isinstance(entry.get("logprob"), (int, float)):
            values.append(float(entry["logprob"]))
    if not values:
        for value in logprobs.get("token_logprobs") or []:
            if isinstance(value, (int, float)):
                values.append(float(value))
    if not values:
        return None
    mean_logprob = sum(values) / len(values)
    return round(max(0.0, min(1.0, math.exp(mean_logprob))), 4)


def _logprobs_enabled() -> bool:
    """Whether real backends should request token log-probabilities."""
    return os.environ.get("CASCADE_LOGPROBS", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


class MockBackend:
    """Deterministic offline backend keyed by (model, task_id, attempt)."""

    def __init__(self, model: str) -> None:
        if model not in ("small", "frontier"):
            raise ValueError(f"unknown mock model: {model}")
        self.model = model

    def complete(self, task: Dict[str, Any], attempt: int = 1) -> Dict[str, Any]:
        difficulty = task["expected_difficulty"]
        key = (self.model, task["task_id"], str(attempt))
        usage_estimate = TOKEN_ESTIMATES[self.model][difficulty]
        prompt_tokens = int(round(usage_estimate["prompt"] * _jitter(*key, "p", spread=0.18)))
        completion_tokens = int(
            round(usage_estimate["completion"] * _jitter(*key, "c", spread=0.22))
        )
        latency_ms = round(
            BASE_LATENCY_MS[self.model][difficulty] * _jitter(*key, "l", spread=0.28), 1
        )
        success = _draw(*key, "success") < SUCCESS_PROBABILITY[self.model][difficulty]
        usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens if success else 0,
            "total_tokens": prompt_tokens + (completion_tokens if success else 0),
        }
        response = {
            "task_id": task["task_id"],
            "model": self.model,
            "content": (
                f"mock {self.model} answer for {task['task_id']} "
                f"({task['kind']}, attempt {attempt})"
                if success else ""
            ),
            "success": success,
            "latency_ms": latency_ms,
            "usage": usage,
        }
        result = validate_model_response(response)
        if not result.valid:
            raise ValueError(f"mock response violates schema: {result.errors}")
        return response


class OpenAICompatibleBackend:
    """Minimal OpenAI-compatible chat client used by the M2 gateway.

    ``role`` is the ledger role of this endpoint ("small" or "frontier"), not
    the vendor model name: the engine and schemas only know those two roles.
    """

    def __init__(self, base_url: str, model_name: str, role: str,
                 api_key: str | None = None, timeout_s: float = 30.0,
                 client: Optional[httpx.Client] = None,
                 request_logprobs: bool = True,
                 logprob_top_n: int = 3) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        if role not in ("small", "frontier"):
            raise ValueError(f"unknown backend role: {role}")
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.role = role
        self.api_key = api_key
        self.timeout_s = timeout_s
        self._client = client
        self.request_logprobs = request_logprobs
        self.logprob_top_n = logprob_top_n

    @property
    def endpoint(self) -> str:
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/v1/chat/completions"

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _post(self, payload: Dict[str, Any]) -> httpx.Response:
        if self._client is not None:
            return self._client.post(
                self.endpoint, json=payload, headers=self._headers(),
                timeout=self.timeout_s,
            )
        return httpx.post(
            self.endpoint, json=payload, headers=self._headers(),
            timeout=self.timeout_s,
        )

    def complete(self, task: Dict[str, Any], attempt: int = 1) -> Dict[str, Any]:
        started = time.perf_counter()
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": task["prompt"]}],
            "temperature": 0,
        }
        if self.request_logprobs:
            payload["logprobs"] = True
            payload["top_logprobs"] = self.logprob_top_n
        try:
            response = self._post(payload)
            if self.request_logprobs and response.status_code == 400:
                # Not every OpenAI-compatible server implements logprobs;
                # retry once without them so the answer still comes through.
                payload.pop("logprobs", None)
                payload.pop("top_logprobs", None)
                response = self._post(payload)
            response.raise_for_status()
            body = response.json()
            choice = body["choices"][0]
            content = choice["message"].get("content") or ""
            usage = body.get("usage") or {}
            prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
            completion_tokens = int(usage.get("completion_tokens", 0) or 0)
            result = {
                "task_id": task["task_id"],
                "model": self.role,
                "content": content,
                "success": True,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            }
            confidence = confidence_from_logprobs(choice.get("logprobs"))
            if confidence is not None:
                result["confidence"] = confidence
            return result
        except Exception:
            # Never leak stack traces, URLs or keys to callers.
            return {
                "task_id": task["task_id"],
                "model": self.role,
                "content": "",
                "success": False,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "usage": _zero_usage(),
            }


# Alibaba Bailian (DashScope) OpenAI-compatible endpoint and defaults.
BAILIAN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
BAILIAN_SMALL_MODEL = "qwen-turbo"
BAILIAN_FRONTIER_MODEL = "qwen-max"


def backends_from_env() -> Dict[str, Any]:
    """Build the real backend pair from environment variables.

    Raises ``RuntimeError`` when configuration is missing; callers should
    surface that as a clear operator error, not fall back silently.
    """
    small_url = os.environ.get("CASCADE_SMALL_BASE_URL", "")
    frontier_url = os.environ.get("CASCADE_FRONTIER_BASE_URL", "")
    if not small_url or not frontier_url:
        raise RuntimeError(
            "missing CASCADE_SMALL_BASE_URL / CASCADE_FRONTIER_BASE_URL; "
            "see AGENTS.md section 5"
        )
    # Bailian uses one key for every model; DASHSCOPE_API_KEY is the
    # platform-wide fallback when a role-specific key is not set.
    dashscope_key = os.environ.get("DASHSCOPE_API_KEY") or None
    return {
        "small": OpenAICompatibleBackend(
            small_url,
            os.environ.get("CASCADE_SMALL_MODEL", "wte-small"),
            role="small",
            api_key=os.environ.get("CASCADE_SMALL_API_KEY") or dashscope_key,
            request_logprobs=_logprobs_enabled(),
        ),
        "frontier": OpenAICompatibleBackend(
            frontier_url,
            os.environ.get("CASCADE_FRONTIER_MODEL", "frontier-model"),
            role="frontier",
            api_key=os.environ.get("CASCADE_FRONTIER_API_KEY") or dashscope_key,
            request_logprobs=_logprobs_enabled(),
        ),
    }


def bailian_backends(small_model: Optional[str] = None,
                     frontier_model: Optional[str] = None,
                     timeout_s: float = 30.0) -> Dict[str, Any]:
    """Build a qwen-turbo / qwen-max pair on Alibaba Bailian.

    Reads ``DASHSCOPE_API_KEY`` from the environment (never hardcode keys).
    Both roles share the OpenAI-compatible DashScope endpoint. Model names
    default to ``CASCADE_SMALL_MODEL`` / ``CASCADE_FRONTIER_MODEL`` when set,
    then to qwen-turbo / qwen-max.
    """
    api_key = os.environ.get("DASHSCOPE_API_KEY") or None
    if not api_key:
        raise RuntimeError(
            "missing DASHSCOPE_API_KEY; create a key in the Bailian console "
            "and export it before calling bailian_backends()"
        )
    small_model = small_model or os.environ.get(
        "CASCADE_SMALL_MODEL", BAILIAN_SMALL_MODEL)
    frontier_model = frontier_model or os.environ.get(
        "CASCADE_FRONTIER_MODEL", BAILIAN_FRONTIER_MODEL)
    return {
        "small": OpenAICompatibleBackend(
            BAILIAN_BASE_URL, small_model, role="small",
            api_key=api_key, timeout_s=timeout_s,
            request_logprobs=_logprobs_enabled(),
        ),
        "frontier": OpenAICompatibleBackend(
            BAILIAN_BASE_URL, frontier_model, role="frontier",
            api_key=api_key, timeout_s=timeout_s,
            request_logprobs=_logprobs_enabled(),
        ),
    }


def mock_backends() -> Dict[str, MockBackend]:
    return {"small": MockBackend("small"), "frontier": MockBackend("frontier")}
