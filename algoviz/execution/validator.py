"""ExecutionTrace 校验：输出正确性、追踪完整性、证据完整性。"""
from __future__ import annotations

from typing import Any

from ..protocol.execution import (
    ExecutionStatus,
    ExecutionTrace,
    ExecutionValidation,
    SemanticKind,
)


def validate_execution(
    execution: ExecutionTrace,
    *,
    expected_output: Any = None,
    verify_output: bool = True,
) -> ExecutionValidation:
    notes: list[str] = []
    errors: list[str] = []
    events = execution.events
    event_ids = [event.event_id for event in events]
    expected_ids = list(range(1, len(events) + 1))
    structure_ok = event_ids == expected_ids
    if not structure_ok:
        errors.append("event_id 不连续")
    trace_ok = execution.result.trace_complete
    if not events:
        errors.append("没有执行事件")
        trace_ok = False
    if not trace_ok:
        errors.append("追踪不完整：缺少入口函数的 return/exception 终态")
    if execution.result.source_hash != execution.program.source_hash:
        errors.append("source_hash 不一致：执行结果与源码不匹配")
        trace_ok = False
    if events and events[-1].event not in {"return", "exception"}:
        errors.append("最后一个事件不是 return/exception")
        trace_ok = False
    terminal = [event for event in events if event.event in {"return", "exception"}]
    if terminal and events[-1].event not in {"return", "exception"}:
        trace_ok = False
    # 源码行范围
    for event in events:
        if event.original_line is not None and event.original_line > execution.static.source_lines:
            errors.append(f"event {event.event_id} 行号越界：{event.original_line}")
            structure_ok = False
    # 证据完整性
    valid_ids = set(event_ids)
    semantic_ok = True
    for op in execution.semantic_ops:
        if not op.evidence_event_ids:
            semantic_ok = False
            errors.append(f"语义操作 {op.op_id} 没有 evidence")
        for event_id in op.evidence_event_ids:
            if event_id not in valid_ids:
                semantic_ok = False
                errors.append(f"语义操作 {op.op_id} 引用了不存在的事件 {event_id}")
    # 返回结果必须与最后一个 return 事件一致
    normal_returns = [event for event in events if event.event == "return" and not event.is_unwind]
    if normal_returns:
        if normal_returns[-1].return_value != execution.result.return_value:
            errors.append("return 事件的值与 result.json 不一致")
            semantic_ok = False
    elif execution.result.exception_type is None:
        errors.append("没有 return 事件，也没有异常")
        trace_ok = False
    # Two Sum 专用：return 之后不能有 hash_insert
    if execution.semantic_quality == "specific":
        return_index = next((op.op_id for op in execution.semantic_ops if op.kind == SemanticKind.RETURN), None)
        if return_index is not None:
            for op in execution.semantic_ops:
                if op.op_id > return_index and op.kind == SemanticKind.HASH_INSERT:
                    semantic_ok = False
                    errors.append("return 之后仍出现 hash_insert：语义顺序错误")
    actual = execution.result.actual_output
    if verify_output:
        expected = expected_output if expected_output is not None else execution.expected_output
        output_ok = expected == actual
        if not output_ok:
            errors.append(f"输出不一致：expected={expected!r}, actual={actual!r}")
    else:
        output_ok = False
        notes.append("未提供 expected_output，未进行输出比较")
    trace_ok = trace_ok and structure_ok
    if structure_ok:
        notes.append("event_id 连续")
    if trace_ok:
        notes.append("追踪包含终态事件")
    if execution.result.status != ExecutionStatus.OK:
        errors.append(f"执行状态：{execution.result.status.value}")
    return ExecutionValidation(
        output_verified=output_ok,
        structure_verified=structure_ok,
        trace_verified=trace_ok,
        semantic_verified=semantic_ok,
        notes=notes,
        errors=errors,
    )
