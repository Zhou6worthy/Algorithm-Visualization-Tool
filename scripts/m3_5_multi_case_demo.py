"""M3-5 多用例执行与 CaseRun 切换演示。

不启动 GUI，不使用 Manim 完整 Scene；用 FakeScene 驱动 TwoSumStage，
验证同一 VisualPlan / 同一批组件实例在不同 true AnimationTrace 间切换。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from algoviz.execution.case_runner import CaseRunner
from algoviz.execution.case_store import CaseRunStore
from algoviz.protocol.cases import CaseSource, TestCaseSpec
from algoviz.render.two_sum_visuals import TwoSumStage

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


def case(case_id: str, name: str, nums: list[int], target: int, expected: Any, source: CaseSource = CaseSource.USER) -> TestCaseSpec:
    return TestCaseSpec(
        case_id=case_id,
        name=name,
        input_data={"nums": nums, "target": target},
        expected_output=expected,
        source=source,
    )


def main() -> int:
    out_dir = Path("output/m3_5")
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = [
        case("normal", "正常查找", [2, 7, 11, 15], 9, [0, 1]),
        case("first", "第一轮命中", [3, 2, 4], 5, [0, 1]),
        case("last", "最后一轮命中", [1, 2, 3, 4], 7, [2, 3]),
        case("none", "遍历结束未找到", [1, 2, 3], 100, []),
        case("duplicate", "重复数字", [3, 3], 6, [0, 1]),
        case("empty", "空输入", [], 9, []),
        case("single", "单元素", [5], 9, []),
        case("mismatch", "预期不一致", [1, 2, 3], 4, [1, 2]),
        TestCaseSpec(
            case_id="invalid",
            name="缺少 target",
            input_data={"nums": [1]},
            expected_output=None,
            source=CaseSource.USER,
        ),
        case("ai_supplemented", "AI 补充边界用例", [1, 2, 3], 5, [1, 2], CaseSource.AI_GENERATED),
    ]

    runner = CaseRunner(out_dir / "runs", source=SOURCE)
    runs = runner.run_cases(cases)
    store = CaseRunStore()
    for spec in cases:
        store.add_case(spec)
    for run in runs:
        store.add_run(run)

    print("=== M3-5 multi-case execution ===")
    for spec, run in zip(cases, runs):
        trace = run.execution_trace
        animation = run.animation_trace
        print(
            f"{spec.case_id:16} source={spec.source.value:12} status={run.status.value:7} "
            f"expected={run.expected_output!r} actual={run.actual_output!r} "
            f"events={len(trace.events) if trace else 0} steps={len(animation.steps) if animation else 0} "
            f"trace={trace.trace_id if trace else '-'}"
        )
        if run.error:
            print(f"{'':16} error={run.error}")

    stage = TwoSumStage(
        FakeScene(),
        colors=COLORS,
        font="Microsoft YaHei",
        code_font="Consolas",
        code=SOURCE,
    )
    normal_run = store.select_case("normal")
    if normal_run.animation_trace is None:
        raise SystemExit("normal case has no animation trace")
    stage.build(normal_run.animation_trace.steps[0].state_after)
    plan = stage.visual_plan
    assembly = stage.assembly
    if plan is None or assembly is None:
        raise SystemExit("stage assembly failed")
    component_ids = sorted(assembly.components)
    plan_id = id(plan)
    assembly_id = id(assembly)

    switch_states: list[dict[str, Any]] = []
    print("\n=== Case 1 -> Case 2 -> Case 1 ===")
    for case_id in ("normal", "first", "normal"):
        run = store.select_case(case_id)
        stage.load_case(run)
        state = {
            "case_id": case_id,
            "run_id": run.run_id,
            "current_case_id": stage.current_case_id,
            "current_step_index": stage.current_step_index,
            "array_values": stage.array_visualizer.displayed_values if stage.array_visualizer else None,
            "array_target": stage.array_visualizer.target_text if stage.array_visualizer else None,
            "hash_keys": stage.hash_visualizer.displayed_keys if stage.hash_visualizer else None,
            "variable_labels": stage.variable_visualizer.displayed_labels if stage.variable_visualizer else None,
            "variable_values": stage.variable_visualizer.displayed_values if stage.variable_visualizer else None,
            "code_line": stage.code_visualizer.current_line if stage.code_visualizer else None,
            "visual_plan_same": id(stage.visual_plan) == plan_id,
            "assembly_same": id(stage.assembly) == assembly_id,
            "component_ids": sorted(stage.assembly.components) if stage.assembly else None,
        }
        switch_states.append(state)
        print(json.dumps(state, ensure_ascii=False, indent=2))

    summary = {
        "source": SOURCE,
        "cases": [
            {
                "case_id": spec.case_id,
                "name": spec.name,
                "source": spec.source.value,
                "input_data": spec.input_data,
                "expected_output": spec.expected_output,
                "run_id": run.run_id,
                "status": run.status.value,
                "actual_output": run.actual_output,
                "execution_trace_id": run.execution_trace.trace_id if run.execution_trace else None,
                "animation_trace_execution_id": (
                    run.animation_trace.metadata.execution_trace_id if run.animation_trace else None
                ),
                "event_count": len(run.execution_trace.events) if run.execution_trace else 0,
                "step_count": len(run.animation_trace.steps) if run.animation_trace else 0,
                "work_dir": run.execution_metadata.get("work_dir"),
                "error": run.error,
            }
            for spec, run in zip(cases, runs)
        ],
        "visual_plan_same_across_switches": all(item["visual_plan_same"] for item in switch_states),
        "assembly_same_across_switches": all(item["assembly_same"] for item in switch_states),
        "component_ids": component_ids,
        "switch_states": switch_states,
    }
    (out_dir / "case_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nsummary: {out_dir / 'case_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
