"""M3-5 多用例协议：TestCaseSpec / CaseRun / CaseRunStore 的模型层。"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field, model_validator

from .events import StrictModel, Trace
from .execution import ExecutionTrace


class CaseSource(str, Enum):
    USER = "user"
    AI_GENERATED = "ai_generated"


class CaseRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"


class TestCaseSpec(StrictModel):
    """用户/AI 提供的测试用例描述，不是执行结果。"""

    __test__ = False  # 防止 pytest 收集这个 Pydantic 模型

    case_id: str = Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")
    name: str = Field(min_length=1)
    input_data: dict[str, Any]
    expected_output: Any = None
    source: CaseSource = CaseSource.USER
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseRun(StrictModel):
    """某个 TestCaseSpec 的一次真实执行实例。

    ExecutionTrace 是执行事实；AnimationTrace 是由它转换得到的视觉步骤。
    两者都不能与其他 case 共享可变对象。
    """

    run_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    status: CaseRunStatus = CaseRunStatus.PENDING
    execution_trace: ExecutionTrace | None = None
    animation_trace: Trace | None = None
    actual_output: Any = None
    expected_output: Any = None
    error: str | None = None
    execution_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_success(self) -> "CaseRun":
        if self.status == CaseRunStatus.SUCCESS:
            if self.execution_trace is None or self.animation_trace is None:
                raise ValueError("SUCCESS CaseRun 必须同时拥有 ExecutionTrace 和 AnimationTrace")
            if not self.animation_trace.steps:
                raise ValueError("SUCCESS CaseRun 的 AnimationTrace 不能为空")
        return self
