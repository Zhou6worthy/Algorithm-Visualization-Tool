"""批量任务执行器：线程池并发、单任务失败重试、SQLite 状态持久化。"""
from __future__ import annotations

import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ..config import Settings, get_settings
from ..pipeline import Pipeline, PipelineError, PipelineResult
from ..protocol.teaching import TaskSpec
from .db import JobRecord, JobStore

ProgressCallback = Callable[[str, str, float], None]


@dataclass
class JobSummary:
    job_id: str
    title: str
    algorithm: str | None
    status: str
    video_path: str | None = None
    duration: float | None = None
    verified: bool | None = None
    error: str | None = None
    attempts: int = 0
    ai_status: str = ""
    ai_calls: int = 0
    ai_model: str = ""

    @property
    def ai_label(self) -> str:
        if self.ai_status == "used":
            return f"DeepSeek {self.ai_calls}次"
        if self.ai_status == "failed":
            return "大模型失败·本地模板"
        if self.ai_status == "disabled":
            return "本地模板"
        if self.ai_status == "unused":
            return "未触发"
        return "未知"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class BatchRunner:
    def __init__(
        self,
        store: JobStore | None = None,
        pipeline: Pipeline | None = None,
        *,
        settings: Settings | None = None,
        workers: int | None = None,
        retries: int | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.store = store or JobStore(self.settings)
        self.pipeline = pipeline or Pipeline(self.settings)
        self.workers = max(1, workers or self.settings.workers)
        self.retries = max(0, retries if retries is not None else self.settings.retries)
        self._print_lock = threading.Lock()

    # ------------------------------------------------------------------ 入队
    def create_jobs(self, tasks: list[TaskSpec], batch_id: str | None = None) -> list[JobRecord]:
        batch_id = batch_id or f"batch_{uuid.uuid4().hex[:8]}"
        records = []
        for task in tasks:
            record = self.store.create(
                task,
                batch_id=batch_id,
                title=task.title or (task.algorithm or "待解析任务"),
                algorithm=task.algorithm,
            )
            records.append(record)
        return records

    # ------------------------------------------------------------------ 执行
    def run(
        self,
        job_ids: list[str] | None = None,
        *,
        batch_id: str | None = None,
        progress_callback: Callable[[str, str, float], None] | None = None,
    ) -> list[JobSummary]:
        if job_ids is None:
            records = self.store.pending(batch_id=batch_id)
            job_ids = [record.id for record in records]
        if not job_ids:
            return []
        summaries: list[JobSummary] = []
        with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="algoviz") as pool:
            futures = {pool.submit(self._run_one, job_id, progress_callback): job_id for job_id in job_ids}
            for future in as_completed(futures):
                job_id = futures[future]
                try:
                    summary = future.result()
                except Exception as exc:  # noqa: BLE001 - 防止线程异常丢失
                    self.store.mark_failed(job_id, f"{type(exc).__name__}: {exc}")
                    summary = JobSummary(job_id=job_id, title="", algorithm=None, status="failed", error=str(exc))
                summaries.append(summary)
                self._echo(summary)
        return summaries

    def _run_one(
        self,
        job_id: str,
        progress_callback: Callable[[str, str, float], None] | None,
    ) -> JobSummary:
        record = self.store.get(job_id)
        if record is None:
            raise PipelineError(f"任务不存在：{job_id}")
        task = record.task()
        job_dir = self.settings.job_dir(job_id)
        last_error: str | None = None
        attempts = 0
        for attempt in range(1, self.retries + 2):
            attempts = attempt
            if attempt > 1:
                self.store.update(
                    job_id,
                    status="pending",
                    stage=f"第 {attempt} 次尝试",
                    progress=0.0,
                )
                time.sleep(min(2.0, attempt))
            self.store.mark_running(job_id)
            self._log(job_dir, f"开始第 {attempt} 次执行：{record.title}")

            def progress(status: str, message: str, value: float) -> None:
                self.store.update(job_id, status=status, stage=message, progress=value)
                if progress_callback is not None:
                    progress_callback(job_id, f"{status}: {message}", value)

            try:
                result: PipelineResult = self.pipeline.run(
                    task=task,
                    job_dir=job_dir,
                    progress=progress,
                )
                self.store.mark_completed(
                    job_id,
                    video_path=str(result.final_video),
                    events_path=result.artifacts.get("events", ""),
                    srt_path=str(result.srt_path),
                    duration=result.duration,
                    verified=result.trace.verified,
                )
                self.store.update(
                    job_id,
                    title=result.script.title or record.title,
                    algorithm=result.trace.metadata.algorithm,
                    ai_used=1 if int(result.ai_usage.get("successes") or 0) > 0 else 0,
                    ai_status=str(result.ai_usage.get("status") or ""),
                    ai_calls=int(result.ai_usage.get("calls") or 0),
                    ai_model=str(result.ai_usage.get("model") or ""),
                )
                self._log(
                    job_dir,
                    f"完成：{result.final_video}，时长 {result.duration:.1f}s，"
                    f"verified={result.trace.verified}，AI={result.ai_usage.get('status')}"
                    f"/{result.ai_usage.get('calls')}次",
                )
                return JobSummary(
                    job_id=job_id,
                    title=result.script.title or record.title,
                    algorithm=result.trace.metadata.algorithm,
                    status="completed",
                    video_path=str(result.final_video),
                    duration=result.duration,
                    verified=result.trace.verified,
                    attempts=attempts,
                    ai_status=str(result.ai_usage.get("status") or ""),
                    ai_calls=int(result.ai_usage.get("calls") or 0),
                    ai_model=str(result.ai_usage.get("model") or ""),
                )
            except Exception as exc:  # noqa: BLE001 - 单个任务失败不影响批次
                last_error = f"{type(exc).__name__}: {exc}"
                self._log(job_dir, f"第 {attempt} 次执行失败：{last_error}")
                self._log(job_dir, traceback.format_exc()[-3000:])
                if attempt > self.retries:
                    break
        error = last_error or "未知错误"
        self.store.mark_failed(job_id, error)
        return JobSummary(
            job_id=job_id,
            title=record.title,
            algorithm=record.algorithm,
            status="failed",
            error=error,
            attempts=attempts,
        )

    # ------------------------------------------------------------------ 工具
    def _log(self, job_dir: Path, message: str) -> None:
        try:
            with (job_dir / "pipeline.log").open("a", encoding="utf-8") as handle:
                handle.write(f"[{_now()}] {message}\n")
        except OSError:
            pass

    def _echo(self, summary: JobSummary) -> None:
        with self._print_lock:
            if summary.status == "completed":
                print(
                    f"  ✓ {summary.title}  {summary.duration:.1f}s  verified={summary.verified}  "
                    f"AI={summary.ai_label}  → {summary.video_path}"
                )
            else:
                print(f"  ✗ {summary.title}  {summary.error}")

    def retry_failed(self, batch_id: str | None = None) -> list[JobSummary]:
        records = self.store.list(batch_id=batch_id, status="failed", limit=500)
        return self.run([record.id for record in records], batch_id=batch_id)

    def close(self) -> None:
        self.store.close()
