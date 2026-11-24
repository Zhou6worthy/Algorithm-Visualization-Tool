"""通用代码高亮组件。

只消费源代码、语言和 ``AnimationStep.code_line``；不读取数组、哈希表、
变量或任何算法语义。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from manim import FadeOut, Rectangle, RoundedRectangle, Text, VGroup

from ...protocol.events import AnimationStep, VisualState
from ...protocol.visual import ComponentKind
from .base import ComponentContext, SceneHost


@dataclass(frozen=True)
class CodeWindow:
    """纯代码窗口逻辑，可脱离 Manim 单独测试。"""

    line_count: int
    size: int = 14

    def __post_init__(self) -> None:
        if self.line_count < 0:
            raise ValueError("line_count 不能为负")
        if self.size < 1:
            raise ValueError("window size 必须大于 0")

    def visible(self, active_line: int) -> tuple[int, int]:
        """返回 0-based [start, end) 可见区间。"""
        if self.line_count == 0:
            return 0, 0
        line = max(1, min(self.line_count, int(active_line)))
        size = min(self.size, self.line_count)
        lead = max(1, self.size // 2 + 1)
        start = max(0, min(self.line_count - size, line - lead))
        return start, min(self.line_count, start + size)


class CodeVisualizer:
    """代码面板组件，保持 M2 的原有视觉尺寸与高亮风格。"""

    kind = ComponentKind.CODE

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
        self.window_size = max(
            1,
            int(
                self.options.get(
                    "window",
                    14,
                )
            ),
        )
        self.title = str(self.options.get("title", "CODE"))
        self.line_numbers = bool(self.options.get("line_numbers", True))
        self.header_size = int(self.options.get("header_size", 13))
        self.code_size = int(self.options.get("code_size", 13))
        self.number_size = int(self.options.get("number_size", 11))
        self.group = VGroup()
        self._panel = VGroup()
        self._body = VGroup()
        self._highlight: Rectangle | None = None
        self._line_y: dict[int, float] = {}
        self._visible_start = 0
        self._visible_end = 0
        self._current_line = 1
        self._left = 0.0
        self._bottom = 0.0
        self._width = 0.0
        self._height = 0.0
        self._top = 0.0

    # ------------------------------------------------------------------ 协议
    def mount(
        self,
        host: SceneHost,
        context: ComponentContext,
        state: VisualState,
    ) -> None:
        del state  # 代码面板不需要状态块，只使用 context.code/step.code_line
        self.host = host
        self.context = context
        self._left, self._bottom, self._width, self._height = context.manim_box()
        self._top = self._bottom + self._height
        self._build_panel()
        self._render_code_window(1)
        self._current_line = 1

    def update(self, step: AnimationStep, duration: float) -> None:
        del duration  # 组件不控制全局时间轴；由 SceneDirector 负责等待
        line = step.code_line
        if line is None:
            return
        line = max(1, min(len(context_lines(self.context)), int(line)))
        self._current_line = line
        if not (self._visible_start < line <= self._visible_end):
            self._render_code_window(line)
            return
        self._move_highlight(line)

    def unmount(self, run_time: float = 0.2) -> None:
        if self.host is not None and len(self.group) > 0:
            self.host.play(FadeOut(self.group), run_time=max(0.05, run_time))
            self.host.remove(self.group)
        self.group = VGroup()
        self._panel = VGroup()
        self._body = VGroup()
        self._highlight = None
        self._line_y = {}

    # ------------------------------------------------------------------ 查询
    @property
    def current_line(self) -> int:
        return self._current_line

    @property
    def visible_range(self) -> tuple[int, int]:
        """1-based 闭区间 [start, end]；空代码返回 (0, 0)。"""
        if self._visible_start >= self._visible_end:
            return 0, 0
        return self._visible_start + 1, self._visible_end

    @property
    def header_text(self) -> str:
        language = self.context.language if self.context else "python"
        return f"{self.title} · {language}" if language else self.title

    @property
    def line_y(self) -> dict[int, float]:
        return dict(self._line_y)

    @property
    def highlight_y(self) -> float | None:
        if self._highlight is None:
            return None
        return float(self._highlight.get_center()[1])

    # ------------------------------------------------------------------ 内部
    def _add(self, *mobjects: Any) -> None:
        if self.host is None:
            raise RuntimeError("CodeVisualizer 未 mount")
        for mob in mobjects:
            self.group.add(mob)
            self.host.add(mob)

    def _remove(self, *mobjects: Any) -> None:
        if self.host is None:
            raise RuntimeError("CodeVisualizer 未 mount")
        for mob in mobjects:
            if mob in self.group:
                self.group.remove(mob)
            self.host.remove(mob)

    def _T(self, text: Any, size: int, color: str, *, weight: str = "NORMAL") -> Text:
        return Text(
            str(text),
            font=self.context.code_font,
            font_size=size,
            color=color,
            weight=weight,
        )

    def _build_panel(self) -> None:
        assert self.context is not None
        colors = self.context.theme
        x = self._left + self._width / 2
        y = (self._top + self._bottom) / 2
        bg = RoundedRectangle(
            width=self._width,
            height=self._height,
            corner_radius=0.12,
            fill_color=colors["panel"],
            fill_opacity=0.92,
            stroke_color=colors["border"],
            stroke_width=1.1,
        ).move_to(np.array([x, y, 0]))
        header = Text(
            self.header_text,
            font=self.context.cn_font,
            font_size=self.header_size,
            color=colors["muted"],
            weight="BOLD",
        )
        header.move_to(
            np.array([self._left + 0.14, self._top - 0.22, 0]),
            aligned_edge=np.array([-1, 0, 0]),
        )
        self._panel = VGroup(bg, header)
        self._add(self._panel)

    def _render_code_window(self, active_line: int) -> None:
        assert self.context is not None
        lines = context_lines(self.context)
        if not lines:
            self._visible_start = self._visible_end = 0
            return
        window = CodeWindow(len(lines), self.window_size)
        start, end = window.visible(active_line)
        self._visible_start, self._visible_end = start, end
        colors = self.context.theme
        x = self._left + 0.14
        top = self._top - 0.53
        gap = min(0.37, (self._height - 0.7) / max(self.window_size, 1))
        body = VGroup()
        line_y: dict[int, float] = {}
        for offset, index in enumerate(range(start, end)):
            y = top - offset * gap
            line_y[index + 1] = y
            if self.line_numbers:
                no = self._T(str(index + 1), self.number_size, colors["muted"])
                no.move_to(np.array([x + 0.02, y, 0]), aligned_edge=np.array([-1, 0, 0]))
                body.add(no)
            code = self._T(lines[index] if lines[index] else " ", self.code_size, colors["text"])
            code.move_to(np.array([x + 0.38, y, 0]), aligned_edge=np.array([-1, 0, 0]))
            if code.width > self._width - 0.8:
                code.scale_to_fit_width(self._width - 0.8)
            body.add(code)

        old_body = self._body
        if len(old_body) > 0:
            self._remove(old_body)
        self._body = body
        self._line_y = line_y
        self._add(body)

        if self._highlight is not None:
            self._remove(self._highlight)
        active_y = line_y.get(active_line, top)
        highlight = Rectangle(
            width=self._width - 0.2,
            height=gap * 0.88,
            fill_color=colors["accent"],
            fill_opacity=0.2,
            stroke_width=0,
        ).move_to(np.array([self._left + self._width / 2, active_y, 0]))
        self._highlight = highlight
        self._add(highlight)
        self.host.bring_to_front(body)

    def _move_highlight(self, line: int) -> None:
        y = self._line_y.get(line)
        if y is None or self._highlight is None:
            return
        self._highlight.move_to(np.array([self._left + self._width / 2, y, 0]))


def context_lines(context: ComponentContext | None) -> list[str]:
    if context is None:
        return []
    return context.code.splitlines()
