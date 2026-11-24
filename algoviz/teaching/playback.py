"""统一播放控制器：教师手动控制与自动播放共享同一份真实 AnimationTrace。

设计边界：
- 控制器只移动 ``step_index``，绝不重新执行算法或生成新轨迹；
- 手动 next/previous/seek 与 Auto 定时推进都经过同一个 ``_apply_index``；
- 切换用例会先停止旧定时器，再从目标 trace 的 step 0 重建状态；
- ``CaseRun`` / ``Trace`` / ``AnimationStep`` 均只读，不在播放过程中修改。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
from typing import Callable, Protocol

from ..protocol.cases import CaseRun
from ..protocol.events import AnimationStep, Trace
from ..protocol.hints import StepHint


class PlaybackMode(str, Enum):
    TEACHER = "teacher"
    AUTO = "auto"


class PlaybackError(RuntimeError):
    pass


class TimerHandle(Protocol):
    def cancel(self) -> None: ...


class Scheduler(Protocol):
    def __call__(self, delay: float, callback: Callable[[], None]) -> TimerHandle: ...


class _ThreadingTimer:
    def __init__(self, delay: float, callback: Callable[[], None]) -> None:
        self._timer = threading.Timer(max(0.0, delay), callback)
        self._timer.daemon = True

    def start(self) -> None:
        self._timer.start()

    def cancel(self) -> None:
        self._timer.cancel()


class ThreadingScheduler:
    """默认调度器；测试可注入确定性 FakeScheduler。"""

    def __call__(self, delay: float, callback: Callable[[], None]) -> _ThreadingTimer:
        timer = _ThreadingTimer(delay, callback)
        timer.start()
        return timer


@dataclass(frozen=True)
class PlaybackSnapshot:
    case_id: str | None
    run_id: str | None
    trace_id: str | None
    step_index: int
    step_count: int
    mode: PlaybackMode
    speed: float
    is_playing: bool
    is_at_end: bool
    step_type: str | None
    hint_id: str | None


class PlaybackController:
    """单个当前用例的播放状态机。

    ``on_step`` 在每次步骤真正切换时调用；``on_state_change`` 在播放状态
    （播放/暂停/速度/模式等）变化时调用。两个回调都只接收只读数据。
    """

    DEFAULT_STEP_DURATION = 1.2
    MIN_SPEED = 0.25
    MAX_SPEED = 4.0

    def __init__(
        self,
        *,
        on_step: Callable[[AnimationStep], None] | None = None,
        on_state_change: Callable[[PlaybackSnapshot], None] | None = None,
        scheduler: Scheduler | None = None,
        default_step_duration: float = DEFAULT_STEP_DURATION,
    ) -> None:
        if default_step_duration <= 0:
            raise ValueError("default_step_duration 必须大于 0")
        self._on_step = on_step
        self._on_state_change = on_state_change
        self._scheduler: Scheduler = scheduler or ThreadingScheduler()
        self._default_step_duration = float(default_step_duration)
        self._lock = threading.RLock()

        self._case: CaseRun | None = None
        self._trace: Trace | None = None
        self._index = 0
        self._mode = PlaybackMode.TEACHER
        self._speed = 1.0
        self._playing = False
        self._timer: TimerHandle | None = None
        self._timer_token = 0
        self._hints: dict[int, StepHint] = {}

    # ------------------------------------------------------------------ 查询
    @property
    def current_case(self) -> CaseRun | None:
        return self._case

    @property
    def current_case_id(self) -> str | None:
        return self._case.case_id if self._case is not None else None

    @property
    def current_animation_trace(self) -> Trace | None:
        return self._trace

    @property
    def current_trace(self) -> Trace | None:
        return self._trace

    @property
    def current_step_index(self) -> int:
        return self._index

    @property
    def current_step(self) -> AnimationStep | None:
        if self._trace is None or not self._trace.steps:
            return None
        return self._trace.steps[self._index]

    @property
    def current_hint(self) -> StepHint | None:
        return self._hints.get(self._index)

    @property
    def playback_mode(self) -> PlaybackMode:
        return self._mode

    @property
    def playback_speed(self) -> float:
        return self._speed

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def is_at_end(self) -> bool:
        return self._trace is not None and self._index >= len(self._trace.steps) - 1

    def snapshot(self) -> PlaybackSnapshot:
        with self._lock:
            step = self.current_step
            hint = self.current_hint
            return PlaybackSnapshot(
                case_id=self.current_case_id,
                run_id=self._case.run_id if self._case is not None else None,
                trace_id=self._trace.metadata.execution_trace_id if self._trace is not None else None,
                step_index=self._index,
                step_count=len(self._trace.steps) if self._trace is not None else 0,
                mode=self._mode,
                speed=self._speed,
                is_playing=self._playing,
                is_at_end=self.is_at_end,
                step_type=step.type.value if step is not None else None,
                hint_id=hint.hint_id if hint is not None else None,
            )

    # ------------------------------------------------------------------ 加载/切换
    def load_case(self, case_run: CaseRun, *, hints: list[StepHint] | None = None) -> PlaybackSnapshot:
        trace = case_run.animation_trace
        if trace is None or not trace.steps:
            raise PlaybackError(f"CaseRun {case_run.run_id} 没有可播放的 AnimationTrace")
        with self._lock:
            self._cancel_timer()
            self._case = case_run
            self._trace = trace
            self._index = 0
            self._mode = PlaybackMode.TEACHER
            self._playing = False
            self._hints = self._index_hints(hints or [], trace)
            self._apply_index(0, step_changed=True)
            return self.snapshot()

    def set_hints(self, hints: list[StepHint]) -> None:
        with self._lock:
            if self._trace is None:
                self._hints = {}
                return
            self._hints = self._index_hints(hints, self._trace)
            self._notify_state()

    # ------------------------------------------------------------------ 教师控制
    def next_step(self) -> PlaybackSnapshot:
        with self._lock:
            self._require_trace()
            return self._manual_to(self._index + 1)

    def previous_step(self) -> PlaybackSnapshot:
        with self._lock:
            self._require_trace()
            return self._manual_to(self._index - 1)

    def seek(self, step_index: int) -> PlaybackSnapshot:
        with self._lock:
            self._require_trace()
            return self._manual_to(int(step_index))

    def reset(self) -> PlaybackSnapshot:
        with self._lock:
            self._require_trace()
            return self._manual_to(0)

    # ------------------------------------------------------------------ 自动播放
    def play(self) -> PlaybackSnapshot:
        with self._lock:
            trace = self._require_trace()
            if self._playing:
                return self.snapshot()
            self._cancel_timer()
            if self._index >= len(trace.steps) - 1:
                self._index = 0
                self._notify_step()
            self._mode = PlaybackMode.AUTO
            self._playing = True
            self._notify_state()
            self._schedule_next()
            return self.snapshot()

    def pause(self) -> PlaybackSnapshot:
        with self._lock:
            self._cancel_timer()
            self._playing = False
            self._mode = PlaybackMode.TEACHER
            self._notify_state()
            return self.snapshot()

    def resume(self) -> PlaybackSnapshot:
        with self._lock:
            trace = self._require_trace()
            if self._playing:
                return self.snapshot()
            self._cancel_timer()
            if self._index >= len(trace.steps) - 1:
                self._index = 0
                self._notify_step()
            self._mode = PlaybackMode.AUTO
            self._playing = True
            self._notify_state()
            self._schedule_next()
            return self.snapshot()

    def set_speed(self, speed: float) -> PlaybackSnapshot:
        speed = float(speed)
        if not (self.MIN_SPEED <= speed <= self.MAX_SPEED):
            raise PlaybackError(f"播放速度必须在 {self.MIN_SPEED}～{self.MAX_SPEED} 之间")
        with self._lock:
            self._speed = speed
            if self._playing:
                self._schedule_next()
            self._notify_state()
            return self.snapshot()

    # ------------------------------------------------------------------ 内部状态
    def _require_trace(self) -> Trace:
        if self._trace is None or not self._trace.steps:
            raise PlaybackError("尚未加载可播放的 AnimationTrace")
        return self._trace

    def _manual_to(self, target: int) -> PlaybackSnapshot:
        self._cancel_timer()
        self._playing = False
        self._mode = PlaybackMode.TEACHER
        # 边界 no-op 不重复触发 on_step，但仍通过 on_state_change 更新控件状态。
        self._apply_index(target, step_changed=False)
        return self.snapshot()

    def _apply_index(self, target: int, *, step_changed: bool) -> None:
        trace = self._require_trace()
        target = max(0, min(len(trace.steps) - 1, int(target)))
        changed = target != self._index
        self._index = target
        if step_changed or changed:
            self._notify_step()
        self._notify_state()

    def _notify_step(self) -> None:
        step = self.current_step
        if step is not None and self._on_step is not None:
            self._on_step(step)

    def _notify_state(self) -> None:
        if self._on_state_change is not None:
            self._on_state_change(self.snapshot())

    def _current_duration(self) -> float:
        step = self.current_step
        if step is not None and step.duration is not None and step.duration > 0:
            return float(step.duration)
        return self._default_step_duration

    def _schedule_next(self) -> None:
        if not self._playing:
            return
        self._cancel_timer()
        token = self._timer_token
        delay = self._current_duration() / self._speed

        def fire() -> None:
            self._on_timer(token)

        self._timer = self._scheduler(delay, fire)

    def _on_timer(self, token: int) -> None:
        with self._lock:
            if token != self._timer_token or not self._playing:
                return
            self._timer = None
            trace = self._trace
            if trace is None:
                self._playing = False
                self._mode = PlaybackMode.TEACHER
                self._notify_state()
                return
            if self._index >= len(trace.steps) - 1:
                self._playing = False
                self._mode = PlaybackMode.TEACHER
                self._notify_state()
                return
            self._index += 1
            self._mode = PlaybackMode.AUTO
            self._notify_step()
            self._notify_state()
            self._schedule_next()

    def _cancel_timer(self) -> None:
        self._timer_token += 1
        if self._timer is not None:
            try:
                self._timer.cancel()
            finally:
                self._timer = None

    @staticmethod
    def _index_hints(hints: list[StepHint], trace: Trace) -> dict[int, StepHint]:
        valid_ids = {step.step_id for step in trace.steps}
        indexed: dict[int, StepHint] = {}
        for hint in hints:
            if hint.related_step_id not in valid_ids:
                raise PlaybackError(
                    f"StepHint {hint.hint_id} 引用了不存在的 step_id={hint.related_step_id}"
                )
            if hint.related_step_id in indexed:
                raise PlaybackError(f"step_id={hint.related_step_id} 存在重复 StepHint")
            indexed[hint.related_step_id] = hint
        return indexed
