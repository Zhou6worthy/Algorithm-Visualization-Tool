"""由 ScenePlan 驱动的 Manim 场景。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from manim import (
    Circle,
    FadeIn,
    FadeOut,
    LaggedStart,
    Line,
    Rectangle,
    RoundedRectangle,
    Scene,
    Text,
    VGroup,
    Write,
    config,
)

from ..config import get_settings
from ..protocol.events import StepType, VisualKind
from ..protocol.teaching import ScenePlan, SegmentKind, TeachingSegment
from ..timeline import wrap_subtitle
from .theme import THEMES, layout_for
from .visuals import ArrayVisual, GraphVisual, MatrixVisual, TreeVisual, VisualBase

TITLE_LIMIT = 9.5


def _fmt(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def input_summary(plan: ScenePlan) -> str:
    meta = plan.trace.metadata
    data = meta.input
    if meta.category in {"sort", "search"}:
        values = data.get("array", [])
        text = "输入数组：[" + ", ".join(_fmt(v) for v in values) + "]"
        if meta.category == "search":
            text += f"，目标值：{_fmt(data.get('target'))}"
        return text
    if meta.category == "tree":
        values = data.get("values", data.get("array", []))
        text = "输入节点序列：[" + ", ".join(_fmt(v) for v in values) + "]"
        if meta.algorithm == "bst_search":
            text += f"，查找目标：{_fmt(data.get('target'))}"
        return text
    if meta.category == "graph":
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        return f"输入图：{len(nodes)} 个节点、{len(edges)} 条边，起点 {data.get('start', '')}"
    if meta.algorithm == "knapsack_01":
        return f"输入：{len(data.get('weights', []))} 个物品，背包容量 {data.get('capacity')}"
    if meta.algorithm == "lcs":
        return f"输入字符串：\"{data.get('s1')}\" 与 \"{data.get('s2')}\""
    return ""


class AlgoVizScene(Scene):
    PLAN_PATH: str = ""

    # ------------------------------------------------------------------ 基础设施
    def _setup(self) -> None:
        self.plan = ScenePlan.model_validate_json(Path(self.PLAN_PATH).read_text(encoding="utf-8"))
        self.trace = self.plan.trace
        self.script = self.plan.script
        self.meta = self.trace.metadata
        self.colors = THEMES.get(self.plan.theme, THEMES["dark"])
        settings = get_settings()
        self.font = settings.cn_font
        self.code_font = settings.code_font
        self.L = layout_for(config.frame_width, config.frame_height)
        self.camera.background_color = self.colors["bg"]
        self.timings = {timing.step_id: timing for timing in self.plan.step_timings}
        self.steps = {step.step_id: step for step in self.trace.steps}
        self.content = VGroup()
        self.visual: VisualBase | None = None
        self.code_panel: VGroup | None = None
        self.code_lines_group: VGroup | None = None
        self.code_highlight: Rectangle | None = None
        self.code_window: tuple[int, int] = (0, 0)
        self.code_line_y: dict[int, float] = {}
        self.exec_started = False
        self._build_header()
        self._build_subtitle_bar()

    def T(
        self,
        text: Any,
        size: int = 24,
        color: str | None = None,
        *,
        font: str | None = None,
        weight: str = "NORMAL",
    ) -> Text:
        return Text(
            str(text),
            font=font or self.font,
            font_size=size,
            color=color or self.colors["text"],
            weight=weight,
        )

    @staticmethod
    def fmt(value: Any) -> str:
        return _fmt(value)

    def _build_header(self) -> None:
        self.title_mob = self.T(self.script.title, 30, self.colors["text"], weight="BOLD")
        if self.title_mob.width > TITLE_LIMIT:
            self.title_mob.scale_to_fit_width(TITLE_LIMIT)
        self.title_mob.move_to(
            np.array([-self.L.frame_w / 2 + self.L.margin, self.L.header_y, 0]),
            aligned_edge=np.array([-1, 0, 0]),
        )
        self.section_mob = self.T("\u00a0", 18, self.colors["muted"])
        self.section_mob.move_to(
            np.array([-self.L.frame_w / 2 + self.L.margin, self.L.header_y - 0.55, 0]),
            aligned_edge=np.array([-1, 0, 0]),
        )
        self.step_mob = self.T("\u00a0", 17, self.colors["muted"])
        self.step_mob.move_to(
            np.array([self.L.frame_w / 2 - self.L.margin, self.L.header_y, 0]),
            aligned_edge=np.array([1, 0, 0]),
        )
        self.header_line = Line(
            np.array([-self.L.frame_w / 2 + self.L.margin, self.L.header_y - 0.78, 0]),
            np.array([self.L.frame_w / 2 - self.L.margin, self.L.header_y - 0.78, 0]),
            stroke_color=self.colors["border"],
            stroke_width=1.2,
        )
        self.add(self.title_mob, self.section_mob, self.step_mob, self.header_line)

    def _build_subtitle_bar(self) -> None:
        y = self.L.subtitle_y
        self.subtitle_bg = RoundedRectangle(
            width=self.L.frame_w - 1.1,
            height=1.14,
            corner_radius=0.16,
            fill_color=self.colors["subtitle_bg"],
            fill_opacity=0.94,
            stroke_color=self.colors["border"],
            stroke_width=1,
        ).move_to(np.array([0, y, 0]))
        self.subtitle_text = self.T(" ", 22, self.colors["text"]).move_to(np.array([0, y, 0]))
        self.add(self.subtitle_bg, self.subtitle_text)

    def _set_subtitle(self, text: str) -> None:
        wrapped = wrap_subtitle(text, width=36, max_lines=2)
        new = self.T(wrapped, 22, self.colors["text"]).move_to(
            np.array([0, self.L.subtitle_y, 0])
        )
        if new.width > self.L.frame_w - 1.5:
            new.scale_to_fit_width(self.L.frame_w - 1.5)
        self.remove(self.subtitle_text)
        self.subtitle_text = new
        self.add(new)

    def _set_section(self, text: str) -> None:
        new = self.T(text, 18, self.colors["muted"]).move_to(
            np.array([-self.L.frame_w / 2 + self.L.margin, self.L.header_y - 0.55, 0]),
            aligned_edge=np.array([-1, 0, 0]),
        )
        self.section_mob.become(new)

    def _set_step_label(self, text: str) -> None:
        new = self.T(text, 17, self.colors["muted"]).move_to(
            np.array([self.L.frame_w / 2 - self.L.margin, self.L.header_y, 0]),
            aligned_edge=np.array([1, 0, 0]),
        )
        self.step_mob.become(new)

    def _pad_to(self, target: float) -> None:
        now = float(self.renderer.time)
        if target - now > 1.0 / max(self.plan.fps, 1) * 0.9:
            self.wait(target - now)

    # ------------------------------------------------------------------ 内容管理
    def _clear_content(self, run_time: float = 0.35) -> None:
        if len(self.content) > 0:
            self.play(FadeOut(self.content), run_time=run_time)
            self.remove(self.content)
            self.content = VGroup()

    def _add_content(self, *mobjects: Any) -> None:
        for mob in mobjects:
            self.content.add(mob)
            self.add(mob)

    # ------------------------------------------------------------------ 各章节
    def _show_intro(self, segment: TeachingSegment) -> None:
        self._set_section("01 · 问题引入")
        self._clear_content(0.2)
        title = self.T(self.script.title, 44, self.colors["text"], weight="BOLD")
        if title.width > self.L.frame_w - 2.0:
            title.scale_to_fit_width(self.L.frame_w - 2.0)
        title.move_to(np.array([0, 1.35, 0]))
        tagline = self.T(
            f"{self._category_name()} · 时间 {self.meta.complexity.time} · 空间 {self.meta.complexity.space}",
            22,
            self.colors["accent"],
        ).move_to(np.array([0, 0.55, 0]))
        input_line = self.T(input_summary(self.plan), 23, self.colors["muted"])
        if input_line.width > self.L.frame_w - 2.2:
            input_line.scale_to_fit_width(self.L.frame_w - 2.2)
        input_line.move_to(np.array([0, -0.3, 0]))
        problem = self.T(self._wrap_display(self.script.problem, 30), 22, self.colors["muted"])
        if problem.width > self.L.frame_w - 2.2:
            problem.scale_to_fit_width(self.L.frame_w - 2.2)
        problem.move_to(np.array([0, -1.35, 0]))
        self._add_content(title, tagline, input_line, problem)
        self.play(
            FadeIn(title, shift=np.array([0, -0.2, 0])),
            FadeIn(tagline),
            FadeIn(input_line),
            FadeIn(problem),
            run_time=1.1,
        )

    def _show_idea(self, segment: TeachingSegment) -> None:
        self._set_section("02 · 核心思想")
        self._clear_content(0.3)
        heading = self.T("核心思想", 34, self.colors["accent"], weight="BOLD")
        heading.move_to(
            np.array([-self.L.frame_w / 2 + self.L.margin + 0.1, 2.0, 0]),
            aligned_edge=np.array([-1, 0, 0]),
        )
        bullets = VGroup()
        for idea in self.script.idea[:4]:
            dot = Circle(
                radius=0.07,
                fill_color=self.colors["accent"],
                fill_opacity=1,
                stroke_width=0,
            )
            text = self.T(self._wrap_display(idea, 34), 24, self.colors["text"])
            if text.width > 11.6:
                text.scale_to_fit_width(11.6)
            item = VGroup(dot, text).arrange(np.array([1, 0, 0]), buff=0.28, aligned_edge=np.array([0, 1, 0]))
            bullets.add(item)
        bullets.arrange(np.array([0, -1, 0]), buff=0.45, aligned_edge=np.array([-1, 0, 0]))
        bullets.move_to(
            np.array([-self.L.frame_w / 2 + self.L.margin + 0.35, 0.55, 0]),
            aligned_edge=np.array([-1, 0, 0]),
        )
        if bullets.height > 4.4:
            bullets.scale_to_fit_height(4.4)
        self._add_content(heading, bullets)
        self.play(FadeIn(heading, shift=np.array([-0.2, 0, 0])), run_time=0.5)
        self.play(
            LaggedStart(*[FadeIn(item, shift=np.array([0.2, 0, 0])) for item in bullets], lag_ratio=0.22),
            run_time=1.0,
        )

    # ------------------------------------------------------------------ 执行章节
    def _ensure_execution(self) -> None:
        if self.exec_started:
            return
        self._clear_content(0.3)
        area = self.L.visual_area
        final_state = self.trace.steps[-1].state_after
        # 第 0 步是 init：state_after 才是算法开始时的可见状态
        initial_state = self.trace.steps[0].state_after
        kind = self.meta.visual_kind
        if kind == VisualKind.ARRAY:
            self.visual = ArrayVisual(self, area, self.colors)
        elif kind == VisualKind.TREE:
            self.visual = TreeVisual(self, area, self.colors, final_state)
        elif kind == VisualKind.GRAPH:
            self.visual = GraphVisual(self, area, self.colors, final_state)
        else:
            self.visual = MatrixVisual(self, area, self.colors)
        self.visual.build(initial_state)
        self._build_code_panel()
        self.exec_started = True

    def _build_code_panel(self) -> None:
        code = self.meta.code or ""
        x = self.L.code_panel_x
        y = (self.L.content_top + self.L.content_bottom) / 2
        height = self.L.content_top - self.L.content_bottom
        width = self.L.code_panel_w
        self.code_panel = VGroup()
        bg = RoundedRectangle(
            width=width,
            height=height,
            corner_radius=0.14,
            fill_color=self.colors["panel"],
            fill_opacity=0.9,
            stroke_color=self.colors["border"],
            stroke_width=1.2,
        ).move_to(np.array([x, y, 0]))
        header = self.T(f"CODE · {self.meta.code_language}", 16, self.colors["muted"]).move_to(
            np.array([x - width / 2 + 0.16, y + height / 2 - 0.26, 0]),
            aligned_edge=np.array([-1, 0, 0]),
        )
        separator = Line(
            np.array([x - width / 2 + 0.1, y + height / 2 - 0.48, 0]),
            np.array([x + width / 2 - 0.1, y + height / 2 - 0.48, 0]),
            stroke_color=self.colors["border"],
            stroke_width=0.8,
        )
        self.code_panel.add(bg, header, separator)
        self.add(self.code_panel)
        self.play(FadeIn(self.code_panel), run_time=0.3)
        first_line = next((step.code_line for step in self.trace.steps if step.code_line), 1)
        self._render_code_window(max(1, first_line))
        if self.code_highlight is not None:
            self._highlight_code(first_line or 1)

    def _render_code_window(self, active_line: int) -> None:
        code = (self.meta.code or "").splitlines()
        if not code:
            return
        if self.code_lines_group is not None:
            self.remove(self.code_lines_group)
            self.code_lines_group = VGroup()
        if self.code_highlight is not None:
            self.remove(self.code_highlight)
            self.code_highlight = None
        window_size = 14
        start = max(0, min(len(code) - window_size, active_line - 8))
        end = min(len(code), start + window_size)
        self.code_window = (start, end)
        x = self.L.code_panel_x - self.L.code_panel_w / 2 + 0.16
        top_y = self.L.content_top - 0.85
        line_gap = min(0.28, (self.L.content_top - self.L.content_bottom - 1.2) / max(window_size, 1))
        self.code_line_y = {}
        group = VGroup()
        for offset, index in enumerate(range(start, end)):
            y = top_y - offset * line_gap
            line_y = round(y, 4)
            self.code_line_y[index + 1] = line_y
            text = Text(
                code[index] if code[index] else " ",
                font=self.code_font,
                font_size=15,
                color=self.colors["text"],
            )
            if text.width > self.L.code_panel_w - 0.3:
                text.scale_to_fit_width(self.L.code_panel_w - 0.3)
            text.move_to(np.array([x, y, 0]), aligned_edge=np.array([-1, 0, 0]))
            group.add(text)
        if start > 0:
            ellipsis = self.T("…", 14, self.colors["muted"]).move_to(
                np.array([x, top_y + line_gap, 0]), aligned_edge=np.array([-1, 0, 0])
            )
            group.add(ellipsis)
        if end < len(code):
            ellipsis = self.T("…", 14, self.colors["muted"]).move_to(
                np.array([x, top_y - (end - start) * line_gap, 0]), aligned_edge=np.array([-1, 0, 0])
            )
            group.add(ellipsis)
        self.code_lines_group = group
        self.add(group)
        highlight = Rectangle(
            width=self.L.code_panel_w - 0.14,
            height=line_gap * 0.95,
            fill_color=self.colors["accent"],
            fill_opacity=0.18,
            stroke_width=0,
        ).move_to(np.array([self.L.code_panel_x, top_y - (active_line - start - 1) * line_gap, 0]))
        self.code_highlight = highlight
        self.add(highlight)
        self.bring_to_front(group)

    def _highlight_code(self, line: int) -> None:
        if not self.code_line_y:
            return
        start, end = self.code_window
        if not (start < line <= end):
            self._render_code_window(line)
            return
        y = self.code_line_y.get(line)
        if y is None:
            return
        if self.code_highlight is None:
            return
        self.code_highlight.move_to(np.array([self.L.code_panel_x, y, 0]))

    def _show_execution(self, segment: TeachingSegment) -> None:
        self._set_section("03 · 执行过程")
        self._ensure_execution()
        if segment.step_start is None or segment.step_end is None:
            return
        for step_id in range(segment.step_start, segment.step_end + 1):
            step = self.steps.get(step_id)
            timing = self.timings.get(step_id)
            if step is None or timing is None:
                continue
            self._set_step_label(f"步骤 {step_id + 1} / {len(self.trace.steps)}")
            if step.code_line:
                self._highlight_code(step.code_line)
            self._pad_to(segment.start + timing.start)
            if self.visual is not None:
                self.visual.step(step, timing.duration)
            self._pad_to(segment.start + timing.start + timing.duration)

    # ------------------------------------------------------------------ 代码章节
    def _show_code(self, segment: TeachingSegment) -> None:
        self._set_section("04 · 代码对应")
        if self.visual is not None:
            self.visual.cleanup(0.4)
            self.visual = None
        self._clear_content(0.25)
        if self.code_panel is None:
            self._build_code_panel()
        heading = self.T("代码对应", 34, self.colors["accent"], weight="BOLD")
        heading.move_to(
            np.array([-self.L.frame_w / 2 + self.L.margin + 0.1, 2.05, 0]),
            aligned_edge=np.array([-1, 0, 0]),
        )
        heading_sub = self.T("动画中的每个操作，都能在代码中找到对应行", 21, self.colors["muted"])
        heading_sub.move_to(
            np.array([-self.L.frame_w / 2 + self.L.margin + 0.1, 1.55, 0]),
            aligned_edge=np.array([-1, 0, 0]),
        )
        code_lines = (self.meta.code or "").splitlines()
        mapping = VGroup()
        seen: set[StepType] = set()
        labels = [
            (StepType.COMPARE, "比较"),
            (StepType.SWAP, "交换"),
            (StepType.UPDATE, "写入"),
            (StepType.VISIT, "访问"),
            (StepType.FOUND, "命中"),
            (StepType.MARK, "标记"),
        ]
        for step_type, label in labels:
            if step_type in seen:
                continue
            step = next(
                (s for s in self.trace.steps if s.type == step_type and s.code_line and s.code_line <= len(code_lines)),
                None,
            )
            if step is None:
                continue
            seen.add(step_type)
            snippet = code_lines[step.code_line - 1].strip()
            if len(snippet) > 34:
                snippet = snippet[:33] + "…"
            line = self.T(f"{label}  →  {snippet}", 20, self.colors["text"])
            if line.width > self.L.visual_area[1] - self.L.visual_area[0] - 0.4:
                line.scale_to_fit_width(self.L.visual_area[1] - self.L.visual_area[0] - 0.4)
            line.move_to(
                np.array([self.L.visual_area[0] + 0.1, 0.75 - len(mapping) * 0.75, 0]),
                aligned_edge=np.array([-1, 0, 0]),
            )
            mapping.add(line)
            if len(mapping) >= 4:
                break
        self._add_content(heading, heading_sub, mapping)
        self.play(FadeIn(heading), FadeIn(heading_sub), run_time=0.6)
        if len(mapping) > 0:
            self.play(LaggedStart(*[FadeIn(item, shift=np.array([0.2, 0, 0])) for item in mapping], lag_ratio=0.2), run_time=1.0)
        compare_step = next((s for s in self.trace.steps if s.type == StepType.COMPARE and s.code_line), None)
        if compare_step and compare_step.code_line:
            self._highlight_code(compare_step.code_line)

    # ------------------------------------------------------------------ 复杂度 / 总结
    def _show_complexity(self, segment: TeachingSegment) -> None:
        self._set_section("05 · 复杂度分析")
        self._clear_content(0.3)
        if self.code_panel is not None:
            self.play(FadeOut(self.code_panel), run_time=0.3)
            self.remove(self.code_panel)
            if self.code_lines_group is not None:
                self.remove(self.code_lines_group)
            if self.code_highlight is not None:
                self.remove(self.code_highlight)
            self.code_panel = None
            self.code_lines_group = None
            self.code_highlight = None
        heading = self.T("复杂度分析", 34, self.colors["accent"], weight="BOLD")
        heading.move_to(
            np.array([-self.L.frame_w / 2 + self.L.margin + 0.1, 2.15, 0]),
            aligned_edge=np.array([-1, 0, 0]),
        )
        time_card = self._make_card("时间复杂度", self.meta.complexity.time, self.colors["accent"], -3.0, 1.0)
        space_card = self._make_card("空间复杂度", self.meta.complexity.space, self.colors["sorted"], 3.0, 1.0)
        points = VGroup()
        for point in self.script.complexity_points[:3]:
            text = self.T("· " + self._wrap_display(point, 40), 20, self.colors["muted"])
            if text.width > self.L.frame_w - 2.4:
                text.scale_to_fit_width(self.L.frame_w - 2.4)
            points.add(text)
        if len(points) > 0:
            points.arrange(np.array([0, -1, 0]), buff=0.25, aligned_edge=np.array([-1, 0, 0]))
            points.move_to(
                np.array([-self.L.frame_w / 2 + self.L.margin + 0.4, -1.15, 0]),
                aligned_edge=np.array([-1, 0, 0]),
            )
        self._add_content(heading, time_card, space_card, points)
        self.play(FadeIn(heading), run_time=0.5)
        self.play(FadeIn(time_card, shift=np.array([0, -0.2, 0])), FadeIn(space_card, shift=np.array([0, -0.2, 0])), run_time=0.8)
        if len(points) > 0:
            self.play(FadeIn(points), run_time=0.6)

    def _make_card(self, label: str, value: str, color: str, x: float, y: float) -> VGroup:
        rect = RoundedRectangle(
            width=5.0,
            height=1.8,
            corner_radius=0.16,
            fill_color=self.colors["panel"],
            fill_opacity=0.95,
            stroke_color=color,
            stroke_width=2,
        ).move_to(np.array([x, y, 0]))
        label_mob = self.T(label, 19, self.colors["muted"]).move_to(
            np.array([x, y + 0.45, 0])
        )
        value_mob = self.T(value, 40, color, weight="BOLD").move_to(np.array([x, y - 0.25, 0]))
        if value_mob.width > 4.5:
            value_mob.scale_to_fit_width(4.5)
        return VGroup(rect, label_mob, value_mob)

    def _show_summary(self, segment: TeachingSegment) -> None:
        self._set_section("06 · 总结")
        self._clear_content(0.3)
        heading = self.T("总结", 34, self.colors["accent"], weight="BOLD")
        heading.move_to(
            np.array([-self.L.frame_w / 2 + self.L.margin + 0.1, 2.05, 0]),
            aligned_edge=np.array([-1, 0, 0]),
        )
        bullets = VGroup()
        for item in self.script.summary[:4]:
            dot = Circle(radius=0.06, fill_color=self.colors["sorted"], fill_opacity=1, stroke_width=0)
            text = self.T(self._wrap_display(item, 36), 23, self.colors["text"])
            if text.width > 11.4:
                text.scale_to_fit_width(11.4)
            bullet = VGroup(dot, text).arrange(np.array([1, 0, 0]), buff=0.25, aligned_edge=np.array([0, 1, 0]))
            bullets.add(bullet)
        if len(bullets) > 0:
            bullets.arrange(np.array([0, -1, 0]), buff=0.42, aligned_edge=np.array([-1, 0, 0]))
            bullets.move_to(
                np.array([-self.L.frame_w / 2 + self.L.margin + 0.4, 0.8, 0]),
                aligned_edge=np.array([-1, 0, 0]),
            )
        footer_text = f"AlgoViz · 自动生成 · {self.meta.algorithm}"
        if self.script.ai_credit:
            footer_text = f"AlgoViz · {self.script.ai_credit} · {self.meta.algorithm}"
        footer = self.T(footer_text, 18, self.colors["muted"]).move_to(
            np.array([0, -2.35, 0])
        )
        self._add_content(heading, bullets, footer)
        self.play(FadeIn(heading), run_time=0.5)
        if len(bullets) > 0:
            self.play(
                LaggedStart(*[FadeIn(item, shift=np.array([0.2, 0, 0])) for item in bullets], lag_ratio=0.2),
                run_time=1.0,
            )
        self.play(FadeIn(footer), run_time=0.4)

    # ------------------------------------------------------------------ 工具
    def _category_name(self) -> str:
        return {
            "sort": "排序算法",
            "search": "查找算法",
            "tree": "树结构",
            "graph": "图算法",
            "dp": "动态规划",
        }.get(self.meta.category, "算法")

    def _wrap_display(self, text: str, max_chars: int) -> str:
        text = str(text).strip()
        lines: list[str] = []
        current = ""
        width = 0
        for char in text:
            char_width = 2 if ord(char) > 127 else 1
            if width + char_width > max_chars * 2 and current:
                lines.append(current)
                current = ""
                width = 0
            current += char
            width += char_width
        if current:
            lines.append(current)
        return "\n".join(lines)

    # ------------------------------------------------------------------ 主流程
    def construct(self) -> None:
        self._setup()
        handlers = {
            SegmentKind.INTRO: self._show_intro,
            SegmentKind.IDEA: self._show_idea,
            SegmentKind.EXECUTION: self._show_execution,
            SegmentKind.CODE: self._show_code,
            SegmentKind.COMPLEXITY: self._show_complexity,
            SegmentKind.SUMMARY: self._show_summary,
        }
        for segment in self.script.segments:
            self._pad_to(segment.start)
            self._set_subtitle(segment.subtitle or segment.narration)
            handler = handlers.get(segment.kind)
            if handler is not None:
                handler(segment)
            self._pad_to(segment.start + segment.duration)
        self._pad_to(self.plan.total_duration)


def build_scene_class(plan_path: str | Path) -> type[AlgoVizScene]:
    class BoundScene(AlgoVizScene):
        PLAN_PATH = str(plan_path)

    BoundScene.__name__ = "AlgoVizScene"
    BoundScene.__qualname__ = "AlgoVizScene"
    return BoundScene
