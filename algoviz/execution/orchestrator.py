"""M1 编排：Adapter → LocalSandbox → GenericTracer → Semantic → Validator → TraceAdapter。"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from ..protocol.execution import (
    ExecutionResult,
    ExecutionStatus,
    ExecutionTrace,
    ExecutionValidation,
    GenericTrace,
    TraceLimits,
)
from .python_adapter import PythonExecutionAdapter
from .sandbox import LocalSandbox, SandboxResult
from .semantic import SemanticContext, TwoSumSemanticTracer
from .static_analyzer import StaticAnalyzer
from .trace_adapter import TwoSumTraceAdapter
from .validator import validate_execution


class M1ExecutionError(RuntimeError):
    pass


class M1TraceAdapterError(M1ExecutionError):
    """语义适配失败；仍携带真实 ExecutionTrace，供上层记录 ERROR。"""

    def __init__(self, message: str, execution: ExecutionTrace | None = None) -> None:
        super().__init__(message)
        self.execution = execution


@dataclass
class M1Run:
    execution: ExecutionTrace
    trace: Any
    work_dir: Path


class M1Executor:
    def __init__(
        self,
        work_dir: str | Path,
        *,
        limits: TraceLimits | None = None,
        sandbox: LocalSandbox | None = None,
    ) -> None:
        self.work_dir = Path(work_dir)
        self.limits = limits or TraceLimits()
        self.adapter = PythonExecutionAdapter(self.limits)
        self.sandbox = sandbox or LocalSandbox()
        self.analyzer = StaticAnalyzer()
        self.semantic = TwoSumSemanticTracer()
        self.trace_adapter = TwoSumTraceAdapter()

    def run_function(
        self,
        *,
        name: str,
        source: str,
        style: str,
        entry_point: str,
        args: list[object],
        input_data: dict[str, object],
        expected_output: object,
        check_output: bool,
        semantic: object,
        trace_adapter: object,
        algorithm_hint: str,
    ) -> M1Run:
        """通用函数执行入口：M1 只负责事实，算法语义由传入的组件决定。"""
        prepared = self.adapter.prepare(
            source,
            style=style,
            entry_point=entry_point,
            args=args,
        )
        job_dir = self.work_dir / name
        job_dir.mkdir(parents=True, exist_ok=True)
        sandbox_result = self.sandbox.run(prepared, job_dir, self.limits)
        if not sandbox_result.frames_json:
            raise M1ExecutionError(f"未获得追踪数据：{sandbox_result.error or sandbox_result.status.value}")
        try:
            generic = GenericTrace.model_validate_json(sandbox_result.frames_json)
        except Exception as exc:  # noqa: BLE001
            raise M1ExecutionError(f"frames 无法解析：{exc}") from exc
        try:
            raw_result = json.loads(sandbox_result.result_json or "{}")
        except json.JSONDecodeError as exc:
            raise M1ExecutionError(f"result 无法解析：{exc}") from exc

        static = self.analyzer.analyze(source)
        annotated_arcs = self.analyzer.annotate_arcs(generic.events, generic.arcs, static)
        generic_for_semantic = generic.model_copy(update={"arcs": annotated_arcs})
        try:
            semantic_result = semantic.analyze(  # type: ignore[attr-defined]
                generic_for_semantic,
                static,
                SemanticContext(algorithm_hint=algorithm_hint, source=source),
            )
        except Exception as exc:  # noqa: BLE001
            raise M1ExecutionError(f"SemanticAdapter 失败：{type(exc).__name__}: {exc}") from exc
        actual = raw_result.get("return_value")
        declared_status = raw_result.get("status", "ok")
        try:
            status = ExecutionStatus(declared_status)
        except ValueError:
            status = ExecutionStatus.SANDBOX_ERROR
        if not generic.trace_complete:
            status = ExecutionStatus.TRACE_INCOMPLETE
        result = ExecutionResult(
            status=status,
            actual_output=actual,
            return_value=actual,
            stdout=raw_result.get("stdout", ""),
            stderr=raw_result.get("stderr", sandbox_result.stderr),
            exception_type=raw_result.get("exception_type"),
            exception_message=raw_result.get("exception_message"),
            duration_ms=float(raw_result.get("duration_ms", sandbox_result.duration_ms) or 0.0),
            source_hash=generic.source_hash,
            trace_complete=generic.trace_complete,
            event_count=len(generic.events),
            sandbox="local",
            limits=self.limits,
        )
        trace = ExecutionTrace(
            trace_id=f"trace_{name}_{uuid.uuid4().hex[:8]}",
            program=prepared_to_program(prepared),
            static=static,
            input=input_data,
            expected_output=expected_output,
            events=generic.events,
            arcs=annotated_arcs,
            semantic_ops=semantic_result.operations,
            unmapped_event_ids=semantic_result.unmapped_event_ids,
            semantic_quality=semantic_result.semantic_quality,  # type: ignore[arg-type]
            result=result,
            validation=ExecutionValidation(),
        )
        validation = validate_execution(
            trace,
            expected_output=expected_output,
            verify_output=check_output,
        )
        trace = trace.model_copy(update={"validation": validation})
        (job_dir / "execution.json").write_text(trace.model_dump_json(indent=2), encoding="utf-8")
        try:
            animation = trace_adapter.adapt(trace)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            raise M1TraceAdapterError(
                f"TraceAdapter 失败：{type(exc).__name__}: {exc}",
                execution=trace,
            ) from exc
        (job_dir / "animation_events.json").write_text(animation.model_dump_json(indent=2), encoding="utf-8")
        return M1Run(execution=trace, trace=animation, work_dir=job_dir)

    def run_two_sum(
        self,
        *,
        name: str,
        source: str,
        style: str,
        entry_point: str,
        nums: list[int],
        target: int,
        expected_output: list[int] | None = None,
        check_output: bool = True,
    ) -> M1Run:
        expected = expected_output if expected_output is not None else ([0, 1] if check_output else None)
        input_data = {
            "nums": nums,
            "target": target,
            "expected_output": expected,
        }
        return self.run_function(
            name=name,
            source=source,
            style=style,
            entry_point=entry_point,
            args=[nums, target],
            input_data=input_data,
            expected_output=expected,
            check_output=check_output,
            semantic=self.semantic,
            trace_adapter=self.trace_adapter,
            algorithm_hint="two_sum",
        )


def prepared_to_program(prepared: Any):
    from ..protocol.execution import ProgramSpec

    return ProgramSpec(
        language="python",
        style=prepared.style,
        source=prepared.source,
        source_hash=prepared.source_hash,
        entry_point=prepared.entry_point,
        source_path=prepared.user_filename,
        harness_path=prepared.harness_filename,
        source_map=prepared.source_map,
        wrapper_lines=prepared.wrapper_lines,
    )
