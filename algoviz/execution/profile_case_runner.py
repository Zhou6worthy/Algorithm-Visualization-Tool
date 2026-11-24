"""Profile-driven case runner used by the M5 workbench.

This is the generic counterpart of the original Two Sum-only CaseRunner. It
still delegates all facts to M1Executor; the AlgorithmProfile only supplies
input parsing, semantic adapter, trace adapter and hint/profile metadata.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from ..algorithms.profiles import AlgorithmProfile, AlgorithmProfileError, get_profile
from ..protocol.cases import CaseRun, CaseRunStatus, TestCaseSpec
from ..protocol.execution import ExecutionStatus, TraceLimits
from .orchestrator import M1ExecutionError, M1Executor, M1TraceAdapterError
from .sandbox import LocalSandbox


class ProfileCaseInputError(ValueError):
    pass


class ProfileCaseRunner:
    def __init__(
        self,
        work_dir: str | Path,
        *,
        source: str,
        style: str = "function",
        profile: AlgorithmProfile | str | None = None,
        limits: TraceLimits | None = None,
        sandbox: LocalSandbox | None = None,
    ) -> None:
        self.work_dir = Path(work_dir)
        self.source = source
        self.style = style
        if profile is None:
            profile = get_profile("two_sum")
        if isinstance(profile, str):
            try:
                profile = get_profile(profile)
            except AlgorithmProfileError as exc:
                raise ValueError(str(exc)) from exc
        self.profile: AlgorithmProfile = profile
        self.entry_point = profile.entry_point_for(style)
        self.limits = limits or TraceLimits()
        self.executor = M1Executor(self.work_dir, limits=self.limits, sandbox=sandbox)

    def run_cases(self, cases: list[TestCaseSpec]) -> list[CaseRun]:
        return [self.run_case(case) for case in cases]

    def run_case(self, case: TestCaseSpec) -> CaseRun:
        run_id = f"run_{case.case_id}_{uuid.uuid4().hex[:8]}"
        try:
            args, input_data = self.profile.prepare_input(case.input_data)
        except (ValueError, TypeError) as exc:
            return CaseRun(
                run_id=run_id,
                case_id=case.case_id,
                status=CaseRunStatus.ERROR,
                expected_output=case.expected_output,
                error=str(exc),
                execution_metadata={
                    "phase": "input_validation",
                    "algorithm": self.profile.key,
                    "case_snapshot": case.model_dump(mode="json"),
                },
            )

        expected = case.expected_output
        input_data = {**input_data, "expected_output": expected}
        try:
            result = self.executor.run_function(
                name=run_id,
                source=self.source,
                style=self.style,
                entry_point=self.entry_point,
                args=args,
                input_data=input_data,
                expected_output=expected,
                check_output=expected is not None,
                semantic=self.profile.semantic_factory(),
                trace_adapter=self.profile.trace_adapter_factory(),
                algorithm_hint=self.profile.key,
            )
        except M1TraceAdapterError as exc:
            execution = exc.execution
            failure = str(exc)
            phase = "semantic_adapter"
            if execution is not None and (
                execution.result.status != ExecutionStatus.OK
                or execution.result.exception_type is not None
            ):
                # Preserve the real execution failure instead of masking it with
                # the downstream adapter failure.
                kind = execution.result.exception_type or execution.result.status.value
                detail = execution.result.exception_message or ""
                failure = f"{kind}: {detail}".strip(": ")
                phase = "execution"
            return CaseRun(
                run_id=run_id,
                case_id=case.case_id,
                status=CaseRunStatus.ERROR,
                execution_trace=execution,
                expected_output=expected,
                error=failure,
                execution_metadata={
                    "phase": phase,
                    "algorithm": self.profile.key,
                    "case_snapshot": case.model_dump(mode="json"),
                },
            )
        except M1ExecutionError as exc:
            return CaseRun(
                run_id=run_id,
                case_id=case.case_id,
                status=CaseRunStatus.ERROR,
                expected_output=expected,
                error=str(exc),
                execution_metadata={
                    "phase": "execution",
                    "algorithm": self.profile.key,
                    "work_dir": str(self.work_dir / run_id),
                    "case_snapshot": case.model_dump(mode="json"),
                },
            )
        except Exception as exc:  # noqa: BLE001 - one case must not poison others
            return CaseRun(
                run_id=run_id,
                case_id=case.case_id,
                status=CaseRunStatus.ERROR,
                expected_output=expected,
                error=f"{type(exc).__name__}: {exc}",
                execution_metadata={
                    "phase": "execution",
                    "algorithm": self.profile.key,
                    "work_dir": str(self.work_dir / run_id),
                    "case_snapshot": case.model_dump(mode="json"),
                },
            )

        execution = result.execution
        animation = result.trace
        actual = execution.result.actual_output
        validation = execution.validation
        metadata = {
            "work_dir": str(result.work_dir),
            "trace_id": execution.trace_id,
            "algorithm": self.profile.key,
            "source_style": self.style,
            "entry_point": self.entry_point,
            "event_count": len(execution.events),
            "step_count": len(animation.steps),
            "duration_ms": execution.result.duration_ms,
            "compare_output": expected is not None,
            "case_snapshot": case.model_dump(mode="json"),
            "validation": validation.model_dump(mode="json"),
        }
        if execution.result.status != ExecutionStatus.OK or not validation.trace_verified:
            return CaseRun(
                run_id=run_id,
                case_id=case.case_id,
                status=CaseRunStatus.ERROR,
                execution_trace=execution,
                animation_trace=animation,
                actual_output=actual,
                expected_output=expected,
                error="；".join(validation.errors) or f"执行状态：{execution.result.status.value}",
                execution_metadata=metadata,
            )
        if expected is not None and actual != expected:
            return CaseRun(
                run_id=run_id,
                case_id=case.case_id,
                status=CaseRunStatus.FAILED,
                execution_trace=execution,
                animation_trace=animation,
                actual_output=actual,
                expected_output=expected,
                error=f"输出不一致：expected={expected!r}, actual={actual!r}",
                execution_metadata=metadata,
            )
        return CaseRun(
            run_id=run_id,
            case_id=case.case_id,
            status=CaseRunStatus.SUCCESS,
            execution_trace=execution,
            animation_trace=animation,
            actual_output=actual,
            expected_output=expected,
            execution_metadata=metadata,
        )
