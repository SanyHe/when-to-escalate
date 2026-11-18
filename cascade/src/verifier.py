"""
Deterministic answer verifier for task-level grading (F2.5).

The LLM judge is expensive, noisy and non-reproducible. Where a task has a
checkable answer, this module decides pass/fail with plain code so the same
answer always gets the same verdict and the evaluation spends no judge tokens.

A task opts in through an optional ``verification`` object (see schema.py):

  exact_match  the answer contains an expected value (or one of ``any_of``)
  field_match  every named regex pattern is present in the answer
  regex        a single pattern is present in the answer
  json_schema  the answer contains a JSON object with required keys/values
  refusal      the answer states that required input is missing and does not
               contain any of the forbidden fabrication patterns
  llm_judge    no deterministic check; the caller must fall back to the judge

``verify_answer`` returns one of three statuses:

  passed      deterministic check succeeded
  failed      deterministic check failed
  needs_judge no deterministic check is possible (or the spec is llm_judge)

Statuses are plain strings so they can be written straight into ledger JSON.

Usage (repo root):
    python3 cascade/src/verifier.py --tasks data/synthetic/seed_tasks.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from typing import Any, Dict, List, Optional

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SRC_DIR)

REPO_ROOT = os.path.abspath(os.path.join(_SRC_DIR, "..", ".."))
DEFAULT_TASKS = os.path.join(REPO_ROOT, "data", "synthetic", "seed_tasks.jsonl")

STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_NEEDS_JUDGE = "needs_judge"

# An answer that merely says "I cannot" without naming the missing material is
# not a useful refusal, but every phrase below is an explicit statement that
# the task cannot be completed from the supplied text. Both Chinese and English
# are accepted because the synthetic prompts are bilingual in practice.
DEFAULT_REFUSAL_PHRASES = (
    "未提供", "未直接提供", "未给出", "未附上", "未包含", "未看到", "未收到",
    "没有提供", "没有附上", "没有附带", "没有具体", "没有相关", "没有看到",
    "没有包含", "没有收到", "没有附件", "无附件",
    "缺少", "缺乏", "缺少附件", "缺少文档", "缺少内容",
    "无法", "不能", "看不到", "读不到", "无法查看", "无法读取", "无法打开",
    "打不开", "请提供", "请上传", "请补充", "请分享", "请粘贴", "请给出",
    "需要您提供", "需要更多信息", "需要看到", "需要具体", "能否提供",
    "可以提供", "麻烦提供", "麻烦上传",
    "missing", "not provided", "not included", "not attached", "not supplied",
    "not available", "no attachment", "no document", "no content",
    "cannot", "can't", "unable", "please provide", "please upload",
    "please share", "please paste", "could you provide", "can you provide",
    "need more information", "not enough information", "without the",
)


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    body = lines[1:]
    if body and body[-1].strip().startswith("```"):
        body = body[:-1]
    return "\n".join(body).strip()


def normalize_text(text: str) -> str:
    """Normalise width, case and whitespace before deterministic comparison."""
    value = unicodedata.normalize("NFKC", _strip_code_fences(text or ""))
    value = value.replace("、", ",")
    value = value.lower()
    return re.sub(r"\s+", " ", value).strip()


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", normalize_text(text))


def _match_expected(answer: str, expected: str) -> bool:
    """True when ``expected`` appears as a value, not as part of a larger number.

    Numeric expectations use digit boundaries so ``3072`` does not match
    ``13072``; text expectations compare on the whitespace-free form so
    ``WHEN TO ESCALATE`` and ``when to escalate`` are the same answer.
    """
    answer_norm = normalize_text(answer)
    expected_norm = normalize_text(expected)
    if not expected_norm:
        return False
    if re.fullmatch(r"-?\d+(?:\.\d+)?", expected_norm):
        pattern = rf"(?<![\d.]){re.escape(expected_norm)}(?![\d])"
        return re.search(pattern, answer_norm) is not None
    return _compact(expected_norm) in _compact(answer_norm)


def _extract_json(text: str) -> Optional[Any]:
    """Return the first JSON object/array embedded in an answer."""
    body = _strip_code_fences(text or "")
    decoder = json.JSONDecoder()
    for index, char in enumerate(body):
        if char not in "{[":
            continue
        try:
            value, _ = decoder.raw_decode(body[index:])
        except json.JSONDecodeError:
            continue
        return value
    return None


def _result(status: str, vtype: str, reason: str,
            **details: Any) -> Dict[str, Any]:
    return {
        "status": status,
        "type": vtype,
        "reason": reason,
        "details": details,
    }


def _verify_exact_match(answer: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    expected = spec.get("expected")
    candidates: List[str] = []
    if expected:
        candidates.append(expected)
    candidates.extend(spec.get("any_of") or [])
    if not candidates:
        return _result(STATUS_FAILED, "exact_match",
                       "verification spec has no expected value")
    if not (answer or "").strip():
        return _result(STATUS_FAILED, "exact_match", "answer is empty")
    for candidate in candidates:
        if _match_expected(answer, candidate):
            return _result(STATUS_PASSED, "exact_match",
                           f"matched expected value {candidate!r}",
                           expected=candidate)
    return _result(STATUS_FAILED, "exact_match",
                   "answer does not contain any expected value",
                   expected=candidates)


def _verify_field_match(answer: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    fields = spec.get("fields") or []
    if not fields:
        return _result(STATUS_FAILED, "field_match",
                       "verification spec has no fields")
    text = answer or ""
    missing: List[str] = []
    for field in fields:
        try:
            matched = re.search(field["pattern"], text,
                                re.IGNORECASE | re.MULTILINE) is not None
        except re.error:
            return _result(STATUS_FAILED, "field_match",
                           f"invalid field pattern for {field['name']!r}",
                           field=field["name"])
        if not matched:
            missing.append(field["name"])
    if missing:
        return _result(STATUS_FAILED, "field_match",
                       f"missing fields: {', '.join(missing)}", missing=missing)
    return _result(STATUS_PASSED, "field_match",
                   f"all {len(fields)} fields matched")


def _verify_regex(answer: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    pattern = spec.get("pattern")
    if not pattern:
        return _result(STATUS_FAILED, "regex",
                       "verification spec has no pattern")
    try:
        matched = re.search(pattern, answer or "",
                            re.IGNORECASE | re.MULTILINE) is not None
    except re.error:
        return _result(STATUS_FAILED, "regex", "invalid verification pattern")
    if matched:
        return _result(STATUS_PASSED, "regex", "pattern matched")
    return _result(STATUS_FAILED, "regex", "pattern did not match")


def _values_equal(actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool):
        return isinstance(actual, bool) and actual is expected
    if isinstance(expected, (int, float)):
        return isinstance(actual, (int, float)) and not isinstance(actual, bool) \
            and abs(float(actual) - float(expected)) <= 1e-9
    return str(actual).strip().lower() == str(expected).strip().lower()


def _verify_json_schema(answer: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    parsed = _extract_json(answer)
    if not isinstance(parsed, dict):
        return _result(STATUS_FAILED, "json_schema",
                       "answer does not contain a JSON object")
    required = spec.get("required_keys") or []
    missing = [key for key in required if key not in parsed]
    if missing:
        return _result(STATUS_FAILED, "json_schema",
                       f"missing JSON keys: {', '.join(missing)}",
                       missing=missing)
    mismatched = [
        key for key, expected in (spec.get("key_values") or {}).items()
        if key not in parsed or not _values_equal(parsed[key], expected)
    ]
    if mismatched:
        return _result(STATUS_FAILED, "json_schema",
                       f"wrong JSON values: {', '.join(mismatched)}",
                       mismatched=mismatched)
    return _result(STATUS_PASSED, "json_schema",
                   f"all {len(required)} required keys matched")


def _verify_refusal(answer: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    text = answer or ""
    if not text.strip():
        return _result(STATUS_FAILED, "refusal", "answer is empty")
    phrases = list(DEFAULT_REFUSAL_PHRASES) + list(spec.get("required_phrases") or [])
    lowered = text.lower()
    matched_phrase = next((p for p in phrases if p.lower() in lowered), None)
    violations: List[str] = []
    for pattern in spec.get("forbidden_patterns") or []:
        try:
            found = re.search(pattern, text, re.IGNORECASE)
        except re.error:
            return _result(STATUS_FAILED, "refusal",
                           "invalid forbidden pattern")
        if found:
            violations.append(found.group(0))
    if violations:
        return _result(STATUS_FAILED, "refusal",
                       "answer invents missing input",
                       violations=violations,
                       missing_inputs=spec.get("missing_inputs") or [])
    if not matched_phrase:
        return _result(STATUS_FAILED, "refusal",
                       "answer does not state that input is missing",
                       missing_inputs=spec.get("missing_inputs") or [])
    return _result(STATUS_PASSED, "refusal",
                   f"refused with phrase {matched_phrase!r}",
                   phrase=matched_phrase,
                   missing_inputs=spec.get("missing_inputs") or [])


_VERIFIERS = {
    "exact_match": _verify_exact_match,
    "field_match": _verify_field_match,
    "regex": _verify_regex,
    "json_schema": _verify_json_schema,
    "refusal": _verify_refusal,
}


def verify_answer(task: Dict[str, Any], answer: str) -> Dict[str, Any]:
    """Run the task's deterministic check, or ask the caller for a judge."""
    spec = task.get("verification")
    if not isinstance(spec, dict) or not spec.get("type"):
        return _result(STATUS_NEEDS_JUDGE, "none",
                       "task has no verification spec")
    vtype = spec["type"]
    verifier = _VERIFIERS.get(vtype)
    if verifier is None:
        return _result(STATUS_NEEDS_JUDGE, vtype,
                       "verification type requires an LLM judge")
    return verifier(answer, spec)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", default=DEFAULT_TASKS,
                        help="task JSONL file to inspect")
    args = parser.parse_args()

    with open(args.tasks, "r", encoding="utf-8") as handle:
        tasks = [json.loads(line) for line in handle if line.strip()]

    counts: Dict[str, Dict[str, int]] = {}
    for task in tasks:
        task_class = task.get("task_class", "unclassified")
        spec = task.get("verification") or {}
        vtype = spec.get("type", "none")
        bucket = counts.setdefault(task_class, {})
        bucket[vtype] = bucket.get(vtype, 0) + 1
    print(json.dumps(counts, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
