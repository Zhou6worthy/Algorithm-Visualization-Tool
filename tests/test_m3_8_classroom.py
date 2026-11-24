from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from algoviz.execution.case_runner import CaseRunner
from algoviz.protocol.cases import CaseSource, TestCaseSpec
from algoviz.teaching.classroom import (
    ClassroomCase,
    ClassroomDeck,
    build_classroom_deck,
)
from algoviz.teaching.classroom_html import write_classroom_html

SOURCE = """def two_sum(nums, target):
    seen = {}
    for i, x in enumerate(nums):
        need = target - x
        if need in seen:
            return [seen[need], i]
        seen[x] = i
    return []
"""


def _case(
    case_id: str,
    nums: list[int],
    target: int,
    expected: list[int] | None,
    source: CaseSource = CaseSource.USER,
) -> TestCaseSpec:
    return TestCaseSpec(
        case_id=case_id,
        name=case_id,
        input_data={"nums": nums, "target": target},
        expected_output=expected,
        source=source,
    )


def test_deck_builds_from_real_runs_and_reuses_one_visual_plan(tmp_path: Path) -> None:
    cases = [
        _case("normal", [2, 7, 11, 15], 9, [0, 1]),
        _case("first", [3, 2, 4], 5, [0, 1]),
        _case("ai_extra", [1, 2, 3], 5, [1, 2], CaseSource.AI_GENERATED),
        TestCaseSpec(case_id="invalid", name="invalid", input_data={"nums": [1]}),
    ]
    runner = CaseRunner(tmp_path / "runs", source=SOURCE)
    runs = runner.run_cases(cases)
    deck = build_classroom_deck(list(zip(cases, runs)), title="课堂测试")

    assert deck.schema_version == "3.8"
    assert [case.case_id for case in deck.cases] == ["normal", "first", "ai_extra", "invalid"]
    assert [case.status.value for case in deck.cases] == ["success", "success", "success", "error"]
    assert deck.active_case_id == "normal"
    assert deck.cases[2].source is CaseSource.AI_GENERATED
    assert deck.cases[3].trace is None
    assert deck.cases[3].hints == []
    assert deck.cases[3].step_views == []
    assert deck.cases[0].trace is not None
    assert len(deck.cases[0].hints) == len(deck.cases[0].trace.steps)
    assert len(deck.cases[0].step_views) == len(deck.cases[0].trace.steps)
    assert deck.cases[0].input_data == {"nums": [2, 7, 11, 15], "target": 9}
    assert [item.component_id for item in deck.visual_plan.components] == [
        "array",
        "hash_map",
        "variables",
        "code",
    ]
    # 所有 case 共用同一个 VisualPlan，不按 CaseRun 复制视觉结构。
    assert deck.visual_plan is not None
    assert deck.code == SOURCE
    assert deck.cases[0].trace.steps[0].state_after.array is not None


def test_html_is_offline_componentized_and_embeds_every_case(tmp_path: Path) -> None:
    cases = [
        _case("normal", [2, 7, 11, 15], 9, [0, 1]),
        _case("first", [3, 2, 4], 5, [0, 1]),
        _case("mismatch", [1, 2, 3], 4, [1, 2]),
    ]
    runner = CaseRunner(tmp_path / "runs", source=SOURCE)
    runs = runner.run_cases(cases)
    deck = build_classroom_deck(list(zip(cases, runs)), title="离线课堂")

    path = write_classroom_html(deck, tmp_path / "classroom.html")
    assert path.exists()
    html = path.read_text(encoding="utf-8")
    assert "http://" not in html
    assert "https://" not in html
    for marker in [
        "class ArrayComponent",
        "class HashMapComponent",
        "class VariableComponent",
        "class CodeComponent",
        "class TeachingHintComponent",
        "class PlaybackControls",
        "class ClassroomPlayback",
        'id="components-root"',
        'id="case-list"',
        'id="seek"',
        'id="speed"',
        'id="hint-toggle"',
        'id="auto"',
        "const makePill",
        ".pill{",
    ]:
        assert marker in html

    match = re.search(
        r'<script id="classroom-data" type="application/json">(.*?)</script>',
        html,
        re.S,
    )
    assert match is not None
    payload = json.loads(match.group(1))
    assert payload["schema_version"] == "3.8"
    assert payload["title"] == "离线课堂"
    assert [item["case_id"] for item in payload["cases"]] == ["normal", "first", "mismatch"]
    assert payload["active_case_id"] == "normal"
    assert [item["component_id"] for item in payload["visual_plan"]["components"]] == [
        "array",
        "hash_map",
        "variables",
        "code",
    ]
    assert payload["cases"][0]["trace"]["metadata"]["algorithm"] == "two_sum"
    assert len(payload["cases"][0]["trace"]["steps"]) == 8
    assert len(payload["cases"][0]["hints"]) == 8
    assert len(payload["cases"][0]["step_views"]) == 8
    assert payload["cases"][2]["status"] == "failed"
    trace_ids = {
        item["trace"]["metadata"]["execution_trace_id"]
        for item in payload["cases"]
        if item["trace"] is not None
    }
    assert len(trace_ids) == 3
    for item in payload["cases"]:
        step_ids = {step["step_id"] for step in item["trace"]["steps"]}
        assert {hint["related_step_id"] for hint in item["hints"]} <= step_ids
        assert [view["step_id"] for view in item["step_views"]] == [
            step["step_id"] for step in item["trace"]["steps"]
        ]
        assert item["step_views"][0]["variables"]


def test_classroom_models_reject_mismatched_views_and_duplicate_cases(tmp_path: Path) -> None:
    case = _case("normal", [2, 7], 9, [0, 1])
    run = CaseRunner(tmp_path / "runs", source=SOURCE).run_case(case)
    deck = build_classroom_deck([(case, run)])
    base_case = deck.cases[0]
    assert base_case.trace is not None

    with pytest.raises(ValidationError):
        ClassroomCase(
            case_id="bad",
            run_id="run_bad",
            name="bad",
            trace=base_case.trace,
            hints=[],
            step_views=[],
        )

    with pytest.raises(ValidationError):
        ClassroomDeck(
            title="duplicate",
            code=SOURCE,
            visual_plan=deck.visual_plan,
            cases=[base_case, base_case],
            active_case_id="normal",
        )

    with pytest.raises(ValidationError):
        ClassroomDeck(
            title="bad active",
            code=SOURCE,
            visual_plan=deck.visual_plan,
            cases=[base_case],
            active_case_id="missing",
        )
