"""统一动画事件协议（Animation Event JSON）。

设计原则（对应 readme 第五节）：
- 每一步都携带 state_before / state_after，可以完整重放每一帧状态；
- 算法执行由追踪器产生事件，大模型只负责描述与讲解，不编造执行步骤；
- 不同算法类别共用同一套事件类型，动画模板按 visual_kind 复用。
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StepType(str, Enum):
    """事件类型：覆盖排序/查找/树/图/DP 五类追踪器。"""

    INIT = "init"
    COMPARE = "compare"
    SWAP = "swap"
    UPDATE = "update"
    VISIT = "visit"
    CREATE = "create"
    MOVE = "move"
    MARK = "mark"
    PUSH = "push"
    POP = "pop"
    ENQUEUE = "enqueue"
    DEQUEUE = "dequeue"
    RELAX = "relax"
    FOUND = "found"
    BACKTRACK = "backtrack"
    NOTE = "note"
    COMPLETE = "complete"


class VisualKind(str, Enum):
    ARRAY = "array"
    TREE = "tree"
    GRAPH = "graph"
    MATRIX = "matrix"


class InputSource(str, Enum):
    NATURAL_LANGUAGE = "natural_language"
    PSEUDOCODE = "pseudocode"
    SOURCE_CODE = "source_code"
    PRESET = "preset"


class ArrayState(StrictModel):
    values: list[Any]
    sorted_indices: list[int] = Field(default_factory=list)
    active_range: list[int] | None = None
    pointers: dict[str, int] = Field(default_factory=dict)
    target: Any = None
    found_index: int | None = None
    aux: list[Any] | None = None
    found_indices: list[int] = Field(default_factory=list)


class TreeNodeState(StrictModel):
    id: str
    value: Any
    left: str | None = None
    right: str | None = None
    parent: str | None = None
    depth: int = 0
    x: float = 0.0  # 中序序号（0..n-1），树场景负责缩放居中


class TreeState(StrictModel):
    nodes: list[TreeNodeState] = Field(default_factory=list)
    root: str | None = None
    visited: list[str] = Field(default_factory=list)
    current: str | None = None
    frontier: list[str] = Field(default_factory=list)


class GraphNodeState(StrictModel):
    id: str
    label: str = ""
    x: float = 0.0
    y: float = 0.0


class GraphEdgeState(StrictModel):
    source: str
    target: str
    weight: float = 1.0
    directed: bool = False
    active: bool = False


class GraphState(StrictModel):
    nodes: list[GraphNodeState] = Field(default_factory=list)
    edges: list[GraphEdgeState] = Field(default_factory=list)
    visited: list[str] = Field(default_factory=list)
    frontier: list[str] = Field(default_factory=list)
    distances: dict[str, float] = Field(default_factory=dict)
    current: str | None = None
    path: list[str] = Field(default_factory=list)


class MatrixState(StrictModel):
    rows: int
    cols: int
    table: list[list[Any]]
    row_headers: list[str] = Field(default_factory=list)
    col_headers: list[str] = Field(default_factory=list)
    current: list[int] | None = None
    dependencies: list[list[int]] = Field(default_factory=list)
    path: list[list[int]] = Field(default_factory=list)
    highlight: list[list[int]] = Field(default_factory=list)
    legend: list[str] = Field(default_factory=list)
    cell_notes: dict[str, str] = Field(default_factory=dict)


class VariableView(StrictModel):
    name: str
    type: str = ""
    value: str = ""
    changed: bool = False
    truncated: bool = False


class DictEntryView(StrictModel):
    key: str
    value: Any
    highlighted: bool = False


class DictState(StrictModel):
    title: str = "哈希表"
    entries: list[DictEntryView] = Field(default_factory=list)
    lookup_key: str | None = None
    lookup_status: Literal["hit", "miss"] | None = None
    highlighted_keys: list[str] = Field(default_factory=list)


class VisualState(StrictModel):
    """可视化快照：只有与 visual_kind 对应的字段会被填充。"""

    kind: VisualKind
    array: ArrayState | None = None
    tree: TreeState | None = None
    graph: GraphState | None = None
    matrix: MatrixState | None = None
    dict_state: DictState | None = None
    variables: list[VariableView] = Field(default_factory=list)
    note: str | None = None

    @model_validator(mode="after")
    def _check_block(self) -> "VisualState":
        if getattr(self, self.kind.value) is None:
            raise ValueError(f"kind={self.kind.value} 时缺少 {self.kind.value} 状态块")
        return self


class AnimationStep(StrictModel):
    step_id: int = Field(ge=0)
    type: StepType
    targets: list[str | int] = Field(default_factory=list)
    description: str
    narration: str = ""
    code_line: int | None = Field(default=None, ge=1)
    duration: float | None = Field(default=None, gt=0)
    visual_action: str = ""
    state_before: VisualState
    state_after: VisualState
    meta: dict[str, Any] = Field(default_factory=dict)


class Complexity(StrictModel):
    time: str
    space: str
    note: str = ""


class TraceMetadata(StrictModel):
    algorithm: str
    title: str
    category: Literal["sort", "search", "tree", "graph", "dp", "custom"]
    visual_kind: VisualKind
    language: str = "python"
    source: InputSource = InputSource.PRESET
    input: dict[str, Any] = Field(default_factory=dict)
    expected_output: dict[str, Any] = Field(default_factory=dict)
    complexity: Complexity
    code: str = ""
    code_language: str = "python"
    description: str = ""
    idea: list[str] = Field(default_factory=list)
    summary: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    source_kind: Literal["builtin", "user_code"] = "builtin"
    execution_trace_id: str | None = None


class Trace(StrictModel):
    schema_version: str = SCHEMA_VERSION
    metadata: TraceMetadata
    steps: list[AnimationStep]
    result: dict[str, Any] = Field(default_factory=dict)
    verified: bool = False
    verification_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_steps(self) -> "Trace":
        expected = list(range(len(self.steps)))
        actual = [s.step_id for s in self.steps]
        if actual != expected:
            raise ValueError("step_id 必须从 0 连续递增")
        for step in self.steps:
            if step.state_before.kind != self.metadata.visual_kind:
                raise ValueError("state_before.kind 与 metadata.visual_kind 不一致")
            if step.state_after.kind != self.metadata.visual_kind:
                raise ValueError("state_after.kind 与 metadata.visual_kind 不一致")
        return self

    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for step in self.steps:
            counts[step.type.value] = counts.get(step.type.value, 0) + 1
        return counts
