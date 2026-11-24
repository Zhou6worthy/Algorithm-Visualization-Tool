"""Two Sum 语义追踪：AST 结构 + 实际执行路径 + 变量证据。

M1 只实现 Two Sum 专用 Semantic Tracer；无法证明时降级为 GENERIC_LINE。
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


class SemanticContext:
    def __init__(self, algorithm_hint: str | None = None, source: str = "") -> None:
        self.algorithm_hint = algorithm_hint
        self.source = source


class SemanticResult:
    def __init__(
        self,
        operations: list[SemanticOperation],
        unmapped_event_ids: list[int],
        semantic_quality: str,
        warnings: list[str] | None = None,
    ) -> None:
        self.operations = operations
        self.unmapped_event_ids = unmapped_event_ids
        self.semantic_quality = semantic_quality
        self.warnings = warnings or []


class TwoSumSemanticTracer:
    name = "two_sum"

    def analyze(
        self,
        generic: GenericTrace,
        static: StaticFacts,
        context: SemanticContext,
    ) -> SemanticResult:
        events = generic.events
        if not events:
            return SemanticResult([], [], "generic", ["没有执行事件"])
        by_id = {event.event_id: event for event in events}
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

        lookup_line = self._lookup_line(static)
        insert_line = self._insert_line(static)
        loop_line = static.loops[0].line if static.loops else None
        if lookup_line is None or insert_line is None or loop_line is None:
            return self._generic(events, "缺少 AST 结构（if/for/subscript）")

        ops: list[SemanticOperation] = []
        consumed: set[int] = set()

        # 1) 初始化：第一个循环帧之前的 line 事件；用 seen 的快照确认
        init_event = next((e for e in events if e.event == "line" and e.line == loop_line - 1), None)
        if init_event and isinstance(init_event.locals_after, dict) and "seen" in init_event.locals_after:
            seen_after = init_event.locals_after.get("seen")
            if isinstance(seen_after, dict) and not seen_after:
                ops.append(
                    self._op(
                        ops,
                        SemanticKind.INIT,
                        evidence=[init_event.event_id] + ([next_event[init_event.event_id].event_id] if init_event.event_id in next_event else []),
                        line=init_event.line,
                        values_after={"seen": seen_after},
                        description="初始化空哈希表 seen",
                    )
                )
                consumed.add(init_event.event_id)

        # 2) 数组访问：for 头行，使用其 after（由下一事件确认）
        for event in events:
            if event.event != "line" or event.line != loop_line:
                continue
            after = event.locals_after or {}
            i, x = after.get("i"), after.get("x")
            if isinstance(i, int) and x is not None:
                ops.append(
                    self._op(
                        ops,
                        SemanticKind.VISIT,
                        evidence=self._evidence_with_next(event, next_event),
                        line=event.line,
                        targets=[i],
                        values_before={"i": i, "x": x, "seen": after.get("seen", {})},
                        values_after={"i": i, "x": x, "seen": after.get("seen", {})},
                        description=f"访问 nums[{i}]={x}",
                        data={"index": i, "value": x},
                    )
                )
                consumed.add(event.event_id)

        # 3) 哈希查找：if 行；hit/miss 必须来自实际 arc
        for event in events:
            if event.event != "line" or event.line != lookup_line:
                continue
            arc = arc_by_from.get(event.event_id)
            if arc is None or arc.kind not in {"if_true", "if_false"}:
                continue
            need = event.locals_before.get("need")
            seen_before = event.locals_before.get("seen", {})
            seen_after = event.locals_after.get("seen", seen_before) if isinstance(event.locals_after, dict) else seen_before
            if not isinstance(seen_before, dict) or need is None:
                continue
            hit = arc.kind == "if_true"
            ops.append(
                self._op(
                    ops,
                    SemanticKind.HASH_LOOKUP,
                    evidence=[event.event_id, arc.to_event_id] if arc.to_event_id else [event.event_id],
                    line=event.line,
                    targets=[event.locals_before.get("i", 0)],
                    values_before={"need": need, "seen": seen_before},
                    values_after={"need": need, "seen": seen_after},
                    description=f"在 seen 中查找 {need}：{'命中' if hit else '未命中'}",
                    data={"key": str(need), "hit": hit},
                )
            )
            consumed.add(event.event_id)

        # 4) 哈希插入：下标赋值行；必须观察到 seen 的实际变化
        for event in events:
            if event.event != "line" or event.line != insert_line:
                continue
            before = event.locals_before.get("seen")
            after = event.locals_after.get("seen") if isinstance(event.locals_after, dict) else None
            if not isinstance(before, dict) or not isinstance(after, dict) or before == after:
                continue
            added = [key for key in after if key not in before]
            if not added:
                continue
            key = added[-1]
            ops.append(
                self._op(
                    ops,
                    SemanticKind.HASH_INSERT,
                    evidence=self._evidence_with_next(event, next_event),
                    line=event.line,
                    targets=[event.locals_before.get("i", 0)],
                    values_before={"seen": before},
                    values_after={"seen": after},
                    description=f"插入 seen[{key}] = {after[key]}",
                    data={"key": str(key), "value": after[key]},
                )
            )
            consumed.add(event.event_id)

        # 5) 返回：真实 return 事件
        returns = [event for event in events if event.event == "return" and not event.is_unwind]
        if returns:
            ret = returns[-1]
            ops.append(
                self._op(
                    ops,
                    SemanticKind.RETURN,
                    evidence=[ret.event_id],
                    line=ret.line,
                    targets=[],
                    values_after={"return": ret.return_value},
                    description=f"函数返回 {ret.return_value}",
                    data={"return": ret.return_value},
                )
            )
            ops.append(
                self._op(
                    ops,
                    SemanticKind.COMPLETE,
                    evidence=[ret.event_id],
                    line=ret.line,
                    values_after={"return": ret.return_value},
                    description="执行完成",
                    data={"return": ret.return_value},
                )
            )
            consumed.add(ret.event_id)
        else:
            return self._generic(events, "没有真实 return 事件，追踪可能不完整")

        # 只把真正关键的语义操作当成 specific；其余 line 事件保持 unmapped
        ops.sort(key=lambda op: min(op.evidence_event_ids))
        for index, op in enumerate(ops):
            op.op_id = index
        unmapped = [event.event_id for event in events if event.event == "line" and event.event_id not in consumed]
        return SemanticResult(ops, unmapped, "specific")

    # ------------------------------------------------------------------ helpers
    def _op(self, ops: list[SemanticOperation], kind: SemanticKind, **kwargs: Any) -> SemanticOperation:
        if "evidence" in kwargs:
            kwargs["evidence_event_ids"] = kwargs.pop("evidence")
        if "line" in kwargs:
            kwargs["original_line"] = kwargs.pop("line")
        return SemanticOperation(op_id=len(ops), kind=kind, **kwargs)

    def _evidence_with_next(self, event: ExecutionEvent, next_event: dict[int, ExecutionEvent]) -> list[int]:
        following = next_event.get(event.event_id)
        return [event.event_id] + ([following.event_id] if following else [])

    def _lookup_line(self, static: StaticFacts) -> int | None:
        for branch in static.branches:
            if " in " in branch.condition and "seen" in branch.condition:
                return branch.line
        return None

    def _insert_line(self, static: StaticFacts) -> int | None:
        for assignment in static.assignments:
            if assignment.kind == "subscript" and assignment.target.startswith("seen["):
                return assignment.line
        return None

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
