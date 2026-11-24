from __future__ import annotations

from typing import Any

import pytest

from algoviz.protocol.cases import CaseRun, CaseRunStatus
from algoviz.protocol.events import (
    AnimationStep,
    ArrayState,
    Complexity,
    DictEntryView,
    DictState,
    StepType,
    Trace,
    TraceMetadata,
    VariableView,
    VisualKind,
    VisualState,
)
from algoviz.protocol.hints import HintKind, StepHint
from algoviz.render.two_sum_visuals import TwoSumStage
from algoviz.teaching.playback import PlaybackController, PlaybackError, PlaybackMode

COLORS = {
    "panel": "#16233D",
    "panel_alt": "#1C2B49",
    "border": "#2A3B5E",
    "text": "#E8EEF9",
    "muted": "#9AA9C2",
    "accent": "#FBBF24",
    "compare": "#38BDF8",
    "sorted": "#34D399",
    "danger": "#F87171",
}
CODE = "def two_sum(nums, target):\n    seen = {}\n    return []\n"


class FakeScene:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.removed: list[Any] = []
        self.played: list[Any] = []

    def add(self, *mobjects: Any) -> None:
        self.added.extend(mobjects)

    def remove(self, *mobjects: Any) -> None:
        self.removed.extend(mobjects)

    def play(self, *animations: Any, run_time: float = 0.25) -> None:
        self.played.append((animations, run_time))

    def wait(self, duration: float) -> None:
        pass

    def bring_to_front(self, *mobjects: Any) -> None:
        pass


class FakeTimer:
    def __init__(self, delay: float, callback: Any) -> None:
        self.delay = delay
        self.callback = callback
        self.cancelled = False
        self.fired = False

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        self.fired = True
        self.callback()


class FakeScheduler:
    def __init__(self) -> None:
        self.timers: list[FakeTimer] = []

    def __call__(self, delay: float, callback: Any) -> FakeTimer:
        timer = FakeTimer(delay, callback)
        self.timers.append(timer)
        return timer

    def pending(self) -> list[FakeTimer]:
        return [timer for timer in self.timers if not timer.cancelled and not timer.fired]

    def fire_next(self) -> FakeTimer:
        pending = self.pending()
        assert pending, "没有待触发的自动播放定时器"
        timer = pending[-1]
        timer.fire()
        return timer


def _state(
    values: list[int],
    *,
    target: int = 9,
    pointer: int | None = None,
    found: list[int] | None = None,
    entries: list[tuple[str, int]] | None = None,
    lookup_key: str | None = None,
    lookup_status: str | None = None,
    variables: list[tuple[str, str, bool]] | None = None,
) -> VisualState:
    state = VisualState(
        kind=VisualKind.ARRAY,
        array=ArrayState(
            values=values,
            pointers={"i": pointer} if pointer is not None else {},
            target=target,
            found_indices=found or [],
        ),
        dict_state=DictState(
            entries=[DictEntryView(key=key, value=value) for key, value in (entries or [])],
            lookup_key=lookup_key,
            lookup_status=lookup_status,  # type: ignore[arg-type]
        ),
        variables=[
            VariableView(name=name, value=value, changed=changed)
            for name, value, changed in (variables or [])
        ],
    )
    return state


def _trace(values: list[int]) -> Trace:
    first = _state(values, variables=[("seen", "{}", False)])
    visited = _state(values, pointer=0, variables=[("i", "0", True), ("x", str(values[0]), True)])
    found = _state(values, found=[0, 1], entries=[(str(values[0]), 0)], lookup_key=str(values[0]), lookup_status="hit")
    steps = [
        AnimationStep(
            step_id=0,
            type=StepType.INIT,
            description="初始化",
            code_line=2,
            state_before=first,
            state_after=first,
        ),
        AnimationStep(
            step_id=1,
            type=StepType.VISIT,
            targets=[0],
            description="访问",
            code_line=3,
            state_before=first,
            state_after=visited,
        ),
        AnimationStep(
            step_id=2,
            type=StepType.FOUND,
            targets=[0, 1],
            description="返回",
            code_line=6,
            state_before=visited,
            state_after=found,
            meta={"return": [0, 1]},
        ),
    ]
    metadata = TraceMetadata(
        algorithm="two_sum",
        title="Two Sum test",
        category="custom",
        visual_kind=VisualKind.ARRAY,
        input={"nums": values, "target": 9},
        complexity=Complexity(time="O(n)", space="O(n)"),
        code=CODE,
        execution_trace_id=f"exec_{values[0]}",
    )
    return Trace(metadata=metadata, steps=steps, verified=True)


def _case(case_id: str, values: list[int]) -> CaseRun:
    trace = _trace(values)
    return CaseRun(
        run_id=f"run_{case_id}",
        case_id=case_id,
        status=CaseRunStatus.FAILED,
        animation_trace=trace,
        actual_output=[0, 1],
        expected_output=[0, 1],
    )


def _hint(step_id: int, *, hint_id: str = "hint") -> StepHint:
    return StepHint(
        hint_id=hint_id,
        related_step_id=step_id,
        kind=HintKind.COMPLETE,
        title="提示",
        explanation="解释",
        question="问题",
        answer="答案",
    )


def test_manual_controls_share_one_index_and_boundaries() -> None:
    scheduler = FakeScheduler()
    steps_seen: list[int] = []
    states: list[Any] = []
    controller = PlaybackController(
        scheduler=scheduler,
        on_step=lambda step: steps_seen.append(step.step_id),
        on_state_change=states.append,
    )
    run = _case("normal", [2, 7])
    snapshot = controller.load_case(run)
    assert snapshot.case_id == "normal"
    assert snapshot.step_count == 3
    assert snapshot.step_index == 0
    assert snapshot.mode is PlaybackMode.TEACHER
    assert steps_seen == [0]

    assert controller.next_step().step_index == 1
    assert controller.next_step().step_index == 2
    assert controller.next_step().step_index == 2
    assert controller.is_at_end is True
    assert controller.previous_step().step_index == 1
    assert controller.previous_step().step_index == 0
    assert controller.previous_step().step_index == 0

    assert controller.seek(99).step_index == 2
    assert controller.seek(-5).step_index == 0
    controller.seek(1)
    assert controller.reset().step_index == 0
    assert steps_seen == [0, 1, 2, 1, 0, 2, 0, 1, 0]
    assert states[-1].step_index == 0

    assert controller.set_speed(1.5).speed == 1.5
    assert controller.playback_speed == 1.5
    with pytest.raises(PlaybackError):
        controller.set_speed(0)
    with pytest.raises(PlaybackError):
        controller.set_speed(99)


def test_auto_play_advances_to_end_and_stops() -> None:
    scheduler = FakeScheduler()
    steps_seen: list[int] = []
    controller = PlaybackController(
        scheduler=scheduler,
        on_step=lambda step: steps_seen.append(step.step_id),
    )
    controller.load_case(_case("normal", [2, 7]))
    snapshot = controller.play()
    assert snapshot.mode is PlaybackMode.AUTO
    assert snapshot.is_playing is True
    assert scheduler.pending()
    assert scheduler.pending()[-1].delay == pytest.approx(1.2)

    scheduler.fire_next()
    assert controller.current_step_index == 1
    assert controller.is_playing is True
    scheduler.fire_next()
    assert controller.current_step_index == 2
    assert controller.is_playing is True
    scheduler.fire_next()
    snapshot = controller.snapshot()
    assert snapshot.step_index == 2
    assert snapshot.is_playing is False
    assert snapshot.mode is PlaybackMode.TEACHER
    assert steps_seen == [0, 1, 2]
    assert not scheduler.pending()


def test_pause_resume_and_speed_reschedule() -> None:
    scheduler = FakeScheduler()
    controller = PlaybackController(scheduler=scheduler)
    controller.load_case(_case("normal", [2, 7]))
    controller.play()
    first = scheduler.pending()[-1]
    assert first.delay == pytest.approx(1.2)

    controller.set_speed(2.0)
    assert first.cancelled is True
    fast = scheduler.pending()[-1]
    assert fast.delay == pytest.approx(0.6)
    scheduler.fire_next()
    assert controller.current_step_index == 1

    controller.pause()
    assert controller.is_playing is False
    assert controller.playback_mode is PlaybackMode.TEACHER
    cancelled = scheduler.pending()
    assert cancelled == []
    scheduler.fire_next() if scheduler.pending() else None
    assert controller.current_step_index == 1

    controller.resume()
    assert controller.is_playing is True
    assert controller.playback_mode is PlaybackMode.AUTO
    scheduler.fire_next()
    assert controller.current_step_index == 2


def test_manual_controls_take_over_auto() -> None:
    scheduler = FakeScheduler()
    controller = PlaybackController(scheduler=scheduler)
    controller.load_case(_case("normal", [2, 7]))
    controller.play()
    task = scheduler.pending()[-1]
    controller.next_step()
    assert task.cancelled is True
    assert controller.is_playing is False
    assert controller.playback_mode is PlaybackMode.TEACHER
    assert controller.current_step_index == 1
    assert not scheduler.pending()


def test_switch_case_cancels_old_timer_and_starts_from_zero() -> None:
    scheduler = FakeScheduler()
    controller = PlaybackController(scheduler=scheduler)
    normal = _case("normal", [2, 7])
    first = _case("first", [3, 2])
    controller.load_case(normal)
    controller.next_step()
    controller.play()
    old_task = scheduler.pending()[-1]
    first_trace_id = first.animation_trace.metadata.execution_trace_id

    snapshot = controller.load_case(first)
    assert old_task.cancelled is True
    assert snapshot.case_id == "first"
    assert snapshot.step_index == 0
    assert snapshot.is_playing is False
    assert snapshot.mode is PlaybackMode.TEACHER
    assert controller.current_animation_trace.metadata.execution_trace_id == first_trace_id
    assert controller.current_step.state_after.array.values == [3, 2]
    scheduler.fire_next() if scheduler.pending() else None
    assert controller.current_step_index == 0


def test_hints_are_indexed_by_step_and_validated() -> None:
    controller = PlaybackController(scheduler=FakeScheduler())
    run = _case("normal", [2, 7])
    controller.load_case(run, hints=[_hint(0, hint_id="h0"), _hint(2, hint_id="h2")])
    assert controller.current_hint is not None
    assert controller.current_hint.hint_id == "h0"
    controller.seek(2)
    assert controller.current_hint.hint_id == "h2"
    with pytest.raises(PlaybackError):
        controller.set_hints([_hint(9, hint_id="bad")])
    with pytest.raises(PlaybackError):
        controller.set_hints([_hint(0, hint_id="dup"), _hint(0, hint_id="dup2")])


def test_controller_and_stage_share_steps_without_reassembling_components() -> None:
    scheduler = FakeScheduler()
    scene = FakeScene()
    stage = TwoSumStage(
        scene,
        colors=COLORS,
        font="Microsoft YaHei",
        code_font="Consolas",
        code=CODE,
    )
    first = _case("first", [3, 2])
    normal = _case("normal", [2, 7])
    stage.build(first.animation_trace.steps[0].state_after)
    plan = stage.visual_plan
    assembly = stage.assembly
    assert plan is not None and assembly is not None
    controller = PlaybackController(scheduler=scheduler, on_step=stage.show_step)
    controller.load_case(first)
    assert stage.current_step_index == 0
    controller.next_step()
    assert stage.current_step_index == 1
    assert stage.array_visualizer.displayed_values == [3, 2]
    assert stage.code_visualizer.current_line == 3

    # 模拟用例切换：stage 先加载目标 trace，控制器再加载同一 run。
    stage.load_case(normal)
    controller.load_case(normal)
    assert stage.visual_plan is plan
    assert stage.assembly is assembly
    assert stage.array_visualizer.displayed_values == [2, 7]
    assert stage.array_visualizer.target_text == "target = 9"
    assert controller.current_case_id == "normal"
    assert stage.current_step_index == 0
