"""Two Sum 教学规划：只读 M1 产物，不重新执行用户代码。

规划器负责三件事：
1. 把真实 AnimationStep 绑定为教学步骤，并计算状态摘要；
2. 生成固定的五段式教学计划与逐步骤旁白；
3. 分别生成 overview / step_by_step 两条时间轴，二者共享同一份 Trace。
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

from ..protocol.events import AnimationStep, Trace
from ..protocol.execution import ExecutionTrace, SemanticKind
from ..protocol.m2 import (
    ComplexityBreakdown,
    M2SectionKind,
    NarrationCue,
    NarrationUnit,
    ObservedComplexity,
    RenderPlan,
    Section,
    SectionTimeline,
    StepBinding,
    StepTiming,
    TeachingPlan,
    VideoTimeline,
)
from ..protocol.teaching import SubtitleCue
from ..tts import estimate_duration


class TeachingPlanError(RuntimeError):
    pass


def _json_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def trace_digest(trace: Trace) -> str:
    return _json_digest(trace.model_dump(mode="json"))


def step_state_digest(step: AnimationStep) -> str:
    return _json_digest(
        {
            "type": step.type.value,
            "code_line": step.code_line,
            "targets": step.targets,
            "state_after": step.state_after.model_dump(mode="json"),
        }
    )


def load_m1_pair(execution_path: str | Path, animation_path: str | Path) -> tuple[ExecutionTrace, Trace]:
    execution_path = Path(execution_path)
    animation_path = Path(animation_path)
    try:
        execution = ExecutionTrace.model_validate_json(execution_path.read_text(encoding="utf-8"))
        trace = Trace.model_validate_json(animation_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise TeachingPlanError(f"M1 产物无法解析：{exc}") from exc
    if trace.metadata.execution_trace_id != execution.trace_id:
        raise TeachingPlanError("animation_events 与 execution 不是同一次真实执行")
    if not execution.validation.trace_verified:
        raise TeachingPlanError("ExecutionTrace 未通过 trace_verified，拒绝生成教学视频")
    if not trace.verified:
        raise TeachingPlanError("AnimationTrace 未通过 verify，拒绝生成教学视频")
    if not trace.steps:
        raise TeachingPlanError("AnimationTrace 没有步骤")
    return execution, trace


# ---------------------------------------------------------------------- 状态提取
def _var(state: Any, name: str) -> str | None:
    for item in state.variables:
        if item.name == name:
            return item.value
    return None


def _step_index(step: AnimationStep) -> int | None:
    value = step.state_after.array.pointers.get("i") if step.state_after.array else None
    if value is None and step.targets and isinstance(step.targets[0], int):
        value = step.targets[0]
    return int(value) if value is not None else None


def _entry_map(step: AnimationStep) -> dict[str, Any]:
    if not step.state_after.dict_state:
        return {}
    return {entry.key: entry.value for entry in step.state_after.dict_state.entries}


def _fmt(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _clean(text: str) -> str:
    return " ".join(str(text).replace("\n", " ").split())


# ---------------------------------------------------------------------- 复杂度
def _ast_features(source: str) -> tuple[int, int, int, int]:
    tree = ast.parse(source, filename="user_solution.py")
    loops = sum(isinstance(node, (ast.For, ast.While, ast.AsyncFor)) for node in ast.walk(tree))
    compares = sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare)
        and any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops)
    )
    subscripts = sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store)
    )
    returns = sum(isinstance(node, ast.Return) for node in ast.walk(tree))
    return loops, compares, subscripts, returns


def _observed(execution: ExecutionTrace, trace: Trace) -> ObservedComplexity:
    kinds = [op.kind for op in execution.semantic_ops]
    lookups = kinds.count(SemanticKind.HASH_LOOKUP)
    hits = sum(1 for op in execution.semantic_ops if op.kind == SemanticKind.HASH_LOOKUP and op.data.get("hit"))
    inserts = kinds.count(SemanticKind.HASH_INSERT)
    visited = kinds.count(SemanticKind.VISIT)
    peak_seen = 0
    for step in trace.steps:
        if step.state_after.dict_state:
            peak_seen = max(peak_seen, len(step.state_after.dict_state.entries))
    nums = trace.metadata.input.get("nums", [])
    summary = (
        f"n={len(nums)}；访问 {visited} 次；查找 {lookups} 次"
        f"（{hits} 次命中 / {lookups - hits} 次未命中）；插入 {inserts} 次；"
        f"seen 峰值 {peak_seen} 项；真实事件 {len(execution.events)} 个；"
        f"执行耗时 {execution.result.duration_ms:.3f} ms。"
    )
    return ObservedComplexity(
        n=len(nums),
        visited=visited,
        lookups=lookups,
        hits=hits,
        misses=max(lookups - hits, 0),
        inserts=inserts,
        peak_seen=peak_seen,
        trace_events=len(execution.events),
        semantic_ops=len(execution.semantic_ops),
        duration_ms=round(execution.result.duration_ms, 3),
        output=execution.result.actual_output,
        summary=summary,
    )


def build_complexity(execution: ExecutionTrace, trace: Trace) -> ComplexityBreakdown:
    loops, compares, subscripts, returns = _ast_features(execution.program.source)
    theory_time = "O(n) 平均 / O(n²) 最坏" if loops == 1 else "按源码循环结构估算"
    code_time = "O(n) 平均 / O(n²) 最坏" if loops == 1 else "需人工复核"
    features = [
        f"源码 {len(execution.program.source.splitlines())} 行，{loops} 个循环",
        f"{compares} 处哈希成员查找（`in`），{subscripts} 处哈希下标写入",
        f"{returns} 个 return，存在提前返回",
    ]
    return ComplexityBreakdown(
        theory_time=theory_time,
        theory_space="O(n)",
        theory_note=(
            "哈希表在平均情况下查找/插入为 O(1)，一次线性遍历的总时间为 O(n)；"
            "额外保存最多 n 个已见元素，空间 O(n)。最坏情况大量哈希冲突时，"
            "单次查找可退化到 O(n)，总时间 O(n²)。"
        ),
        code_time=code_time,
        code_space="O(n)",
        code_note="对用户 AC 代码的静态结构估算；不是对某台机器运行时长的外推。",
        code_features=features,
        observed=_observed(execution, trace),
    )


# ---------------------------------------------------------------------- 旁白
def _step_narration(step: AnimationStep, target: Any, total_steps: int) -> str:
    if step.type.value == "init":
        return "先初始化一个空哈希表 seen，准备记录已经出现过的数字和下标。"
    if step.type.value == "visit":
        index = _step_index(step)
        x = _var(step.state_after, "x")
        if x is not None:
            return f"访问下标 {index}，当前元素是 {x}。下一步计算目标值 {target} 与它的补数。"
        return f"访问下标 {index}，读取当前元素。"
    if step.type.value == "compare":
        need = _var(step.state_after, "need")
        status = step.state_after.dict_state.lookup_status if step.state_after.dict_state else None
        if status == "hit":
            entries = _entry_map(step)
            key = step.state_after.dict_state.lookup_key if step.state_after.dict_state else None
            return f"补数是 {need}，在 seen 中命中，对应下标是 {entries.get(str(key), '—')}。可以返回答案了。"
        if status == "miss":
            return f"计算补数 {need}，在 seen 中查找：未命中。说明还没有遇到能配对的数字。"
        return f"在 seen 中查找补数 {need}。"
    if step.type.value == "update":
        entries = _entry_map(step)
        if entries:
            key, value = next(iter(entries.items()))
            return f"把当前元素 {key} 和下标 {value} 写入 seen，后续可用它直接查到补数。"
        return "把当前元素写入 seen。"
    if step.type.value == "found":
        result = step.meta.get("return", step.targets)
        return f"命中补数，返回两个下标 {_fmt(result)}；它们的和等于目标值。"
    if step.type.value == "complete":
        return "算法执行完成。"
    return _clean(step.narration or step.description)


def build_sections(execution: ExecutionTrace, trace: Trace) -> list[Section]:
    steps = trace.steps
    all_ids = [step.step_id for step in steps]
    target = trace.metadata.input.get("target")
    nums = trace.metadata.input.get("nums", [])
    n = len(nums)
    result = trace.result.get("return", trace.metadata.expected_output.get("return"))
    insert_step = next(
        (step for step in steps if step.type.value == "update" and step.state_after.dict_state and step.state_after.dict_state.entries),
        None,
    )
    hit_step = next(
        (
            step
            for step in steps
            if step.state_after.dict_state and step.state_after.dict_state.lookup_status == "hit"
        ),
        None,
    )
    if insert_step is not None and hit_step is not None:
        first_entry = insert_step.state_after.dict_state.entries[0]
        hit_index = hit_step.state_after.array.pointers.get("i") if hit_step.state_after.array else None
        hit_x = nums[int(hit_index)] if hit_index is not None and 0 <= int(hit_index) < len(nums) else None
        replay_text = (
            f"最后快速回放：seen 从空开始，记录 {first_entry.key} 对应下标 {first_entry.value}；"
            f"访问元素 {hit_x if hit_x is not None else '—'} 时补数 "
            f"{_var(hit_step.state_after, 'need') or hit_step.state_after.dict_state.lookup_key} 命中，"
            f"返回 {_fmt(result)}。"
        )
    else:
        replay_text = f"最后快速回放整个算法过程，结果 {_fmt(result)}。"
    demo_text = (
        f"完整演示 Two Sum：数组有 {n} 个元素，目标是 {target}。"
        "遍历数组，用哈希表记录已见数字和下标；补数命中就返回。"
    )
    idea_text = (
        "核心是空间换时间：对当前数字 x，用哈希表平均 O(1) 查找 target 减 x；"
        "未命中就记录 x 和下标，因此不用反复扫描数组。"
    )
    step_units = [
        NarrationUnit(
            unit_id=f"step_{step.step_id:02d}",
            step_id=step.step_id,
            text=_step_narration(step, target, len(steps)),
        )
        for step in steps
    ]
    complexity = build_complexity(execution, trace)
    observed = complexity.observed.summary
    sections = [
        Section(
            section_id="complete_demo",
            kind=M2SectionKind.COMPLETE_DEMO,
            title="01 · 完整演示",
            narration=demo_text,
            subtitle="先完整看一遍算法，不逐行讲解",
            step_ids=all_ids,
            speed=1.8,
            narration_units=[NarrationUnit(unit_id="complete_demo", text=demo_text)],
        ),
        Section(
            section_id="idea",
            kind=M2SectionKind.IDEA,
            title="02 · 算法思想",
            narration=idea_text,
            subtitle="哈希表记录已见数字，补数查找平均 O(1)",
            speed=1.0,
            narration_units=[NarrationUnit(unit_id="idea", text=idea_text)],
        ),
        Section(
            section_id="stepwise",
            kind=M2SectionKind.STEPWISE,
            title="03 · 逐步讲解",
            narration="逐步讲解：逐行结合真实代码执行，观察变量、查找、插入和返回。",
            subtitle="按真实执行步骤逐行讲解",
            step_ids=all_ids,
            speed=1.0,
            narration_units=step_units,
        ),
        Section(
            section_id="complexity",
            kind=M2SectionKind.COMPLEXITY,
            title="04 · 复杂度分析",
            narration=(
                "分别看理论复杂度、用户 AC 代码的静态估算，以及当前样例的真实执行统计。"
            ),
            subtitle="理论 / 用户代码 / 本次实测",
            speed=1.0,
            narration_units=[
                NarrationUnit(
                    unit_id="complexity_theory",
                    text=(
                        "理论复杂度：一次遍历，哈希表平均 O(1)，平均时间 O(n)，"
                        "额外空间 O(n)；大量冲突时最坏 O(n²)。"
                    ),
                ),
                NarrationUnit(
                    unit_id="complexity_code",
                    text=(
                        "用户代码估算：一个循环，一次成员查找、一次下标写入，"
                        "平均 O(n)，最坏 O(n²)，空间 O(n)。"
                    ),
                ),
                NarrationUnit(
                    unit_id="complexity_observed",
                    text=f"本次实测：{observed}单样例不能证明复杂度。",
                ),
            ],
        ),
        Section(
            section_id="replay",
            kind=M2SectionKind.REPLAY,
            title="05 · 完整回放",
            narration=replay_text,
            subtitle="快速回放整个算法过程",
            step_ids=all_ids,
            speed=2.2,
            narration_units=[NarrationUnit(unit_id="replay", text=replay_text)],
        ),
    ]
    return sections


def build_plan(execution: ExecutionTrace, trace: Trace, *, execution_file: Path, animation_file: Path) -> TeachingPlan:
    if trace.metadata.execution_trace_id != execution.trace_id:
        raise TeachingPlanError("trace_id 不一致")
    all_ids = [step.step_id for step in trace.steps]
    sections = build_sections(execution, trace)
    complexity = build_complexity(execution, trace)
    observed_text = f"本次实测：{complexity.observed.summary}单样例不能证明复杂度。"
    sections[3] = sections[3].model_copy(
        update={
            "narration_units": [
                sections[3].narration_units[0],
                sections[3].narration_units[1],
                sections[3].narration_units[2].model_copy(update={"text": observed_text}),
            ]
        }
    )
    bindings = [
        StepBinding(
            step_id=step.step_id,
            step_type=step.type.value,
            code_line=step.code_line,
            state_sha256=step_state_digest(step),
            description=step.description,
        )
        for step in trace.steps
    ]
    plan = TeachingPlan(
        title=trace.metadata.title,
        source_style=execution.program.style.value,
        entry_point=execution.program.entry_point,
        trace_id=execution.trace_id,
        execution_file=str(execution_file),
        animation_file=str(animation_file),
        execution_sha256=file_sha256(execution_file),
        animation_sha256=file_sha256(animation_file),
        code=execution.program.source,
        code_language=execution.program.language,
        input=execution.input,
        expected_output=execution.expected_output,
        actual_output=execution.result.actual_output,
        verified=execution.validation.output_verified
        and execution.validation.structure_verified
        and execution.validation.trace_verified,
        steps=bindings,
        idea=list(trace.metadata.idea),
        summary=list(trace.metadata.summary),
        complexity=complexity,
        sections=sections,
        videos=[],
    )
    if [binding.step_id for binding in bindings] != all_ids:
        raise TeachingPlanError("步骤绑定不连续")
    return plan


# ---------------------------------------------------------------------- 时间轴
def _audio_duration(unit: NarrationUnit) -> float:
    return unit.audio_duration if unit.audio_duration > 0 else estimate_duration(unit.text)


def attach_audio(plan: TeachingPlan, audio: dict[str, tuple[float, str | None]]) -> TeachingPlan:
    sections: list[Section] = []
    for section in plan.sections:
        units = []
        for unit in section.narration_units:
            duration, path = audio.get(unit.unit_id, (0.0, None))
            if duration <= 0:
                duration = estimate_duration(unit.text)
            units.append(unit.model_copy(update={"audio_duration": round(duration, 3), "audio_path": path}))
        sections.append(section.model_copy(update={"narration_units": units}))
    return plan.model_copy(update={"sections": sections})


def _cue(unit: NarrationUnit, start: float, duration: float | None = None) -> NarrationCue:
    actual = duration if duration is not None else _audio_duration(unit)
    return NarrationCue(
        unit_id=unit.unit_id,
        step_id=unit.step_id,
        text=unit.text,
        start=round(start, 4),
        duration=round(max(0.5, actual), 4),
        audio_path=unit.audio_path,
    )


def _section_timeline(
    section: Section,
    start: float,
    *,
    variant: str,
    trace: Trace,
) -> SectionTimeline:
    steps = {step.step_id: step for step in trace.steps}
    units = section.narration_units
    audio_total = sum(_audio_duration(unit) for unit in units) or 1.0
    if section.kind in {M2SectionKind.COMPLETE_DEMO, M2SectionKind.REPLAY}:
        per = 0.72 if section.kind == M2SectionKind.COMPLETE_DEMO else 0.42
        lead = 0.7 if section.kind == M2SectionKind.COMPLETE_DEMO else 0.35
        tail = 0.4
        count = max(len(section.step_ids), 1)
        duration = max(lead + per * count + tail, audio_total + 1.1)
        step_window = max(duration - lead - tail, 0.4)
        step_per = step_window / count
        timings = [
            StepTiming(
                step_id=step_id,
                start=round(start + lead + index * step_per, 4),
                duration=round(step_per, 4),
                speed=section.speed,
            )
            for index, step_id in enumerate(section.step_ids)
            if step_id in steps
        ]
        cue_unit = units[0] if units else NarrationUnit(unit_id=f"{section.section_id}_none", text=section.narration)
        cues = [_cue(cue_unit, start + 0.15, max(audio_total, min(duration - 0.2, 2.0)))]
        # 完整演示/回放只有一个旁白块，字幕覆盖整个演示段，避免每步刷屏。
        cues = [
            NarrationCue(
                unit_id=cue_unit.unit_id,
                step_id=None,
                text=cue_unit.text,
                start=round(start + 0.1, 4),
                duration=round(max(1.0, duration - 0.2), 4),
                audio_path=cue_unit.audio_path,
            )
        ]
        return SectionTimeline(
            section_id=section.section_id,
            kind=section.kind,
            title=section.title,
            start=round(start, 4),
            duration=round(duration, 4),
            step_ids=section.step_ids,
            speed=section.speed,
            narration_units=cues,
            step_timings=timings,
        )

    if section.kind == M2SectionKind.IDEA:
        duration = max(4.5, audio_total + 1.15)
        cue_unit = units[0]
        return SectionTimeline(
            section_id=section.section_id,
            kind=section.kind,
            title=section.title,
            start=round(start, 4),
            duration=round(duration, 4),
            step_ids=[],
            speed=section.speed,
            narration_units=[_cue(cue_unit, start + 0.1, duration - 0.2)],
            step_timings=[],
        )

    if section.kind == M2SectionKind.COMPLEXITY:
        cue_start = start
        cues: list[NarrationCue] = []
        for unit in units:
            audio = _audio_duration(unit)
            length = max(3.2, audio + 0.55)
            cues.append(_cue(unit, cue_start + 0.1, length - 0.15))
            cue_start += length
        duration = max(10.0, cue_start - start + 0.25)
        return SectionTimeline(
            section_id=section.section_id,
            kind=section.kind,
            title=section.title,
            start=round(start, 4),
            duration=round(duration, 4),
            step_ids=[],
            speed=section.speed,
            narration_units=cues,
            step_timings=[],
        )

    # STEPWISE
    lead = 0.45
    tail = 0.35
    cursor = start + lead
    timings: list[StepTiming] = []
    cues: list[NarrationCue] = []
    by_step = {unit.step_id: unit for unit in units if unit.step_id is not None}
    for step_id in section.step_ids:
        if step_id not in steps:
            continue
        unit = by_step.get(step_id)
        audio = _audio_duration(unit) if unit else 1.2
        length = max(1.35, audio + 0.45)
        timings.append(
            StepTiming(
                step_id=step_id,
                start=round(cursor, 4),
                duration=round(length, 4),
                speed=section.speed,
            )
        )
        if unit is not None:
            cues.append(_cue(unit, cursor + 0.05, max(0.8, min(audio, length - 0.1))))
        cursor += length
    duration = max(cursor - start + tail, 1.8)
    return SectionTimeline(
        section_id=section.section_id,
        kind=section.kind,
        title=section.title,
        start=round(start, 4),
        duration=round(duration, 4),
        step_ids=section.step_ids,
        speed=section.speed,
        narration_units=cues,
        step_timings=timings,
    )


def build_timelines(plan: TeachingPlan, trace: Trace) -> TeachingPlan:
    by_id = {section.section_id: section for section in plan.sections}
    specs = {
        "overview": ["complete_demo", "idea", "complexity", "replay"],
        "step_by_step": ["complete_demo", "idea", "stepwise", "complexity", "replay"],
    }
    videos: list[VideoTimeline] = []
    for variant, ids in specs.items():
        sections: list[SectionTimeline] = []
        cursor = 0.0
        for section_id in ids:
            section = by_id[section_id]
            timeline = _section_timeline(section, cursor, variant=variant, trace=trace)
            sections.append(timeline)
            cursor = timeline.start + timeline.duration
        total = round(cursor, 4)
        subtitles = [
            SubtitleCue(start=cue.start, end=round(cue.start + cue.duration, 4), text=cue.text)
            for section in sections
            for cue in section.narration_units
        ]
        videos.append(
            VideoTimeline(
                variant=variant,
                output_name=f"{variant}.mp4",
                total_duration=total,
                sections=sections,
                subtitles=subtitles,
            )
        )
    return plan.model_copy(update={"videos": videos})


def render_plan(plan: TeachingPlan, trace: Trace, variant: str) -> RenderPlan:
    video = next((item for item in plan.videos if item.variant == variant), None)
    if video is None:
        raise TeachingPlanError(f"教学计划没有视频形态 {variant}")
    return RenderPlan(trace=trace, teaching=plan, video=video)


def verify_plan(plan: TeachingPlan, trace: Trace) -> list[str]:
    errors: list[str] = []
    if plan.trace_id != trace.metadata.execution_trace_id:
        errors.append("trace_id 不一致")
    if len(plan.steps) != len(trace.steps):
        errors.append("step 绑定数量不一致")
    actual_digests = {step.step_id: step_state_digest(step) for step in trace.steps}
    for binding in plan.steps:
        if actual_digests.get(binding.step_id) != binding.state_sha256:
            errors.append(f"step {binding.step_id} 状态摘要不一致")
        step = next((item for item in trace.steps if item.step_id == binding.step_id), None)
        if step and step.code_line != binding.code_line:
            errors.append(f"step {binding.step_id} 代码行不一致")
    if {video.variant for video in plan.videos} != {"overview", "step_by_step"}:
        errors.append("缺少 overview 或 step_by_step 视频时间轴")
    expected_ids = {step.step_id for step in trace.steps}
    for video in plan.videos:
        ids = {timing.step_id for section in video.sections for timing in section.step_timings}
        if ids != expected_ids:
            errors.append(f"{video.variant} 没有覆盖全部真实步骤")
        for section in video.sections:
            if section.step_timings and section.step_timings[-1].start + section.step_timings[-1].duration > section.start + section.duration + 0.01:
                errors.append(f"{video.variant}/{section.section_id} 步骤超出章节")
        if video.variant == "overview" and any(s.kind == M2SectionKind.STEPWISE for s in video.sections):
            errors.append("overview 不应包含逐行讲解章节")
        if video.variant == "step_by_step" and not any(s.kind == M2SectionKind.STEPWISE for s in video.sections):
            errors.append("step_by_step 缺少逐行讲解章节")
    complete = next((s for s in plan.sections if s.kind == M2SectionKind.STEPWISE), None)
    if complete is None or complete.step_ids != [step.step_id for step in trace.steps]:
        errors.append("逐步讲解没有按顺序引用全部真实步骤")
    return errors
