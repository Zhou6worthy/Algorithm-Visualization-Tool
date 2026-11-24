from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from algoviz.algorithms.profiles import AlgorithmProfileError, get_profile
from algoviz.api.app import create_app
from algoviz.config import Settings
from algoviz.execution.profile_case_runner import ProfileCaseRunner
from algoviz.protocol.cases import CaseSource, CaseRunStatus, TestCaseSpec
from algoviz.protocol.visual import ComponentKind
from algoviz.teaching.binary_search_hints import build_binary_search_hints
from algoviz.teaching.classroom import build_classroom_deck

SOURCE = """def binary_search(nums, target):
    left, right = 0, len(nums) - 1
    while left <= right:
        mid = (left + right) // 2
        if nums[mid] == target:
            return mid
        if nums[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1
"""


def _case(case_id: str, nums: list[int], target: int, expected: object) -> TestCaseSpec:
    return TestCaseSpec(
        case_id=case_id,
        name=case_id,
        input_data={"nums": nums, "target": target},
        expected_output=expected,
        source=CaseSource.USER,
    )


def _runner(tmp_path: Path) -> ProfileCaseRunner:
    return ProfileCaseRunner(
        tmp_path / "runs",
        source=SOURCE,
        profile="binary_search",
    )


def test_profiles_register_two_algorithms_and_distinct_visual_plans() -> None:
    two_sum = get_profile("two_sum")
    binary = get_profile("binary_search")
    assert two_sum.key == "two_sum"
    assert binary.key == "binary_search"
    two_plan = two_sum.build_visual_plan()
    binary_plan = binary.build_visual_plan()
    assert [item.kind for item in two_plan.components] == [
        ComponentKind.ARRAY,
        ComponentKind.HASH_MAP,
        ComponentKind.VARIABLES,
        ComponentKind.CODE,
    ]
    assert [item.kind for item in binary_plan.components] == [
        ComponentKind.ARRAY,
        ComponentKind.SEARCH_RANGE,
        ComponentKind.VARIABLES,
        ComponentKind.CODE,
    ]
    assert binary_plan.components[1].slot == "search_range"
    assert binary.entry_point_for("function") == "binary_search"
    assert binary.entry_point_for("leetcode_class") == "Solution.binary_search"
    with pytest.raises(AlgorithmProfileError):
        get_profile("bubble_sort")


def test_binary_search_real_trace_has_range_pointers_and_hints(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    middle = runner.run_case(_case("middle", [1, 3, 5, 7, 9, 11], 7, 3))
    none = runner.run_case(_case("none", [1, 3, 5, 7, 9, 11], 8, -1))
    empty = runner.run_case(_case("empty", [], 5, -1))
    assert middle.status is CaseRunStatus.SUCCESS
    assert none.status is CaseRunStatus.SUCCESS
    assert empty.status is CaseRunStatus.SUCCESS
    assert middle.actual_output == 3
    assert none.actual_output == -1
    assert empty.actual_output == -1
    assert middle.animation_trace is not None
    assert none.animation_trace is not None
    assert empty.animation_trace is not None
    assert middle.animation_trace.metadata.algorithm == "binary_search"
    assert middle.animation_trace.metadata.category == "search"
    assert middle.animation_trace.metadata.visual_kind.value == "array"
    assert len(middle.animation_trace.steps) >= 9
    assert len(none.animation_trace.steps) > len(empty.animation_trace.steps)
    assert middle.animation_trace.steps[0].state_after.array is not None
    assert middle.animation_trace.steps[0].state_after.array.active_range == [0, 5]
    assert middle.animation_trace.steps[1].state_after.array.pointers["mid"] == 2
    found_steps = [step for step in middle.animation_trace.steps if step.type.value == "found"]
    assert found_steps and found_steps[-1].state_after.array.found_indices == [3]
    moves = [step for step in middle.animation_trace.steps if step.type.value == "move"]
    assert moves and moves[0].state_after.array.active_range == [3, 5]
    hints = build_binary_search_hints(middle.animation_trace)
    assert len(hints) == len(middle.animation_trace.steps)
    assert [hint.related_step_id for hint in hints] == [step.step_id for step in middle.animation_trace.steps]
    assert any("左半区" in hint.title for hint in hints)
    assert any("右半区" in hint.title for hint in hints)
    assert any("O(log n)" in hint.explanation for hint in hints)


def test_binary_search_mismatch_invalid_and_independent_cases(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    runs = runner.run_cases(
        [
            _case("middle", [1, 3, 5, 7], 3, 1),
            _case("mismatch", [1, 3, 5, 7], 3, 99),
            _case("invalid", [1, 3, 5, 7], 3, None),
        ]
    )
    # The third case is valid; separate invalid input below.
    assert runs[0].status is CaseRunStatus.SUCCESS
    assert runs[1].status is CaseRunStatus.FAILED
    assert runs[1].actual_output == 1
    assert runs[1].execution_trace is not None and runs[1].animation_trace is not None
    assert runs[0].execution_trace.trace_id != runs[1].execution_trace.trace_id
    assert runs[0].animation_trace.metadata.execution_trace_id != runs[1].animation_trace.metadata.execution_trace_id
    assert runs[2].status is CaseRunStatus.SUCCESS
    assert runs[2].execution_trace.validation.output_verified is False

    invalid = runner.run_case(
        TestCaseSpec(
            case_id="bad_input",
            name="bad_input",
            input_data={"nums": [1]},
            expected_output=-1,
        )
    )
    assert invalid.status is CaseRunStatus.ERROR
    assert invalid.execution_trace is None
    assert invalid.animation_trace is None
    assert "target" in (invalid.error or "")


def test_binary_search_execution_exception_is_case_error(tmp_path: Path) -> None:
    runner = ProfileCaseRunner(
        tmp_path / "exception",
        source="def binary_search(nums, target):\n    raise RuntimeError('boom')\n",
        profile="binary_search",
    )
    run = runner.run_case(_case("explode", [1, 2, 3], 2, 1))
    assert run.status is CaseRunStatus.ERROR
    assert run.animation_trace is None
    assert "boom" in (run.error or "") or "未获得追踪数据" in (run.error or "")


def test_binary_search_trace_adapter_rejects_unsupported_source(tmp_path: Path) -> None:
    runner = ProfileCaseRunner(
        tmp_path / "unsupported",
        source="def binary_search(nums, target):\n    return 0\n",
        profile="binary_search",
    )
    run = runner.run_case(_case("unsupported", [1, 2, 3], 2, 0))
    assert run.status is CaseRunStatus.ERROR
    assert run.execution_trace is not None
    assert run.animation_trace is None
    assert "TraceAdapter" in (run.error or "")
    assert "generic" in (run.error or "").lower() or "语义" in (run.error or "")


def test_binary_search_classroom_deck_uses_profile_hints_and_views(tmp_path: Path) -> None:
    profile = get_profile("binary_search")
    runner = _runner(tmp_path)
    spec = _case("middle", [1, 3, 5, 7, 9, 11], 7, 3)
    run = runner.run_case(spec)
    deck = build_classroom_deck([(spec, run)], profile=profile, title="二分查找课堂")
    assert deck.algorithm == "binary_search"
    assert deck.title == "二分查找课堂"
    assert [item.kind.value for item in deck.visual_plan.components] == [
        "array",
        "search_range",
        "variables",
        "code",
    ]
    case = deck.cases[0]
    assert case.trace is not None
    assert len(case.hints) == len(case.trace.steps)
    assert len(case.step_views) == len(case.trace.steps)
    assert any(item.label == "range" for item in case.step_views[0].variables)
    assert any(item.label == "left" for item in case.step_views[0].variables)


def _settings(tmp_path: Path) -> Settings:
    settings = Settings()
    settings.output_dir = tmp_path
    return settings


def _wait_run(client: TestClient, run_id: str, timeout: float = 40.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/v1/workbench/runs/{run_id}")
        assert response.status_code == 200, response.text
        data = response.json()
        if data["status"] in {"completed", "failed"}:
            return data
        time.sleep(0.1)
    raise AssertionError("run did not finish in time")


def test_binary_search_workbench_api_end_to_end(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        payload = {
            "name": "二分查找 API 项目",
            "problem": {
                "title": "Binary Search · API",
                "description": "真实二分查找",
                "idea": "维护区间",
                "source": SOURCE,
                "language": "python",
                "algorithm": "binary_search",
                "source_style": "function",
            },
            "cases": [
                {
                    "case_id": "middle",
                    "name": "中间命中",
                    "input_data": {"nums": [1, 3, 5, 7, 9, 11], "target": 7},
                    "expected_output": 3,
                    "source": "user",
                    "description": "",
                },
                {
                    "case_id": "none",
                    "name": "不存在",
                    "input_data": {"nums": [1, 3, 5, 7, 9, 11], "target": 8},
                    "expected_output": -1,
                    "source": "user",
                    "description": "",
                },
                {
                    "case_id": "mismatch",
                    "name": "预期不一致",
                    "input_data": {"nums": [1, 3, 5, 7], "target": 3},
                    "expected_output": 99,
                    "source": "user",
                    "description": "",
                },
                {
                    "case_id": "empty",
                    "name": "空数组",
                    "input_data": {"nums": [], "target": 5},
                    "expected_output": -1,
                    "source": "user",
                    "description": "",
                },
                {
                    "case_id": "ai_extra",
                    "name": "AI 补充",
                    "input_data": {"nums": [2, 4, 6, 8], "target": 1},
                    "expected_output": -1,
                    "source": "ai_generated",
                    "description": "",
                },
            ],
        }
        created = client.post("/api/v1/workbench/projects", json=payload)
        assert created.status_code == 201, created.text
        project = created.json()
        started = client.post(f"/api/v1/workbench/projects/{project['project_id']}/runs")
        assert started.status_code == 202
        run = _wait_run(client, started.json()["run_id"])
        assert run["status"] == "completed"
        assert run["summary"]["case_count"] == 5
        assert run["summary"]["success"] == 4
        assert run["summary"]["failed"] == 1
        assert run["summary"]["error"] == 0
        assert run["summary"]["trace_count"] == 5

        envelope = client.get(f"/api/v1/workbench/runs/{run['run_id']}/classroom")
        assert envelope.status_code == 200, envelope.text
        body = envelope.json()
        classroom = body["classroom"]
        assert classroom["algorithm"] == "binary_search"
        assert classroom["code"] == SOURCE
        assert [item["kind"] for item in classroom["visual_plan"]["components"]] == [
            "array",
            "search_range",
            "variables",
            "code",
        ]
        assert len(classroom["cases"]) == 5
        middle = next(item for item in classroom["cases"] if item["case_id"] == "middle")
        assert middle["status"] == "success"
        assert middle["actual_output"] == 3
        assert len(middle["hints"]) == len(middle["trace"]["steps"])
        assert middle["step_views"][0]["variables"]
        empty = next(item for item in classroom["cases"] if item["case_id"] == "empty")
        assert empty["actual_output"] == -1

        cases = client.get(f"/api/v1/workbench/runs/{run['run_id']}/cases").json()
        assert len(cases) == 5
        assert len({item["execution_trace_id"] for item in cases}) == 5
        assert all(item["animation_trace_id"] for item in cases)
    app.state.store.close()


def test_unsupported_algorithm_run_fails_clearly(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        payload = {
            "name": "不支持算法",
            "problem": {
                "title": "Bubble Sort",
                "description": "",
                "idea": "",
                "source": "def bubble_sort(nums):\n    return nums\n",
                "language": "python",
                "algorithm": "bubble_sort",
                "source_style": "function",
            },
            "cases": [
                {
                    "case_id": "one",
                    "name": "one",
                    "input_data": {"nums": [2, 1]},
                    "expected_output": [1, 2],
                    "source": "user",
                    "description": "",
                }
            ],
        }
        project = client.post("/api/v1/workbench/projects", json=payload).json()
        started = client.post(f"/api/v1/workbench/projects/{project['project_id']}/runs")
        assert started.status_code == 202
        run = _wait_run(client, started.json()["run_id"])
        assert run["status"] == "failed"
        assert "不支持的算法" in (run["error"] or "")
        classroom = client.get(f"/api/v1/workbench/runs/{run['run_id']}/classroom")
        assert classroom.status_code == 409
    app.state.store.close()
