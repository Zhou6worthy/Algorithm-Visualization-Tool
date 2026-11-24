"""Binary Search 课堂提示：语义由真实 AnimationStep / VisualState 驱动。"""
from __future__ import annotations

import json
from typing import Any

from ..protocol.events import AnimationStep, Trace, VisualState
from ..protocol.hints import HintKind, StepHint


def _fmt(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _range(step: AnimationStep) -> tuple[int | None, int | None]:
    array = step.state_after.array
    if array is None or not array.active_range or len(array.active_range) != 2:
        return None, None
    return int(array.active_range[0]), int(array.active_range[1])


def _mid(step: AnimationStep) -> int | None:
    array = step.state_after.array
    if array and "mid" in array.pointers:
        return int(array.pointers["mid"])
    if step.targets and isinstance(step.targets[0], int):
        return int(step.targets[0])
    return None


def _value(step: AnimationStep, mid: int | None) -> Any:
    array = step.state_after.array
    if array and mid is not None and 0 <= mid < len(array.values):
        return array.values[mid]
    return None


def _make(
    step: AnimationStep,
    *,
    kind: HintKind,
    title: str,
    explanation: str,
    common_mistake: str,
    question: str,
    answer: str,
    concepts: list[str],
) -> StepHint:
    return StepHint(
        hint_id=f"binary_search_step_{step.step_id:02d}",
        related_step_id=step.step_id,
        kind=kind,
        title=title,
        explanation=explanation,
        common_mistake=common_mistake,
        question=question,
        answer=answer,
        concepts=concepts,
    )


def _init_hint(step: AnimationStep, trace: Trace) -> StepHint:
    left, right = _range(step)
    n = len(trace.metadata.input.get("nums", []))
    return _make(
        step,
        kind=HintKind.RANGE_INIT,
        title="初始化搜索区间",
        explanation=(
            f"二分查找只适用于有序数组。这里把整个数组作为初始搜索区间：left={left}，"
            f"right={right}，候选元素数量为 {n}。每次比较后，区间会缩小一半左右。"
        ),
        common_mistake="把 right 初始化为 len(nums)，导致访问越界；应使用最后一个下标 len(nums)-1。",
        question="为什么二分查找的初始搜索区间是 [0, n-1]，而不是 [0, n]？",
        answer="数组下标范围是 0 到 n-1；right 指向闭区间最后一个元素，所以是 n-1。",
        concepts=["初始化区间", "left/right", "有序数组"],
    )


def _visit_hint(step: AnimationStep, trace: Trace) -> StepHint:
    left, right = _range(step)
    mid = _mid(step)
    value = _value(step, mid)
    target = trace.metadata.input.get("target")
    return _make(
        step,
        kind=HintKind.PROBE,
        title=f"计算中点：mid = {mid}",
        explanation=(
            f"当前区间是 [{left}, {right}]。取中点 mid = (left + right) // 2 = {mid}，"
            f"读取 nums[{mid}] = {_fmt(value)}，准备和目标值 {_fmt(target)} 比较。"
            "整数除法保证 mid 是一个合法下标。"
        ),
        common_mistake="使用 (left + right) / 2 得到浮点数，或忘记 mid 是下标而不是数组值。",
        question=f"当前区间 [{left}, {right}] 的中点为什么是 {mid}？下一步比较哪两个值？",
        answer=f"mid=({left}+{right})//2={mid}；比较 nums[{mid}]={_fmt(value)} 与 target={_fmt(target)}。",
        concepts=["计算中点", "mid", "数组访问"],
    )


def _compare_hint(step: AnimationStep, trace: Trace) -> StepHint:
    outcome = str(step.meta.get("outcome") or "")
    left, right = _range(step)
    mid = _mid(step)
    value = _value(step, mid)
    target = trace.metadata.input.get("target")
    if outcome == "hit":
        return _make(
            step,
            kind=HintKind.FOUND,
            title="命中目标，可以立即返回",
            explanation=(
                f"nums[mid] = nums[{mid}] = {_fmt(value)}，正好等于 target = {_fmt(target)}。"
                f"题目只要求一个下标，所以直接返回 mid={mid}，不继续搜索。"
            ),
            common_mistake="命中后仍继续移动 left/right，错过答案；或者返回 nums[mid] 而不是下标。",
            question=f"为什么 nums[{mid}] 等于 target 后可以立即返回？应该返回下标还是数组值？",
            answer=f"已经找到精确匹配，可以提前结束；应返回下标 {mid}，而不是值 {_fmt(value)}。",
            concepts=["命中", "提前返回", "返回值是下标"],
        )
    if outcome == "less":
        return _make(
            step,
            kind=HintKind.COMPARE_LESS,
            title="中间值小于 target：放弃左半区",
            explanation=(
                f"nums[{mid}] = {_fmt(value)} < target = {_fmt(target)}。由于数组有序，"
                f"mid 及其左侧的所有元素都不大于 {_fmt(value)}，不可能等于 target，"
                f"所以搜索区间缩小为 [{mid + 1}, {right}]。"
            ),
            common_mistake="把 left 更新成 mid 而不是 mid+1，导致重复访问同一个 mid，甚至死循环。",
            question=f"既然 nums[{mid}] < target，为什么可以排除 mid 及左侧？新的 left 应该是什么？",
            answer=(
                f"有序数组中 mid 左侧都 ≤ nums[{mid}] < target，可以安全排除；"
                f"left 应更新为 mid+1={mid + 1}。"
            ),
            concepts=["比较", "中间值偏小", "left = mid + 1"],
        )
    if outcome == "greater":
        return _make(
            step,
            kind=HintKind.COMPARE_GREATER,
            title="中间值大于 target：放弃右半区",
            explanation=(
                f"nums[{mid}] = {_fmt(value)} > target = {_fmt(target)}。由于数组有序，"
                f"mid 及其右侧的所有元素都不小于 {_fmt(value)}，不可能等于 target，"
                f"所以搜索区间缩小为 [{left}, {mid - 1}]。"
            ),
            common_mistake="把 right 更新成 mid，而不是 mid-1；或者忘记使用闭区间。",
            question=f"既然 nums[{mid}] > target，为什么可以排除 mid 及右侧？新的 right 应该是什么？",
            answer=(
                f"有序数组中 mid 右侧都 ≥ nums[{mid}] > target，可以安全排除；"
                f"right 应更新为 mid-1={mid - 1}。"
            ),
            concepts=["比较", "中间值偏大", "right = mid - 1"],
        )
    return _make(
        step,
        kind=HintKind.PROBE,
        title="比较中间值与目标值",
        explanation=f"比较 nums[{mid}] = {_fmt(value)} 与 target = {_fmt(target)}，根据大小关系缩小搜索区间。",
        common_mistake="比较了数组值但下一步移动了错误的边界。",
        question="当前比较结果会排除哪一半？为什么？",
        answer="根据有序性，比较结果可以排除一半候选区间。",
        concepts=["比较", "缩小区间"],
    )


def _move_hint(step: AnimationStep, trace: Trace) -> StepHint:
    left, right = _range(step)
    mid = _mid(step)
    return _make(
        step,
        kind=HintKind.PROBE,
        title="更新边界，搜索区间缩小",
        explanation=(
            f"根据上一次比较结果更新边界，当前搜索区间变为 [{left}, {right}]。"
            "区间中的元素数量至少减少一半，因此最多进行 O(log n) 轮。"
        ),
        common_mistake="边界更新方向反了，或者使用了开区间/闭区间混用。",
        question=f"新区间 [{left}, {right}] 是否仍然可能包含 target？为什么？",
        answer="由于数组有序，刚才排除的一半不可能包含 target，新区间保留的才是可能候选。",
        concepts=["边界移动", "区间收缩", "O(log n)"],
    )


def _return_hint(step: AnimationStep, trace: Trace) -> StepHint:
    returned = step.meta.get("return", step.targets[0] if step.targets else None)
    if isinstance(returned, int) and returned >= 0:
        return _make(
            step,
            kind=HintKind.FOUND,
            title=f"找到目标：返回下标 {returned}",
            explanation=(
                f"nums[{returned}] 与 target 相等，返回下标 {returned}。"
                "最后一次比较已经确认答案，不需要继续循环。"
            ),
            common_mistake="返回数组值而不是下标；或者在返回后继续执行循环。",
            question="返回值应该是什么？为什么不能返回 nums[mid]？",
            answer=f"应返回下标 {returned}；题目要求位置，数组值只是用来比较。",
            concepts=["完成返回", "返回下标"],
        )
    return _make(
        step,
        kind=HintKind.NOT_FOUND,
        title="区间为空：返回 -1",
        explanation=(
            "left > right 时，搜索区间已经没有元素。说明 target 不在数组中，"
            "返回 -1 是合法结果，不是执行错误。"
        ),
        common_mistake="把 -1 当成程序失败；或者在区间为空后继续访问 nums[mid]。",
        question="left 超过 right 说明什么？为什么此时可以确定 target 不存在？",
        answer="搜索区间为空，所有候选都被排除，因此 target 不存在，返回 -1。",
        concepts=["未找到", "空区间", "返回 -1"],
    )


def _complete_hint(step: AnimationStep) -> StepHint:
    return _make(
        step,
        kind=HintKind.SEARCH_COMPLETE,
        title="二分查找完成：复杂度是什么？",
        explanation=(
            "每轮比较都把候选区间大约减半，最多执行 O(log n) 轮；只使用 left/right/mid 常量个变量，"
            "额外空间 O(1)。"
        ),
        common_mistake="把二分查找说成 O(n)，或忽略数组必须有序这一前提。",
        question="二分查找的时间复杂度和空间复杂度是多少？为什么它比线性查找快？",
        answer="时间 O(log n)，额外空间 O(1)；每轮排除一半元素，因此比 O(n) 线性查找更快。",
        concepts=["复杂度", "O(log n)", "O(1)"],
    )


def build_binary_search_hints(trace: Trace) -> list[StepHint]:
    hints: list[StepHint] = []
    for step in trace.steps:
        if step.type.value == "init":
            hint = _init_hint(step, trace)
        elif step.type.value == "visit":
            hint = _visit_hint(step, trace)
        elif step.type.value == "compare":
            hint = _compare_hint(step, trace)
        elif step.type.value == "move":
            hint = _move_hint(step, trace)
        elif step.type.value == "found":
            hint = _return_hint(step, trace)
        elif step.type.value == "complete":
            hint = _complete_hint(step)
        else:
            hint = None
        if hint is not None:
            hints.append(hint)
    return hints


def hints_by_step(hints: list[StepHint]) -> dict[int, StepHint]:
    return {hint.related_step_id: hint for hint in hints}
