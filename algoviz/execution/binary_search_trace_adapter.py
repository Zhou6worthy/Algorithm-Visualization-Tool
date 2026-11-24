"""ExecutionTrace -> Binary Search AnimationTrace.

只消费 BinarySearchSemanticTracer 产生的真实操作；没有具体语义证据时明确失败，
不把 generic line 直接猜成二分查找动画。
"""
from __future__ import annotations

from typing import Any

from ..protocol.events import (
    AnimationStep,
    ArrayState,
    Complexity,
    InputSource,
    StepType,
    Trace,
    TraceMetadata,
    VariableView,
    VisualKind,
    VisualState,
)
from ..protocol.execution import ExecutionTrace, SemanticKind, SemanticOperation


class BinarySearchTraceError(RuntimeError):
    pass


class BinarySearchTraceAdapter:
    algorithm = "binary_search"

    def adapt(self, execution: ExecutionTrace) -> Trace:
        ops = sorted(execution.semantic_ops, key=lambda op: min(op.evidence_event_ids))
        if not ops:
            raise BinarySearchTraceError("Binary Search 没有可用的语义操作")
        if all(op.kind == SemanticKind.GENERIC_LINE for op in ops):
            raise BinarySearchTraceError("Binary Search 语义适配失败：只有 generic line，拒绝生成猜测动画")
        nums = list(execution.input.get("nums") or [])
        target = execution.input.get("target")
        steps: list[AnimationStep] = []
        current = self._state(nums, target)
        for op in ops:
            if op.kind not in {
                SemanticKind.INIT,
                SemanticKind.VISIT,
                SemanticKind.COMPARE,
                SemanticKind.POINTER_MOVE,
                SemanticKind.RETURN,
                SemanticKind.COMPLETE,
            }:
                continue
            after = self._next_state(current, op, nums, target)
            step_type = {
                SemanticKind.INIT: StepType.INIT,
                SemanticKind.VISIT: StepType.VISIT,
                SemanticKind.COMPARE: StepType.COMPARE,
                SemanticKind.POINTER_MOVE: StepType.MOVE,
                SemanticKind.RETURN: StepType.FOUND,
                SemanticKind.COMPLETE: StepType.COMPLETE,
            }[op.kind]
            steps.append(
                AnimationStep(
                    step_id=len(steps),
                    type=step_type,
                    targets=self._targets(op),
                    description=op.description,
                    narration=op.description,
                    code_line=op.original_line,
                    visual_action=op.kind.value,
                    state_before=current,
                    state_after=after,
                    meta={
                        **dict(op.data),
                        "frame_ids": op.evidence_event_ids,
                        "semantic_kind": op.kind.value,
                        "confidence": op.confidence,
                    },
                )
            )
            current = after
        if not steps:
            raise BinarySearchTraceError("Binary Search 适配后没有任何可视化步骤")
        validation = execution.validation
        metadata = TraceMetadata(
            algorithm="binary_search",
            title="Binary Search · 二分查找",
            category="search",
            visual_kind=VisualKind.ARRAY,
            language="python",
            source=InputSource.SOURCE_CODE,
            input={"nums": nums, "target": target},
            expected_output={"return": execution.expected_output},
            complexity=Complexity(
                time="O(log n)",
                space="O(1)",
                note="每轮排除一半搜索区间；单样例轨迹不证明复杂度。",
            ),
            code=execution.program.source,
            code_language=execution.program.language,
            description="在有序数组中用 left/right/mid 不断缩小搜索区间。",
            idea=[
                "维护有序数组中的搜索区间 [left, right]",
                "取中点 mid，与 target 比较",
                "根据大小关系排除一半区间",
                "区间为空时返回 -1",
            ],
            summary=["二分查找每次将候选区间缩小约一半", "时间 O(log n)，额外空间 O(1)"],
            tags=["binary_search", "array", "search"],
            source_kind="user_code",
            execution_trace_id=execution.trace_id,
        )
        return Trace(
            metadata=metadata,
            steps=steps,
            result={"return": execution.result.actual_output, "verified": validation.output_verified},
            verified=validation.output_verified and validation.structure_verified and validation.trace_verified,
            verification_notes=validation.notes + validation.errors,
        )

    @staticmethod
    def _state(
        nums: list[Any],
        target: Any,
        *,
        left: int | None = None,
        right: int | None = None,
        mid: int | None = None,
        found: int | None = None,
    ) -> VisualState:
        pointers: dict[str, int] = {}
        if left is not None:
            pointers["left"] = left
        if right is not None:
            pointers["right"] = right
        if mid is not None:
            pointers["mid"] = mid
        active_range = [left, right] if left is not None and right is not None and left <= right else None
        found_indices = [found] if found is not None and 0 <= found < len(nums) else []
        state = VisualState(
            kind=VisualKind.ARRAY,
            array=ArrayState(
                values=list(nums),
                pointers=pointers,
                active_range=active_range,
                target=target,
                found_indices=found_indices,
            ),
        )
        rows: list[VariableView] = []
        for name, value in (("left", left), ("right", right), ("mid", mid)):
            if value is not None:
                rows.append(VariableView(name=name, type="int", value=str(value)))
        if target is not None:
            rows.append(VariableView(name="target", type=type(target).__name__, value=str(target)))
        state.variables = rows
        return state

    def _next_state(
        self,
        current: VisualState,
        op: SemanticOperation,
        nums: list[Any],
        target: Any,
    ) -> VisualState:
        data = op.data
        if op.kind == SemanticKind.INIT:
            return self._state(nums, target, left=data.get("left"), right=data.get("right"))
        if op.kind in {SemanticKind.VISIT, SemanticKind.COMPARE}:
            mid = data.get("mid")
            found = mid if op.kind == SemanticKind.COMPARE and data.get("outcome") == "hit" else None
            return self._state(
                nums,
                target,
                left=data.get("left"),
                right=data.get("right"),
                mid=mid,
                found=found,
            )
        if op.kind == SemanticKind.POINTER_MOVE:
            return self._state(
                nums,
                target,
                left=data.get("left"),
                right=data.get("right"),
                mid=data.get("mid"),
            )
        if op.kind in {SemanticKind.RETURN, SemanticKind.COMPLETE}:
            returned = data.get("return")
            found = returned if isinstance(returned, int) and returned >= 0 else None
            # 保留最后一次区间和指针，仅追加 found。
            array = current.array
            return self._state(
                nums,
                target,
                left=array.pointers.get("left") if array else None,
                right=array.pointers.get("right") if array else None,
                mid=array.pointers.get("mid") if array else None,
                found=found,
            )
        return current

    @staticmethod
    def _targets(op: SemanticOperation) -> list[str | int]:
        if op.kind in {SemanticKind.VISIT, SemanticKind.COMPARE} and op.data.get("mid") is not None:
            return [int(op.data["mid"])]
        if op.kind == SemanticKind.POINTER_MOVE:
            return [op.data.get("left"), op.data.get("right")]
        if op.kind in {SemanticKind.RETURN, SemanticKind.COMPLETE}:
            return [op.data.get("return")]
        return list(op.targets)
