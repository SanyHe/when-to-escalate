"""
OpenAI-compatible gateway for the cascade demo (F2.4).

The gateway speaks the standard OpenAI chat-completions shape so any OpenAI
client can call it, while the actual work is done by the cascade engine:

  small model first -> escalate to the frontier model on failure or low
  confidence -> return the winning answer plus routing/cost metadata

Endpoints:
  GET  /healthz                liveness + policy + backend roles
  GET  /v1/models              minimal OpenAI model list (for client probes)
  POST /v1/chat/completions    standard chat completion with ``cascade`` metadata

Configuration is environment-only (see backends.py). When the endpoints are
not configured the gateway starts in an "unconfigured" state: it answers
503 with a clear operator message instead of crashing at import time. Errors
never echo stack traces, endpoints or API keys.

Run locally (with backends configured):
    uvicorn cascade.src.gateway:app --port 8000
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SRC_DIR)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from engine import CascadeEngine  # noqa: E402
from pricing import load_pricing  # noqa: E402
from router import load_policy  # noqa: E402
from schema import validate_task  # noqa: E402


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessage]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False


def classify_prompt(prompt: str) -> tuple[str, str]:
    """Map prompt length to the task kind used by the demo router."""
    length = len(prompt)
    if length <= 120:
        return "simple", "low"
    if length <= 320:
        return "medium", "medium"
    return "complex", "high"


def build_task(prompt: str, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Build a schema-valid task from a raw gateway prompt."""
    kind, difficulty = classify_prompt(prompt)
    moment = now or datetime.now(timezone.utc)
    digest = hashlib.sha256(
        (prompt + "\n" + moment.isoformat()).encode("utf-8")
    ).hexdigest()[:12]
    task = {
        "task_id": f"req_{digest}",
        "kind": kind,
        "prompt": prompt,
        "expected_difficulty": difficulty,
        "tags": ["gateway", kind],
        "created_at": moment.isoformat(),
    }
    result = validate_task(task)
    if not result.valid:
        raise ValueError(f"gateway built an invalid task: {result.errors}")
    return task


def _last_user_content(payload: ChatCompletionRequest) -> str:
    for message in reversed(payload.messages):
        if message.role == "user" and message.content.strip():
            return message.content
    return payload.messages[-1].content


def _openai_error(status: int, message: str, error_type: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": error_type}},
    )


def _sum_usage(responses: List[Dict[str, Any]]) -> Dict[str, int]:
    prompt = sum(int(r["usage"]["prompt_tokens"]) for r in responses)
    completion = sum(int(r["usage"]["completion_tokens"]) for r in responses)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


def create_app(engine: Optional[CascadeEngine] = None) -> FastAPI:
    """Build the FastAPI app. Tests inject an engine; production resolves env."""
    app = FastAPI(title="When to Escalate — Cascade Gateway", version="1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    state: Dict[str, Any] = {"engine": engine, "error": None}

    def resolve_engine() -> Optional[CascadeEngine]:
        if state["engine"] is not None:
            return state["engine"]
        if state["error"] is not None:
            return None
        try:
            from backends import backends_from_env, bailian_backends

            # Bailian shortcut: with only DASHSCOPE_API_KEY set, serve the
            # qwen-turbo / qwen-max cascade straight from DashScope.
            if os.environ.get("CASCADE_SMALL_BASE_URL"):
                backends = backends_from_env()
            elif os.environ.get("DASHSCOPE_API_KEY"):
                backends = bailian_backends()
            else:
                backends = backends_from_env()  # raises the clear error
            state["engine"] = CascadeEngine(
                backends, load_pricing(), load_policy(), "cascade"
            )
        except Exception as exc:  # configuration error, not a request error
            # RuntimeError messages only name missing env vars, never secrets.
            state["error"] = str(exc)
            return None
        return state["engine"]

    @app.get("/healthz")
    def healthz() -> Any:
        resolved = resolve_engine()
        if resolved is None:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unconfigured",
                    "policy": "cascade",
                    "detail": state["error"] or "backends are not configured",
                },
            )
        return {
            "status": "ok",
            "policy": resolved.policy_name,
            "backends": sorted(resolved.backends.keys()),
        }

    @app.get("/v1/models")
    def list_models() -> Dict[str, Any]:
        return {
            "object": "list",
            "data": [
                {"id": "cascade", "object": "model", "owned_by": "when-to-escalate"}
            ],
        }

    @app.post("/v1/chat/completions")
    def chat_completions(payload: ChatCompletionRequest) -> Any:
        if payload.stream:
            return _openai_error(
                400, "streaming is not supported by this gateway", "invalid_request_error"
            )

        resolved = resolve_engine()
        if resolved is None:
            return _openai_error(
                503,
                "gateway is not configured: "
                + (state["error"] or "backends are not configured"),
                "service_unavailable",
            )

        if not payload.messages:
            return _openai_error(400, "messages must not be empty", "invalid_request_error")

        prompt = _last_user_content(payload)
        if not prompt.strip():
            return _openai_error(400, "the prompt is empty", "invalid_request_error")

        try:
            task = build_task(prompt)
            trace = resolved.run_task(task)
        except Exception:
            # Never leak stack traces, URLs or keys to clients.
            return _openai_error(500, "internal gateway error", "server_error")

        responses = trace["responses"]
        usage = _sum_usage(responses)
        succeeded = [
            response for response in responses if response.get("success")
        ]
        content = succeeded[-1]["content"] if succeeded else ""
        selected = responses[-1]["model"]
        escalated = any(decision["escalated"] for decision in trace["route_decisions"])
        record = trace["cost_record"]

        body = {
            "id": f"chatcmpl-{task['task_id'].replace('req_', '')}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": selected,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                    "logprobs": None,
                }
            ],
            "usage": usage,
            "cascade": {
                "policy": trace["policy"],
                "task_id": task["task_id"],
                "kind": task["kind"],
                "expected_difficulty": task["expected_difficulty"],
                "success": record["success"],
                "confidence": trace["route_decisions"][0]["confidence"],
                "escalated": escalated,
                "attempts": record["attempts"],
                "cost_usd": record["cost_usd"],
                "latency_ms": record["latency_ms"],
                "decisions": [
                    {
                        "selected_model": decision["selected_model"],
                        "confidence": decision["confidence"],
                        "escalated": decision["escalated"],
                        "reason": decision["reason"],
                    }
                    for decision in trace["route_decisions"]
                ],
            },
        }
        return body

    return app


app = create_app()
