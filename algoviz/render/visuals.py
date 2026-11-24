"""Manim 可视化组件：数组 / 树 / 图 / DP 矩阵。

组件只消费统一事件协议中的 state_before/state_after，不关心具体算法。
"""
from __future__ import annotations

from typing import Any

import numpy as np
from manim import (
    Arrow,
    Circle,
    FadeIn,
    FadeOut,
    GrowFromCenter,
    Line,
    Rectangle,
    RoundedRectangle,
    Text,
    Transform,
    VGroup,
    Write,
)

from ..protocol.events import AnimationStep, StepType, VisualState

Point = np.ndarray


class VisualBase:
    def __init__(self, scene: Any, area: tuple[float, float, float, float], colors: dict[str, str]) -> None:
        self.scene = scene
        self.colors = colors
        self.xmin, self.xmax, self.ymin, self.ymax = area
        self.width = self.xmax - self.xmin
        self.height = self.ymax - self.ymin
        self.cx = (self.xmin + self.xmax) / 2
        self.cy = (self.ymin + self.ymax) / 2
        self.group = VGroup()
        self.note_text = ""
        self._note_mob = None
        self._built = False

    # ------------------------------------------------------------------ 工具
    def T(
        self,
        text: Any,
        size: int = 24,
        color: str | None = None,
        *,
        font: str | None = None,
        weight: str = "NORMAL",
    ) -> Text:
        return self.scene.T(text, size, color, font=font, weight=weight)

    def add(self, *mobjects: Any) -> None:
        for mob in mobjects:
            self.group.add(mob)
            self.scene.add(mob)

    def remove(self, *mobjects: Any) -> None:
        for mob in mobjects:
            if mob in self.group:
                self.group.remove(mob)
            self.scene.remove(mob)

    def play(self, *animations: Any, run_time: float) -> None:
        if animations:
            self.scene.play(*animations, run_time=max(0.05, run_time))
        else:
            self.scene.wait(max(0.05, run_time))

    def set_note(self, text: str) -> None:
        if not text:
            return
        self.note_text = text
        if self._note_mob is not None:
            self.remove(self._note_mob)
        mob = self.T(text, 18, self.colors["muted"]).to_corner() if False else self.T(text, 18, self.colors["muted"])
        mob.move_to(np.array([self.xmin + 0.15, self.ymax - 0.18, 0]), aligned_edge=np.array([-1, 0, 0]))
        if mob.width > self.width - 0.3:
            mob.scale_to_fit_width(self.width - 0.3)
        self._note_mob = mob
        self.add(mob)

    def cleanup(self, run_time: float = 0.4) -> None:
        if len(self.group) > 0:
            self.scene.play(FadeOut(self.group), run_time=run_time)
        self.group = VGroup()

    # ------------------------------------------------------------------ 子类接口
    def build(self, state: VisualState, animate: bool = True) -> None:
        raise NotImplementedError

    def step(self, step: AnimationStep, run_time: float) -> None:
        raise NotImplementedError


class ArrayVisual(VisualBase):
    def __init__(self, scene: Any, area: tuple[float, float, float, float], colors: dict[str, str]) -> None:
        super().__init__(scene, area, colors)
        self.cells: list[VGroup] = []
        self.positions: list[Point] = []
        self.index_labels: list[Text] = []
        self.cell_w = 0.9
        self.array_y = self.cy + 0.3
        self._pointer_group = VGroup()
        self._pointer_mobs: list[Text] = []
        self._aux_group = VGroup()
        self._aux_mobs: list[Any] = []
        self._target_mob = None
        self._aux_y = self.array_y + 1.35
        self._n = 0

    # ------------------------------------------------------------------ 构建
    def build(self, state: VisualState, animate: bool = True) -> None:
        arr = state.array
        values = list(arr.values)
        n = len(values)
        self._n = n
        self.cell_w = min(0.98, (self.width - 0.5) / max(n, 1) - 0.1)
        gap = min(0.12, self.cell_w * 0.16)
        total = n * self.cell_w + (n - 1) * gap
        start_x = self.cx - total / 2 + self.cell_w / 2
        self.array_y = self.cy + 0.35
        value_size = 26 if self.cell_w >= 0.72 else 22 if self.cell_w >= 0.5 else 18
        self.value_size = value_size
        for index, value in enumerate(values):
            x = start_x + index * (self.cell_w + gap)
            self.positions.append(np.array([x, self.array_y, 0]))
            rect = RoundedRectangle(
                width=self.cell_w,
                height=0.9,
                corner_radius=0.1,
                stroke_color=self.colors["border"],
                stroke_width=2,
                fill_color=self.colors["panel"],
                fill_opacity=0.85,
            )
            label = self.T(value, value_size, self.colors["text"])
            cell = VGroup(rect, label).move_to(self.positions[index])
            self.cells.append(cell)
            self.add(cell)
            idx_label = self.T(index, 16, self.colors["muted"]).move_to(
                np.array([x, self.array_y - 0.68, 0])
            )
            self.index_labels.append(idx_label)
            self.add(idx_label)
        if arr.target is not None:
            self._target_mob = self.T(f"target = {arr.target}", 22, self.colors["accent"]).move_to(
                np.array([self.cx, self.array_y + 1.02, 0])
            )
            self.add(self._target_mob)
        self._render_pointers(arr)
        self._render_aux(state, highlight=[])
        self._base_paint(state)
        self.set_note(state.note or "")
        if animate:
            self.play(FadeIn(self.group, shift=np.array([0, 0.15, 0])), run_time=0.35)

    # ------------------------------------------------------------------ 基础绘制
    def _base_paint(self, state: VisualState) -> None:
        arr = state.array
        sorted_set = set(arr.sorted_indices)
        active = arr.active_range
        for index, cell in enumerate(self.cells):
            rect, label = cell[0], cell[1]
            in_active = active is None or (active[0] <= index <= active[1])
            if index in sorted_set and in_active:
                rect.set_fill(self.colors["sorted"], opacity=0.38)
                rect.set_stroke(self.colors["sorted"], 2)
                label.set_opacity(1.0)
            elif not in_active:
                rect.set_fill(self.colors["panel"], opacity=0.25)
                rect.set_stroke(self.colors["border"], 1.2)
                label.set_opacity(0.45)
            else:
                rect.set_fill(self.colors["panel"], opacity=0.9)
                rect.set_stroke(self.colors["border"], 2)
                label.set_opacity(1.0)

    def _highlight(self, indices: list[int], color: str, opacity: float = 0.55) -> list[Any]:
        animations = []
        for index in indices:
            if 0 <= index < len(self.cells):
                animations.append(self.cells[index][0].animate.set_fill(color, opacity=opacity))
                animations.append(self.cells[index][0].animate.set_stroke(color, 2.5))
        return animations

    def _render_pointers(self, arr) -> None:
        for mob in self._pointer_mobs:
            self.remove(mob)
        self._pointer_mobs = []
        self._pointer_group = VGroup()
        if not arr.pointers:
            return
        by_index: dict[int, list[str]] = {}
        for name, index in arr.pointers.items():
            if 0 <= int(index) < len(self.positions):
                by_index.setdefault(int(index), []).append(name)
        for index in sorted(by_index):
            names = by_index[index]
            for stack, name in enumerate(names):
                chip = self.T(f"{name}={index}", 15, self.colors["accent"])
                chip.move_to(
                    np.array(
                        [
                            self.positions[index][0],
                            self.array_y - 1.0 - 0.24 * stack,
                            0,
                        ]
                    )
                )
                self._pointer_group.add(chip)
                self._pointer_mobs.append(chip)
                self.add(chip)

    def _render_aux(self, state: VisualState, highlight: list[int]) -> None:
        for mob in self._aux_mobs:
            self.remove(mob)
        self._aux_mobs = []
        self._aux_group = VGroup()
        aux = state.array.aux
        if not aux:
            return
        present = [(i, v) for i, v in enumerate(aux) if v is not None]
        if not present:
            return
        label = self.T("合并缓冲", 15, self.colors["muted"])
        label.move_to(np.array([self.xmin + 0.08, self._aux_y + 0.55, 0]), aligned_edge=np.array([-1, 0, 0]))
        self._aux_mobs.append(label)
        self.add(label)
        for index, value in present:
            if index >= len(self.positions):
                continue
            size = self.cell_w * 0.78
            rect = RoundedRectangle(
                width=size,
                height=size * 0.82,
                corner_radius=0.06,
                stroke_color=self.colors["border"],
                stroke_width=1.5,
                fill_color=self.colors["accent"] if index in highlight else self.colors["panel_alt"],
                fill_opacity=0.5 if index in highlight else 0.8,
            )
            text = self.T(value, 17, self.colors["text"])
            cell = VGroup(rect, text).move_to(np.array([self.positions[index][0], self._aux_y, 0]))
            self._aux_mobs.append(cell)
            self.add(cell)

    # ------------------------------------------------------------------ 单步动画
    def step(self, step: AnimationStep, run_time: float) -> None:
        before, after = step.state_before.array, step.state_after.array
        rt = max(0.15, run_time)
        self.set_note(step.state_after.note or step.state_before.note or "")
        targets = [t for t in step.targets if isinstance(t, int)]
        if step.type == StepType.SWAP and len(targets) >= 2:
            i, j = int(targets[0]), int(targets[1])
            if 0 <= i < len(self.cells) and 0 <= j < len(self.cells) and i != j:
                self._base_paint(step.state_before)
                # 只对整组做位移动画；不要在同一次 play 中再动画子对象，
                # 否则 Manim 会把子对象从 VGroup 的动画中拆出来，导致文字漂移。
                self.cells[i][0].set_fill(self.colors["swap"], opacity=0.55)
                self.cells[j][0].set_fill(self.colors["swap"], opacity=0.55)
                self.play(
                    self.cells[i].animate.move_to(self.positions[j]),
                    self.cells[j].animate.move_to(self.positions[i]),
                    run_time=rt * 0.72,
                )
                self.cells[i], self.cells[j] = self.cells[j], self.cells[i]
                self._base_paint(step.state_after)
                self._render_pointers(after)
                self.play(run_time=rt * 0.28)
                return
        if step.type == StepType.UPDATE and targets:
            index = int(targets[0])
            new_value = after.values[index] if 0 <= index < len(after.values) else None
            if 0 <= index < len(self.cells) and new_value is not None:
                self._base_paint(step.state_before)
                new_text = self.T(new_value, self.value_size, self.colors["text"]).move_to(
                    self.cells[index].get_center()
                )
                self.play(
                    Transform(self.cells[index][1], new_text),
                    self.cells[index][0].animate.set_fill(self.colors["swap"], opacity=0.5),
                    run_time=rt * 0.7,
                )
                self._base_paint(step.state_after)
                self._render_pointers(after)
                self._render_aux(step.state_after, highlight=[index])
                self.play(run_time=rt * 0.3)
                return
        if step.type == StepType.COMPLETE:
            self._base_paint(step.state_after)
            self._render_pointers(after)
            self.play(run_time=rt)
            return
        color = self.colors["compare"]
        if step.type in {StepType.SWAP}:
            color = self.colors["swap"]
        elif step.type in {StepType.FOUND, StepType.VISIT}:
            color = self.colors["accent"]
        elif step.type in {StepType.MARK, StepType.COMPLETE}:
            color = self.colors["sorted"]
        elif step.type in {StepType.NOTE, StepType.RELAX}:
            color = self.colors["current"]
        self._base_paint(step.state_before)
        animations = self._highlight(targets, color)
        self.play(*animations, run_time=rt * 0.65)
        self._base_paint(step.state_after)
        self._render_pointers(after)
        self._render_aux(step.state_after, highlight=[])
        self.play(run_time=rt * 0.35)


class TreeVisual(VisualBase):
    def __init__(
        self,
        scene: Any,
        area: tuple[float, float, float, float],
        colors: dict[str, str],
        final_state: VisualState,
    ) -> None:
        super().__init__(scene, area, colors)
        self.final_state = final_state
        self.node_mobs: dict[str, VGroup] = {}
        self.edge_mobs: dict[tuple[str, str], VGroup] = {}
        self.positions: dict[str, Point] = {}
        self.radius = 0.34
        self._output_mob = None
        self._frontier_mob = None
        self._compute_positions()

    def _compute_positions(self) -> None:
        tree = self.final_state.tree
        if not tree or not tree.nodes:
            return
        xs = [node.x for node in tree.nodes]
        depths = [node.depth for node in tree.nodes]
        span = max(max(xs) - min(xs), 1.0)
        max_depth = max(max(depths), 1)
        spacing = min(1.35, (self.width - 1.2) / span)
        level_gap = min(1.15, (self.height - 1.9) / max_depth)
        self.radius = min(0.38, spacing * 0.33)
        y_top = self.ymax - 0.85
        x0 = self.cx - (max(xs) + min(xs)) / 2 * spacing
        for node in tree.nodes:
            self.positions[node.id] = np.array([x0 + node.x * spacing, y_top - node.depth * level_gap, 0])

    def _node(self, node_id: str) -> VGroup:
        return self.node_mobs[node_id]

    def _make_node(self, node) -> VGroup:
        circle = Circle(
            radius=self.radius,
            stroke_color=self.colors["border"],
            stroke_width=2,
            fill_color=self.colors["panel"],
            fill_opacity=0.95,
        )
        label = self.T(node.value, 22 if self.radius >= 0.3 else 17, self.colors["text"])
        group = VGroup(circle, label).move_to(self.positions.get(node.id, np.array([self.cx, self.cy, 0])))
        return group

    def _make_edges(self, state: VisualState) -> None:
        tree = state.tree
        if not tree:
            return
        for node in tree.nodes:
            for child in (node.left, node.right):
                if not child or child not in self.positions:
                    continue
                if child not in self.node_mobs or node.id not in self.node_mobs:
                    continue
                key = (node.id, child)
                if key in self.edge_mobs:
                    continue
                line = Line(
                    self.positions[node.id],
                    self.positions[child],
                    stroke_color=self.colors["edge"],
                    stroke_width=2,
                )
                self.edge_mobs[key] = line
                self.add(line)

    def build(self, state: VisualState, animate: bool = True) -> None:
        tree = state.tree
        if not tree:
            return
        for node in tree.nodes:
            if node.id in self.node_mobs:
                continue
            mob = self._make_node(node)
            self.node_mobs[node.id] = mob
            self.add(mob)
        self._make_edges(state)
        self._update_status(state)
        self.set_note(state.note or "")
        if self.node_mobs:
            self.scene.bring_to_front(*self.node_mobs.values())
        if animate and self.node_mobs:
            self.play(FadeIn(self.group), run_time=0.4)

    def _update_status(self, state: VisualState) -> None:
        tree = state.tree
        if not tree:
            return
        if self._output_mob is not None and self._output_mob in self.group:
            self.remove(self._output_mob)
            self._output_mob = None
        if tree.visited:
            values = []
            for node_id in tree.visited:
                node = next((n for n in tree.nodes if n.id == node_id), None)
                if node:
                    values.append(str(node.value))
            text = "访问序列：" + " → ".join(values)
            mob = self.T(text, 18, self.colors["sorted"])
            mob.move_to(np.array([self.xmin + 0.1, self.ymin + 0.25, 0]), aligned_edge=np.array([-1, 0, 0]))
            if mob.width > self.width - 0.3:
                mob.scale_to_fit_width(self.width - 0.3)
            self._output_mob = mob
            self.add(mob)
        if self._frontier_mob is not None and self._frontier_mob in self.group:
            self.remove(self._frontier_mob)
            self._frontier_mob = None
        if tree.frontier:
            values = []
            for node_id in tree.frontier:
                node = next((n for n in tree.nodes if n.id == node_id), None)
                values.append(str(node.value) if node else node_id)
            mob = self.T("队列：" + "、".join(values), 16, self.colors["accent"])
            mob.move_to(np.array([self.xmax - 0.1, self.ymin + 0.25, 0]), aligned_edge=np.array([1, 0, 0]))
            self._frontier_mob = mob
            self.add(mob)

    def _paint(self, state: VisualState) -> None:
        tree = state.tree
        if not tree:
            return
        visited = set(tree.visited)
        for node_id, mob in self.node_mobs.items():
            circle = mob[0]
            if node_id == tree.current:
                circle.set_fill(self.colors["accent"], opacity=0.55)
                circle.set_stroke(self.colors["accent"], 3)
            elif node_id in visited:
                circle.set_fill(self.colors["sorted"], opacity=0.42)
                circle.set_stroke(self.colors["sorted"], 2)
            else:
                circle.set_fill(self.colors["panel"], opacity=0.95)
                circle.set_stroke(self.colors["border"], 2)
        for (parent, child), line in self.edge_mobs.items():
            if parent in visited and child in visited:
                line.set_stroke(self.colors["sorted"], 2.2, opacity=0.8)
            elif child in visited:
                line.set_stroke(self.colors["accent"], 2.4, opacity=0.8)
            else:
                line.set_stroke(self.colors["edge"], 2)

    def step(self, step: AnimationStep, run_time: float) -> None:
        rt = max(0.15, run_time)
        after = step.state_after.tree
        self.set_note(step.state_after.note or step.state_before.note or "")
        if step.type == StepType.CREATE:
            for node_id in step.targets:
                node_id = str(node_id)
                if node_id in self.node_mobs:
                    continue
                node = next((n for n in after.nodes if n.id == node_id), None)
                if node is None:
                    continue
                mob = self._make_node(node)
                self.node_mobs[node_id] = mob
                self.add(mob)
                self.scene.bring_to_front(mob)
                self._make_edges(step.state_after)
                self.play(GrowFromCenter(mob), run_time=rt * 0.75)
            self._paint(step.state_after)
            self._update_status(step.state_after)
            self.play(run_time=rt * 0.25)
            return
        self._paint(step.state_before)
        animations = []
        for node_id in step.targets:
            node_id = str(node_id)
            if node_id in self.node_mobs:
                circle = self.node_mobs[node_id][0]
                color = self.colors["accent"] if step.type in {StepType.VISIT, StepType.FOUND} else self.colors["compare"]
                if step.type == StepType.VISIT:
                    color = self.colors["sorted"]
                animations.append(circle.animate.set_fill(color, opacity=0.6))
                animations.append(circle.animate.set_stroke(color, 3))
        self.play(*animations, run_time=rt * 0.6)
        self._paint(step.state_after)
        self._update_status(step.state_after)
        self.play(run_time=rt * 0.4)


class GraphVisual(VisualBase):
    def __init__(self, scene: Any, area: tuple[float, float, float, float], colors: dict[str, str], final_state: VisualState) -> None:
        super().__init__(scene, area, colors)
        self.final_state = final_state
        self.node_mobs: dict[str, VGroup] = {}
        self.edge_mobs: dict[tuple[str, str], VGroup] = {}
        self.node_pos: dict[str, Point] = {}
        self.radius = 0.33
        self._status_mob = None
        self._compute_positions()

    def _compute_positions(self) -> None:
        graph = self.final_state.graph
        if not graph:
            return
        xs = [n.x for n in graph.nodes]
        ys = [n.y for n in graph.nodes]
        span_x = max(max(xs) - min(xs), 0.001)
        span_y = max(max(ys) - min(ys), 0.001)
        usable_w = self.width - 1.3
        usable_h = self.height - 1.9
        scale = min(usable_w / span_x, usable_h / span_y)
        mid_x = (max(xs) + min(xs)) / 2
        mid_y = (max(ys) + min(ys)) / 2
        for node in graph.nodes:
            self.node_pos[node.id] = np.array(
                [self.cx + (node.x - mid_x) * scale, self.cy + 0.1 + (node.y - mid_y) * scale, 0]
            )
        # 避免节点重叠：最少间距
        self.radius = 0.33

    def _edge_key(self, u: str, v: str, directed: bool) -> tuple[str, str]:
        return (u, v) if directed else tuple(sorted((u, v)))  # type: ignore[return-value]

    def build(self, state: VisualState, animate: bool = True) -> None:
        graph = state.graph
        if not graph:
            return
        for edge in graph.edges:
            key = self._edge_key(edge.source, edge.target, edge.directed)
            if key in self.edge_mobs:
                continue
            if edge.source not in self.node_pos or edge.target not in self.node_pos:
                continue
            start, end = self.node_pos[edge.source], self.node_pos[edge.target]
            direction = end - start
            norm = np.linalg.norm(direction)
            if norm > 0:
                unit = direction / norm
                start = start + unit * self.radius
                end = end - unit * self.radius
            if edge.directed:
                line: Any = Arrow(
                    start,
                    end,
                    buff=0,
                    stroke_width=2,
                    color=self.colors["edge"],
                    tip_length=0.16,
                )
            else:
                line = Line(start, end, stroke_color=self.colors["edge"], stroke_width=2)
            group = VGroup(line)
            if abs(edge.weight - 1.0) > 1e-9:
                label = self.T(self.scene.fmt(edge.weight), 15, self.colors["muted"])
                label.move_to((start + end) / 2 + np.array([0.0, 0.16, 0]))
                group.add(label)
            self.edge_mobs[key] = group
            self.add(group)
        for node in graph.nodes:
            circle = Circle(
                radius=self.radius,
                stroke_color=self.colors["border"],
                stroke_width=2,
                fill_color=self.colors["panel"],
                fill_opacity=0.98,
            )
            label = self.T(node.label or node.id, 20, self.colors["text"])
            group = VGroup(circle, label).move_to(self.node_pos[node.id])
            self.node_mobs[node.id] = group
            self.add(group)
        self.set_note(state.note or "")
        self._update_status(state)
        if animate:
            self.play(FadeIn(self.group), run_time=0.4)

    def _update_status(self, state: VisualState) -> None:
        graph = state.graph
        if not graph:
            return
        if self._status_mob is not None and self._status_mob in self.group:
            self.remove(self._status_mob)
            self._status_mob = None
        if graph.distances:
            parts = []
            for node in graph.nodes:
                value = graph.distances.get(node.id)
                parts.append(f"{node.id}={'∞' if value is None else self.scene.fmt(value)}")
            text = "最短距离：" + "   ".join(parts)
            color = self.colors["accent"]
        elif graph.visited:
            text = "访问顺序：" + " → ".join(graph.visited)
            color = self.colors["sorted"]
        elif graph.frontier:
            text = "队列/栈：" + "、".join(graph.frontier)
            color = self.colors["accent"]
        else:
            return
        mob = self.T(text, 17, color)
        mob.move_to(np.array([self.xmin + 0.1, self.ymin + 0.28, 0]), aligned_edge=np.array([-1, 0, 0]))
        if mob.width > self.width - 0.25:
            mob.scale_to_fit_width(self.width - 0.25)
        self._status_mob = mob
        self.add(mob)

    def _paint(self, state: VisualState) -> None:
        graph = state.graph
        if not graph:
            return
        visited = set(graph.visited)
        path = set(graph.path)
        for node_id, mob in self.node_mobs.items():
            circle = mob[0]
            if node_id in path:
                circle.set_fill(self.colors["accent"], opacity=0.55)
                circle.set_stroke(self.colors["accent"], 3)
            elif node_id == graph.current:
                circle.set_fill(self.colors["accent"], opacity=0.6)
                circle.set_stroke(self.colors["accent"], 3)
            elif node_id in visited:
                circle.set_fill(self.colors["sorted"], opacity=0.4)
                circle.set_stroke(self.colors["sorted"], 2)
            elif node_id in graph.frontier:
                circle.set_fill(self.colors["panel"], opacity=0.95)
                circle.set_stroke(self.colors["current"], 2.4)
            else:
                circle.set_fill(self.colors["panel"], opacity=0.95)
                circle.set_stroke(self.colors["border"], 2)
        path_edges = set()
        for i in range(len(graph.path) - 1):
            path_edges.add(self._edge_key(graph.path[i], graph.path[i + 1], False))
        for edge in graph.edges:
            key = self._edge_key(edge.source, edge.target, edge.directed)
            mob = self.edge_mobs.get(key)
            if mob is None:
                continue
            line = mob[0]
            if edge.active:
                line.set_stroke(self.colors["accent"], 4, opacity=1)
            elif key in path_edges:
                line.set_stroke(self.colors["accent"], 3.2, opacity=1)
            else:
                line.set_stroke(self.colors["edge"], 2, opacity=0.75)

    def step(self, step: AnimationStep, run_time: float) -> None:
        rt = max(0.15, run_time)
        self.set_note(step.state_after.note or step.state_before.note or "")
        self._paint(step.state_before)
        color = self.colors["accent"]
        if step.type in {StepType.RELAX, StepType.ENQUEUE, StepType.PUSH}:
            color = self.colors["compare"]
        elif step.type in {StepType.VISIT, StepType.FOUND}:
            color = self.colors["sorted"]
        animations = []
        for target in step.targets:
            node_id = str(target)
            if node_id in self.node_mobs:
                animations.append(self.node_mobs[node_id][0].animate.set_stroke(color, 3.2))
        self.play(*animations, run_time=rt * 0.55)
        self._paint(step.state_after)
        self._update_status(step.state_after)
        self.play(run_time=rt * 0.45)


class MatrixVisual(VisualBase):
    def __init__(self, scene: Any, area: tuple[float, float, float, float], colors: dict[str, str]) -> None:
        super().__init__(scene, area, colors)
        self.cells: list[list[VGroup]] = []
        self.cell_size = 0.6
        self._legend_mob = None
        self._answer_mob = None
        self._grid_origin = np.array([self.cx, self.cy, 0])

    def build(self, state: VisualState, animate: bool = True) -> None:
        matrix = state.matrix
        if not matrix:
            return
        rows, cols = matrix.rows, matrix.cols
        size = min(0.66, (self.width - 1.3) / max(cols, 1), (self.height - 1.8) / max(rows, 1))
        self.cell_size = size
        grid_w = cols * size
        grid_h = rows * size
        top_y = self.ymax - 0.85
        left_x = self.cx - grid_w / 2
        self._grid_origin = np.array([left_x, top_y, 0])
        for i in range(rows):
            row_cells: list[VGroup] = []
            for j in range(cols):
                x = left_x + j * size + size / 2
                y = top_y - i * size - size / 2
                rect = Rectangle(
                    width=size,
                    height=size,
                    stroke_color=self.colors["border"],
                    stroke_width=1.4,
                    fill_color=self.colors["panel"],
                    fill_opacity=0.9,
                )
                value = matrix.table[i][j] if i < len(matrix.table) and j < len(matrix.table[i]) else ""
                text = self.T(value, 19 if size >= 0.55 else 16, self.colors["text"])
                cell = VGroup(rect, text).move_to(np.array([x, y, 0]))
                row_cells.append(cell)
                self.add(cell)
            self.cells.append(row_cells)
        for i, header in enumerate(matrix.row_headers[:rows]):
            y = top_y - i * size - size / 2
            text = self.T(header, 16, self.colors["muted"])
            text.move_to(np.array([left_x - 0.42, y, 0]))
            self.add(text)
        for j, header in enumerate(matrix.col_headers[:cols]):
            x = left_x + j * size + size / 2
            text = self.T(header, 16, self.colors["muted"])
            text.move_to(np.array([x, top_y + 0.32, 0]))
            self.add(text)
        if matrix.legend:
            text = "   ".join(matrix.legend)
            mob = self.T(text, 15, self.colors["muted"])
            mob.move_to(np.array([self.xmin + 0.1, self.ymin + 0.22, 0]), aligned_edge=np.array([-1, 0, 0]))
            if mob.width > self.width - 0.2:
                mob.scale_to_fit_width(self.width - 0.2)
            self._legend_mob = mob
            self.add(mob)
        self.set_note(state.note or "")
        self._paint(state)
        if animate:
            self.play(FadeIn(self.group), run_time=0.4)

    def _cell_center(self, i: int, j: int) -> Point:
        size = self.cell_size
        return np.array(
            [self._grid_origin[0] + j * size + size / 2, self._grid_origin[1] - i * size - size / 2, 0]
        )

    def _paint(self, state: VisualState) -> None:
        matrix = state.matrix
        if not matrix:
            return
        deps = {tuple(dep) for dep in matrix.dependencies}
        path = {tuple(p) for p in matrix.path}
        for i in range(len(self.cells)):
            for j in range(len(self.cells[i])):
                rect = self.cells[i][j][0]
                if matrix.current == [i, j]:
                    rect.set_fill(self.colors["accent"], opacity=0.45)
                    rect.set_stroke(self.colors["accent"], 2.6)
                elif (i, j) in path:
                    rect.set_fill(self.colors["sorted"], opacity=0.42)
                    rect.set_stroke(self.colors["sorted"], 2.2)
                elif (i, j) in deps:
                    rect.set_fill(self.colors["compare"], opacity=0.25)
                    rect.set_stroke(self.colors["compare"], 2.2)
                else:
                    rect.set_fill(self.colors["panel"], opacity=0.9)
                    rect.set_stroke(self.colors["border"], 1.4)

    def step(self, step: AnimationStep, run_time: float) -> None:
        rt = max(0.15, run_time)
        matrix = step.state_after.matrix
        self.set_note(step.state_after.note or step.state_before.note or "")
        self._paint(step.state_before)
        if step.type == StepType.UPDATE and isinstance(step.targets, list) and len(step.targets) >= 2:
            i, j = int(step.targets[0]), int(step.targets[1])
            if 0 <= i < len(self.cells) and 0 <= j < len(self.cells[i]):
                value = matrix.table[i][j] if i < len(matrix.table) and j < len(matrix.table[i]) else ""
                new_text = self.T(value, 19 if self.cell_size >= 0.55 else 16, self.colors["text"]).move_to(
                    self.cells[i][j].get_center()
                )
                self.play(
                    Transform(self.cells[i][j][1], new_text),
                    self.cells[i][j][0].animate.set_fill(self.colors["accent"], opacity=0.45),
                    run_time=rt * 0.65,
                )
                self._paint(step.state_after)
                self.play(run_time=rt * 0.35)
                return
        if step.type == StepType.BACKTRACK:
            animations = []
            for i, j in matrix.path:
                if 0 <= i < len(self.cells) and 0 <= j < len(self.cells[i]):
                    animations.append(self.cells[i][j][0].animate.set_fill(self.colors["sorted"], opacity=0.5))
            self.play(*animations, run_time=rt * 0.7)
            self._paint(step.state_after)
            self.play(run_time=rt * 0.3)
            return
        self.play(run_time=rt * 0.4)
        self._paint(step.state_after)
