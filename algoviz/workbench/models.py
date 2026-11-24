"""M4 workbench protocol: persistent projects, runs and classroom payloads."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..protocol.cases import CaseSource


class M4Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProblemPayload(M4Model):
    title: str = Field(default="Two Sum", min_length=1, max_length=200)
    description: str = ""
    idea: str = ""
    source: str = ""
    language: Literal["python"] = "python"
    algorithm: str = Field(default="two_sum", min_length=1)
    source_style: Literal["function", "leetcode_class"] = "function"


class TestCasePayload(M4Model):
    case_id: str = Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")
    name: str = Field(min_length=1, max_length=120)
    input_data: dict[str, Any] = Field(default_factory=dict)
    expected_output: Any = None
    source: CaseSource = CaseSource.USER
    description: str = ""


class ProjectPayload(M4Model):
    name: str = Field(default="未命名算法项目", min_length=1, max_length=120)
    problem: ProblemPayload = Field(default_factory=ProblemPayload)
    cases: list[TestCasePayload] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_cases(self) -> "ProjectPayload":
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("测试用例 case_id 必须唯一")
        return self


class ProjectSummary(M4Model):
    project_id: str
    name: str
    title: str
    algorithm: str
    updated_at: str
    case_count: int
    last_run_status: str | None = None


class RunRecord(M4Model):
    run_id: str
    project_id: str
    status: Literal["queued", "running", "completed", "failed"]
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    project_name: str = ""
    problem_title: str = ""


class CaseRunRecord(M4Model):
    case_id: str
    name: str
    source: CaseSource
    status: str
    expected_output: Any = None
    actual_output: Any = None
    error: str | None = None
    step_count: int = 0
    execution_trace_id: str | None = None
    animation_trace_id: str | None = None


class ClassroomEnvelope(M4Model):
    run: RunRecord
    cases: list[CaseRunRecord] = Field(default_factory=list)
    classroom: dict[str, Any]
