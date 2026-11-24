from __future__ import annotations

import json
import re
from pathlib import Path

from algoviz.protocol.m2 import M2SectionKind
from algoviz.teaching.html_player import write_html_player
from algoviz.teaching.two_sum_planner import (
    attach_audio,
    build_plan,
    build_timelines,
    load_m1_pair,
    verify_plan,
)

ROOT = Path(__file__).resolve().parent.parent
M1 = ROOT / "output" / "m1"


def _plan(form: str = "two_sum_function"):
    directory = M1 / form
    execution, trace = load_m1_pair(directory / "execution.json", directory / "animation_events.json")
    plan = build_plan(
        execution,
        trace,
        execution_file=directory / "execution.json",
        animation_file=directory / "animation_events.json",
    )
    audio = {unit.unit_id: (0.25, None) for section in plan.sections for unit in section.narration_units}
    plan = build_timelines(attach_audio(plan, audio), trace)
    return execution, trace, plan


def test_plan_has_fixed_five_sections_and_shared_trace() -> None:
    _, trace, plan = _plan()
    assert [section.kind for section in plan.sections] == [
        M2SectionKind.COMPLETE_DEMO,
        M2SectionKind.IDEA,
        M2SectionKind.STEPWISE,
        M2SectionKind.COMPLEXITY,
        M2SectionKind.REPLAY,
    ]
    assert plan.trace_id == trace.metadata.execution_trace_id
    assert verify_plan(plan, trace) == []
    assert len(plan.steps) == len(trace.steps) == 8


def test_overview_and_stepwise_use_same_real_steps() -> None:
    _, trace, plan = _plan()
    expected = [step.step_id for step in trace.steps]
    videos = {video.variant: video for video in plan.videos}
    assert set(videos) == {"overview", "step_by_step"}
    assert [s.kind for s in videos["overview"].sections] == [
        M2SectionKind.COMPLETE_DEMO,
        M2SectionKind.IDEA,
        M2SectionKind.COMPLEXITY,
        M2SectionKind.REPLAY,
    ]
    assert [s.kind for s in videos["step_by_step"].sections] == [
        M2SectionKind.COMPLETE_DEMO,
        M2SectionKind.IDEA,
        M2SectionKind.STEPWISE,
        M2SectionKind.COMPLEXITY,
        M2SectionKind.REPLAY,
    ]
    for video in plan.videos:
        for section in video.sections:
            if section.kind in {M2SectionKind.COMPLETE_DEMO, M2SectionKind.STEPWISE, M2SectionKind.REPLAY}:
                assert section.step_ids == expected
    stepwise = next(s for s in videos["step_by_step"].sections if s.kind == M2SectionKind.STEPWISE)
    assert [timing.step_id for timing in stepwise.step_timings] == expected
    assert video_resolution(videos["overview"]) == (1920, 1080)
    assert video_resolution(videos["step_by_step"]) == (1920, 1080)


def video_resolution(video) -> tuple[int, int]:
    return (video.width, video.height)


def test_hash_states_and_code_lines_are_from_trace() -> None:
    _, trace, plan = _plan()
    steps = trace.steps
    first_lookup = steps[2].state_after.dict_state
    second_lookup = steps[5].state_after.dict_state
    assert first_lookup is not None and first_lookup.lookup_key == "7" and first_lookup.lookup_status == "miss"
    assert second_lookup is not None and second_lookup.lookup_key == "2" and second_lookup.lookup_status == "hit"
    assert [entry.key for entry in second_lookup.entries] == ["2"]
    assert [entry.value for entry in second_lookup.entries] == [0]
    assert steps[2].state_after.array.pointers == {"i": 0}
    assert steps[5].state_after.array.pointers == {"i": 1}
    assert steps[6].state_after.array.found_indices == [0, 1]
    # 命中后不执行第二次插入：seen 的峰值始终只有 1 项。
    assert max(len(step.state_after.dict_state.entries) for step in steps) == 1
    for binding in plan.steps:
        assert binding.code_line == steps[binding.step_id].code_line


def test_timelines_cover_sections_steps_and_subtitles() -> None:
    _, _, plan = _plan()
    for video in plan.videos:
        assert video.total_duration > 5
        for section in video.sections:
            assert section.duration > 0
            assert section.start >= 0
            assert section.start + section.duration <= video.total_duration + 1e-6
            for cue in section.narration_units:
                assert cue.start >= section.start - 1e-6
                assert cue.duration > 0
        starts = [cue.start for cue in video.subtitles]
        assert starts == sorted(starts)
        assert all(cue.end > cue.start for cue in video.subtitles)


def test_complexity_is_three_way_separated() -> None:
    _, _, plan = _plan()
    c = plan.complexity
    assert c.theory_time and c.theory_space
    assert c.code_time and c.code_space
    assert c.code_features
    o = c.observed
    assert (o.n, o.visited, o.lookups, o.hits, o.misses, o.inserts) == (4, 2, 2, 1, 1, 1)
    assert o.peak_seen == 1
    assert o.trace_events == 11
    assert o.duration_ms > 0
    assert o.output == [0, 1]
    assert "不能单独证明复杂度" in c.caveat


def test_class_plan_is_same_semantic_execution() -> None:
    execution, trace, plan = _plan("two_sum_class")
    assert execution.program.style.value == "leetcode_class"
    assert plan.source_style == "leetcode_class"
    assert len(plan.steps) == 8
    assert plan.verified
    assert "class Solution" in plan.code
    assert verify_plan(plan, trace) == []
    assert trace.metadata.execution_trace_id and plan.trace_id == trace.metadata.execution_trace_id


def test_html_is_standalone_and_embeds_unified_trace(tmp_path: Path) -> None:
    _, trace, plan = _plan()
    path = write_html_player(trace, plan, tmp_path / "interactive.html")
    text = path.read_text(encoding="utf-8")
    assert "fetch(" not in text
    assert "http://" not in text
    assert "https://" not in text
    for control in ('id="play"', 'id="prev"', 'id="next"', 'id="seek"', 'id="speed"', 'id="array"', 'id="dict"', 'id="code"'):
        assert control in text
    assert "requestAnimationFrame" in text
    assert "state_after" in text
    match = re.search(r'<script id="trace-data" type="application/json">(.*?)</script>', text, re.S)
    assert match is not None
    payload = json.loads(match.group(1))
    assert len(payload["trace"]["steps"]) == 8
    assert len(payload["teaching"]["sections"]) == 5
    assert len(payload["step_timeline"]) == 8
    assert payload["step_timeline"][0]["start"] == 0
    assert payload["trace"]["steps"][5]["state_after"]["dict_state"]["lookup_status"] == "hit"
    assert payload["trace"]["steps"][6]["state_after"]["array"]["found_indices"] == [0, 1]
    assert payload["teaching"]["videos"][1]["variant"] == "step_by_step"


def test_html_contains_controls_for_arbitrary_step_jump(tmp_path: Path) -> None:
    _, trace, plan = _plan()
    path = write_html_player(trace, plan, tmp_path / "player.html")
    text = path.read_text(encoding="utf-8")
    assert "setStep" in text
    assert "seekAbsolute" in text
    assert "data-step" in text
    assert "speed" in text
    # 每个真实 step 都由图例动态生成，不额外生成算法步骤。
    assert 'data-step="${i}"' in text
    assert "STEPS.map" in text
