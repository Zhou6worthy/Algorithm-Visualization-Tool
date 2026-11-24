"""Two Sum 教学场景：消费 M2 RenderPlan，渲染 overview / step_by_step。

场景不执行用户代码，也不推断算法操作；所有数组、哈希表、变量和代码行都直接
来自 RenderPlan.trace 中的真实 AnimationStep。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from manim import (
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
from ..protocol.events import AnimationStep, StepType
from ..protocol.m2 import M2SectionKind, RenderPlan, SectionTimeline
from ..timeline import wrap_subtitle
from .theme import THEMES, layout_for
from .two_sum_visuals import TwoSumStage


def _fmt(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


class M2Scene(Scene):
    PLAN_PATH: str = ""

    # ------------------------------------------------------------------ 基础
    def _setup(self) -> None:
        self.plan = RenderPlan.model_validate_json(Path(self.PLAN_PATH).read_text(encoding="utf-8"))
        self.trace = self.plan.trace
        self.teaching = self.plan.teaching
        self.video = self.plan.video
        self.meta = self.trace.metadata
        self.steps = {step.step_id: step for step in self.trace.steps}
        self.colors = THEMES["dark"]
        settings = get_settings()
        self.font = settings.cn_font
        self.code_font = settings.code_font
        self.L = layout_for(config.frame_width, config.frame_height)
        self.camera.background_color = self.colors["bg"]
        self.content = VGroup()
        self.stage: TwoSumStage | None = None
        self._build_header()
        self._build_subtitle_bar()

    def T(
        self,
        text: Any,
        size: int = 22,
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
        self.title_mob = self.T(self.teaching.title, 28, self.colors["text"], weight="BOLD")
        if self.title_mob.width > 9.8:
            self.title_mob.scale_to_fit_width(9.8)
        self.title_mob.move_to(
            np.array([-self.L.frame_w / 2 + self.L.margin, self.L.header_y, 0]),
            aligned_edge=np.array([-1, 0, 0]),
        )
        self.section_mob = self.T("\u00a0", 17, self.colors["muted"])
        self.section_mob.move_to(
            np.array([-self.L.frame_w / 2 + self.L.margin, self.L.header_y - 0.48, 0]),
            aligned_edge=np.array([-1, 0, 0]),
        )
        self.step_mob = self.T("\u00a0", 15, self.colors["muted"])
        self.step_mob.move_to(
            np.array([self.L.frame_w / 2 - self.L.margin, self.L.header_y, 0]),
            aligned_edge=np.array([1, 0, 0]),
        )
        self.header_line = Line(
            np.array([-self.L.frame_w / 2 + self.L.margin, self.L.header_y - 0.7, 0]),
            np.array([self.L.frame_w / 2 - self.L.margin, self.L.header_y - 0.7, 0]),
            stroke_color=self.colors["border"],
            stroke_width=1.0,
        )
        self.add(self.title_mob, self.section_mob, self.step_mob, self.header_line)

    def _build_subtitle_bar(self) -> None:
        y = self.L.subtitle_y
        self.subtitle_bg = RoundedRectangle(
            width=self.L.frame_w - 1.0,
            height=1.08,
            corner_radius=0.14,
            fill_color=self.colors["subtitle_bg"],
            fill_opacity=0.96,
            stroke_color=self.colors["border"],
            stroke_width=0.8,
        ).move_to(np.array([0, y, 0]))
        self.subtitle_text = self.T(" ", 19, self.colors["text"]).move_to(np.array([0, y, 0]))
        self.add(self.subtitle_bg, self.subtitle_text)

    def _set_subtitle(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        wrapped = wrap_subtitle(text, width=44, max_lines=2)
        new = self.T(wrapped, 19, self.colors["text"]).move_to(np.array([0, self.L.subtitle_y, 0]))
        if new.width > self.L.frame_w - 1.35:
            new.scale_to_fit_width(self.L.frame_w - 1.35)
        self.remove(self.subtitle_text)
        self.subtitle_text = new
        self.add(new)

    def _set_section(self, text: str) -> None:
        new = self.T(text, 17, self.colors["muted"]).move_to(
            np.array([-self.L.frame_w / 2 + self.L.margin, self.L.header_y - 0.48, 0]),
            aligned_edge=np.array([-1, 0, 0]),
        )
        self.section_mob.become(new)

    def _set_step_label(self, text: str) -> None:
        new = self.T(text, 15, self.colors["muted"]).move_to(
            np.array([self.L.frame_w / 2 - self.L.margin, self.L.header_y, 0]),
            aligned_edge=np.array([1, 0, 0]),
        )
        self.step_mob.become(new)

    def _pad_to(self, target: float) -> None:
        now = float(self.renderer.time)
        if target - now > 1.0 / max(self.video.fps, 1) * 0.9:
            self.wait(target - now)

    # ------------------------------------------------------------------ 内容
    def _clear_content(self, run_time: float = 0.25) -> None:
        if len(self.content) > 0:
            self.play(FadeOut(self.content), run_time=run_time)
            self.remove(self.content)
            self.content = VGroup()

    def _add_content(self, *mobjects: Any) -> None:
        for mob in mobjects:
            self.content.add(mob)
            self.add(mob)

    def _clear_stage(self, run_time: float = 0.25) -> None:
        if self.stage is not None:
            self.stage.cleanup(run_time)
            self.stage = None

    def _ensure_stage(self) -> TwoSumStage:
        if self.stage is None:
            self._clear_content(0.2)
            initial = self.trace.steps[0].state_before
            self.stage = TwoSumStage(
                self,
                colors=self.colors,
                font=self.font,
                code_font=self.code_font,
                code=self.meta.code,
            )
            self.stage.build(initial)
        return self.stage

    # ------------------------------------------------------------------ 执行段
    def _show_steps(self, section: SectionTimeline) -> None:
        stage = self._ensure_stage()
        cues_by_step = {cue.step_id: cue for cue in section.narration_units if cue.step_id is not None}
        general_cues = [cue for cue in section.narration_units if cue.step_id is None]
        if section.kind in {M2SectionKind.COMPLETE_DEMO, M2SectionKind.REPLAY} and general_cues:
            self._set_subtitle(general_cues[0].text)
        for timing in section.step_timings:
            step = self.steps.get(timing.step_id)
            if step is None:
                continue
            self._pad_to(timing.start)
            cue = cues_by_step.get(timing.step_id)
            if cue is not None:
                self._set_subtitle(cue.text)
            elif section.kind == M2SectionKind.STEPWISE:
                self._set_subtitle(step.description)
            self._set_step_label(f"步骤 {step.step_id + 1} / {len(self.trace.steps)}")
            stage.play_step(step, timing.duration)
            self._pad_to(timing.start + timing.duration)
        self._pad_to(section.start + section.duration)

    # ------------------------------------------------------------------ 思想段
    def _show_idea(self, section: SectionTimeline) -> None:
        self._clear_stage(0.2)
        self._clear_content(0.2)
        self._set_step_label("")
        cue = section.narration_units[0] if section.narration_units else None
        if cue:
            self._set_subtitle(cue.text)
        heading = self.T("核心思想：用哈希表把补数查找降到平均 O(1)", 26, self.colors["accent"], weight="BOLD")
        heading.move_to(
            np.array([-self.L.frame_w / 2 + self.L.margin + 0.1, 2.18, 0]),
            aligned_edge=np.array([-1, 0, 0]),
        )
        formula_box = RoundedRectangle(
            width=self.L.frame_w - 1.2,
            height=1.55,
            corner_radius=0.14,
            fill_color=self.colors["panel"],
            fill_opacity=0.92,
            stroke_color=self.colors["border"],
            stroke_width=1.1,
        ).move_to(np.array([0, 1.05, 0]))
        formula = VGroup(
            self.T("need = target − x", 24, self.colors["compare"], font=self.code_font),
            self.T("seen[x] = i", 20, self.colors["muted"], font=self.code_font),
            self.T("if need in seen:  return [seen[need], i]", 20, self.colors["accent"], font=self.code_font),
        ).arrange(np.array([0, -1, 0]), buff=0.18)
        formula.move_to(formula_box.get_center())
        self._add_content(heading, formula_box, formula)
        self.play(FadeIn(heading, shift=np.array([-0.15, 0, 0])), FadeIn(formula_box), run_time=0.45)
        self.play(Write(formula), run_time=0.55)
        ideas = list(self.teaching.idea) or ["遍历数组", "记录已见值与下标", "补数命中立即返回"]
        cards = VGroup()
        for index, text in enumerate(ideas[:3]):
            card = RoundedRectangle(
                width=3.95,
                height=2.25,
                corner_radius=0.12,
                fill_color=self.colors["panel_alt"],
                fill_opacity=0.9,
                stroke_color=self.colors["border"],
                stroke_width=1.0,
            )
            num = self.T(f"0{index + 1}", 22, self.colors["accent"], weight="BOLD")
            num.move_to(card.get_corner(np.array([-1, 1, 0])) + np.array([0.3, -0.3, 0]))
            body = self.T(text, 18, self.colors["text"])
            if body.width > 3.45:
                body.scale_to_fit_width(3.45)
            body.move_to(card.get_center() + np.array([0.05, -0.15, 0]))
            cards.add(VGroup(card, num, body))
        cards.arrange(np.array([1, 0, 0]), buff=0.2).move_to(np.array([0, -1.2, 0]))
        self._add_content(cards)
        self.play(LaggedStart(*[FadeIn(card, shift=np.array([0, 0.15, 0])) for card in cards], lag_ratio=0.18), run_time=0.8)
        self._pad_to(section.start + section.duration)

    # ------------------------------------------------------------------ 复杂度段
    def _fit(self, mob: Text, width: float) -> Text:
        if mob.width > width:
            mob.scale_to_fit_width(width)
        return mob

    def _complexity_card(
        self,
        x: float,
        title: str,
        accent: str,
        rows: list[tuple[str, str]],
        note: str,
    ) -> VGroup:
        width, height = 4.05, 4.0
        center_y = -0.35
        bg = RoundedRectangle(
            width=width,
            height=height,
            corner_radius=0.14,
            fill_color=self.colors["panel"],
            fill_opacity=0.94,
            stroke_color=accent,
            stroke_width=1.4,
        ).move_to(np.array([x, center_y, 0]))
        heading = self.T(title, 19, accent, weight="BOLD")
        heading.move_to(np.array([x, center_y + height / 2 - 0.32, 0]))
        body = VGroup()
        for label, value in rows:
            l = self.T(label, 14, self.colors["muted"])
            v = self.T(value, 16, self.colors["text"], weight="BOLD")
            line = VGroup(l, v)
            l.move_to(np.array([x - 1.78, 0, 0]), aligned_edge=np.array([-1, 0, 0]))
            v.move_to(np.array([x + 1.78, 0, 0]), aligned_edge=np.array([1, 0, 0]))
            body.add(line)
        body.arrange(np.array([0, -1, 0]), buff=0.18, aligned_edge=np.array([-1, 0, 0]))
        body.move_to(np.array([x, -0.05, 0]))
        note_mob = self.T(note, 12, self.colors["muted"])
        if note_mob.width > 3.55:
            note_mob.scale_to_fit_width(3.55)
        note_mob.move_to(np.array([x, -1.72, 0]))
        return VGroup(bg, heading, body, note_mob)

    def _show_complexity(self, section: SectionTimeline) -> None:
        self._clear_stage(0.2)
        self._clear_content(0.2)
        self._set_step_label("")
        heading = self.T("复杂度三分解", 28, self.colors["accent"], weight="BOLD")
        heading.move_to(
            np.array([-self.L.frame_w / 2 + self.L.margin + 0.1, 2.18, 0]),
            aligned_edge=np.array([-1, 0, 0]),
        )
        sub = self.T("理论复杂度  ·  用户 AC 代码估算  ·  本次真实执行统计", 16, self.colors["muted"])
        sub.move_to(
            np.array([-self.L.frame_w / 2 + self.L.margin + 0.1, 1.78, 0]),
            aligned_edge=np.array([-1, 0, 0]),
        )
        c = self.teaching.complexity
        o = c.observed
        card1 = self._complexity_card(
            -4.55,
            "01 · 理论复杂度",
            self.colors["compare"],
            [("时间", c.theory_time), ("空间", c.theory_space), ("模型", "平均 / 最坏")],
            "哈希表平均 O(1)，冲突最坏 O(n)",
        )
        card2 = self._complexity_card(
            0.0,
            "02 · 用户 AC 代码",
            self.colors["accent"],
            [("时间", c.code_time), ("空间", c.code_space), ("循环", "1 个")],
            "静态结构估算，不是运行时外推",
        )
        card3 = self._complexity_card(
            4.55,
            "03 · 本次实测",
            self.colors["sorted"],
            [
                ("n", str(o.n)),
                ("访问 / 插入", f"{o.visited} / {o.inserts}"),
                ("查找 命中 / 未命中", f"{o.hits} / {o.misses}"),
                ("seen 峰值", f"{o.peak_seen} 项"),
                ("真实事件", f"{o.trace_events} 个"),
                ("耗时", f"{o.duration_ms:.3f} ms"),
            ],
            f"输出 {self.fmt(o.output)}；单样例只描述本次运行",
        )
        cards = VGroup(card1, card2, card3)
        for card in cards:
            card.set_opacity(0.24)
        self._add_content(heading, sub, cards)
        self.play(FadeIn(heading), FadeIn(sub), run_time=0.4)
        for index, cue in enumerate(section.narration_units[:3]):
            self._pad_to(cue.start)
            self._set_subtitle(cue.text)
            if index < len(cards):
                self.play(cards[index].animate.set_opacity(1.0), run_time=0.35)
        self._pad_to(section.start + section.duration)

    # ------------------------------------------------------------------ 主流程
    def construct(self) -> None:
        self._setup()
        handlers = {
            M2SectionKind.COMPLETE_DEMO: self._show_steps,
            M2SectionKind.IDEA: self._show_idea,
            M2SectionKind.STEPWISE: self._show_steps,
            M2SectionKind.COMPLEXITY: self._show_complexity,
            M2SectionKind.REPLAY: self._show_steps,
        }
        for section in self.video.sections:
            self._pad_to(section.start)
            self._set_section(section.title)
            handler = handlers.get(section.kind)
            if handler is not None:
                handler(section)
            self._pad_to(section.start + section.duration)
        self._pad_to(self.video.total_duration)


def build_m2_scene_class(plan_path: str | Path) -> type[M2Scene]:
    class BoundScene(M2Scene):
        PLAN_PATH = str(plan_path)

    BoundScene.__name__ = "AlgoVizScene"
    BoundScene.__qualname__ = "AlgoVizScene"
    return BoundScene
