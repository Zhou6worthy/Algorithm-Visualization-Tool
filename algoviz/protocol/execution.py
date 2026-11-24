"""ExecutionTrace 2.0：用户代码真实执行事实与语义操作协议。

与现有 Animation Trace（`protocol/events.py` 的 `Trace`）分离：
- ExecutionTrace 记录“真实执行了什么”；
- AnimationTrace 仍由 TraceAdapter 生成，供现有 Manim 渲染器消费。
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .events import StrictModel


class ExecutionStyle(str, Enum):
    FUNCTION = "function"
    LEETCODE_CLASS = "leetcode_class"
    STDIN = "stdin"


class ExecutionStatus(str, Enum):
    OK = "ok"
    TRACE_INCOMPLETE = "trace_incomplete"
    TIMEOUT = "timeout"
    OUTPUT_LIMIT = "output_limit"
    EVENT_LIMIT = "event_limit"
    SANDBOX_ERROR = "sandbox_error"
    UNSUPPORTED = "unsupported"


class TraceLimits(BaseModel):
    wall_timeout_s: float = Field(default=10.0, gt=0)
    cpu_time_s: float = Field(default=2.0, gt=0)
    memory_mb: int = Field(default=256, gt=0)
    max_frames: int = Field(default=5000, gt=0)
    max_stdout_bytes: int = Field(default=64 * 1024, gt=0)
    max_locals_keys: int = Field(default=50, gt=0)
    max_value_bytes: int = Field(default=4096, gt=0)
    max_semantic_ops: int = Field(default=2000, gt=0)
    max_source_bytes: int = Field(default=64 * 1024, gt=0)


class ProgramSpec(StrictModel):
    language: Literal["python", "java", "cpp"] = "python"
    style: ExecutionStyle = ExecutionStyle.FUNCTION
    source: str
    source_hash: str
    entry_point: str
    source_path: str = "user_solution.py"
    harness_path: str = "harness.py"
    source_map: dict[int, int | None] = Field(default_factory=dict)
    wrapper_lines: list[int] = Field(default_factory=list)


class BranchArc(StrictModel):
    arc_id: int = Field(ge=0)
    from_event_id: int | None = None
    to_event_id: int | None = None
    from_line: int
    to_line: int
    kind: Literal[
        "sequential",
        "if_true",
        "if_false",
        "loop_back",
        "function_call",
        "function_return",
        "exception",
    ] = "sequential"
    ast_node_id: str | None = None
    condition_text: str | None = None
    evidence_event_ids: list[int] = Field(default_factory=list)


class ExecutionEvent(StrictModel):
    event_id: int = Field(ge=1)
    frame_id: int = Field(ge=1)
    parent_frame_id: int | None = None
    event: Literal["call", "line", "return", "exception"]
    line: int = Field(ge=1)
    original_line: int | None = Field(default=None, ge=1)
    function: str = ""
    depth: int = Field(default=0, ge=0)
    locals_before: dict[str, Any] = Field(default_factory=dict)
    locals_after: dict[str, Any] | None = None
    after_event_id: int | None = None
    changed: list[str] = Field(default_factory=list)
    stdout_delta: str = ""
    return_value: Any = None
    exception_type: str | None = None
    exception_message: str | None = None
    is_unwind: bool = False


class FunctionFact(StrictModel):
    name: str
    line: int
    end_line: int
    args: list[str] = Field(default_factory=list)


class LoopFact(StrictModel):
    node_id: str
    line: int
    end_line: int
    body_start: int
    body_end: int
    target_names: list[str] = Field(default_factory=list)


class BranchFact(StrictModel):
    node_id: str
    line: int
    condition: str = ""
    body_start: int | None = None
    body_end: int | None = None
    orelse_start: int | None = None
    orelse_end: int | None = None


class AssignmentFact(StrictModel):
    line: int
    target: str
    kind: Literal["assign", "subscript", "augassign"] = "assign"


class ReturnFact(StrictModel):
    line: int


class StaticFacts(StrictModel):
    functions: list[FunctionFact] = Field(default_factory=list)
    loops: list[LoopFact] = Field(default_factory=list)
    branches: list[BranchFact] = Field(default_factory=list)
    assignments: list[AssignmentFact] = Field(default_factory=list)
    returns: list[ReturnFact] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list)
    source_lines: int = 0


class SemanticKind(str, Enum):
    INIT = "init"
    VISIT = "visit"
    COMPARE = "compare"
    HASH_LOOKUP = "hash_lookup"
    HASH_INSERT = "hash_insert"
    POINTER_MOVE = "pointer_move"
    DP_UPDATE = "dp_update"
    TREE_VISIT = "tree_visit"
    GRAPH_RELAX = "graph_relax"
    RETURN = "return"
    COMPLETE = "complete"
    GENERIC_LINE = "generic_line"


class SemanticOperation(StrictModel):
    op_id: int = Field(ge=0)
    kind: SemanticKind
    evidence_event_ids: list[int] = Field(min_length=1)
    original_line: int | None = Field(default=None, ge=1)
    targets: list[str | int] = Field(default_factory=list)
    values_before: dict[str, Any] = Field(default_factory=dict)
    values_after: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    description: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class ExecutionResult(StrictModel):
    status: ExecutionStatus = ExecutionStatus.OK
    actual_output: Any = None
    return_value: Any = None
    stdout: str = ""
    stderr: str = ""
    exception_type: str | None = None
    exception_message: str | None = None
    duration_ms: float = 0.0
    source_hash: str = ""
    trace_complete: bool = False
    event_count: int = 0
    sandbox: Literal["local", "docker"] = "local"
    limits: TraceLimits = Field(default_factory=TraceLimits)


class ExecutionValidation(StrictModel):
    output_verified: bool = False
    structure_verified: bool = False
    trace_verified: bool = False
    semantic_verified: bool = False
    notes: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class GenericTrace(StrictModel):
    """Generic Tracer 的输出：只含事实，不含算法语义。"""

    source_hash: str
    events: list[ExecutionEvent] = Field(default_factory=list)
    arcs: list[BranchArc] = Field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    return_value: Any = None
    exception_type: str | None = None
    exception_message: str | None = None
    trace_complete: bool = False
    event_count: int = 0


class ExecutionTrace(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    trace_id: str
    program: ProgramSpec
    static: StaticFacts
    input: dict[str, Any] = Field(default_factory=dict)
    expected_output: Any = None
    events: list[ExecutionEvent]
    arcs: list[BranchArc]
    semantic_ops: list[SemanticOperation]
    unmapped_event_ids: list[int] = Field(default_factory=list)
    semantic_quality: Literal["specific", "generic"] = "specific"
    result: ExecutionResult
    validation: ExecutionValidation

    @model_validator(mode="after")
    def _check_events(self) -> "ExecutionTrace":
        if self.events:
            expected = list(range(1, len(self.events) + 1))
            actual = [event.event_id for event in self.events]
            if actual != expected:
                raise ValueError("ExecutionTrace.event_id 必须从 1 连续递增")
        for op in self.semantic_ops:
            if not op.evidence_event_ids:
                raise ValueError("SemanticOperation 必须至少有一个 evidence event")
        return self
