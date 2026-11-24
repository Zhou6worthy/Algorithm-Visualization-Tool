"""SQLite storage for M4 projects, test cases, runs and case-run traces."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..protocol.cases import CaseSource
from .models import (
    CaseRunRecord,
    ProjectPayload,
    ProjectSummary,
    RunRecord,
    TestCasePayload,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _loads(value: str | None, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


class WorkbenchStore:
    """Small SQLite store with one connection guarded by an RLock.

    Tables intentionally separate Project, Problem, TestCase, Run and CaseRun.
    ExecutionTrace / AnimationTrace live in CaseRun JSON columns so a run is
    independently reproducible and does not depend on the current project.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS problems (
                    project_id TEXT PRIMARY KEY REFERENCES projects(project_id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    idea TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    language TEXT NOT NULL DEFAULT 'python',
                    algorithm TEXT NOT NULL DEFAULT 'two_sum',
                    source_style TEXT NOT NULL DEFAULT 'function'
                );
                CREATE TABLE IF NOT EXISTS test_cases (
                    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                    case_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    expected_json TEXT,
                    source TEXT NOT NULL DEFAULT 'user',
                    description TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (project_id, case_id)
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    error TEXT,
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    classroom_json TEXT,
                    snapshot_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS case_runs (
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    case_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'user',
                    status TEXT NOT NULL,
                    expected_json TEXT,
                    actual_json TEXT,
                    error TEXT,
                    execution_json TEXT,
                    animation_json TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    step_count INTEGER NOT NULL DEFAULT 0,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (run_id, case_id)
                );
                CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_case_runs_run ON case_runs(run_id, sort_order);
                """
            )

    # ------------------------------------------------------------------ projects
    def create_project(self, payload: ProjectPayload) -> dict[str, Any]:
        project_id = f"prj_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO projects(project_id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (project_id, payload.name, now, now),
            )
            self._write_problem(project_id, payload)
            self._replace_cases(project_id, payload.cases)
        result = self.get_project(project_id)
        assert result is not None
        return result

    def update_project(self, project_id: str, payload: ProjectPayload) -> dict[str, Any]:
        now = _now()
        with self._lock, self._conn:
            exists = self._conn.execute(
                "SELECT 1 FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
            if exists is None:
                raise KeyError(project_id)
            self._conn.execute(
                "UPDATE projects SET name = ?, updated_at = ? WHERE project_id = ?",
                (payload.name, now, project_id),
            )
            self._write_problem(project_id, payload)
            self._replace_cases(project_id, payload.cases)
        result = self.get_project(project_id)
        assert result is not None
        return result

    def _write_problem(self, project_id: str, payload: ProjectPayload) -> None:
        p = payload.problem
        self._conn.execute(
            """
            INSERT INTO problems(project_id, title, description, idea, source, language, algorithm, source_style)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                title=excluded.title,
                description=excluded.description,
                idea=excluded.idea,
                source=excluded.source,
                language=excluded.language,
                algorithm=excluded.algorithm,
                source_style=excluded.source_style
            """,
            (
                project_id,
                p.title,
                p.description,
                p.idea,
                p.source,
                p.language,
                p.algorithm,
                p.source_style,
            ),
        )

    def _replace_cases(self, project_id: str, cases: list[TestCasePayload]) -> None:
        self._conn.execute("DELETE FROM test_cases WHERE project_id = ?", (project_id,))
        for index, case in enumerate(cases):
            self._conn.execute(
                """
                INSERT INTO test_cases(project_id, case_id, name, input_json, expected_json,
                                       source, description, sort_order)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    case.case_id,
                    case.name,
                    _json(case.input_data),
                    _json(case.expected_output),
                    case.source.value,
                    case.description,
                    index,
                ),
            )

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT p.project_id, p.name, p.created_at, p.updated_at,
                       pr.title, pr.description, pr.idea, pr.source, pr.language,
                       pr.algorithm, pr.source_style
                FROM projects p JOIN problems pr ON pr.project_id = p.project_id
                WHERE p.project_id = ?
                """,
                (project_id,),
            ).fetchone()
            if row is None:
                return None
            cases = self._cases_for_project(project_id)
            last_run = self._last_run(project_id)
        return {
            "project_id": row["project_id"],
            "name": row["name"],
            "problem": {
                "title": row["title"],
                "description": row["description"],
                "idea": row["idea"],
                "source": row["source"],
                "language": row["language"],
                "algorithm": row["algorithm"],
                "source_style": row["source_style"],
            },
            "cases": cases,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_run": last_run,
        }

    def _cases_for_project(self, project_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM test_cases WHERE project_id = ? ORDER BY sort_order, case_id",
            (project_id,),
        ).fetchall()
        return [
            {
                "case_id": row["case_id"],
                "name": row["name"],
                "input_data": _loads(row["input_json"], {}),
                "expected_output": _loads(row["expected_json"], None),
                "source": row["source"],
                "description": row["description"],
            }
            for row in rows
        ]

    def list_projects(self) -> list[ProjectSummary]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT p.project_id, p.name, p.updated_at, pr.title, pr.algorithm,
                       (SELECT COUNT(*) FROM test_cases tc WHERE tc.project_id = p.project_id) AS case_count,
                       (SELECT status FROM runs r WHERE r.project_id = p.project_id
                        ORDER BY r.created_at DESC, r.rowid DESC LIMIT 1) AS last_run_status
                FROM projects p JOIN problems pr ON pr.project_id = p.project_id
                ORDER BY p.updated_at DESC
                """
            ).fetchall()
        return [
            ProjectSummary(
                project_id=row["project_id"],
                name=row["name"],
                title=row["title"],
                algorithm=row["algorithm"],
                updated_at=row["updated_at"],
                case_count=int(row["case_count"] or 0),
                last_run_status=row["last_run_status"],
            )
            for row in rows
        ]

    def _last_run(self, project_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT run_id, status, created_at, finished_at FROM runs "
            "WHERE project_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    # ------------------------------------------------------------------ runs
    def create_run(self, project_id: str) -> RunRecord:
        project = self.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        if not project["cases"]:
            raise ValueError("项目至少需要一个测试用例")
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        now = _now()
        snapshot = {"name": project["name"], "problem": project["problem"], "cases": project["cases"]}
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO runs(run_id, project_id, status, created_at, summary_json, snapshot_json)
                VALUES (?, ?, 'queued', ?, '{}', ?)
                """,
                (run_id, project_id, now, _json(snapshot)),
            )
        record = self.get_run(run_id)
        assert record is not None
        return record

    def get_run_snapshot(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                "SELECT snapshot_json FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return _loads(row["snapshot_json"], {})

    def mark_run_running(self, run_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE runs SET status = 'running', started_at = ? WHERE run_id = ?",
                (_now(), run_id),
            )

    def complete_run(
        self,
        run_id: str,
        *,
        classroom: dict[str, Any],
        case_records: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE runs SET status='completed', finished_at=?, error=NULL,
                                classroom_json=?, summary_json=?
                WHERE run_id=?
                """,
                (_now(), _json(classroom), _json(summary), run_id),
            )
            self._conn.execute("DELETE FROM case_runs WHERE run_id = ?", (run_id,))
            for index, case in enumerate(case_records):
                self._conn.execute(
                    """
                    INSERT INTO case_runs(run_id, case_id, name, source, status, expected_json,
                                          actual_json, error, execution_json, animation_json,
                                          metadata_json, step_count, sort_order)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        case["case_id"],
                        case["name"],
                        case["source"],
                        case["status"],
                        _json(case.get("expected_output")),
                        _json(case.get("actual_output")),
                        case.get("error"),
                        _json(case.get("execution_trace")) if case.get("execution_trace") is not None else None,
                        _json(case.get("animation_trace")) if case.get("animation_trace") is not None else None,
                        _json(case.get("execution_metadata") or {}),
                        int(case.get("step_count") or 0),
                        index,
                    ),
                )

    def fail_run(self, run_id: str, error: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE runs SET status='failed', finished_at=?, error=? WHERE run_id=?",
                (_now(), error[-8000:], run_id),
            )

    def recover_interrupted(self) -> int:
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "UPDATE runs SET status='failed', finished_at=?, error=? "
                "WHERE status IN ('queued', 'running')",
                (_now(), "服务重启，执行任务中断；请重新执行"),
            )
            return cursor.rowcount

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT r.*, p.name AS project_name, pr.title AS problem_title
                FROM runs r JOIN projects p ON p.project_id = r.project_id
                JOIN problems pr ON pr.project_id = r.project_id
                WHERE r.run_id = ?
                """,
                (run_id,),
            ).fetchone()
        return self._run_row(row) if row is not None else None

    def _run_row(self, row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            run_id=row["run_id"],
            project_id=row["project_id"],
            status=row["status"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            error=row["error"],
            summary=_loads(row["summary_json"], {}),
            project_name=row["project_name"],
            problem_title=row["problem_title"],
        )

    def list_runs(self, project_id: str | None = None, limit: int = 30) -> list[RunRecord]:
        query = (
            "SELECT r.*, p.name AS project_name, pr.title AS problem_title "
            "FROM runs r JOIN projects p ON p.project_id = r.project_id "
            "JOIN problems pr ON pr.project_id = r.project_id"
        )
        params: list[Any] = []
        if project_id:
            query += " WHERE r.project_id = ?"
            params.append(project_id)
        query += " ORDER BY r.created_at DESC, r.rowid DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._run_row(row) for row in rows]

    def get_case_runs(self, run_id: str) -> list[CaseRunRecord]:
        with self._lock:
            if self._conn.execute("SELECT 1 FROM runs WHERE run_id = ?", (run_id,)).fetchone() is None:
                raise KeyError(run_id)
            rows = self._conn.execute(
                "SELECT * FROM case_runs WHERE run_id = ? ORDER BY sort_order, case_id",
                (run_id,),
            ).fetchall()
        return [self._case_row(row, include_traces=True) for row in rows]

    def get_case_run(self, run_id: str, case_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM case_runs WHERE run_id = ? AND case_id = ?",
                (run_id, case_id),
            ).fetchone()
        if row is None:
            return None
        return {
            "case_id": row["case_id"],
            "name": row["name"],
            "source": row["source"],
            "status": row["status"],
            "expected_output": _loads(row["expected_json"], None),
            "actual_output": _loads(row["actual_json"], None),
            "error": row["error"],
            "step_count": int(row["step_count"] or 0),
            "execution_trace": _loads(row["execution_json"], None),
            "animation_trace": _loads(row["animation_json"], None),
            "execution_metadata": _loads(row["metadata_json"], {}),
        }

    def _case_row(self, row: sqlite3.Row, *, include_traces: bool) -> CaseRunRecord:
        return CaseRunRecord(
            case_id=row["case_id"],
            name=row["name"],
            source=CaseSource(row["source"]),
            status=row["status"],
            expected_output=_loads(row["expected_json"], None),
            actual_output=_loads(row["actual_json"], None),
            error=row["error"],
            step_count=int(row["step_count"] or 0),
            execution_trace_id=(
                (_loads(row["execution_json"], {}) or {}).get("trace_id") if include_traces else None
            ),
            animation_trace_id=(
                ((_loads(row["animation_json"], {}) or {}).get("metadata") or {}).get("execution_trace_id")
                if include_traces
                else None
            ),
        )

    def get_classroom(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT classroom_json FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        return _loads(row["classroom_json"], None)

    def close(self) -> None:
        with self._lock:
            self._conn.close()
