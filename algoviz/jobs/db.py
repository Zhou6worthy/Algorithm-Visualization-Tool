"""SQLite 任务存储（对应 readme 8.2 的任务状态机）。"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import Settings, get_settings
from ..protocol.teaching import TaskSpec

STATUSES = (
    "pending",
    "parsing",
    "executing",
    "rendering",
    "synthesizing",
    "validating",
    "completed",
    "failed",
)
ACTIVE_STATUSES = {"parsing", "executing", "rendering", "synthesizing", "validating"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class JobRecord:
    id: str
    batch_id: str | None
    title: str
    algorithm: str | None
    status: str
    stage: str
    progress: float
    attempts: int
    error: str | None
    video_path: str | None
    events_path: str | None
    srt_path: str | None
    duration: float | None
    verified: int | None
    created_at: str
    updated_at: str
    finished_at: str | None
    ai_used: int = 0
    ai_status: str = ""
    ai_calls: int = 0
    ai_model: str = ""
    input_json: str = field(repr=False, default="{}")

    def task(self) -> TaskSpec:
        return TaskSpec.model_validate_json(self.input_json)

    def as_dict(self, include_input: bool = False) -> dict[str, Any]:
        data = asdict(self)
        data.pop("input_json", None)
        data["video_exists"] = bool(self.video_path and Path(self.video_path).exists())
        if include_input:
            data["task"] = json.loads(self.input_json)
        return data


class JobStore:
    def __init__(self, settings: Settings | None = None, path: Path | None = None) -> None:
        self.settings = settings or get_settings()
        self.path = path or self.settings.db_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    batch_id TEXT,
                    title TEXT,
                    algorithm TEXT,
                    input_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT DEFAULT '',
                    progress REAL DEFAULT 0,
                    attempts INTEGER DEFAULT 0,
                    error TEXT,
                    video_path TEXT,
                    events_path TEXT,
                    srt_path TEXT,
                    duration REAL,
                    verified INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    finished_at TEXT
                )
                """
            )
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_batch ON jobs(batch_id)")
            existing = {row[1] for row in self._conn.execute("PRAGMA table_info(jobs)")}
            migrations = {
                "ai_used": "ai_used INTEGER DEFAULT 0",
                "ai_status": "ai_status TEXT DEFAULT ''",
                "ai_calls": "ai_calls INTEGER DEFAULT 0",
                "ai_model": "ai_model TEXT DEFAULT ''",
            }
            for name, ddl in migrations.items():
                if name not in existing:
                    self._conn.execute(f"ALTER TABLE jobs ADD COLUMN {ddl}")
        self.backfill_ai_status()

    def backfill_ai_status(self) -> int:
        """旧任务没有 AI 字段：从 meta.json 回填，避免界面显示“未知”。"""
        updated = 0
        with self._lock:
            rows = self._conn.execute(
                "SELECT id FROM jobs WHERE ai_status IS NULL OR ai_status = ''"
            ).fetchall()
        for row in rows:
            job_id = row["id"]
            meta_path = self.settings.job_dir(job_id) / "meta.json"
            if not meta_path.exists():
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            usage = meta.get("ai_usage") or {}
            if usage:
                status = str(usage.get("status") or "")
                calls = int(usage.get("calls") or 0)
                model = str(usage.get("model") or "")
                used = 1 if int(usage.get("successes") or 0) > 0 else 0
            else:
                ai_info = meta.get("ai") or {}
                status = "disabled" if not ai_info.get("has_key") else "unused"
                calls = 0
                model = str(ai_info.get("model") or "")
                used = 0
            if not status:
                continue
            self.update(
                job_id,
                ai_status=status,
                ai_calls=calls,
                ai_model=model,
                ai_used=used,
            )
            updated += 1
        return updated

    # ------------------------------------------------------------------ 创建 / 更新
    def create(
        self,
        task: TaskSpec,
        *,
        batch_id: str | None = None,
        title: str | None = None,
        algorithm: str | None = None,
        job_id: str | None = None,
    ) -> JobRecord:
        job_id = job_id or task.task_id or uuid.uuid4().hex[:12]
        if self.get(job_id) is not None:
            job_id = f"{job_id}-{uuid.uuid4().hex[:4]}"
        fallback_title = (task.prompt or "").strip().splitlines()[0][:24] if task.prompt else ""
        title = title or task.title or (algorithm or task.algorithm) or fallback_title or "未命名任务"
        algorithm = algorithm or task.algorithm
        now = _now()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO jobs
                (id, batch_id, title, algorithm, input_json, status, stage, progress,
                 attempts, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'pending', '等待执行', 0, 0, NULL, ?, ?)
                """,
                (job_id, batch_id, title, algorithm, task.model_dump_json(), now, now),
            )
        self.settings.job_dir(job_id)
        record = self.get(job_id)
        assert record is not None
        return record

    def update(self, job_id: str, **fields: Any) -> None:
        allowed = {
            "status",
            "stage",
            "progress",
            "attempts",
            "error",
            "video_path",
            "events_path",
            "srt_path",
            "duration",
            "verified",
            "finished_at",
            "title",
            "algorithm",
            "ai_used",
            "ai_status",
            "ai_calls",
            "ai_model",
        }
        clean = {k: v for k, v in fields.items() if k in allowed}
        if not clean:
            return
        clean["updated_at"] = _now()
        columns = ", ".join(f"{key} = ?" for key in clean)
        with self._lock, self._conn:
            self._conn.execute(
                f"UPDATE jobs SET {columns} WHERE id = ?",
                (*clean.values(), job_id),
            )

    def mark_running(self, job_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE jobs SET attempts = attempts + 1, status = 'parsing', stage = '开始执行',"
                " error = NULL, updated_at = ? WHERE id = ?",
                (_now(), job_id),
            )

    def mark_completed(
        self,
        job_id: str,
        *,
        video_path: str,
        events_path: str,
        srt_path: str,
        duration: float,
        verified: bool,
    ) -> None:
        self.update(
            job_id,
            status="completed",
            stage="生成完成",
            progress=1.0,
            error=None,
            video_path=video_path,
            events_path=events_path,
            srt_path=srt_path,
            duration=duration,
            verified=1 if verified else 0,
            finished_at=_now(),
        )

    def mark_failed(self, job_id: str, error: str) -> None:
        self.update(
            job_id,
            status="failed",
            stage="执行失败",
            error=error[-4000:],
            finished_at=_now(),
        )

    # ------------------------------------------------------------------ 查询
    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row(row) if row else None

    def list(
        self,
        *,
        batch_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[JobRecord]:
        query = "SELECT * FROM jobs"
        clauses: list[str] = []
        params: list[Any] = []
        if batch_id:
            clauses.append("batch_id = ?")
            params.append(batch_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at ASC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._row(row) for row in rows]

    def pending(self, batch_id: str | None = None, limit: int = 500) -> list[JobRecord]:
        return self.list(batch_id=batch_id, status="pending", limit=limit)

    def counts(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) AS n FROM jobs GROUP BY status"
            ).fetchall()
        return {row["status"]: row["n"] for row in rows}

    def stats(self) -> dict[str, Any]:
        counts = self.counts()
        return {
            "total": sum(counts.values()),
            "counts": counts,
            "completed": counts.get("completed", 0),
            "failed": counts.get("failed", 0),
        }

    def recover_interrupted(self) -> int:
        placeholders = ", ".join("?" for _ in STATUSES if _ in ACTIVE_STATUSES)
        active = tuple(status for status in STATUSES if status in ACTIVE_STATUSES)
        with self._lock, self._conn:
            cur = self._conn.execute(
                f"UPDATE jobs SET status = 'pending', stage = '进程中断，重新排队', updated_at = ?"
                f" WHERE status IN ({', '.join('?' for _ in active)})",
                (_now(), *active),
            )
            return cur.rowcount

    def _row(self, row: sqlite3.Row) -> JobRecord:
        data = dict(row)
        if data.get("duration") is not None:
            data["duration"] = float(data["duration"])
        if data.get("progress") is not None:
            data["progress"] = float(data["progress"])
        data["ai_used"] = int(data.get("ai_used") or 0)
        data["ai_calls"] = int(data.get("ai_calls") or 0)
        data["ai_status"] = data.get("ai_status") or ""
        data["ai_model"] = data.get("ai_model") or ""
        return JobRecord(**data)

    def close(self) -> None:
        with self._lock:
            self._conn.close()
