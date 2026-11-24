"""M3-5 多用例执行：复用 M1Executor，为每个 TestCaseSpec 生成独立 CaseRun。"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from ..protocol.cases import CaseRun, CaseRunStatus, TestCaseSpec
from ..protocol.execution import ExecutionStatus, TraceLimits
from .orchestrator import M1ExecutionError, M1Executor
from .sandbox import LocalSandbox


class CaseInputError(ValueError):
    pass


class CaseRunner:
    """一个 AC 代码源对应一个 runner；每个用例独立执行、独立 trace。"""

    def __init__(
        self,
        work_dir: str | Path,
        *,
        source: str,
        style: str = "function",
        entry_point: str = "two_sum",
        limits: TraceLimits | None = None,
        sandbox: LocalSandbox | None = None,
    ) -> None:
        self.work_dir = Path(work_dir)
        self.source = source
        self.style = style
        self.entry_point = entry_point
        self.limits = limits or TraceLimits()
        self.executor = M1Executor(self.work_dir, limits=self.limits, sandbox=sandbox)

    def run_cases(self, cases: list[TestCaseSpec]) -> list[CaseRun]:
        return [self.run_case(case) for case in cases]

    def run_case(self, case: TestCaseSpec) -> CaseRun:
        run_id = f"run_{case.case_id}_{uuid.uuid4().hex[:8]}"
        try:
            nums, target = self._extract(case)
        except CaseInputError as exc:
            return CaseRun(
                run_id=run_id,
                case_id=case.case_id,
                status=CaseRunStatus.ERROR,
                expected_output=case.expected_output,
                error=str(exc),
                execution_metadata={
                    "phase": "input_validation",
                    "case_snapshot": case.model_dump(mode="json"),
                },
            )

        expected = case.expected_output
        try:
            result = self.executor.run_two_sum(
                name=run_id,
                source=self.source,
                style=self.style,
                entry_point=self.entry_point,
                nums=nums,
                target=target,
                expected_output=expected,
                check_output=expected is not None,
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
                    "work_dir": str(self.work_dir / run_id),
                    "case_snapshot": case.model_dump(mode="json"),
                },
            )
        except Exception as exc:  # noqa: BLE001 - 单个用例失败不能污染其他用例
            return CaseRun(
                run_id=run_id,
                case_id=case.case_id,
                status=CaseRunStatus.ERROR,
                expected_output=expected,
                error=f"{type(exc).__name__}: {exc}",
                execution_metadata={
                    "phase": "execution",
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
            error = "；".join(validation.errors) or f"执行状态：{execution.result.status.value}"
            return CaseRun(
                run_id=run_id,
                case_id=case.case_id,
                status=CaseRunStatus.ERROR,
                execution_trace=execution,
                animation_trace=animation,
                actual_output=actual,
                expected_output=expected,
                error=error,
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

    @staticmethod
    def _extract(case: TestCaseSpec) -> tuple[list[int], int]:
        data: dict[str, Any] = case.input_data
        if "nums" not in data or "target" not in data:
            raise CaseInputError("Two Sum 用例必须包含 nums 和 target")
        nums = data["nums"]
        target = data["target"]
        if not isinstance(nums, list) or not all(isinstance(value, int) and not isinstance(value, bool) for value in nums):
            raise CaseInputError("nums 必须是整数列表")
        if not isinstance(target, int) or isinstance(target, bool):
            raise CaseInputError("target 必须是整数")
        return list(nums), target
