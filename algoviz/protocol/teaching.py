"""教学脚本 / 时间轴 / 场景计划模型。"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field, model_validator

from .events import StrictModel, Trace


class SegmentKind(str, Enum):
    INTRO = "intro"
    IDEA = "idea"
    EXECUTION = "execution"
    CODE = "code"
    COMPLEXITY = "complexity"
    SUMMARY = "summary"


class TeachingSegment(StrictModel):
    id: str
    kind: SegmentKind
    title: str
    narration: str
    subtitle: str = ""
    start: float = Field(default=0.0, ge=0.0)
    duration: float = Field(default=0.0, ge=0.0)
    audio_duration: float = Field(default=0.0, ge=0.0)
    audio_path: str | None = None
    step_start: int | None = None
    step_end: int | None = None

    @model_validator(mode="after")
    def _check_range(self) -> "TeachingSegment":
        if self.step_start is not None and self.step_end is not None:
            if self.step_end < self.step_start:
                raise ValueError("step_end 不能小于 step_start")
        return self


class SubtitleCue(StrictModel):
    start: float = Field(ge=0.0)
    end: float = Field(gt=0.0)
    text: str


class StepTiming(StrictModel):
    step_id: int = Field(ge=0)
    start: float = Field(ge=0.0)
    duration: float = Field(gt=0.0)


class TeachingScript(StrictModel):
    schema_version: str = "1.0"
    title: str
    problem: str = ""
    idea: list[str] = Field(default_factory=list)
    complexity_points: list[str] = Field(default_factory=list)
    summary: list[str] = Field(default_factory=list)
    segments: list[TeachingSegment] = Field(default_factory=list)
    total_duration: float = Field(default=0.0, ge=0.0)
    ai_credit: str = ""


class ScenePlan(StrictModel):
    """交给 Manim 场景的完整渲染计划。"""

    schema_version: str = "1.0"
    trace: Trace
    script: TeachingScript
    step_timings: list[StepTiming] = Field(default_factory=list)
    subtitles: list[SubtitleCue] = Field(default_factory=list)
    total_duration: float = Field(gt=0.0)
    theme: str = "dark"
    resolution: list[int] = Field(default_factory=lambda: [1920, 1080])
    fps: int = 30


class RenderOptions(StrictModel):
    theme: str = "dark"
    resolution: tuple[int, int] = (1920, 1080)
    fps: int = 30
    tts: bool = True
    voice: str | None = None
    tts_provider: str | None = None
    burn_subtitles: bool = True
    max_seconds: float = 240.0
    steps_per_segment: int = 3
    render_quality: str = "high"
    keep_silent_video: bool = True

    def resolved_resolution(self) -> tuple[int, int]:
        if self.render_quality == "low":
            return (854, 480)
        if self.render_quality == "medium":
            return (1280, 720)
        return self.resolution


class TaskSpec(StrictModel):
    """一次视频生成任务的定义（AI 解析或用户显式给出）。"""

    task_id: str | None = None
    algorithm: str | None = None
    title: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    prompt: str | None = None
    source: str = "preset"
    options: RenderOptions = Field(default_factory=RenderOptions)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_input(self) -> "TaskSpec":
        if not self.algorithm and not self.prompt:
            raise ValueError("必须提供 algorithm 或 prompt")
        if self.algorithm:
            self.algorithm = self.algorithm.strip().lower().replace("-", "_").replace(" ", "_")
        return self


class BatchFile(StrictModel):
    batch_name: str = "batch"
    defaults: RenderOptions = Field(default_factory=RenderOptions)
    tasks: list[TaskSpec] = Field(min_length=1)
