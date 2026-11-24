from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from algoviz.execution.orchestrator import M1Executor
from algoviz.execution.python_adapter import ExecutionAdapterError, PythonExecutionAdapter
from algoviz.execution.safe_serializer import SafeSerializer
from algoviz.execution.sandbox import DockerSandbox, LocalSandbox
from algoviz.protocol.execution import ExecutionStatus


TWO_SUM_FUNCTION = '''def two_sum(nums, target):
    seen = {}
    for i, x in enumerate(nums):
        need = target - x
        if need in seen:
            return [seen[need], i]
        seen[x] = i
    return []
'''

TWO_SUM_CLASS = '''class Solution:
    def two_sum(self, nums, target):
        seen = {}
        for i, x in enumerate(nums):
            need = target - x
            if need in seen:
                return [seen[need], i]
            seen[x] = i
        return []
'''


def test_safe_serializer_no_side_effects_and_cycles() -> None:
    class Evil:
        def __repr__(self) -> str:  # pragma: no cover - must never run
            raise AssertionError("repr must not be called")

        @property
        def secret(self):  # pragma: no cover - must never run
            raise AssertionError("property must not be called")

    @dataclass
    class Point:
        x: int
        y: int

    serializer = SafeSerializer()
    assert serializer.to_native(serializer.serialize(Evil())) == {"$unsupported": "Evil"}
    assert serializer.to_native(serializer.serialize(Point(1, 2))) == {"x": 1, "y": 2}

    loop: list = []
    loop.append(loop)
    native = serializer.to_native(serializer.serialize(loop))
    assert native and native[0]["$cycle"]


def test_safe_serializer_nodes_and_hostile_objects() -> None:
    class TreeNode:
        def __init__(self, val=0, left=None, right=None):
            self.val = val
            self.left = left
            self.right = right

        def __repr__(self) -> str:  # pragma: no cover - must never run
            raise AssertionError("repr must not be called")

    class ListNode:
        def __init__(self, val=0, next=None):
            self.val = val
            self.next = next

    class Hostile:
        def __getattribute__(self, name):  # pragma: no cover - must never run
            raise AssertionError("attribute access must not happen")

    serializer = SafeSerializer()
    tree = TreeNode(2, TreeNode(1), TreeNode(3))
    tree_native = serializer.to_native(serializer.serialize(tree))
    assert tree_native["val"] == 2
    assert tree_native["left"]["val"] == 1
    assert tree_native["right"]["val"] == 3

    linked = ListNode(1, ListNode(2))
    linked_native = serializer.to_native(serializer.serialize(linked))
    assert linked_native["val"] == 1
    assert linked_native["next"]["val"] == 2

    assert serializer.to_native(serializer.serialize(Hostile())) == {"$unsupported": "Hostile"}


def test_adapter_keeps_user_source_exact() -> None:
    adapter = PythonExecutionAdapter()
    prepared = adapter.prepare(
        TWO_SUM_FUNCTION,
        style="function",
        entry_point="two_sum",
        args=[[2, 7, 11, 15], 9],
    )
    assert prepared.source == TWO_SUM_FUNCTION
    assert prepared.source_map[1] == 1
    assert prepared.source_map[len(TWO_SUM_FUNCTION.splitlines())] == len(TWO_SUM_FUNCTION.splitlines())
    assert prepared.user_filename == "user_solution.py"
    assert prepared.harness_filename == "harness.py"

    with pytest.raises(ExecutionAdapterError):
        adapter.prepare("def other(): pass", style="function", entry_point="two_sum")


def test_two_sum_function_real_trace(tmp_path: Path) -> None:
    run = M1Executor(tmp_path).run_two_sum(
        name="two_sum_function",
        source=TWO_SUM_FUNCTION,
        style="function",
        entry_point="two_sum",
        nums=[2, 7, 11, 15],
        target=9,
    )
    execution = run.execution
    assert execution.validation.output_verified
    assert execution.validation.structure_verified
    assert execution.validation.trace_verified
    assert execution.validation.semantic_verified
    assert execution.result.actual_output == [0, 1]
    assert execution.program.source_hash == execution.result.source_hash
    assert execution.result.trace_complete
    assert len(execution.events) == 11
    # 真实 sys.settrace 时序：line 事件是执行前；after 由下一事件确认
    line2 = next(e for e in execution.events if e.event == "line" and e.line == 2)
    assert "seen" not in line2.locals_before
    assert line2.locals_after is not None and line2.locals_after.get("seen") == {}
    line7 = next(e for e in execution.events if e.event == "line" and e.line == 7)
    assert line7.locals_before.get("seen") == {}
    assert line7.locals_after is not None and line7.locals_after.get("seen") == {"2": 0}
    assert not any(e.event == "line" and e.line == 8 for e in execution.events)

    lookups = [op for op in execution.semantic_ops if op.kind.value == "hash_lookup"]
    inserts = [op for op in execution.semantic_ops if op.kind.value == "hash_insert"]
    assert [lookup.data["hit"] for lookup in lookups] == [False, True]
    assert len(inserts) == 1 and inserts[0].data["key"] == "2"

    steps = run.trace.steps
    assert len(steps) == 8
    assert steps[2].state_before.dict_state.lookup_status is None
    assert steps[2].state_after.dict_state.lookup_status == "miss"
    assert steps[5].state_before.dict_state.lookup_status is None
    assert steps[5].state_after.dict_state.lookup_status == "hit"
    assert steps[6].state_after.array.found_indices == [0, 1]
    assert {(entry.key, entry.value) for entry in steps[6].state_after.dict_state.entries} == {("2", 0)}
    assert steps[6].code_line == 6


def test_two_sum_leetcode_class(tmp_path: Path) -> None:
    run = M1Executor(tmp_path).run_two_sum(
        name="two_sum_class",
        source=TWO_SUM_CLASS,
        style="leetcode_class",
        entry_point="Solution.two_sum",
        nums=[2, 7, 11, 15],
        target=9,
    )
    assert run.execution.validation.trace_verified
    assert run.execution.result.actual_output == [0, 1]
    assert run.execution.static.source_lines == 9
    assert run.trace.steps[0].code_line == 3
    assert run.trace.steps[3].code_line == 8
    assert run.trace.steps[6].code_line == 7


def test_trace_incomplete_when_user_disables_settrace(tmp_path: Path) -> None:
    source = "import sys\n\ndef two_sum(nums, target):\n    sys.settrace(None)\n    return [0, 1]\n"
    run = M1Executor(tmp_path).run_two_sum(
        name="trace_incomplete",
        source=source,
        style="function",
        entry_point="two_sum",
        nums=[2, 7, 11, 15],
        target=9,
    )
    assert run.execution.result.status == ExecutionStatus.TRACE_INCOMPLETE
    assert not run.execution.result.trace_complete
    assert not run.execution.validation.trace_verified
    assert not run.trace.verified


def test_output_mismatch_rejected(tmp_path: Path) -> None:
    run = M1Executor(tmp_path).run_two_sum(
        name="mismatch",
        source=TWO_SUM_FUNCTION,
        style="function",
        entry_point="two_sum",
        nums=[2, 7, 11, 15],
        target=9,
        expected_output=[0, 0],
    )
    assert not run.execution.validation.output_verified


def test_docker_lifecycle_copies_then_removes(tmp_path: Path) -> None:
    job_dir = tmp_path / "docker_job"
    calls: list[list[str]] = []

    def fake_runner(command, **kwargs):
        calls.append(command)
        if "cp" in command:
            destination = Path(command[-1])
            destination.parent.mkdir(parents=True, exist_ok=True)
            if command[-1].endswith("frames.jsonl"):
                destination.write_text('{"schema_version":"2.0"}', encoding="utf-8")
            else:
                destination.write_text('{"status":"ok"}', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    sandbox = DockerSandbox(command_runner=fake_runner)
    prepared = PythonExecutionAdapter().prepare(
        TWO_SUM_FUNCTION, style="function", entry_point="two_sum", args=[[2], 1]
    )
    result = sandbox.run(prepared, job_dir)
    assert result.sandbox == "docker"
    flattened = [" ".join(call) for call in calls]
    assert any(call.startswith("docker create") for call in flattened)
    assert not any("--rm" in call for call in flattened[:1])
    assert any("docker cp" in call for call in flattened)
    assert any(call.startswith("docker rm -f") for call in flattened)

    # 容器名必须一致地用于 create/start/wait/cp/rm
    name = calls[0][calls[0].index("--name") + 1]
    assert any(name in call for call in flattened[1:])


def test_docker_cleanup_on_copy_failure(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def failing_runner(command, **kwargs):
        calls.append(command)
        if "cp" in command:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="copy failed")
        if "wait" in command:
            raise subprocess.TimeoutExpired(command, 1)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    sandbox = DockerSandbox(command_runner=failing_runner)
    prepared = PythonExecutionAdapter().prepare(
        TWO_SUM_FUNCTION, style="function", entry_point="two_sum", args=[[2], 1]
    )
    result = sandbox.run(prepared, tmp_path / "docker_fail")
    assert result.status in {ExecutionStatus.TIMEOUT, ExecutionStatus.TRACE_INCOMPLETE, ExecutionStatus.SANDBOX_ERROR}
    assert any("rm -f" in " ".join(call) for call in calls)
