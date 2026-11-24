"""M2 教学可视化协议：五段式 TeachingPlan 与两条视频时间轴。

M2 不修改 M1 的 ExecutionTrace/ExecutionEvent，也不修改旧 Animation Trace。
本模块只增加“如何教学、如何分组、如何同步”的上一层描述，所有算法事实仍然
来自 M1 的 execution.json / animation_events.json。
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import Field, model_validator

from .events import StrictModel, Trace
from .teaching import SubtitleCue


class M2SectionKind(str, Enum):
    COMPLETE_DEMO = "complete_demo"
    IDEA = "idea"
    STEPWISE = "stepwise"
    COMPLEXITY = "complexity"
    REPLAY = "replay"


class StepBinding(StrictModel):
    """教学计划与真实动画步骤之间的不可变绑定。"""

    step_id: int = Field(ge=0)
    step_type: str
    code_line: int | None = Field(default=None, ge=1)
    state_sha256: str
    description: str = ""


class NarrationUnit(StrictModel):
    """一段可独立合成、可独立对齐字幕的旁白。"""

    unit_id: str
    text: str
    step_id: int | None = Field(default=None, ge=0)
    audio_duration: float = Field(default=0.0, ge=0.0)
    audio_path: str | None = None


class Section(StrictModel):
    section_id: str
    kind: M2SectionKind
    title: str
    narration: str
    subtitle: str = ""
    step_ids: list[int] = Field(default_factory=list)
    speed: float = Field(default=1.0, gt=0.0)
    narration_units: list[NarrationUnit] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_steps(self) -> "Section":
        if len(set(self.step_ids)) != len(self.step_ids):
            raise ValueError("section.step_ids 不能重复")
        if self.kind in {M2SectionKind.COMPLETE_DEMO, M2SectionKind.STEPWISE, M2SectionKind.REPLAY}:
            if not self.step_ids:
                raise ValueError(f"{self.kind.value} 必须引用真实动画步骤")
        return self


class ObservedComplexity(StrictModel):
    n: int = Field(ge=0)
    visited: int = Field(ge=0)
    lookups: int = Field(ge=0)
    hits: int = Field(ge=0)
    misses: int = Field(ge=0)
    inserts: int = Field(ge=0)
    peak_seen: int = Field(ge=0)
    trace_events: int = Field(ge=0)
    semantic_ops: int = Field(ge=0)
    duration_ms: float = Field(ge=0.0)
    output: Any = None
    summary: str = ""


class ComplexityBreakdown(StrictModel):
    """严格分离：理论 / 用户 AC 代码估算 / 当前样例实测。"""

    theory_time: str
    theory_space: str
    theory_note: str
    code_time: str
    code_space: str
    code_note: str
    code_features: list[str] = Field(default_factory=list)
    observed: ObservedComplexity
    caveat: str = "单样例执行统计只描述本次运行，不能单独证明复杂度。"


class NarrationCue(StrictModel):
    unit_id: str
    step_id: int | None = Field(default=None, ge=0)
    text: str
    start: float = Field(ge=0.0)
    duration: float = Field(gt=0.0)
    audio_path: str | None = None


class StepTiming(StrictModel):
    step_id: int = Field(ge=0)
    start: float = Field(ge=0.0)
    duration: float = Field(gt=0.0)
    speed: float = Field(default=1.0, gt=0.0)


class SectionTimeline(StrictModel):
    section_id: str
    kind: M2SectionKind
    title: str
    start: float = Field(ge=0.0)
    duration: float = Field(gt=0.0)
    step_ids: list[int] = Field(default_factory=list)
    speed: float = Field(default=1.0, gt=0.0)
    narration_units: list[NarrationCue] = Field(default_factory=list)
    step_timings: list[StepTiming] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_timings(self) -> "SectionTimeline":
        current = self.start
        for timing in self.step_timings:
            # 时间轴写 JSON 时保留 4 位小数，允许 1ms 的舍入误差。
            if timing.start < current - 1e-3:
                raise ValueError("section 内 step_timings 必须按时间递增")
            current = max(current, timing.start + timing.duration)
        if current > self.start + self.duration + 1e-3:
            raise ValueError("step_timings 超出 section 时间范围")
        return self


class VideoTimeline(StrictModel):
    variant: Literal["overview", "step_by_step"]
    output_name: str
    width: int = 1920
    height: int = 1080
    fps: int = 30
    total_duration: float = Field(gt=0.0)
    sections: list[SectionTimeline] = Field(min_length=1)
    subtitles: list[SubtitleCue] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_video(self) -> "VideoTimeline":
        if (self.width, self.height) != (1920, 1080):
            raise ValueError("M2 视频固定为 16:9 1920×1080")
        starts = [section.start for section in self.sections]
        if starts != sorted(starts):
            raise ValueError("sections 必须按开始时间排序")
        if self.total_duration < max(section.start + section.duration for section in self.sections) - 1e-6:
            raise ValueError("total_duration 小于 section 结束时间")
        if [cue.start for cue in self.subtitles] != sorted(cue.start for cue in self.subtitles):
            raise ValueError("subtitles 必须按时间排序")
        return self


class TeachingPlan(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    algorithm: str = "two_sum"
    title: str
    source_style: str
    entry_point: str
    trace_id: str
    execution_file: str
    animation_file: str
    execution_sha256: str
    animation_sha256: str
    code: str
    code_language: str = "python"
    input: dict[str, Any] = Field(default_factory=dict)
    expected_output: Any = None
    actual_output: Any = None
    verified: bool = False
    steps: list[StepBinding] = Field(default_factory=list)
    idea: list[str] = Field(default_factory=list)
    summary: list[str] = Field(default_factory=list)
    complexity: ComplexityBreakdown
    sections: list[Section] = Field(min_length=5, max_length=5)
    videos: list[VideoTimeline] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_five_sections(self) -> "TeachingPlan":
        kinds = [section.kind for section in self.sections]
        expected = [
            M2SectionKind.COMPLETE_DEMO,
            M2SectionKind.IDEA,
            M2SectionKind.STEPWISE,
            M2SectionKind.COMPLEXITY,
            M2SectionKind.REPLAY,
        ]
        if kinds != expected:
            raise ValueError("教学计划必须按固定顺序包含五段")
        return self


class RenderPlan(StrictModel):
    """交给 TwoSumScene 的完整渲染计划。"""

    trace: Trace
    teaching: TeachingPlan
    video: VideoTimeline

    @model_validator(mode="after")
    def _check_binding(self) -> "RenderPlan":
        if self.trace.metadata.execution_trace_id != self.teaching.trace_id:
            raise ValueError("RenderPlan 的 Trace 与 TeachingPlan 不是同一次真实执行")
        if self.video.variant not in {"overview", "step_by_step"}:
            raise ValueError("未知视频形态")
        return self
