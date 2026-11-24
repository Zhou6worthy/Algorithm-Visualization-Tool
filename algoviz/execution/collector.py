"""Python Generic Tracer：在 LocalSandbox 进程内采集真实执行事实。

实现要点：
- line 事件记录的是“执行该行之前”的 locals；
- 该行的 after 状态由同一 frame 的下一个事件确认；
- call/return/exception 单独记录；
- 事件写入受控文件（由 harness 负责），stdout 独立捕获；
- 不在此层生成算法语义。
"""
from __future__ import annotations

import io
import os
from typing import Any

from ..protocol.execution import (
    BranchArc,
    ExecutionEvent,
    ExecutionStatus,
    GenericTrace,
    TraceLimits,
)
from .safe_serializer import SafeSerializer


class BoundedTextIO(io.TextIOBase):
    """限制输出的 stdout/stderr 替身；不触碰文件描述符。"""

    def __init__(self, limit: int) -> None:
        super().__init__()
        self.limit = limit
        self._buffer: list[str] = []
        self._size = 0
        self._consumed = 0
        self.truncated = False

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return "utf-8"

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:  # type: ignore[override]
        if not isinstance(text, str):
            text = str(text)
        if self._size >= self.limit:
            self.truncated = True
            return len(text)
        remaining = self.limit - self._size
        chunk = text[:remaining]
        self._buffer.append(chunk)
        self._size += len(chunk)
        if len(chunk) < len(text):
            self.truncated = True
        return len(text)

    def flush(self) -> None:
        return None

    def getvalue(self) -> str:
        return "".join(self._buffer)

    def take_delta(self) -> str:
        text = "".join(self._buffer)[self._consumed :]
        self._consumed = len(text) + self._consumed
        return text


class _FrameState:
    __slots__ = (
        "frame_id",
        "parent_frame_id",
        "depth",
        "pending_event_id",
        "pending_before",
        "exception_seen",
    )

    def __init__(self, frame_id: int, parent: int | None, depth: int) -> None:
        self.frame_id = frame_id
        self.parent_frame_id = parent
        self.depth = depth
        self.pending_event_id: int | None = None
        self.pending_before: dict[str, Any] | None = None
        self.exception_seen = False


class PythonTraceCollector:
    def __init__(
        self,
        user_path: str,
        *,
        limits: TraceLimits | None = None,
        serializer: SafeSerializer | None = None,
        stdout: BoundedTextIO | None = None,
    ) -> None:
        self.user_path = os.path.realpath(user_path)
        self.limits = limits or TraceLimits()
        self.serializer = serializer or SafeSerializer()
        self.stdout = stdout or BoundedTextIO(self.limits.max_stdout_bytes)
        self.events: list[ExecutionEvent] = []
        self.arcs: list[BranchArc] = []
        self._frames: dict[int, _FrameState] = {}
        self._frame_seq = 0
        self._event_seq = 0
        self._entry_frame_id: int | None = None
        self._terminal_event_id: int | None = None
        self._trace_complete = False
        self._limit_hit = False
        self.return_value: Any = None
        self.exception_type: str | None = None
        self.exception_message: str | None = None
        self.exception_seen = False

    # ------------------------------------------------------------------ trace hook
    def trace(self, frame: Any, event: str, arg: Any) -> Any:
        try:
            filename = os.path.realpath(frame.f_code.co_filename)
        except Exception:  # noqa: BLE001
            return None
        if filename != self.user_path:
            return None
        try:
            self._handle(frame, event, arg)
        except Exception:
            # 追踪器本身不能影响用户程序；记录失败并停止采集
            self._trace_complete = False
            return None
        return self.trace

    def _snapshot(self, frame: Any) -> dict[str, Any]:
        return self.serializer.serialize_locals(frame.f_locals)

    def _append_event(
        self,
        *,
        frame: Any,
        state: _FrameState,
        event: str,
        before: dict[str, Any],
        after: dict[str, Any] | None = None,
        return_value: Any = None,
        exception_type: str | None = None,
        exception_message: str | None = None,
        is_unwind: bool = False,
    ) -> ExecutionEvent:
        self._event_seq += 1
        item = ExecutionEvent(
            event_id=self._event_seq,
            frame_id=state.frame_id,
            parent_frame_id=state.parent_frame_id,
            event=event,  # type: ignore[arg-type]
            line=max(1, int(frame.f_lineno)),
            original_line=max(1, int(frame.f_lineno)),
            function=str(frame.f_code.co_name),
            depth=state.depth,
            locals_before=before,
            locals_after=after,
            return_value=return_value,
            exception_type=exception_type,
            exception_message=exception_message,
            is_unwind=is_unwind,
            stdout_delta=self.stdout.take_delta(),
        )
        self.events.append(item)
        if len(self.events) >= self.limits.max_frames:
            self._limit_hit = True
            self._trace_complete = False
        return item

    def _finalize_pending(self, state: _FrameState, current: dict[str, Any]) -> None:
        if state.pending_event_id is None:
            return
        event = self.events[state.pending_event_id - 1]
        before = state.pending_before or {}
        event.locals_after = current
        event.changed = sorted(
            key
            for key in set(before) | set(current)
            if before.get(key) != current.get(key)
        )
        state.pending_event_id = None
        state.pending_before = None

    def _handle(self, frame: Any, event: str, arg: Any) -> None:
        key = id(frame)
        state = self._frames.get(key)
        current = self._snapshot(frame)

        if event == "call":
            self._frame_seq += 1
            parent = self._frames.get(id(frame.f_back)) if frame.f_back is not None else None
            state = _FrameState(
                frame_id=self._frame_seq,
                parent=parent.frame_id if parent else None,
                depth=(parent.depth + 1) if parent else 0,
            )
            self._frames[key] = state
            if self._entry_frame_id is None:
                self._entry_frame_id = state.frame_id
            self._append_event(frame=frame, state=state, event="call", before=current)
            return

        if state is None:
            # 追踪从函数中间开始（理论上不应发生）：构造合成 frame，保持事件连续
            self._frame_seq += 1
            state = _FrameState(frame_id=self._frame_seq, parent=None, depth=0)
            self._frames[key] = state
            if self._entry_frame_id is None:
                self._entry_frame_id = state.frame_id

        if event == "line":
            if self._limit_hit:
                return
            # 上一个 line 的 after = 当前的 before
            if state.pending_event_id is not None:
                prev_id = state.pending_event_id
                self._finalize_pending(state, current)
                if prev_id - 1 < len(self.events):
                    self.events[prev_id - 1].after_event_id = self._event_seq + 1
            item = self._append_event(frame=frame, state=state, event="line", before=current)
            state.pending_event_id = item.event_id
            state.pending_before = current
            return

        if event == "return":
            was_exception = state.exception_seen or self.exception_seen
            if state.pending_event_id is not None:
                prev_id = state.pending_event_id
                self._finalize_pending(state, current)
                if prev_id - 1 < len(self.events):
                    self.events[prev_id - 1].after_event_id = self._event_seq + 1
            return_value = self._safe_value(arg)
            self.return_value = return_value
            item = self._append_event(
                frame=frame,
                state=state,
                event="return",
                before=current,
                after=current,
                return_value=return_value,
                is_unwind=was_exception,
            )
            if state.frame_id == self._entry_frame_id:
                self._terminal_event_id = item.event_id
                self._trace_complete = not was_exception and not self._limit_hit
            self._frames.pop(key, None)
            return

        if event == "exception":
            if state.pending_event_id is not None:
                prev_id = state.pending_event_id
                self._finalize_pending(state, current)
                if prev_id - 1 < len(self.events):
                    self.events[prev_id - 1].after_event_id = self._event_seq + 1
            exc_type, exc_value, _tb = arg
            self.exception_seen = True
            state.exception_seen = True
            self.exception_type = getattr(exc_type, "__name__", str(exc_type))
            self.exception_message = str(exc_value)
            item = self._append_event(
                frame=frame,
                state=state,
                event="exception",
                before=current,
                after=current,
                exception_type=self.exception_type,
                exception_message=self.exception_message,
            )
            if state.frame_id == self._entry_frame_id:
                self._terminal_event_id = item.event_id
                self._trace_complete = True
            return

    def _safe_value(self, value: Any) -> Any:
        serialized = self.serializer.serialize(value)
        return self.serializer.to_native(serialized)

    # ------------------------------------------------------------------ finish
    def finish(self) -> GenericTrace:
        # 未确认的 pending line：没有 after，不假装完成
        for state in self._frames.values():
            if state.pending_event_id is not None:
                self._trace_complete = False
        if self._limit_hit:
            self._trace_complete = False
        self._build_arcs()
        return GenericTrace(
            source_hash="",
            events=self.events,
            arcs=self.arcs,
            stdout=self.stdout.getvalue(),
            stderr="",
            return_value=self.return_value,
            exception_type=self.exception_type,
            exception_message=self.exception_message,
            trace_complete=self._trace_complete,
            event_count=len(self.events),
        )

    def _build_arcs(self) -> None:
        by_frame: dict[int, list[ExecutionEvent]] = {}
        for event in self.events:
            by_frame.setdefault(event.frame_id, []).append(event)
        arcs: list[BranchArc] = []
        for frame_events in by_frame.values():
            for previous, current in zip(frame_events, frame_events[1:]):
                arcs.append(
                    BranchArc(
                        arc_id=len(arcs),
                        from_event_id=previous.event_id,
                        to_event_id=current.event_id,
                        from_line=previous.line,
                        to_line=current.line,
                        kind="sequential",
                        evidence_event_ids=[previous.event_id, current.event_id],
                    )
                )
        self.arcs = arcs

    @property
    def trace_complete(self) -> bool:
        return self._trace_complete

    @property
    def limit_hit(self) -> bool:
        return self._limit_hit

    @property
    def status(self) -> ExecutionStatus:
        if self._limit_hit:
            return ExecutionStatus.EVENT_LIMIT
        if not self._trace_complete:
            return ExecutionStatus.TRACE_INCOMPLETE
        return ExecutionStatus.OK
