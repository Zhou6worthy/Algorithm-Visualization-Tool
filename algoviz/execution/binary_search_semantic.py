"""Binary Search semantic tracer.

它只把真实 GenericTrace 中可被证据支持的区间 / mid / 比较 / 边界移动 / 返回
转换成 SemanticOperation；不重新执行用户代码，也不为未知结构伪造动画。
"""
from __future__ import annotations

from typing import Any

from ..protocol.execution import (
    BranchArc,
    ExecutionEvent,
    GenericTrace,
    SemanticKind,
    SemanticOperation,
    StaticFacts,
)
from .semantic import SemanticContext, SemanticResult


class BinarySearchSemanticTracer:
    name = "binary_search"

    def analyze(
        self,
        generic: GenericTrace,
        static: StaticFacts,
        context: SemanticContext,
    ) -> SemanticResult:
        del context
        events = generic.events
        if not events:
            return SemanticResult([], [], "generic", ["没有执行事件"])
        if not static.loops:
            return self._generic(events, "缺少 while 循环结构")
        loop_line = static.loops[0].line
        branch_lines = {branch.line: branch for branch in static.branches}
        eq_line = next(
            (
                line
                for line, branch in branch_lines.items()
                if "==" in branch.condition and "target" in branch.condition
            ),
            None,
        )
        lt_line = next(
            (
                line
                for line, branch in branch_lines.items()
                if "<" in branch.condition and "target" in branch.condition and "=" not in branch.condition
            ),
            None,
        )
        mid_line = next(
            (
                assignment.line
                for assignment in static.assignments
                if assignment.target == "mid"
            ),
            None,
        )
        if eq_line is None or lt_line is None or mid_line is None:
            return self._generic(events, "缺少 mid / 比较 / 边界移动的 AST 结构")

        by_frame: dict[int, list[ExecutionEvent]] = {}
        for event in events:
            by_frame.setdefault(event.frame_id, []).append(event)
        next_event: dict[int, ExecutionEvent] = {}
        for frame_events in by_frame.values():
            for previous, current in zip(frame_events, frame_events[1:]):
                next_event[previous.event_id] = current
        arc_by_from: dict[int, BranchArc] = {
            arc.from_event_id: arc for arc in generic.arcs if arc.from_event_id is not None
        }

        ops: list[SemanticOperation] = []
        consumed: set[int] = set()

        init_event = next(
            (
                event
                for event in events
                if event.event == "line"
                and event.line < loop_line
                and isinstance(event.locals_after, dict)
                and isinstance(event.locals_after.get("left"), int)
                and isinstance(event.locals_after.get("right"), int)
            ),
            None,
        )
        if init_event is not None and isinstance(init_event.locals_after, dict):
            left = int(init_event.locals_after["left"])
            right = int(init_event.locals_after["right"])
            ops.append(
                self._op(
                    ops,
                    SemanticKind.INIT,
                    evidence=self._evidence_with_next(init_event, next_event),
                    line=init_event.line,
                    values_before={"left": left, "right": right},
                    values_after={"left": left, "right": right},
                    description=f"初始化搜索区间 [{left}, {right}]",
                    data={"left": left, "right": right},
                )
            )
            consumed.add(init_event.event_id)

        # 指针移动的实际赋值行：left = mid + 1 / right = mid - 1
        move_lines = {
            assignment.line
            for assignment in static.assignments
            if assignment.target in {"left", "right"} and assignment.line > loop_line
        }

        for event in events:
            if event.event != "line":
                continue
            after = event.locals_after if isinstance(event.locals_after, dict) else {}
            before = event.locals_before if isinstance(event.locals_before, dict) else {}
            left = after.get("left", before.get("left"))
            right = after.get("right", before.get("right"))
            mid = after.get("mid", before.get("mid"))
            if event.line == mid_line and isinstance(mid, int) and isinstance(left, int) and isinstance(right, int):
                value = self._array_value(before.get("nums", after.get("nums")), mid)
                ops.append(
                    self._op(
                        ops,
                        SemanticKind.VISIT,
                        evidence=self._evidence_with_next(event, next_event),
                        line=event.line,
                        targets=[mid],
                        values_before={"left": left, "right": right, "mid": mid},
                        values_after={"left": left, "right": right, "mid": mid},
                        description=f"计算 mid={mid}，访问 nums[{mid}]={value!r}",
                        data={"left": left, "right": right, "mid": mid, "value": value},
                    )
                )
                consumed.add(event.event_id)
                continue
            if event.line in {eq_line, lt_line}:
                arc = arc_by_from.get(event.event_id)
                if arc is None or arc.kind not in {"if_true", "if_false"}:
                    continue
                value = self._array_value(before.get("nums", after.get("nums")), mid)
                if event.line == eq_line:
                    outcome = "hit" if arc.kind == "if_true" else "not_equal"
                    desc = (
                        f"nums[{mid}]={value!r} 等于 target，命中"
                        if outcome == "hit"
                        else f"nums[{mid}]={value!r} 不等于 target，继续缩小范围"
                    )
                else:
                    outcome = "less" if arc.kind == "if_true" else "greater"
                    desc = (
                        f"nums[{mid}]={value!r} 小于 target，搜索右半区"
                        if outcome == "less"
                        else f"nums[{mid}]={value!r} 大于 target，搜索左半区"
                    )
                ops.append(
                    self._op(
                        ops,
                        SemanticKind.COMPARE,
                        evidence=[event.event_id] + ([arc.to_event_id] if arc.to_event_id else []),
                        line=event.line,
                        values_before={"left": left, "right": right, "mid": mid},
                        values_after={"left": left, "right": right, "mid": mid},
                        description=desc,
                        data={
                            "left": left,
                            "right": right,
                            "mid": mid,
                            "value": value,
                            "target": before.get("target", after.get("target")),
                            "outcome": outcome,
                        },
                    )
                )
                consumed.add(event.event_id)
                continue
            if event.line in move_lines and isinstance(left, int) and isinstance(right, int):
                old_left = int(before.get("left", left))
                old_right = int(before.get("right", right))
                if left == old_left and right == old_right:
                    continue
                ops.append(
                    self._op(
                        ops,
                        SemanticKind.POINTER_MOVE,
                        evidence=self._evidence_with_next(event, next_event),
                        line=event.line,
                        values_before={"left": old_left, "right": old_right, "mid": mid},
                        values_after={"left": left, "right": right, "mid": mid},
                        description=(
                            f"缩小搜索区间：left {old_left}→{left}，right {old_right}→{right}"
                        ),
                        data={"left": left, "right": right, "old_left": old_left, "old_right": old_right},
                    )
                )
                consumed.add(event.event_id)

        returns = [event for event in events if event.event == "return" and not event.is_unwind]
        if returns:
            ret = returns[-1]
            returned = ret.return_value
            found = isinstance(returned, int) and returned >= 0
            ops.append(
                self._op(
                    ops,
                    SemanticKind.RETURN,
                    evidence=[ret.event_id],
                    line=ret.line,
                    values_after={"return": returned},
                    description=f"返回 {returned!r}",
                    data={"return": returned, "found": found},
                )
            )
            ops.append(
                self._op(
                    ops,
                    SemanticKind.COMPLETE,
                    evidence=[ret.event_id],
                    line=ret.line,
                    values_after={"return": returned},
                    description="二分查找执行完成",
                    data={"return": returned, "found": found},
                )
            )
            consumed.add(ret.event_id)
        else:
            return self._generic(events, "没有真实 return 事件，追踪可能不完整")

        ops.sort(key=lambda op: min(op.evidence_event_ids))
        for index, op in enumerate(ops):
            op.op_id = index
        unmapped = [
            event.event_id
            for event in events
            if event.event == "line" and event.event_id not in consumed
        ]
        return SemanticResult(ops, unmapped, "specific")

    @staticmethod
    def _array_value(nums: Any, index: Any) -> Any:
        if isinstance(nums, list) and isinstance(index, int) and 0 <= index < len(nums):
            return nums[index]
        return None

    def _op(self, ops: list[SemanticOperation], kind: SemanticKind, **kwargs: Any) -> SemanticOperation:
        if "evidence" in kwargs:
            kwargs["evidence_event_ids"] = kwargs.pop("evidence")
        if "line" in kwargs:
            kwargs["original_line"] = kwargs.pop("line")
        return SemanticOperation(op_id=len(ops), kind=kind, **kwargs)

    @staticmethod
    def _evidence_with_next(event: ExecutionEvent, next_event: dict[int, ExecutionEvent]) -> list[int]:
        following = next_event.get(event.event_id)
        return [event.event_id] + ([following.event_id] if following else [])

    def _generic(self, events: list[ExecutionEvent], reason: str) -> SemanticResult:
        ops: list[SemanticOperation] = []
        for event in events:
            if event.event != "line" or not event.changed:
                continue
            ops.append(
                SemanticOperation(
                    op_id=len(ops),
                    kind=SemanticKind.GENERIC_LINE,
                    evidence_event_ids=[event.event_id],
                    original_line=event.line,
                    values_before={key: event.locals_before.get(key) for key in event.changed},
                    values_after={key: (event.locals_after or {}).get(key) for key in event.changed},
                    confidence=1.0,
                    description=f"执行第 {event.line} 行，变量变化：{', '.join(event.changed)}",
                )
            )
        return SemanticResult(ops, [event.event_id for event in events if event.event == "line"], "generic", [reason])
