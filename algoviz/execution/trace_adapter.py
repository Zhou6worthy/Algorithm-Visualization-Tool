"""ExecutionTrace -> 现有 Animation Trace（Trace）的适配器。

只生成有语义证据的事件；不重新执行用户代码。
"""
from __future__ import annotations

import json
from typing import Any

from ..protocol.events import (
    AnimationStep,
    ArrayState,
    Complexity,
    DictEntryView,
    DictState,
    InputSource,
    StepType,
    Trace,
    TraceMetadata,
    VariableView,
    VisualKind,
    VisualState,
)
from ..protocol.execution import ExecutionTrace, SemanticKind, SemanticOperation


class TwoSumTraceAdapter:
    def adapt(self, execution: ExecutionTrace) -> Trace:
        input_data = execution.input
        nums = list(input_data.get("nums", []) or [])
        target = input_data.get("target")
        validation = execution.validation

        steps: list[AnimationStep] = []
        seen: dict[str, Any] = {}
        lookup_key: str | None = None
        lookup_status: str | None = None
        pointers: dict[str, int] = {}
        found_indices: list[int] = []

        def make_state(
            variables_before: dict[str, Any] | None = None,
            variables_after: dict[str, Any] | None = None,
        ) -> VisualState:
            entries = [
                DictEntryView(
                    key=str(key),
                    value=value,
                    highlighted=(lookup_key == str(key) and lookup_status == "hit"),
                )
                for key, value in sorted(seen.items(), key=lambda item: str(item[0]))
            ]
            state = VisualState(
                kind=VisualKind.ARRAY,
                array=ArrayState(
                    values=nums,
                    pointers=dict(pointers),
                    target=target,
                    found_indices=list(found_indices),
                ),
                dict_state=DictState(
                    title="seen",
                    entries=entries,
                    lookup_key=lookup_key,
                    lookup_status=lookup_status,  # type: ignore[arg-type]
                ),
            )
            state.variables = _variable_views(variables_before or {}, variables_after or {})
            return state

        def add_step(
            step_type: StepType,
            op: SemanticOperation,
            description: str,
            *,
            before: VisualState,
            after: VisualState,
            targets: list[str | int] | None = None,
            code_line: int | None = None,
            action: str = "",
            meta: dict[str, Any] | None = None,
        ) -> None:
            payload = {
                "frame_ids": op.evidence_event_ids,
                "semantic_kind": op.kind.value,
                "confidence": op.confidence,
            }
            if meta:
                payload.update(meta)
            steps.append(
                AnimationStep(
                    step_id=len(steps),
                    type=step_type,
                    targets=targets or [],
                    description=description,
                    narration=description,
                    code_line=code_line,
                    visual_action=action,
                    state_before=before,
                    state_after=after,
                    meta=payload,
                )
            )

        for op in sorted(execution.semantic_ops, key=lambda item: item.op_id):
            if op.kind == SemanticKind.INIT:
                before = make_state(op.values_before, op.values_after)
                seen.clear()
                lookup_key, lookup_status = None, None
                pointers.clear()
                after = make_state(op.values_before, op.values_after)
                add_step(StepType.INIT, op, op.description, before=before, after=after, code_line=op.original_line, action="init")
                continue

            if op.kind == SemanticKind.VISIT:
                index = int(op.data.get("index", op.targets[0] if op.targets else 0))
                lookup_key, lookup_status = None, None
                before = make_state(op.values_before, op.values_before)
                pointers = {"i": index}
                after = make_state(op.values_before, op.values_after)
                add_step(
                    StepType.VISIT,
                    op,
                    op.description,
                    before=before,
                    after=after,
                    targets=[index],
                    code_line=op.original_line,
                    action="visit",
                    meta={"index": index},
                )
                continue

            if op.kind == SemanticKind.HASH_LOOKUP:
                key = str(op.data.get("key", ""))
                hit = bool(op.data.get("hit", False))
                lookup_key, lookup_status = None, None
                before = make_state(op.values_before, op.values_before)
                lookup_key = key
                lookup_status = "hit" if hit else "miss"
                after = make_state(op.values_before, op.values_after)
                add_step(
                    StepType.COMPARE,
                    op,
                    op.description,
                    before=before,
                    after=after,
                    targets=[int(op.targets[0])] if op.targets else [],
                    code_line=op.original_line,
                    action="hash_lookup",
                    meta={"hit": hit, "lookup_key": key},
                )
                continue

            if op.kind == SemanticKind.HASH_INSERT:
                key = str(op.data.get("key", ""))
                value = op.data.get("value")
                lookup_key, lookup_status = None, None
                before = make_state(op.values_before, op.values_before)
                seen[key] = value
                after = make_state(op.values_before, op.values_after)
                add_step(
                    StepType.UPDATE,
                    op,
                    op.description,
                    before=before,
                    after=after,
                    targets=[int(op.targets[0])] if op.targets else [],
                    code_line=op.original_line,
                    action="hash_insert",
                    meta={"key": key, "value": value},
                )
                continue

            if op.kind == SemanticKind.RETURN:
                returned = op.data.get("return")
                before = make_state(op.values_before, op.values_before)
                if isinstance(returned, list) and all(isinstance(item, int) for item in returned):
                    found_indices = list(returned)
                    pointers.clear()
                after = make_state(op.values_before, op.values_after)
                add_step(
                    StepType.FOUND,
                    op,
                    op.description,
                    before=before,
                    after=after,
                    targets=list(found_indices),
                    code_line=op.original_line,
                    action="found",
                    meta={"return": returned},
                )
                continue

            if op.kind == SemanticKind.COMPLETE:
                before = make_state(op.values_before, op.values_before)
                after = make_state(op.values_before, op.values_after)
                add_step(
                    StepType.COMPLETE,
                    op,
                    op.description,
                    before=before,
                    after=after,
                    targets=list(found_indices),
                    code_line=op.original_line,
                    action="complete",
                )
                continue

            before = make_state(op.values_before, op.values_before)
            after = make_state(op.values_before, op.values_after)
            add_step(
                StepType.NOTE,
                op,
                op.description,
                before=before,
                after=after,
                code_line=op.original_line,
                action="generic_line",
            )

        metadata = TraceMetadata(
            algorithm="two_sum",
            title="Two Sum · 哈希表",
            category="custom",
            visual_kind=VisualKind.ARRAY,
            language="python",
            source=InputSource.SOURCE_CODE,
            input={"nums": nums, "target": target},
            expected_output={"return": input_data.get("expected_output")},
            complexity=Complexity(time="O(n) 平均", space="O(n)", note="用户代码静态估算；单样例不证明复杂度"),
            code=execution.program.source,
            code_language="python",
            description="使用哈希表查找 complement，返回两个下标。",
            idea=["遍历数组", "用哈希表记录已见值与下标", "查找 target - x"],
            summary=["哈希表把查找从 O(n) 降为平均 O(1)"],
            tags=["two_sum", "hash"],
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


def _variable_views(before: dict[str, Any], after: dict[str, Any]) -> list[VariableView]:
    views: list[VariableView] = []
    for name in ["i", "x", "need", "seen"]:
        if name not in before and name not in after:
            continue
        value = after.get(name, before.get(name))
        views.append(
            VariableView(
                name=name,
                type=type(value).__name__,
                value=json.dumps(value, ensure_ascii=False, default=str),
                changed=before.get(name) != after.get(name),
            )
        )
    return views
