"""
LLM-as-a-judge helpers for the F2.5 evaluation.

A successful HTTP call does not mean the task was solved, so the evaluation
needs a quality signal. The judge is used **offline**, after the candidate
answers are already recorded: it never influences routing or the online
gateway. That keeps production latency and cost predictable.

The judge is deliberately strict and rubric-driven. It is blind to which
policy or model produced the answer, uses temperature 0, and must return a
JSON verdict. Judge cost is recorded separately so it can be excluded from
serving economics or folded in explicitly.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

from backends import BAILIAN_BASE_URL, OpenAICompatibleBackend

JUDGE_PROMPT = """You are a strict grader for an AI assistant evaluation.

Decide whether the candidate answer actually solves the user's task.

Task:
{task}

Candidate answer:
{answer}

Rubric:
- Pass only if the answer addresses the core request with correct, usable content.
- Do not reward length, confidence, or polite filler.
- Missing key facts, wrong facts, or an answer that merely restates the task = fail.
- If the task needs live/real-time data the model cannot know, pass only when
  the answer clearly states that limitation and still gives actionable next steps.
- Judge the answer, not the model or the policy that produced it.

Return JSON only, with no markdown:
{{"pass": true, "reason": "<one short sentence>"}}"""


def build_judge_backend(timeout_s: float = 60.0) -> OpenAICompatibleBackend:
    """Build the judge client from environment variables only."""
    base_url = os.environ.get("CASCADE_JUDGE_BASE_URL")
    api_key = (
        os.environ.get("CASCADE_JUDGE_API_KEY")
        or os.environ.get("DASHSCOPE_API_KEY")
    )
    model = os.environ.get("CASCADE_JUDGE_MODEL", "qwen-max")
    if not base_url:
        if not api_key:
            raise RuntimeError(
                "Set DASHSCOPE_API_KEY or CASCADE_JUDGE_BASE_URL before judging."
            )
        base_url = BAILIAN_BASE_URL
    return OpenAICompatibleBackend(
        base_url, model, role="frontier", api_key=api_key,
        timeout_s=timeout_s, request_logprobs=False,
    )


def build_judge_task(task_prompt: str, answer: str) -> Dict[str, Any]:
    return {
        "task_id": "judge",
        "prompt": JUDGE_PROMPT.format(task=task_prompt, answer=answer),
    }


def parse_verdict(content: str) -> Dict[str, Any]:
    """Parse a judge reply into ``{"pass": bool, "reason": str}``.

    Malformed or non-boolean verdicts become a fail with an explicit reason so
    a broken judge can never silently inflate the success rate.
    """
    text = (content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:])
    if text.rstrip().endswith("```"):
        text = text.rstrip()[:-3]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return {"pass": False, "reason": "judge returned no JSON verdict"}
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return {"pass": False, "reason": "judge returned invalid JSON"}
    verdict = data.get("pass")
    if not isinstance(verdict, bool):
        return {"pass": False, "reason": "judge verdict has no boolean 'pass'"}
    return {"pass": verdict, "reason": str(data.get("reason", ""))[:300]}


def judge_answer(backend: OpenAICompatibleBackend, task_prompt: str,
                 answer: str) -> Dict[str, Any]:
    """Call the judge once and return the verdict plus judge usage."""
    response = backend.complete(build_judge_task(task_prompt, answer), 1)
    if not response["success"]:
        return {
            "pass": False,
            "reason": "judge call failed",
            "judge_failed": True,
            "usage": response["usage"],
        }
    verdict = parse_verdict(response["content"])
    verdict["usage"] = response["usage"]
    return verdict


def summarize_judged(records: list[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate judged records into success / CPST metrics.

    ``records`` items need ``cost_usd`` (serving cost), ``passed`` and
    ``judge_cost_usd``. Costs of failed tasks are reported separately, not
    folded into CPST. Records whose judge call itself failed
    (``judge_failed``) are infrastructure failures, not quality verdicts:
    they are excluded from the success-rate denominator and reported as
    ``judge_failures`` instead of pass/fail.
    """
    tasks = len(records)
    judge_failures = [record for record in records if record.get("judge_failed")]
    judged = [record for record in records if not record.get("judge_failed")]
    passed = [record for record in judged if record["passed"]]
    failed = [record for record in judged if not record["passed"]]
    pass_cost = sum(record["cost_usd"] for record in passed)
    judge_cost = sum(record.get("judge_cost_usd", 0.0) for record in records)
    pass_count = len(passed)
    judged_count = len(judged)
    return {
        "tasks": tasks,
        "judged": judged_count,
        "judge_failures": len(judge_failures),
        "passed": pass_count,
        "failed": len(failed),
        "success_rate": (pass_count / judged_count) if judged_count else 0.0,
        "cpst_usd": (pass_cost / pass_count) if pass_count else 0.0,
        "pass_cost_usd": pass_cost,
        "failed_cost_usd": sum(record["cost_usd"] for record in failed),
        "judge_cost_usd": judge_cost,
        "all_in_cpst_usd": (
            (pass_cost + judge_cost) / pass_count if pass_count else 0.0
        ),
    }
