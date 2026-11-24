from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from algoviz.api.app import create_app
from algoviz.config import Settings

SOURCE = """def two_sum(nums, target):
    seen = {}
    for i, x in enumerate(nums):
        need = target - x
        if need in seen:
            return [seen[need], i]
        seen[x] = i
    return []
"""


def _payload() -> dict:
    return {
        "name": "M4 API 测试项目",
        "problem": {
            "title": "Two Sum · API",
            "description": "测试持久化与真实执行",
            "idea": "哈希表记录已见元素",
            "source": SOURCE,
            "language": "python",
            "algorithm": "two_sum",
            "source_style": "function",
        },
        "cases": [
            {
                "case_id": "normal",
                "name": "正常查找",
                "input_data": {"nums": [2, 7, 11, 15], "target": 9},
                "expected_output": [0, 1],
                "source": "user",
                "description": "",
            },
            {
                "case_id": "mismatch",
                "name": "预期不一致",
                "input_data": {"nums": [1, 2, 3], "target": 4},
                "expected_output": [1, 2],
                "source": "user",
                "description": "",
            },
            {
                "case_id": "invalid",
                "name": "缺少 target",
                "input_data": {"nums": [1]},
                "expected_output": None,
                "source": "user",
                "description": "",
            },
        ],
    }


def _settings(tmp_path: Path) -> Settings:
    settings = Settings()
    settings.output_dir = tmp_path
    return settings


def _wait_run(client: TestClient, run_id: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/v1/workbench/runs/{run_id}")
        assert response.status_code == 200, response.text
        data = response.json()
        if data["status"] in {"completed", "failed"}:
            return data
        time.sleep(0.1)
    raise AssertionError("run did not finish in time")


def _close_app(app) -> None:
    # The TestClient context runs the lifespan shutdown, which closes the
    # workbench SQLite connection and run executor. Only the legacy JobStore
    # is not part of that lifespan.
    app.state.store.close()


def test_project_crud_persists_and_lists(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        created = client.post("/api/v1/workbench/projects", json=_payload())
        assert created.status_code == 201, created.text
        project = created.json()
        project_id = project["project_id"]
        assert project["cases"][0]["case_id"] == "normal"
        assert project["cases"][0]["expected_output"] == [0, 1]

        listed = client.get("/api/v1/workbench/projects").json()
        assert len(listed) == 1
        assert listed[0]["project_id"] == project_id
        assert listed[0]["case_count"] == 3

        updated_payload = _payload()
        updated_payload["name"] = "更新后的项目"
        updated_payload["problem"]["title"] = "更新后的 Two Sum"
        updated_payload["cases"] = [
            {
                "case_id": "empty",
                "name": "空数组",
                "input_data": {"nums": [], "target": 9},
                "expected_output": [],
                "source": "user",
                "description": "",
            }
        ]
        updated = client.put(f"/api/v1/workbench/projects/{project_id}", json=updated_payload)
        assert updated.status_code == 200, updated.text
        assert updated.json()["name"] == "更新后的项目"
        assert updated.json()["problem"]["title"] == "更新后的 Two Sum"
        assert [item["case_id"] for item in updated.json()["cases"]] == ["empty"]

        missing = client.get("/api/v1/workbench/projects/missing")
        assert missing.status_code == 404
        bad = client.put("/api/v1/workbench/projects/missing", json=updated_payload)
        assert bad.status_code == 404
        no_cases = client.post(f"/api/v1/workbench/projects/{project_id}/runs")
        assert no_cases.status_code == 202  # has one case, so this starts a run; checked separately
        run_id = no_cases.json()["run_id"]
        _wait_run(client, run_id)
    _close_app(app)

    # A new process / app creation reads the same SQLite file.
    app2 = create_app(_settings(tmp_path))
    with TestClient(app2) as client:
        restored = client.get(f"/api/v1/workbench/projects/{project_id}")
        assert restored.status_code == 200
        assert restored.json()["name"] == "更新后的项目"
        assert [item["case_id"] for item in restored.json()["cases"]] == ["empty"]
        assert client.get("/api/v1/workbench/projects").json()[0]["last_run_status"] == "completed"
    _close_app(app2)


def test_real_run_generates_independent_case_traces_and_classroom(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        project = client.post("/api/v1/workbench/projects", json=_payload()).json()
        project_id = project["project_id"]
        created = client.post(f"/api/v1/workbench/projects/{project_id}/runs")
        assert created.status_code == 202
        run = _wait_run(client, created.json()["run_id"])
        assert run["status"] == "completed"
        assert run["summary"] == {
            "case_count": 3,
            "success": 1,
            "failed": 1,
            "error": 1,
            "trace_count": 2,
            "steps_total": 19,
        }

        cases = client.get(f"/api/v1/workbench/runs/{run['run_id']}/cases").json()
        assert [item["case_id"] for item in cases] == ["normal", "mismatch", "invalid"]
        assert [item["status"] for item in cases] == ["success", "failed", "error"]
        assert cases[0]["actual_output"] == [0, 1]
        assert cases[1]["actual_output"] == [0, 2]
        assert cases[1]["error"] and "输出不一致" in cases[1]["error"]
        assert cases[2]["step_count"] == 0
        assert cases[2]["execution_trace_id"] is None
        assert cases[0]["execution_trace_id"] != cases[1]["execution_trace_id"]
        assert cases[0]["animation_trace_id"] != cases[1]["animation_trace_id"]

        invalid_detail = client.get(f"/api/v1/workbench/runs/{run['run_id']}/cases/invalid").json()
        assert invalid_detail["execution_trace"] is None
        assert invalid_detail["animation_trace"] is None
        assert "target" in invalid_detail["error"]

        envelope = client.get(f"/api/v1/workbench/runs/{run['run_id']}/classroom")
        assert envelope.status_code == 200, envelope.text
        body = envelope.json()
        assert body["run"]["run_id"] == run["run_id"]
        assert len(body["cases"]) == 3
        classroom = body["classroom"]
        assert classroom["schema_version"] == "3.8"
        assert classroom["code"] == SOURCE
        assert classroom["active_case_id"] == "normal"
        assert len(classroom["visual_plan"]["components"]) == 4
        assert [item["case_id"] for item in classroom["cases"]] == ["normal", "mismatch", "invalid"]
        normal = classroom["cases"][0]
        assert len(normal["trace"]["steps"]) == 8
        assert len(normal["hints"]) == 8
        assert len(normal["step_views"]) == 8
        assert normal["hints"][0]["related_step_id"] == 0
        assert classroom["cases"][2]["trace"] is None
        assert classroom["cases"][2]["hints"] == []

        run_list = client.get(f"/api/v1/workbench/projects/{project_id}/runs").json()
        assert len(run_list) == 1
        assert run_list[0]["run_id"] == run["run_id"]

        second = client.post(f"/api/v1/workbench/projects/{project_id}/runs")
        second_run = _wait_run(client, second.json()["run_id"])
        assert second_run["run_id"] != run["run_id"]
        assert len(client.get(f"/api/v1/workbench/projects/{project_id}/runs").json()) == 2
    _close_app(app)


def test_workbench_runs_leetcode_class_source(tmp_path: Path) -> None:
    source = """class Solution:
    def two_sum(self, nums, target):
        seen = {}
        for i, x in enumerate(nums):
            need = target - x
            if need in seen:
                return [seen[need], i]
            seen[x] = i
        return []
"""
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        payload = _payload()
        payload["problem"]["source"] = source
        payload["problem"]["source_style"] = "leetcode_class"
        payload["cases"] = [
            {
                "case_id": "class_case",
                "name": "类版命中",
                "input_data": {"nums": [3, 2, 4], "target": 5},
                "expected_output": [0, 1],
                "source": "user",
                "description": "",
            }
        ]
        project = client.post("/api/v1/workbench/projects", json=payload).json()
        created = client.post(f"/api/v1/workbench/projects/{project['project_id']}/runs")
        run = _wait_run(client, created.json()["run_id"])
        assert run["status"] == "completed"
        assert run["summary"]["success"] == 1
        classroom = client.get(f"/api/v1/workbench/runs/{run['run_id']}/classroom").json()["classroom"]
        assert classroom["code"] == source
        case = classroom["cases"][0]
        assert case["status"] == "success"
        assert case["trace"]["steps"][0]["code_line"] == 3
    _close_app(app)


def test_run_without_expected_keeps_real_trace_but_is_unverified(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        payload = _payload()
        payload["cases"] = [
            {
                "case_id": "no_expected",
                "name": "不提供 expected",
                "input_data": {"nums": [4, 5], "target": 9},
                "expected_output": None,
                "source": "user",
                "description": "",
            }
        ]
        project = client.post("/api/v1/workbench/projects", json=payload).json()
        created = client.post(f"/api/v1/workbench/projects/{project['project_id']}/runs")
        run = _wait_run(client, created.json()["run_id"])
        assert run["status"] == "completed"
        assert run["summary"]["success"] == 1
        case = client.get(f"/api/v1/workbench/runs/{run['run_id']}/cases/no_expected").json()
        assert case["execution_trace"] is not None
        assert case["animation_trace"] is not None
        assert case["execution_trace"]["validation"]["output_verified"] is False
        assert case["animation_trace"]["verified"] is False
        assert case["actual_output"] == [0, 1]
        assert case["expected_output"] is None
    _close_app(app)


def test_api_errors_for_missing_project_and_run(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/v1/workbench/projects/missing").status_code == 404
        assert client.post("/api/v1/workbench/projects/missing/runs").status_code == 404
        assert client.get("/api/v1/workbench/runs/missing").status_code == 404
        assert client.get("/api/v1/workbench/runs/missing/cases").status_code == 404
        assert client.get("/api/v1/workbench/runs/missing/classroom").status_code == 404

        blank_payload = _payload()
        blank_payload["cases"] = []
        blank = client.post("/api/v1/workbench/projects", json=blank_payload).json()
        no_cases = client.post(f"/api/v1/workbench/projects/{blank['project_id']}/runs")
        assert no_cases.status_code == 422
        assert "测试用例" in no_cases.json()["detail"]
    _close_app(app)
