from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from algoviz.execution.case_runner import CaseRunner
from algoviz.execution.case_store import CaseStoreError, CaseRunStore
from algoviz.protocol.cases import CaseRun, CaseRunStatus, CaseSource, TestCaseSpec
from algoviz.protocol.events import ArrayState, VisualKind, VisualState
from algoviz.render.two_sum_visuals import CaseLoadError, TwoSumStage

SOURCE = """def two_sum(nums, target):
    seen = {}
    for i, x in enumerate(nums):
        need = target - x
        if need in seen:
            return [seen[need], i]
        seen[x] = i
    return []
"""

COLORS = {
    "panel": "#16233D",
    "panel_alt": "#1C2B49",
    "border": "#2A3B5E",
    "text": "#E8EEF9",
    "muted": "#9AA9C2",
    "accent": "#FBBF24",
    "compare": "#38BDF8",
    "sorted": "#34D399",
    "danger": "#F87171",
}


class FakeScene:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.removed: list[Any] = []
        self.played: list[Any] = []

    def add(self, *mobjects: Any) -> None:
        self.added.extend(mobjects)

    def remove(self, *mobjects: Any) -> None:
        self.removed.extend(mobjects)

    def play(self, *animations: Any, run_time: float = 0.25) -> None:
        self.played.append((animations, run_time))

    def wait(self, duration: float) -> None:
        pass

    def bring_to_front(self, *mobjects: Any) -> None:
        pass


def _case(case_id: str, nums: list[int], target: int, expected: Any, source: CaseSource = CaseSource.USER) -> TestCaseSpec:
    return TestCaseSpec(
        case_id=case_id,
        name=case_id,
        input_data={"nums": nums, "target": target},
        expected_output=expected,
        source=source,
    )


def _runner(tmp_path: Path) -> CaseRunner:
    return CaseRunner(tmp_path / "runs", source=SOURCE)


def test_case_models_and_sources() -> None:
    spec = _case("case_1", [2, 7], 9, [0, 1], CaseSource.AI_GENERATED)
    assert spec.source is CaseSource.AI_GENERATED
    assert spec.input_data["nums"] == [2, 7]

    pending = CaseRun(run_id="run_1", case_id="case_1", status=CaseRunStatus.PENDING)
    assert pending.status is CaseRunStatus.PENDING

    with pytest.raises(ValidationError):
        CaseRun(run_id="run_bad", case_id="case_1", status=CaseRunStatus.SUCCESS)


def test_case_runner_edge_cases(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    cases = [
        _case("normal", [2, 7, 11, 15], 9, [0, 1]),
        _case("first", [3, 2, 4], 5, [0, 1]),
        _case("last", [1, 2, 3, 4], 7, [2, 3]),
        _case("none", [1, 2, 3], 100, []),
        _case("duplicate", [3, 3], 6, [0, 1]),
        _case("empty", [], 9, []),
        _case("single", [5], 9, []),
    ]
    runs = runner.run_cases(cases)
    assert [run.status for run in runs] == [CaseRunStatus.SUCCESS] * len(cases)
    assert [run.actual_output for run in runs] == [[0, 1], [0, 1], [2, 3], [], [0, 1], [], []]
    assert len({run.run_id for run in runs}) == len(cases)
    assert len({run.execution_trace.trace_id for run in runs if run.execution_trace}) == len(cases)
    assert all(run.execution_trace is not None and run.animation_trace is not None for run in runs)
    assert len({id(run.execution_trace) for run in runs}) == len(cases)
    assert len({id(run.animation_trace) for run in runs}) == len(cases)
    assert len({len(run.animation_trace.steps) for run in runs if run.animation_trace}) > 1
    assert runs[0].execution_metadata["case_snapshot"]["input_data"] == {"nums": [2, 7, 11, 15], "target": 9}
    assert runs[0].execution_trace is not runs[1].execution_trace
    assert runs[0].execution_trace.events is not runs[1].execution_trace.events
    assert runs[0].animation_trace.steps is not runs[1].animation_trace.steps


def test_case_runner_leetcode_class_shape(tmp_path: Path) -> None:
    source = """class Solution:
    def two_sum(self, nums, target):
        seen = {}
        for i, x in enumerate(nums):
            need = target - x
            if need in seen:
                return [seen[need], i]
            seen[x] = i
        return []
"""
    runner = CaseRunner(
        tmp_path / "class_runs",
        source=source,
        style="leetcode_class",
        entry_point="Solution.two_sum",
    )
    run = runner.run_case(_case("class_case", [3, 2, 4], 5, [0, 1]))
    assert run.status is CaseRunStatus.SUCCESS
    assert run.actual_output == [0, 1]
    assert run.execution_trace is not None
    assert run.animation_trace is not None
    assert run.animation_trace.steps[0].code_line == 3


def test_case_runner_mismatch_optional_and_input_error(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    mismatch = runner.run_case(_case("mismatch", [1, 2, 3], 4, [1, 2]))
    assert mismatch.status is CaseRunStatus.FAILED
    assert mismatch.actual_output == [0, 2]
    assert mismatch.animation_trace is not None
    assert mismatch.execution_trace is not None
    assert "输出不一致" in (mismatch.error or "")

    optional = runner.run_case(_case("optional", [2, 7], 9, None))
    assert optional.status is CaseRunStatus.SUCCESS
    assert optional.actual_output == [0, 1]
    assert optional.execution_trace is not None
    assert optional.animation_trace is not None
    assert optional.execution_trace.validation.output_verified is False

    invalid = runner.run_case(
        TestCaseSpec(case_id="invalid", name="invalid", input_data={"nums": [1]})
    )
    assert invalid.status is CaseRunStatus.ERROR
    assert invalid.execution_trace is None
    assert invalid.animation_trace is None
    assert "target" in (invalid.error or "")


def test_repeated_case_run_creates_new_run_and_store_keeps_both(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    spec = _case("repeat", [2, 7], 9, [0, 1])
    first = runner.run_case(spec)
    second = runner.run_case(spec)
    assert first.run_id != second.run_id
    assert first.execution_trace.trace_id != second.execution_trace.trace_id

    store = CaseRunStore()
    store.add_case(spec)
    store.add_run(first)
    store.add_run(second)
    assert store.run_count == 2
    assert [run.run_id for run in store.runs_for_case("repeat")] == [first.run_id, second.run_id]
    selected = store.select_case("repeat")
    assert selected.run_id == second.run_id
    assert store.current_case_id == "repeat"
    assert store.select_run(first.run_id).run_id == first.run_id


def test_case_store_errors(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    spec = _case("case", [2, 7], 9, [0, 1])
    store = CaseRunStore()
    with pytest.raises(CaseStoreError):
        store.get_case("missing")
    with pytest.raises(CaseStoreError):
        store.select_case("missing")
    store.add_case(spec)
    with pytest.raises(CaseStoreError):
        store.add_case(spec)
    run = runner.run_case(spec)
    store.add_run(run)
    with pytest.raises(CaseStoreError):
        store.add_run(run)
    with pytest.raises(CaseStoreError):
        store.select_case("not_run")


def test_stage_switch_reuses_assembly_and_visual_plan(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    normal = runner.run_case(_case("normal", [2, 7, 11, 15], 9, [0, 1]))
    last = runner.run_case(_case("last", [1, 2, 3, 4], 7, [2, 3]))
    assert normal.animation_trace is not None and last.animation_trace is not None

    stage = TwoSumStage(
        FakeScene(),
        colors=COLORS,
        font="Microsoft YaHei",
        code_font="Consolas",
        code=SOURCE,
    )
    stage.build(normal.animation_trace.steps[0].state_after)
    plan = stage.visual_plan
    assembly = stage.assembly
    ids = set(assembly.components)
    array_id = id(stage.array_visualizer)
    hash_id = id(stage.hash_visualizer)
    variable_id = id(stage.variable_visualizer)
    code_id = id(stage.code_visualizer)

    stage.load_case(normal)
    assert stage.current_case_id == "normal"
    assert stage.current_step_index == 0
    assert stage.array_visualizer.displayed_values == [2, 7, 11, 15]
    assert stage.hash_visualizer.displayed_keys == []

    # 把 normal 走到插入之后，留下 seen 状态，再切换到 last。
    for step in normal.animation_trace.steps[:4]:
        stage.play_step(step, 0.2)
    assert stage.hash_visualizer.displayed_keys == ["2"]

    stage.load_case(last)
    assert stage.visual_plan is plan
    assert stage.assembly is assembly
    assert set(stage.assembly.components) == ids
    assert id(stage.array_visualizer) == array_id
    assert id(stage.hash_visualizer) == hash_id
    assert id(stage.variable_visualizer) == variable_id
    assert id(stage.code_visualizer) == code_id
    assert stage.current_case_id == "last"
    assert stage.array_visualizer.displayed_values == [1, 2, 3, 4]
    assert stage.array_visualizer.target_text == "target = 7"
    assert stage.hash_visualizer.displayed_keys == []
    assert stage.variable_visualizer.displayed_values[3] == "7"
    assert stage.current_step_index == 0

    stage.load_case(normal)
    assert stage.array_visualizer.displayed_values == [2, 7, 11, 15]
    assert stage.array_visualizer.target_text == "target = 9"
    assert stage.hash_visualizer.displayed_keys == []
    assert stage.variable_visualizer.displayed_values[3] == "9"
    stage.play_step(normal.animation_trace.steps[0], 0.2)
    stage.reset()
    assert stage.current_case_id == "normal"
    assert stage.current_step_index == 0
    assert stage.array_visualizer.displayed_values == [2, 7, 11, 15]


def test_stage_rejects_case_without_animation_trace() -> None:
    stage = TwoSumStage(
        FakeScene(),
        colors=COLORS,
        font="Microsoft YaHei",
        code_font="Consolas",
        code=SOURCE,
    )
    stage.build(VisualState(kind=VisualKind.ARRAY, array=ArrayState(values=[])))
    run = CaseRun(run_id="run_error", case_id="case_error", status=CaseRunStatus.ERROR)
    with pytest.raises(CaseLoadError):
        stage.load_case(run)
