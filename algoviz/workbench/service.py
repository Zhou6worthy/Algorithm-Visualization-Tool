"""M4 real execution service: project snapshot -> CaseRunner -> ClassroomDeck."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..algorithms.profiles import AlgorithmProfileError, get_profile
from ..config import Settings, get_settings
from ..execution.profile_case_runner import ProfileCaseRunner
from ..protocol.cases import CaseSource, TestCaseSpec
from ..teaching.classroom import build_classroom_deck
from .models import RunRecord
from .store import WorkbenchStore


class WorkbenchRunService:
    """单 worker 后台执行队列；每次 run 使用创建时的不可变快照。"""

    def __init__(
        self,
        store: WorkbenchStore,
        settings: Settings | None = None,
        *,
        max_workers: int = 1,
    ) -> None:
        self.store = store
        self.settings = settings or get_settings()
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, max_workers),
            thread_name_prefix="m4-run",
        )

    def submit(self, run_id: str) -> RunRecord:
        self._executor.submit(self._execute, run_id)
        record = self.store.get_run(run_id)
        assert record is not None
        return record

    def _execute(self, run_id: str) -> None:
        try:
            snapshot = self.store.get_run_snapshot(run_id)
            problem = snapshot.get("problem") or {}
            case_snapshots = snapshot.get("cases") or []
            if not case_snapshots:
                raise ValueError("执行快照没有测试用例")
            if problem.get("language") != "python":
                raise ValueError(f"M5 只支持 Python，收到 {problem.get('language')!r}")
            algorithm = str(problem.get("algorithm") or "")
            try:
                profile = get_profile(algorithm)
            except AlgorithmProfileError as exc:
                raise ValueError(f"不支持的算法：{algorithm!r}") from exc
            source = str(problem.get("source") or "")
            if not source.strip():
                raise ValueError("源码为空，无法执行")
            self.store.mark_run_running(run_id)

            specs = [
                TestCaseSpec(
                    case_id=item["case_id"],
                    name=item["name"],
                    input_data=item.get("input_data") or {},
                    expected_output=item.get("expected_output"),
                    source=CaseSource(item.get("source") or "user"),
                    description=item.get("description") or "",
                )
                for item in case_snapshots
            ]
            style = str(problem.get("source_style") or "function")
            run_dir = self.settings.output_dir / "m4" / "runs" / run_id
            runner = ProfileCaseRunner(
                run_dir,
                source=source,
                style=style,
                profile=profile,
            )
            runs = runner.run_cases(specs)
            deck = build_classroom_deck(
                list(zip(specs, runs)),
                profile=profile,
                title=str(problem.get("title") or profile.title),
                code=source,
            )
            case_records = [self._case_record(spec, run) for spec, run in zip(specs, runs)]
            summary = {
                "case_count": len(runs),
                "success": sum(1 for run in runs if run.status.value == "success"),
                "failed": sum(1 for run in runs if run.status.value == "failed"),
                "error": sum(1 for run in runs if run.status.value == "error"),
                "trace_count": sum(1 for run in runs if run.animation_trace is not None),
                "steps_total": sum(
                    len(run.animation_trace.steps) if run.animation_trace is not None else 0
                    for run in runs
                ),
            }
            self.store.complete_run(
                run_id,
                classroom=deck.model_dump(mode="json"),
                case_records=case_records,
                summary=summary,
            )
        except Exception as exc:  # noqa: BLE001 - run-level failure must be persisted
            self.store.fail_run(run_id, f"{type(exc).__name__}: {exc}")

    @staticmethod
    def _case_record(spec: TestCaseSpec, run: Any) -> dict[str, Any]:
        execution = run.execution_trace
        animation = run.animation_trace
        return {
            "case_id": spec.case_id,
            "name": spec.name,
            "source": spec.source.value,
            "status": run.status.value,
            "expected_output": run.expected_output,
            "actual_output": run.actual_output,
            "error": run.error,
            "execution_trace": execution.model_dump(mode="json") if execution is not None else None,
            "animation_trace": animation.model_dump(mode="json") if animation is not None else None,
            "execution_metadata": run.execution_metadata,
            "step_count": len(animation.steps) if animation is not None else 0,
        }

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
