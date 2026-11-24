import json

import pytest

from algoviz.algorithms.registry import ALGORITHMS, execute_task, list_algorithms
from algoviz.protocol.events import StepType, Trace
from algoviz.protocol.teaching import TaskSpec


@pytest.mark.parametrize("key", [spec.key for spec in list_algorithms()])
def test_every_registered_algorithm_runs_and_verifies(key: str) -> None:
    outcome = execute_task(TaskSpec(algorithm=key))
    trace = outcome.trace
    assert trace.verified, trace.verification_notes
    assert trace.steps, "至少应有 init/complete 事件"
    assert trace.steps[0].step_id == 0
    assert trace.steps[-1].type == StepType.COMPLETE
    for previous, current in zip(trace.steps, trace.steps[1:]):
        assert current.state_before == previous.state_after, "状态快照必须可以连续重放"
        assert current.step_id == previous.step_id + 1


def test_bubble_sort_result_and_events() -> None:
    trace = execute_task(TaskSpec(algorithm="bubble_sort", params={"array": [5, 3, 8, 1]})).trace
    assert trace.result["array"] == [1, 3, 5, 8]
    assert any(step.type == StepType.SWAP for step in trace.steps)
    assert any(step.type == StepType.COMPARE for step in trace.steps)
    assert trace.steps[-1].state_after.array.values == [1, 3, 5, 8]


def test_binary_search_found_and_missing() -> None:
    found = execute_task(TaskSpec(algorithm="binary_search", params={"array": [1, 3, 5, 7, 9], "target": 7})).trace
    assert found.result["index"] == 3
    missing = execute_task(TaskSpec(algorithm="binary_search", params={"array": [1, 3, 5], "target": 8})).trace
    assert missing.result["index"] == -1
    assert missing.steps[-1].type == StepType.COMPLETE


def test_binary_search_auto_sorts_unsorted_input() -> None:
    outcome = execute_task(TaskSpec(algorithm="binary_search", params={"array": [9, 1, 5, 3], "target": 5}))
    assert outcome.trace.result["array"] == [1, 3, 5, 9]
    assert outcome.warnings


def test_knapsack_backtrack_is_consistent() -> None:
    trace = execute_task(TaskSpec(algorithm="knapsack_01")).trace
    chosen = trace.result["chosen"]
    weights = trace.metadata.input["weights"]
    capacity = trace.metadata.input["capacity"]
    assert sum(weights[i] for i in chosen) <= capacity
    assert trace.result["max_value"] == 10


def test_lcs_subsequence() -> None:
    trace = execute_task(TaskSpec(algorithm="lcs", params={"s1": "ABCBDAB", "s2": "BDCABA"})).trace
    subsequence = trace.result["subsequence"]
    assert len(subsequence) == trace.result["length"] == 4


def test_trace_json_roundtrip() -> None:
    trace = execute_task(TaskSpec(algorithm="quick_sort", params={"array": [8, 3, 5, 1]})).trace
    payload = trace.model_dump_json()
    restored = Trace.model_validate_json(payload)
    assert restored.metadata.algorithm == "quick_sort"
    assert len(restored.steps) == len(trace.steps)
    assert json.loads(payload)["metadata"]["visual_kind"] == "array"


def test_unknown_algorithm_raises() -> None:
    from algoviz.algorithms.registry import TaskValidationError

    with pytest.raises(TaskValidationError):
        execute_task(TaskSpec(algorithm="not_a_real_algorithm"))
