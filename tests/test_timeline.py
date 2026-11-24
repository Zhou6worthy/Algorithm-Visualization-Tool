from algoviz.algorithms.registry import ALGORITHMS, execute_task
from algoviz.protocol.teaching import RenderOptions, TaskSpec
from algoviz.script import build_teaching_script
from algoviz.timeline import build_scene_plan, wrap_subtitle


def test_timeline_covers_all_execution_steps() -> None:
    options = RenderOptions(tts=False, steps_per_segment=3)
    trace = execute_task(TaskSpec(algorithm="merge_sort")).trace
    script, _ = build_teaching_script(trace, ALGORITHMS["merge_sort"], options, None)
    for segment in script.segments:
        segment.audio_duration = 2.0
    plan = build_scene_plan(trace, script, options)
    assert plan.plan.total_duration > 5
    step_ids = {timing.step_id for timing in plan.plan.step_timings}
    execution_ranges = [
        (seg.step_start, seg.step_end)
        for seg in script.segments
        if seg.kind.value == "execution"
    ]
    expected = {sid for start, end in execution_ranges for sid in range(start, end + 1)}
    assert step_ids == expected
    assert plan.plan.subtitles
    assert all(cue.end > cue.start for cue in plan.plan.subtitles)
    assert [cue.start for cue in plan.plan.subtitles] == sorted(cue.start for cue in plan.plan.subtitles)
    assert abs(sum(seg.duration for seg in script.segments) - plan.plan.total_duration) < 0.01


def test_subtitle_wrap() -> None:
    text = "比较 a[0]=5 与 a[1]=3；随后，交换两个元素；继续比较相邻元素，直到数组有序。" * 2
    wrapped = wrap_subtitle(text, width=12, max_lines=2)
    assert "\n" in wrapped
    assert len(wrapped.splitlines()) <= 2


def test_script_has_six_section_kinds() -> None:
    options = RenderOptions(tts=False)
    trace = execute_task(TaskSpec(algorithm="binary_search")).trace
    script, _ = build_teaching_script(trace, ALGORITHMS["binary_search"], options, None)
    kinds = {segment.kind.value for segment in script.segments}
    assert {"intro", "idea", "execution", "code", "complexity", "summary"} <= kinds
    assert script.title
    assert script.complexity_points
