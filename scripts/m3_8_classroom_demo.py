"""M3-6～M3-8 真实演示：10 个 Two Sum 用例 -> 独立轨迹 -> 课堂 HTML。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from algoviz.execution.case_runner import CaseRunner
from algoviz.execution.case_store import CaseRunStore
from algoviz.protocol.cases import CaseSource, TestCaseSpec
from algoviz.protocol.hints import StepHint
from algoviz.teaching.classroom import build_classroom_deck
from algoviz.teaching.classroom_html import write_classroom_html
from algoviz.teaching.playback import PlaybackController
from algoviz.teaching.step_hints import build_two_sum_hints, hint_concepts
from algoviz.teaching.two_sum_profile import TwoSumVisualProfile

SOURCE = """def two_sum(nums, target):
    seen = {}
    for i, x in enumerate(nums):
        need = target - x
        if need in seen:
            return [seen[need], i]
        seen[x] = i
    return []
"""


def case(
    case_id: str,
    name: str,
    nums: list[int],
    target: int,
    expected: Any,
    source: CaseSource = CaseSource.USER,
    description: str = "",
) -> TestCaseSpec:
    return TestCaseSpec(
        case_id=case_id,
        name=name,
        input_data={"nums": nums, "target": target},
        expected_output=expected,
        source=source,
        description=description,
    )


CASES = [
    case("normal", "正常查找", [2, 7, 11, 15], 9, [0, 1], description="第二轮命中"),
    case("first", "第二个元素命中", [3, 2, 4], 5, [0, 1], description="补数在 seen 中"),
    case("last", "最后一个元素命中", [1, 2, 3, 4], 7, [2, 3], description="走到最后才命中"),
    case("none", "找不到答案", [1, 2, 3], 100, [], description="遍历结束返回空列表"),
    case("duplicate", "重复数字", [3, 3], 6, [0, 1], description="先查后插避免自配对"),
    case("empty", "空数组", [], 9, [], description="没有元素可遍历"),
    case("single", "单元素数组", [5], 9, [], description="只有一个元素时无解"),
    case("mismatch", "预期输出不匹配", [1, 2, 3], 4, [1, 2], description="真实执行返回 [0,2]"),
    TestCaseSpec(
        case_id="invalid",
        name="缺少 target",
        input_data={"nums": [1]},
        expected_output=None,
        source=CaseSource.USER,
        description="输入校验失败，没有伪造轨迹",
    ),
    case(
        "ai_supplemented",
        "AI 补充边界用例",
        [1, 2, 3],
        5,
        [1, 2],
        CaseSource.AI_GENERATED,
        "边界补充用例",
    ),
]


def _controller_check(runs: dict[str, Any]) -> dict[str, Any]:
    """实际走一遍 Python 控制器的用例切换，不启动 Manim。"""
    seen_steps: list[int] = []
    controller = PlaybackController(on_step=lambda step: seen_steps.append(step.step_id))
    normal = runs["normal"]
    first = runs["first"]
    controller.load_case(normal, hints=build_two_sum_hints(normal.animation_trace))
    normal_trace_id = controller.snapshot().trace_id
    normal_steps = controller.snapshot().step_count
    controller.next_step()
    controller.next_step()
    after_next = controller.current_step_index
    controller.load_case(first, hints=build_two_sum_hints(first.animation_trace))
    first_trace_id = controller.snapshot().trace_id
    first_steps = controller.snapshot().step_count
    first_array = controller.current_step.state_after.array.values if controller.current_step else []
    controller.load_case(normal, hints=build_two_sum_hints(normal.animation_trace))
    return {
        "normal_trace_id": normal_trace_id,
        "normal_step_count": normal_steps,
        "after_two_next": after_next,
        "first_trace_id": first_trace_id,
        "first_step_count": first_steps,
        "first_array": first_array,
        "switched_back_trace_id": controller.snapshot().trace_id,
        "switched_back_index": controller.current_step_index,
        "same_trace_after_switch_back": controller.snapshot().trace_id == normal_trace_id,
        "callback_step_ids": seen_steps,
    }


def main() -> int:
    out_dir = Path("output/m3_8")
    out_dir.mkdir(parents=True, exist_ok=True)
    runner = CaseRunner(out_dir / "runs", source=SOURCE)
    runs = runner.run_cases(CASES)
    by_id = {spec.case_id: run for spec, run in zip(CASES, runs)}
    store = CaseRunStore()
    for spec in CASES:
        store.add_case(spec)
    for run in runs:
        store.add_run(run)

    deck = build_classroom_deck(
        store.latest_pairs(),
        profile=TwoSumVisualProfile(),
        title="Two Sum · 哈希表课堂演示",
        code=SOURCE,
    )
    html_path = write_classroom_html(deck, out_dir / "classroom.html")
    deck_path = out_dir / "classroom_deck.json"
    deck_path.write_text(deck.model_dump_json(indent=2), encoding="utf-8")

    print("=== M3-8 真实多用例 ===")
    for spec, run in zip(CASES, runs):
        trace = run.animation_trace
        print(
            f"{spec.case_id:16} source={spec.source.value:12} status={run.status.value:7} "
            f"expected={run.expected_output!r} actual={run.actual_output!r} "
            f"steps={len(trace.steps) if trace else 0} trace={trace.metadata.execution_trace_id if trace else '-'}"
        )
        if run.error:
            print(f"{'':16} error={run.error}")

    hints: list[StepHint] = []
    if deck.cases[0].trace is not None:
        hints = build_two_sum_hints(deck.cases[0].trace)
    concepts = sorted(hint_concepts(hints))
    controller = _controller_check(by_id)
    summary = {
        "source": SOURCE,
        "html": str(html_path),
        "deck_json": str(deck_path),
        "case_count": len(CASES),
        "case_count_with_trace": sum(1 for run in runs if run.animation_trace is not None),
        "store_case_count": store.case_count,
        "store_run_count": store.run_count,
        "store_active_case": store.current_case_id,
        "cases": [
            {
                "case_id": spec.case_id,
                "name": spec.name,
                "source": spec.source.value,
                "status": run.status.value,
                "input_data": spec.input_data,
                "expected_output": run.expected_output,
                "actual_output": run.actual_output,
                "run_id": run.run_id,
                "execution_trace_id": run.execution_trace.trace_id if run.execution_trace else None,
                "animation_trace_id": (
                    run.animation_trace.metadata.execution_trace_id if run.animation_trace else None
                ),
                "step_count": len(run.animation_trace.steps) if run.animation_trace else 0,
                "event_count": len(run.execution_trace.events) if run.execution_trace else 0,
                "error": run.error,
            }
            for spec, run in zip(CASES, runs)
        ],
        "hint_concepts": concepts,
        "normal_hint_count": len(hints),
        "controller_switch": controller,
        "deck": {
            "visual_plan_component_ids": [item.component_id for item in deck.visual_plan.components],
            "active_case_id": deck.active_case_id,
        },
    }
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== 课堂 HTML ===")
    print(f"html     : {html_path}")
    print(f"deck     : {deck_path}")
    print(f"summary  : {summary_path}")
    print(f"hints    : {len(hints)} 条；概念覆盖 {', '.join(concepts)}")
    print(f"controller switch: {json.dumps(controller, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
