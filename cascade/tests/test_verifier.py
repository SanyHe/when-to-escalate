from gen_tasks import build_tasks
from verifier import (
    STATUS_FAILED,
    STATUS_NEEDS_JUDGE,
    STATUS_PASSED,
    normalize_text,
    verify_answer,
)


def _task(verification):
    return {"task_id": "t1", "prompt": "prompt", "verification": verification}


def test_exact_match_accepts_an_embedded_value():
    task = _task({"type": "exact_match", "expected": "3072"})
    assert verify_answer(task, "128 × 24 = 3072")["status"] == STATUS_PASSED


def test_exact_match_does_not_match_inside_a_larger_number():
    task = _task({"type": "exact_match", "expected": "3072"})
    assert verify_answer(task, "13072")["status"] == STATUS_FAILED


def test_exact_match_normalises_width_case_and_spacing():
    task = _task({"type": "exact_match", "expected": "WHEN TO ESCALATE"})
    assert verify_answer(task, "ｗｈｅｎ　ｔｏ　ｅｓｃａｌａｔｅ")["status"] == STATUS_PASSED
    task = _task({"type": "exact_match", "expected": "3,5,7,11"})
    assert verify_answer(task, "3、5、7、11")["status"] == STATUS_PASSED


def test_exact_match_accepts_any_of_and_rejects_empty_answers():
    task = _task({"type": "exact_match", "expected": "星期四",
                  "any_of": ["周四", "四"]})
    assert verify_answer(task, "周四")["status"] == STATUS_PASSED
    assert verify_answer(task, "")["status"] == STATUS_FAILED


def test_field_match_requires_every_field():
    task = _task({"type": "field_match", "fields": [
        {"name": "level", "pattern": r'"level"\s*:\s*"ERROR"'},
        {"name": "date", "pattern": r'"date"\s*:\s*"2026-11-18"'},
    ]})
    good = '{"level": "ERROR", "date": "2026-11-18"}'
    assert verify_answer(task, good)["status"] == STATUS_PASSED
    result = verify_answer(task, '{"level": "ERROR"}')
    assert result["status"] == STATUS_FAILED
    assert result["details"]["missing"] == ["date"]


def test_regex_matches_the_python_expression():
    task = _task({"type": "regex",
                  "pattern": r"sum\s*\(\s*\[\s*1\s*,\s*2\s*,\s*3\s*\]\s*\)"})
    assert verify_answer(task, "sum([1, 2, 3])")["status"] == STATUS_PASSED
    assert verify_answer(task, "sum([1, 2])")["status"] == STATUS_FAILED


def test_json_schema_checks_keys_and_values():
    task = _task({
        "type": "json_schema",
        "required_keys": ["total", "currency"],
        "key_values": {"total": 30, "currency": "USD"},
    })
    assert verify_answer(
        task, 'Here is the result: {"total": 30.0, "currency": "usd"}'
    )["status"] == STATUS_PASSED
    assert verify_answer(task, '{"total": 30}')["status"] == STATUS_FAILED
    assert verify_answer(
        task, '{"total": 31, "currency": "USD"}'
    )["status"] == STATUS_FAILED
    assert verify_answer(task, "total is 30 USD")["status"] == STATUS_FAILED


def test_refusal_passes_on_a_clear_missing_input_statement():
    task = _task({
        "type": "refusal",
        "missing_inputs": ["会议纪要附件"],
        "forbidden_patterns": [r"\d{1,2}\s*[:：]\s*\d{2}"],
    })
    answer = "您没有提供会议纪要附件，我无法整理待办。请上传后我再处理。"
    assert verify_answer(task, answer)["status"] == STATUS_PASSED


def test_refusal_accepts_common_polite_missing_input_phrasings():
    task = _task({
        "type": "refusal",
        "missing_inputs": ["技术方案文档"],
        "forbidden_patterns": [r"\d+(?:\.\d+)?\s*%"],
    })
    assert verify_answer(
        task, "您提到的技术方案文件内容未直接提供，我只能给出通用框架。"
    )["status"] == STATUS_PASSED
    assert verify_answer(
        task, "需要看到具体的 JSON 内容，您能否提供？"
    )["status"] == STATUS_PASSED


def test_refusal_fails_when_the_answer_invents_the_missing_input():
    task = _task({
        "type": "refusal",
        "missing_inputs": ["会议纪要附件"],
        "forbidden_patterns": [r"\d{1,2}\s*[:：]\s*\d{2}"],
    })
    answer = "根据附件，会议在 14:30 讨论了预算，请跟进。"
    result = verify_answer(task, answer)
    assert result["status"] == STATUS_FAILED
    assert result["details"]["violations"]


def test_refusal_fails_without_an_explicit_statement():
    task = _task({"type": "refusal", "missing_inputs": ["数据"],
                  "forbidden_patterns": []})
    assert verify_answer(task, "好的，我来整理。")["status"] == STATUS_FAILED
    assert verify_answer(task, "")["status"] == STATUS_FAILED


def test_llm_and_missing_specs_ask_for_a_judge():
    assert verify_answer(_task({"type": "llm_judge"}),
                         "answer")["status"] == STATUS_NEEDS_JUDGE
    assert verify_answer({"task_id": "t1"}, "answer")["status"] == STATUS_NEEDS_JUDGE


def test_generated_tasks_route_to_the_expected_grader():
    tasks = build_tasks()
    refusing = [task for task in tasks if task["task_class"] == "should_refuse"]
    solvable = [task for task in tasks if task["task_class"] == "small_sufficient"]
    frontier = [task for task in tasks if task["task_class"] == "frontier_required"]

    assert all(
        verify_answer(task, "我无法完成，因为没有提供必要输入")["status"]
        != STATUS_NEEDS_JUDGE
        for task in refusing
    )
    assert all(
        verify_answer(task, "")["status"] != STATUS_NEEDS_JUDGE
        for task in solvable
    )
    assert all(
        verify_answer(task, "answer")["status"] == STATUS_NEEDS_JUDGE
        for task in frontier
    )


def test_normalize_text_collapses_whitespace():
    assert normalize_text("  A\tB \n C ") == "a b c"
