"""通用变量行展示组件。

组件只接收已经投影好的 ``VariableRow`` 列表。它不知道任何变量名或
算法语义；变量投影由算法适配层完成。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from manim import FadeIn, FadeOut, VGroup

from ...protocol.events import AnimationStep, VisualState
from ...protocol.visual import ComponentKind
from .base import ComponentContext, SceneHost
from .primitives import make_card, make_text


@dataclass(frozen=True)
class VariableRow:
    label: str
    value: str
    changed: bool = False


class VariableVisualizer:
    kind = ComponentKind.VARIABLES

    def __init__(
        self,
        *,
        host: SceneHost | None = None,
        context: ComponentContext | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        self.host = host
        self.context = context
        self.options = dict(options or {})
        self.title = str(self.options.get("title", "变量"))
        self.max_rows = max(1, int(self.options.get("max_rows", 5)))
        self.empty_text = str(self.options.get("empty_text", "暂无变量"))
        self.note = str(self.options.get("note", ""))
        self.group = VGroup()
        self._panel = VGroup()
        self._body = VGroup()
        self._frame = None
        self._rows: list[VariableRow] = []

    # ------------------------------------------------------------------ 协议
    def mount(
        self,
        host: SceneHost,
        context: ComponentContext,
        state: VisualState,
    ) -> None:
        del state
        self.host = host
        self.context = context
        self._frame = make_card(context, self.title)
        self._panel = self._frame.panel
        self._add(self._panel)

    def update(self, step: AnimationStep, duration: float) -> None:
        # 行数据由 set_rows 从适配层投影后传入；这里不猜测算法变量。
        del step, duration

    def unmount(self, run_time: float = 0.2) -> None:
        if self.host is not None and len(self.group) > 0:
            self.host.play(FadeOut(self.group), run_time=max(0.05, run_time))
            self.host.remove(self.group)
        self.group = VGroup()
        self._body = VGroup()
        self._rows = []

    # ------------------------------------------------------------------ 行数据
    def set_rows(self, rows: list[VariableRow], *, animate: bool = True) -> None:
        assert self.host is not None and self.context is not None and self._frame is not None
        old = self._body
        self._rows = list(rows)[: self.max_rows]
        new = self._make_body()
        if animate and len(old) > 0:
            self._add(new)
            self.host.play(FadeOut(old), FadeIn(new), run_time=0.22)
            self._remove(old)
        else:
            if len(old) > 0:
                self._remove(old)
            self._add(new)
        self._body = new

    @property
    def displayed_labels(self) -> list[str]:
        return [row.label for row in self._rows]

    @property
    def displayed_values(self) -> list[str]:
        return [row.value for row in self._rows]

    @property
    def changed_labels(self) -> list[str]:
        return [row.label for row in self._rows if row.changed]

    @property
    def is_empty(self) -> bool:
        return not self._rows

    # ------------------------------------------------------------------ 构建
    def _add(self, *mobjects: Any) -> None:
        assert self.host is not None
        for mob in mobjects:
            self.group.add(mob)
            self.host.add(mob)

    def _remove(self, *mobjects: Any) -> None:
        assert self.host is not None
        for mob in mobjects:
            if mob in self.group:
                self.group.remove(mob)
            self.host.remove(mob)

    def _make_body(self) -> VGroup:
        assert self.context is not None and self._frame is not None
        body = VGroup()
        frame = self._frame
        if not self._rows:
            empty = make_text(self.context, self.empty_text, 16, self.context.theme["muted"])
            empty.move_to(np.array([frame.center_x, frame.center_y, 0]))
            body.add(empty)
        else:
            for row, item in enumerate(self._rows):
                y = frame.top_y - 0.645 - row * 0.33
                color = self.context.theme["accent"] if item.changed else self.context.theme["muted"]
                label = make_text(self.context, item.label, 15, color)
                label.move_to(
                    np.array([frame.left_x + 0.1, y, 0]),
                    aligned_edge=np.array([-1, 0, 0]),
                )
                value = make_text(
                    self.context,
                    item.value,
                    16,
                    self.context.theme["text"],
                    weight="BOLD" if item.changed else "NORMAL",
                )
                value.move_to(
                    np.array([frame.left_x + 1.15, y, 0]),
                    aligned_edge=np.array([-1, 0, 0]),
                )
                if value.width > 2.55:
                    value.scale_to_fit_width(2.55)
                body.add(label, value)
            if self.note:
                note = make_text(self.context, self.note, 11, self.context.theme["muted"])
                note.move_to(
                    np.array([frame.left_x + 0.1, frame.bottom + 0.105, 0]),
                    aligned_edge=np.array([-1, 0, 0]),
                )
                body.add(note)
        return body
