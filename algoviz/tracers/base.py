"""追踪器基类：负责把真实执行过程转成统一 Animation Event。"""
from __future__ import annotations

from typing import Any

from ..protocol.events import (
    AnimationStep,
    StepType,
    Trace,
    TraceMetadata,
    VisualKind,
    VisualState,
)


class BaseTracer:
    category: str = ""
    visual_kind: VisualKind = VisualKind.ARRAY

    def __init__(self, code: str = "") -> None:
        self.code = code
        self.steps: list[AnimationStep] = []
        self._last_state: VisualState | None = None
        self._current_line: int | None = None
        self._line_cache: dict[tuple[str, int], int | None] = {}
        self._init_state()

    # ------------------------------------------------------------------ 子类实现
    def snapshot(self) -> VisualState:
        raise NotImplementedError

    # ------------------------------------------------------------------ 工具
    def _init_state(self) -> None:
        self._last_state = self.snapshot()

    @staticmethod
    def fmt(value: Any) -> str:
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    def line(self, needle: str, occurrence: int = 0) -> int | None:
        """按源码子串定位行号（1 基），用于代码高亮。"""
        key = (needle, occurrence)
        if key in self._line_cache:
            return self._line_cache[key]
        found: int | None = None
        seen = 0
        for idx, text in enumerate(self.code.splitlines(), start=1):
            if needle in text:
                if seen == occurrence:
                    found = idx
                    break
                seen += 1
        self._line_cache[key] = found
        return found

    def at(self, needle: str, occurrence: int = 0) -> "BaseTracer":
        """设置后续事件默认高亮的代码行。"""
        self._current_line = self.line(needle, occurrence)
        return self

    def emit(
        self,
        step_type: StepType,
        description: str,
        *,
        targets: list[str | int] | None = None,
        state: VisualState | None = None,
        code_line: int | None = None,
        visual_action: str = "",
        narration: str = "",
        meta: dict[str, Any] | None = None,
    ) -> AnimationStep:
        after = state if state is not None else self.snapshot()
        before = self._last_state if self._last_state is not None else after
        step = AnimationStep(
            step_id=len(self.steps),
            type=step_type,
            targets=targets or [],
            description=description,
            narration=narration or description,
            code_line=code_line if code_line is not None else self._current_line,
            visual_action=visual_action or step_type.value,
            state_before=before,
            state_after=after,
            meta=meta or {},
        )
        self.steps.append(step)
        self._last_state = after
        return step

    # ------------------------------------------------------------------ 常用事件
    def init(self, description: str, meta: dict[str, Any] | None = None) -> None:
        self.emit(StepType.INIT, description, visual_action="init", meta=meta)

    def complete(self, description: str, meta: dict[str, Any] | None = None) -> None:
        self.emit(StepType.COMPLETE, description, visual_action="complete", meta=meta)

    def note(self, description: str, *, targets: list[str | int] | None = None, **meta: Any) -> None:
        self.emit(StepType.NOTE, description, targets=targets, visual_action="note", meta=meta)

    # ------------------------------------------------------------------ 汇总
    def build_trace(
        self,
        metadata: TraceMetadata,
        result: dict[str, Any],
        verified: bool,
        verification_notes: list[str] | None = None,
    ) -> Trace:
        if not self.steps or self.steps[-1].type != StepType.COMPLETE:
            self.complete(f"算法执行结束：{result.get('summary', '完成')}")
        return Trace(
            metadata=metadata,
            steps=self.steps,
            result=result,
            verified=verified,
            verification_notes=verification_notes or [],
        )
