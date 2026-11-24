"""时间轴：把教学脚本、TTS 时长与逐步事件合成可渲染的 ScenePlan。"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .protocol.events import AnimationStep, StepType, Trace
from .protocol.teaching import (
    RenderOptions,
    ScenePlan,
    SegmentKind,
    StepTiming,
    SubtitleCue,
    TeachingScript,
)

log = logging.getLogger("algoviz.timeline")

MIN_DURATION = {
    SegmentKind.INTRO: 3.2,
    SegmentKind.IDEA: 3.8,
    SegmentKind.CODE: 3.6,
    SegmentKind.COMPLEXITY: 4.0,
    SegmentKind.SUMMARY: 3.4,
}
AUDIO_PAD = 0.35
EXEC_BASE = 1.4
EXEC_PER_STEP = 0.65
EXEC_MIN_STEP = 0.28

_SLOW_TYPES = {StepType.NOTE, StepType.MARK, StepType.INIT, StepType.COMPLETE}
_FAST_TYPES = {
    StepType.COMPARE,
    StepType.SWAP,
    StepType.VISIT,
    StepType.UPDATE,
    StepType.RELAX,
    StepType.FOUND,
}


@dataclass
class TimelineResult:
    plan: ScenePlan
    warnings: list[str] = field(default_factory=list)


def _segment_min_duration(segment) -> float:
    if segment.kind == SegmentKind.EXECUTION and segment.step_start is not None and segment.step_end is not None:
        step_count = segment.step_end - segment.step_start + 1
        return EXEC_BASE + EXEC_PER_STEP * step_count
    return MIN_DURATION.get(segment.kind, 3.0)


def _step_weight(step: AnimationStep) -> float:
    if step.type in _SLOW_TYPES:
        return 0.8
    if step.type in _FAST_TYPES:
        return 1.1
    return 1.0


def _distribute_steps(segment, duration: float) -> list[StepTiming]:
    if segment.step_start is None or segment.step_end is None:
        return []
    steps = list(range(segment.step_start, segment.step_end + 1))
    if not steps:
        return []
    lead = min(0.8, max(0.25, duration * 0.2))
    available = max(0.4, duration - lead - 0.08)
    # 这里拿不到步骤对象，按步数平均分配（步骤类型权重在场景内不影响总时长）
    per = max(EXEC_MIN_STEP, available / len(steps))
    if per * len(steps) > available:
        per = available / len(steps)
    timings: list[StepTiming] = []
    cursor = lead
    for step_id in steps:
        timings.append(StepTiming(step_id=step_id, start=cursor, duration=per))
        cursor += per
    return timings


def build_scene_plan(
    trace: Trace,
    script: TeachingScript,
    options: RenderOptions,
) -> TimelineResult:
    warnings: list[str] = []
    steps_by_id = {step.step_id: step for step in trace.steps}
    cursor = 0.0
    step_timings: list[StepTiming] = []
    subtitles: list[SubtitleCue] = []
    for segment in script.segments:
        audio = max(0.0, segment.audio_duration)
        duration = max(audio + AUDIO_PAD, _segment_min_duration(segment))
        if segment.kind == SegmentKind.EXECUTION and segment.step_start is not None:
            step_count = segment.step_end - segment.step_start + 1
            slow = sum(
                1.0
                for sid in range(segment.step_start, segment.step_end + 1)
                if steps_by_id.get(sid) and _step_weight(steps_by_id[sid]) > 1.0
            )
            need = EXEC_BASE + EXEC_PER_STEP * max(step_count - slow, 0) + 0.9 * slow
            duration = max(duration, need)
        segment.start = round(cursor, 4)
        segment.duration = round(duration, 4)
        cursor += duration
        for timing in _distribute_steps(segment, duration):
            step_timings.append(timing)
        text = (segment.subtitle or segment.narration).strip()
        if text:
            cue_end = segment.start + max(0.6, duration - 0.05)
            subtitles.append(
                SubtitleCue(start=round(segment.start, 3), end=round(cue_end, 3), text=text)
            )
    total = round(cursor, 4)
    if total > options.max_seconds:
        warnings.append(
            f"视频计划时长 {total:.1f}s 超过上限 {options.max_seconds:.0f}s；已保留完整讲解，可在任务选项里缩短输入或减少步骤"
        )
    script.total_duration = total
    resolution = list(options.resolved_resolution())
    plan = ScenePlan(
        trace=trace,
        script=script,
        step_timings=step_timings,
        subtitles=subtitles,
        total_duration=total,
        theme=options.theme,
        resolution=resolution,
        fps=options.fps,
    )
    return TimelineResult(plan=plan, warnings=warnings)


def wrap_subtitle(text: str, width: int = 24, max_lines: int = 2) -> str:
    """按显示宽度给字幕插入换行（中文按 2、英文按 1 计）。"""
    text = text.strip()
    if not text:
        return ""
    lines: list[str] = []
    current = ""
    current_width = 0
    consumed = 0
    for char in text:
        char_width = 2 if ord(char) > 127 else 1
        if current_width + char_width > width * 2 and current:
            lines.append(current)
            consumed += len(current)
            current = ""
            current_width = 0
            if len(lines) >= max_lines:
                break
        current += char
        current_width += char_width
    if current and len(lines) < max_lines:
        lines.append(current)
        consumed += len(current)
    remaining = text[consumed:]
    if remaining and lines:
        lines[-1] = lines[-1].rstrip() + "…"
    return "\n".join(lines)
