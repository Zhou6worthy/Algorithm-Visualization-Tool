"""Two Sum 课堂提示生成器。

提示是独立的教学素材层：它读取真实 AnimationStep / VisualState，生成带
``related_step_id`` 的 StepHint，但绝不修改 AnimationTrace，也不重新执行算法。
"""
from __future__ import annotations

import json
from typing import Any

from ..protocol.events import AnimationStep, Trace, VisualState
from ..protocol.hints import HintKind, StepHint


def _fmt(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _var(state: VisualState, name: str) -> str | None:
    for item in state.variables:
        if item.name == name:
            return item.value
    return None


def _pointer_index(step: AnimationStep) -> int | None:
    state = step.state_after
    value = state.array.pointers.get("i") if state.array else None
    if value is None and step.targets and isinstance(step.targets[0], int):
        value = step.targets[0]
    return int(value) if value is not None else None


def _current_value(step: AnimationStep) -> str:
    state = step.state_after
    value = _var(state, "x")
    if value is not None:
        return value
    index = _pointer_index(step)
    if state.array and index is not None and 0 <= index < len(state.array.values):
        return _fmt(state.array.values[index])
    return "—"


def _entries(step: AnimationStep) -> dict[str, Any]:
    if not step.state_after.dict_state:
        return {}
    return {entry.key: entry.value for entry in step.state_after.dict_state.entries}


def _matched_index(step: AnimationStep) -> Any:
    if not step.state_after.dict_state:
        return None
    key = step.state_after.dict_state.lookup_key
    return _entries(step).get(str(key)) if key is not None else None


def _is_empty_return(step: AnimationStep) -> bool:
    returned = step.meta.get("return", step.targets)
    return isinstance(returned, list) and len(returned) == 0


def _hint_id(step: AnimationStep, suffix: str = "") -> str:
    base = f"two_sum_step_{step.step_id:02d}"
    return base + (f"_{suffix}" if suffix else "")


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
    suffix: str = "",
) -> StepHint:
    return StepHint(
        hint_id=_hint_id(step, suffix),
        related_step_id=step.step_id,
        kind=kind,
        title=title,
        explanation=explanation,
        common_mistake=common_mistake,
        question=question,
        answer=answer,
        concepts=concepts,
    )


def _init_hint(step: AnimationStep) -> StepHint:
    return _make(
        step,
        kind=HintKind.INITIALIZE,
        title="初始化：为什么要用哈希表？",
        explanation=(
            "Two Sum 的暴力做法要枚举所有数对，时间 O(n²)。这里先建立一个空的哈希表 seen，"
            "用来记录“已经见过的数字 → 它的下标”。每遍历到一个数字 x，只要查 target - x "
            "是否在 seen 中，就能在平均 O(1) 时间内判断它有没有搭档。"
        ),
        common_mistake="把哈希表当成保存答案的容器；它保存的是已经遍历过的元素和下标。",
        question="为什么需要哈希表？如果不用它，怎样找到两个数？",
        answer=(
            "哈希表把“查找另一个数”从线性扫描变成平均 O(1)。暴力解法要两层循环枚举数对，"
            "时间 O(n²)；哈希表只需一次遍历，平均时间 O(n)，代价是 O(n) 的额外空间。"
        ),
        concepts=["初始化", "为什么需要哈希表"],
    )


def _visit_hint(step: AnimationStep, trace: Trace) -> StepHint:
    index = _pointer_index(step)
    x = _current_value(step)
    target = trace.metadata.input.get("target")
    target_text = _fmt(target) if target is not None else "—"
    try:
        complement = _fmt(int(target) - int(x))
    except (TypeError, ValueError):
        complement = "—"
    seen_size = len(step.state_after.dict_state.entries) if step.state_after.dict_state else 0
    return _make(
        step,
        kind=HintKind.VISIT,
        title=f"访问 nums[{index if index is not None else '?'}] = {x}",
        explanation=(
            f"现在遍历到下标 {index if index is not None else '?'}，当前数字是 {x}。"
            f"目标是 {target_text}，所以这次要找的另一个数字是 {target_text} - {x} = {complement}。"
            f"此时 seen 中已经保存了 {seen_size} 个数字。"
        ),
        common_mistake="只盯着当前元素，忘了目标值 target 决定真正要查找的补数。",
        question=f"当前元素是 {x}，要凑成 {target_text}，还需要哪个数字？",
        answer=(
            f"还需要 {target_text} - {x} = {complement}。如果它已经在 seen 中，"
            "把它的下标和当前下标一起返回即可；否则先记录当前元素，继续往后找。"
        ),
        concepts=["遍历元素", "当前元素与 target"],
    )


def _compare_hint(step: AnimationStep, trace: Trace) -> StepHint | None:
    dict_state = step.state_after.dict_state
    if dict_state is None:
        return None
    need = _var(step.state_after, "need") or dict_state.lookup_key
    x = _current_value(step)
    index = _pointer_index(step)
    status = dict_state.lookup_status
    target = trace.metadata.input.get("target")
    target_text = _fmt(target) if target is not None else "—"
    if status == "hit":
        matched = _matched_index(step)
        return _make(
            step,
            kind=HintKind.COMPLEMENT_HIT,
            title="计算补数并查询：命中",
            explanation=(
                f"当前数字是 {x}。为了凑成 {target_text}，需要 target - x = {need}。"
                f"前面已经把 {need} 和它的下标 {matched} 存进了 seen，所以这次查询直接命中。"
                f"当前下标是 {index if index is not None else '?'}，可以返回 [{matched}, "
                f"{index if index is not None else '?'}]。"
            ),
            common_mistake="先插入当前元素再查询，可能把当前元素自己当成搭档，返回重复下标。",
            question="为什么找到补数后就可以返回？如果数组中有重复数字，算法还能正常工作吗？",
            answer=(
                "因为每个位置只访问一次，补数已经在前面出现过，它的下标与当前下标不同，"
                "已经构成答案。重复数字如 [3, 3] 时，第二次遇到 3 才会命中；"
                "先查询后插入保证不会用同一个下标。"
            ),
            concepts=["计算补数", "查询哈希表", "查询 hit"],
            suffix="hit",
        )
    if status == "miss":
        return _make(
            step,
            kind=HintKind.COMPLEMENT_MISS,
            title="计算补数并查询：未命中",
            explanation=(
                f"当前数字是 {x}，目标是 {target_text}，需要补数 {target_text} - {x} = {need}。"
                f"在 seen 中查找 {need}：未命中，说明前面还没有出现能和 {x} 配对的数字。"
                "所以现在还不能返回，需要把当前数字记录下来，继续遍历后面的元素。"
            ),
            common_mistake="查询未命中就返回；其实当前元素可能正是后面某个元素的补数。",
            question="为什么当前元素暂时不能组成答案？下一步应该做什么？",
            answer=(
                f"因为前面还没有出现 {need}。下一步把当前数字 {x} 和下标 "
                f"{index if index is not None else '?'} 写入 seen，然后继续遍历；"
                f"后面的元素如果正好需要 {x}，就会命中。"
            ),
            concepts=["计算补数", "查询哈希表", "查询 miss"],
            suffix="miss",
        )
    return None


def _insert_hint(step: AnimationStep) -> StepHint:
    key = step.meta.get("key")
    value = step.meta.get("value")
    x = _current_value(step)
    index = _pointer_index(step)
    return _make(
        step,
        kind=HintKind.INSERT,
        title="写入 seen：保存的是什么？",
        explanation=(
            f"把当前数字 {key if key is not None else x} 作为 key，下标 "
            f"{value if value is not None else index if index is not None else '?'} 作为 value "
            "写进 seen。以后遇到数字 y 时，只要查 seen 里有没有 target - y，"
            "就能直接拿到搭档的下标。"
        ),
        common_mistake="只保存数字不保存下标；或者把下标当 key，导致无法按补数查找。",
        question="哈希表中保存的是什么信息？为什么 key 是数字，value 是下标？",
        answer=(
            "key 是已经出现过的数字，方便直接按 target - x 查找；"
            "value 是它在数组中的下标，命中后返回的正是这个下标。"
        ),
        concepts=["插入元素", "哈希表保存内容"],
    )


def _found_hint(step: AnimationStep, trace: Trace) -> StepHint:
    returned = step.meta.get("return", step.targets)
    if _is_empty_return(step):
        return _make(
            step,
            kind=HintKind.NOT_FOUND,
            title="遍历结束：没有找到答案",
            explanation=(
                "数组已经全部访问完，seen 中始终没有出现当前元素需要的补数，"
                "因此返回空列表。空列表是合法结果，不是执行失败。"
            ),
            common_mistake="把空结果当成程序错误；Two Sum 在无解时返回 [] 是正常行为。",
            question="遍历结束仍未找到，说明什么？如果题目保证有解，应该检查什么？",
            answer=(
                "说明不存在两个不同下标之和等于 target。如果题目保证有解，"
                "应检查是否写错了下标、是否提前把当前元素插入 seen，或输入是否满足题目条件。"
            ),
            concepts=["完成返回", "未找到"],
            suffix="not_found",
        )
    nums = trace.metadata.input.get("nums", [])
    values = []
    if isinstance(returned, list):
        for item in returned:
            if isinstance(item, int) and 0 <= item < len(nums):
                values.append(f"nums[{item}]={nums[item]}")
    pair_text = "、".join(values) if values else "这两个下标"
    return _make(
        step,
        kind=HintKind.RETURN,
        title="返回答案：为什么可以提前结束？",
        explanation=(
            f"已经找到一对下标 {_fmt(returned)}，{pair_text} 的和等于目标值。"
            "题目只要求返回任意一对答案，所以找到后可以立即结束，不需要继续遍历。"
        ),
        common_mistake="找到答案后仍继续遍历，可能覆盖结果；或者返回了同一个下标两次。",
        question="为什么可以提前返回？这对时间复杂度有什么影响？",
        answer=(
            "一旦命中，就说明存在一对合法下标，继续遍历不会让答案更正确。"
            "最好情况下第一个元素就命中，时间 O(1)；最坏情况仍要遍历整个数组，平均 O(n)。"
        ),
        concepts=["完成返回", "为什么可以返回"],
        suffix="return",
    )


def _complete_hint(step: AnimationStep) -> StepHint:
    return _make(
        step,
        kind=HintKind.COMPLETE,
        title="算法完成：复杂度是什么？",
        explanation=(
            "整个算法只遍历数组一次，每个元素最多做一次哈希查找和一次插入。"
            "哈希表查找/插入平均 O(1)，所以平均时间复杂度 O(n)；"
            "额外保存最多 n 个数字及其下标，空间复杂度 O(n)。"
        ),
        common_mistake="把哈希表的平均 O(1) 说成绝对 O(1)；大量冲突时单次查找可能退化。",
        question="算法的时间和空间复杂度是多少？如果不用哈希表，还有什么解法？",
        answer=(
            "平均时间 O(n)，额外空间 O(n)。也可以先排序再用双指针，时间 O(n log n)，"
            "空间取决于排序实现；或者使用两层循环暴力枚举，时间 O(n²)、空间 O(1)。"
        ),
        concepts=["完成", "复杂度"],
    )


def build_two_sum_hints(trace: Trace) -> list[StepHint]:
    """为一条真实 Two Sum AnimationTrace 生成按 step_id 对齐的提示列表。"""
    hints: list[StepHint] = []
    for step in trace.steps:
        hint: StepHint | None = None
        step_type = step.type.value
        if step_type == "init":
            hint = _init_hint(step)
        elif step_type == "visit":
            hint = _visit_hint(step, trace)
        elif step_type == "compare":
            hint = _compare_hint(step, trace)
        elif step_type == "update":
            hint = _insert_hint(step)
        elif step_type == "found":
            hint = _found_hint(step, trace)
        elif step_type == "complete":
            hint = _complete_hint(step)
        if hint is not None:
            hints.append(hint)
    return hints


def hints_by_step(hints: list[StepHint]) -> dict[int, StepHint]:
    return {hint.related_step_id: hint for hint in hints}


def hint_concepts(hints: list[StepHint]) -> set[str]:
    return {concept for hint in hints for concept in hint.concepts}
