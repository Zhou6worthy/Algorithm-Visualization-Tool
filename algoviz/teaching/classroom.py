"""课堂演示数据装配层：CaseRun + VisualPlan + StepHint -> 离线 HTML deck。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from ..protocol.cases import CaseRun, CaseRunStatus, CaseSource, TestCaseSpec
from ..protocol.events import StrictModel, Trace
from ..protocol.hints import StepHint
from ..protocol.visual import VisualPlan
from .step_hints import build_two_sum_hints
from .two_sum_profile import TwoSumVisualProfile


class ClassroomVariable(StrictModel):
    label: str
    value: str
    changed: bool = False


class ClassroomStepView(StrictModel):
    step_id: int = Field(ge=0)
    variables: list[ClassroomVariable] = Field(default_factory=list)


class ClassroomCase(StrictModel):
    case_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    source: CaseSource = CaseSource.USER
    status: CaseRunStatus = CaseRunStatus.PENDING
    input_data: dict[str, Any] = Field(default_factory=dict)
    expected_output: Any = None
    actual_output: Any = None
    error: str | None = None
    trace: Trace | None = None
    hints: list[StepHint] = Field(default_factory=list)
    step_views: list[ClassroomStepView] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_views(self) -> "ClassroomCase":
        if self.trace is None:
            if self.hints or self.step_views:
                raise ValueError("没有 AnimationTrace 的 case 不应携带提示或步骤视图")
            return self
        step_ids = [step.step_id for step in self.trace.steps]
        view_ids = [view.step_id for view in self.step_views]
        if view_ids != step_ids:
            raise ValueError("step_views 必须与 AnimationTrace 步骤一一对应")
        for hint in self.hints:
            if hint.related_step_id not in step_ids:
                raise ValueError("StepHint 引用了不存在的 step_id")
        return self


class ClassroomDeck(StrictModel):
    schema_version: Literal["3.8"] = "3.8"
    title: str = "Two Sum · 哈希表"
    algorithm: str = "two_sum"
    code: str
    code_language: str = "python"
    visual_plan: VisualPlan
    cases: list[ClassroomCase] = Field(min_length=1)
    active_case_id: str
    default_step_duration: float = Field(default=1.2, gt=0.0)

    @model_validator(mode="after")
    def _check_cases(self) -> "ClassroomDeck":
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("ClassroomDeck.case_id 必须唯一")
        if self.active_case_id not in set(ids):
            raise ValueError("active_case_id 不在 cases 中")
        return self


def build_classroom_deck(
    cases: list[tuple[TestCaseSpec, CaseRun]],
    *,
    profile: Any | None = None,
    title: str | None = None,
    code: str | None = None,
) -> ClassroomDeck:
    """把一组已执行用例装配成课堂 deck；不执行算法、不修改任何 trace。

    ``profile`` 可以是完整的 AlgorithmProfile（提供 build_hints），也可以是
    历史调用中使用的 TwoSumVisualProfile；后者保留兼容回退。
    """
    if not cases:
        raise ValueError("至少需要一个用例")
    profile = profile or TwoSumVisualProfile()
    if hasattr(profile, "build_hints"):
        hint_builder = profile.build_hints
    elif isinstance(profile, TwoSumVisualProfile):
        hint_builder = build_two_sum_hints
    else:
        raise ValueError("ClassroomDeck Profile 必须提供 build_hints()，或使用 TwoSumVisualProfile")
    deck_cases: list[ClassroomCase] = []
    resolved_code = code
    resolved_title = title
    resolved_algorithm = str(getattr(profile, "key", None) or getattr(profile, "algorithm", None) or "two_sum")
    for spec, run in cases:
        trace = run.animation_trace
        if resolved_code is None:
            resolved_code = trace.metadata.code if trace is not None else ""
        if resolved_title is None and trace is not None:
            resolved_title = trace.metadata.title
        hints: list[StepHint] = []
        views: list[ClassroomStepView] = []
        if trace is not None:
            hints = hint_builder(trace)
            for step in trace.steps:
                rows = profile.project_variables(step.state_after, step)
                views.append(
                    ClassroomStepView(
                        step_id=step.step_id,
                        variables=[
                            ClassroomVariable(label=row.label, value=row.value, changed=row.changed)
                            for row in rows
                        ],
                    )
                )
        deck_cases.append(
            ClassroomCase(
                case_id=spec.case_id,
                run_id=run.run_id,
                name=spec.name,
                source=spec.source,
                status=run.status,
                input_data=dict(spec.input_data),
                expected_output=spec.expected_output,
                actual_output=run.actual_output,
                error=run.error,
                trace=trace,
                hints=hints,
                step_views=views,
            )
        )
    active = next((case.case_id for case in deck_cases if case.trace is not None), deck_cases[0].case_id)
    return ClassroomDeck(
        title=resolved_title or "Two Sum · 哈希表",
        algorithm=resolved_algorithm,
        code=resolved_code or "",
        visual_plan=profile.build_visual_plan(),
        cases=deck_cases,
        active_case_id=active,
    )
