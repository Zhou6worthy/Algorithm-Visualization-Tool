"""通用数组/索引/指针/高亮组件。

只消费 ``VisualState.array`` 与当前 ``AnimationStep``；不包含任何算法名称、
补数、查找或循环语义。
"""
from __future__ import annotations

from typing import Any

import numpy as np
from manim import FadeIn, FadeOut, RoundedRectangle, Transform, VGroup

from ...protocol.events import AnimationStep, VisualState
from ...protocol.visual import ComponentKind
from .base import ComponentContext, SceneHost
from .primitives import make_card, make_text


class ArrayVisualizer:
    kind = ComponentKind.ARRAY

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
        self.title = str(self.options.get("title", "数组"))
        self.array_name = str(self.options.get("array_name", "array"))
        self.show_target = bool(self.options.get("show_target", True))
        self.active_pointer = str(self.options.get("active_pointer", "i"))
        self.show_current = bool(self.options.get("show_current", True))
        self.found_text = str(self.options.get("found_text", "已标记"))
        self.empty_text = str(self.options.get("empty_text", "空数组"))
        self.group = VGroup()
        self._panel = VGroup()
        self._body = VGroup()
        self._frame = None
        self._cells: list[VGroup] = []
        self._cell_positions: list[np.ndarray] = []
        self._index_labels: list[Any] = []
        self._pointer_mobs: list[Any] = []
        self._pointer_text_values: list[str] = []
        self._target_mob: Any = None
        self._target_value: Any = None
        self._active_mob: Any = None
        self._empty_mob: Any = None
        self._values: list[Any] = []
        self._found: set[int] = set()
        self._pointers: dict[str, int] = {}
        self._cell_w = 0.9

    # ------------------------------------------------------------------ 协议
    def mount(
        self,
        host: SceneHost,
        context: ComponentContext,
        state: VisualState,
    ) -> None:
        self.host = host
        self.context = context
        self._frame = make_card(context, self.title)
        self._panel = self._frame.panel
        self._add(self._panel)
        self._build_body(state)

    def update(self, step: AnimationStep, duration: float) -> None:
        assert self.host is not None and self.context is not None
        after = step.state_after.array
        if after is None:
            return
        old_values = list(self._values)
        new_values = list(after.values)
        if len(old_values) != len(new_values):
            old = self._body
            self._build_body(step.state_after)
            self.host.play(FadeOut(old), FadeIn(self._body), run_time=0.22)
            return
        rt = max(0.12, min(0.26, duration * 0.3))
        animations: list[Any] = []
        for index, value in enumerate(new_values):
            if index < len(self._cells) and str(old_values[index]) != str(value):
                new_text = make_text(
                    self.context,
                    value,
                    24,
                    self.context.theme["text"],
                    weight="BOLD",
                )
                new_text.move_to(self._cells[index].get_center())
                animations.append(Transform(self._cells[index][1], new_text))
        self._values = new_values
        self._found = set(after.found_indices)
        self._pointers = dict(after.pointers)
        animations.extend(self._paint(after, animate=True))
        animations.extend(self._refresh_pointers(after, animate=True))
        animations.extend(self._refresh_status(after, animate=True))
        animations.extend(self._refresh_target(after, animate=True))
        if animations:
            self.host.play(*animations, run_time=rt)

    def unmount(self, run_time: float = 0.2) -> None:
        if self.host is not None and len(self.group) > 0:
            self.host.play(FadeOut(self.group), run_time=max(0.05, run_time))
            self.host.remove(self.group)
        self.group = VGroup()
        self._body = VGroup()
        self._cells = []

    # ------------------------------------------------------------------ 查询
    @property
    def displayed_values(self) -> list[Any]:
        return list(self._values)

    @property
    def cell_count(self) -> int:
        return len(self._cells)

    @property
    def index_values(self) -> list[int]:
        return list(range(len(self._values)))

    @property
    def pointer_texts(self) -> list[str]:
        return list(self._pointer_text_values)

    @property
    def found_indices(self) -> list[int]:
        return sorted(self._found)

    @property
    def target_text(self) -> str | None:
        if self._target_value is None:
            return None
        return f"target = {self._target_value}"

    @property
    def is_empty(self) -> bool:
        return not self._values

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

    def _build_body(self, state: VisualState) -> None:
        assert self.context is not None and self._frame is not None
        if len(self._body) > 0:
            self._remove(self._body)
        for mob in self._pointer_mobs:
            self._remove(mob)
        body = VGroup()
        self._cells = []
        self._cell_positions = []
        self._index_labels = []
        self._pointer_mobs = []
        self._pointer_text_values = []
        self._target_mob = None
        self._active_mob = None
        self._empty_mob = None
        arr = state.array
        self._target_value = arr.target if arr is not None else None
        self._values = list(arr.values) if arr else []
        self._found = set(arr.found_indices) if arr else set()
        self._pointers = dict(arr.pointers) if arr else {}
        frame = self._frame
        if not self._values:
            self._empty_mob = make_text(
                self.context, self.empty_text, 18, self.context.theme["muted"]
            )
            self._empty_mob.move_to(np.array([frame.center_x, frame.center_y, 0]))
            body.add(self._empty_mob)
        else:
            n = len(self._values)
            self._cell_w = min(1.15, (7.4 - 0.2 * (n - 1)) / n)
            gap = 0.2
            total = n * self._cell_w + (n - 1) * gap
            start_x = frame.center_x - total / 2 + self._cell_w / 2
            for index, value in enumerate(self._values):
                x = start_x + index * (self._cell_w + gap)
                self._cell_positions.append(np.array([x, frame.center_y, 0]))
                rect = RoundedRectangle(
                    width=self._cell_w,
                    height=0.9,
                    corner_radius=0.09,
                    fill_color=self.context.theme["panel_alt"],
                    fill_opacity=0.9,
                    stroke_color=self.context.theme["border"],
                    stroke_width=1.6,
                )
                label = make_text(
                    self.context, value, 24, self.context.theme["text"], weight="BOLD"
                )
                cell = VGroup(rect, label).move_to(self._cell_positions[index])
                self._cells.append(cell)
                body.add(cell)
                idx = make_text(self.context, index, 13, self.context.theme["muted"])
                idx.move_to(np.array([x, frame.center_y - 0.63, 0]))
                self._index_labels.append(idx)
                body.add(idx)
            self._active_mob = make_text(
                self.context,
                f"当前元素：—",
                14,
                self.context.theme["muted"],
            )
            self._active_mob.move_to(
                np.array([frame.left_x + 0.18, frame.center_y - 0.83, 0]),
                aligned_edge=np.array([-1, 0, 0]),
            )
            body.add(self._active_mob)
            if self.show_target and arr is not None and arr.target is not None:
                self._target_mob = make_text(
                    self.context,
                    f"target = {arr.target}",
                    16,
                    self.context.theme["accent"],
                )
                self._target_mob.move_to(
                    np.array([frame.left_x + frame.width - 0.18, frame.top_y - 0.25, 0]),
                    aligned_edge=np.array([1, 0, 0]),
                )
                body.add(self._target_mob)
            self._paint(arr, animate=False)
            self._refresh_pointers(arr, animate=False)
            self._refresh_status(arr, animate=False)
        self._body = body
        self._add(body)

    # ------------------------------------------------------------------ 状态
    def _paint(self, arr: Any, *, animate: bool) -> list[Any]:
        assert self.context is not None
        animations: list[Any] = []
        active = arr.pointers.get(self.active_pointer) if arr else None
        found = set(arr.found_indices) if arr else set()
        for index, cell in enumerate(self._cells):
            rect = cell[0]
            if index in found:
                fill, stroke, opacity = self.context.theme["sorted"], self.context.theme["sorted"], 0.42
            elif active is not None and index == active:
                fill, stroke, opacity = self.context.theme["accent"], self.context.theme["accent"], 0.35
            else:
                fill, stroke, opacity = self.context.theme["panel_alt"], self.context.theme["border"], 0.9
            if animate:
                animations.append(rect.animate.set_fill(fill, opacity=opacity).set_stroke(stroke, 2.2))
            else:
                rect.set_fill(fill, opacity=opacity)
                rect.set_stroke(stroke, 2.2)
        return animations

    def _refresh_pointers(self, arr: Any, *, animate: bool) -> list[Any]:
        for mob in self._pointer_mobs:
            self._remove(mob)
        self._pointer_mobs = []
        self._pointer_text_values = []
        if arr is None or not arr.pointers:
            return []
        animations: list[Any] = []
        for name, index in arr.pointers.items():
            if not (0 <= int(index) < len(self._cell_positions)):
                continue
            chip = make_text(
                self.context,
                f"{name} = {index}",
                13,
                self.context.theme["compare"],
            )
            chip.move_to(np.array([self._cell_positions[int(index)][0], 2.17, 0]))
            self._pointer_mobs.append(chip)
            self._pointer_text_values.append(f"{name} = {index}")
            self._add(chip)
            if animate:
                animations.append(FadeIn(chip, shift=np.array([0, -0.08, 0])))
        return animations

    def _refresh_target(self, arr: Any, *, animate: bool) -> list[Any]:
        assert self.context is not None and self._frame is not None
        if not self.show_target or arr is None or arr.target is None:
            self._target_value = None
            if self._target_mob is not None:
                mob = self._target_mob
                self._target_mob = None
                self._remove(mob)
            return []
        self._target_value = arr.target
        new = make_text(
            self.context,
            f"target = {arr.target}",
            16,
            self.context.theme["accent"],
        )
        new.move_to(
            np.array([self._frame.left_x + self._frame.width - 0.18, self._frame.top_y - 0.25, 0]),
            aligned_edge=np.array([1, 0, 0]),
        )
        if self._target_mob is None:
            self._target_mob = new
            self._add(new)
            return []
        self._target_mob.become(new)
        return []

    def _refresh_status(self, arr: Any, *, animate: bool) -> list[Any]:
        assert self.context is not None
        if self._active_mob is None or arr is None:
            return []
        active = arr.pointers.get(self.active_pointer)
        found = set(arr.found_indices)
        if active is not None and 0 <= int(active) < len(arr.values):
            text = f"当前元素：{self.array_name}[{active}] = {arr.values[int(active)]}"
            color = self.context.theme["accent"]
        elif found:
            text = f"当前元素：{self.found_text} {sorted(found)}"
            color = self.context.theme["accent"]
        else:
            text = "当前元素：—"
            color = self.context.theme["muted"]
        new = make_text(self.context, text, 14, color)
        new.move_to(self._active_mob.get_center())
        if animate:
            return [self._active_mob.animate.become(new)]
        self._active_mob.become(new)
        return []
