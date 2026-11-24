from __future__ import annotations

from pathlib import Path

from algoviz.execution.case_runner import CaseRunner
from algoviz.protocol.cases import CaseSource, TestCaseSpec
from algoviz.protocol.events import (
    AnimationStep,
    ArrayState,
    Complexity,
    StepType,
    Trace,
    TraceMetadata,
    VisualKind,
    VisualState,
)
from algoviz.protocol.hints import HintKind, StepHint
from algoviz.teaching.step_hints import build_two_sum_hints, hint_concepts, hints_by_step

SOURCE = """def two_sum(nums, target):
    seen = {}
    for i, x in enumerate(nums):
        need = target - x
        if need in seen:
            return [seen[need], i]
        seen[x] = i
    return []
"""


def _case(case_id: str, nums: list[int], target: int, expected: list[int]) -> TestCaseSpec:
    return TestCaseSpec(
        case_id=case_id,
        name=case_id,
        input_data={"nums": nums, "target": target},
        expected_output=expected,
        source=CaseSource.USER,
    )


def test_hints_align_with_real_steps_and_cover_required_teaching_nodes(tmp_path: Path) -> None:
    runner = CaseRunner(tmp_path / "runs", source=SOURCE)
    normal = runner.run_case(_case("normal", [2, 7, 11, 15], 9, [0, 1]))
    empty = runner.run_case(_case("empty", [], 9, []))
    assert normal.animation_trace is not None
    assert empty.animation_trace is not None
    trace = normal.animation_trace
    before = trace.model_dump_json()

    hints = build_two_sum_hints(trace)
    assert len(hints) == len(trace.steps)
    assert [hint.related_step_id for hint in hints] == [step.step_id for step in trace.steps]
    assert len({hint.hint_id for hint in hints}) == len(hints)
    assert trace.model_dump_json() == before

    indexed = hints_by_step(hints)
    assert indexed[1].kind is HintKind.VISIT
    miss = next(hint for hint in hints if hint.kind is HintKind.COMPLEMENT_MISS)
    hit = next(hint for hint in hints if hint.kind is HintKind.COMPLEMENT_HIT)
    insert = next(hint for hint in hints if hint.kind is HintKind.INSERT)
    found = next(hint for hint in hints if hint.kind is HintKind.RETURN)
    complete = next(hint for hint in hints if hint.kind is HintKind.COMPLETE)
    assert "7" in miss.explanation and "9" in miss.explanation
    assert "2" in hit.explanation
    assert "seen" in insert.explanation
    assert found.question and found.answer
    assert "O(n)" in complete.explanation
    assert "O(n)" in complete.answer
    for hint in hints:
        assert hint.explanation
        assert hint.question
        assert hint.answer
        assert hint.common_mistake
        assert hint.related_step_id in {step.step_id for step in trace.steps}

    concepts = hint_concepts(hints)
    required = {
        "初始化",
        "为什么需要哈希表",
        "遍历元素",
        "当前元素与 target",
        "计算补数",
        "查询哈希表",
        "查询 miss",
        "查询 hit",
        "插入元素",
        "哈希表保存内容",
        "完成返回",
        "为什么可以返回",
        "完成",
        "复杂度",
    }
    assert required <= concepts

    empty_hints = build_two_sum_hints(empty.animation_trace)
    empty_titles = [hint.title for hint in empty_hints]
    assert any("没有找到答案" in title for title in empty_titles)
    assert all(hint.kind is not HintKind.COMPLEMENT_HIT for hint in empty_hints)


def test_no_hint_is_forced_for_unknown_note_step() -> None:
    state = VisualState(kind=VisualKind.ARRAY, array=ArrayState(values=[1, 2], target=3))
    step = AnimationStep(
        step_id=0,
        type=StepType.NOTE,
        description="普通代码行",
        code_line=2,
        state_before=state,
        state_after=state,
    )
    metadata = TraceMetadata(
        algorithm="two_sum",
        title="note",
        category="custom",
        visual_kind=VisualKind.ARRAY,
        complexity=Complexity(time="O(n)", space="O(n)"),
    )
    trace = Trace(metadata=metadata, steps=[step], verified=False)
    assert build_two_sum_hints(trace) == []


def test_step_hint_keeps_question_and_answer_independent() -> None:
    only_question = StepHint(
        hint_id="q_only",
        related_step_id=0,
        kind=HintKind.VISIT,
        title="问题",
        explanation="解释",
        question="为什么？",
    )
    only_answer = StepHint(
        hint_id="a_only",
        related_step_id=0,
        kind=HintKind.VISIT,
        title="答案",
        explanation="解释",
        answer="因为这样。",
    )
    assert only_question.question == "为什么？"
    assert only_question.answer == ""
    assert only_answer.answer == "因为这样。"
    assert only_answer.question == ""
