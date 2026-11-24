"""Two Sum 固定场景适配器。

视觉配置由 TwoSumVisualProfile 提供，组件由 VisualAssembler 按 VisualPlan
创建；本类只负责 scene 适配、状态分发和组件生命周期。
"""
from __future__ import annotations

from typing import Any

import numpy as np
from manim import FadeIn, FadeOut, VGroup, config

from ..protocol.cases import CaseRun
from ..protocol.events import AnimationStep, Trace, VisualState
from ..protocol.visual import LayoutBox, VisualPlan
from ..teaching.two_sum_profile import TwoSumVisualProfile
from .components import (
    ComponentContext,
    VariableVisualizer,
    VisualComponent,
    default_registry,
)
from .components.assembler import AssemblyResult, VisualAssembler


class CaseLoadError(RuntimeError):
    pass


class TwoSumStage:
    REQUIRED_IDS = ("array", "hash_map", "variables", "code")

    def __init__(
        self,
        scene: Any,
        *,
        colors: dict[str, str],
        font: str,
        code_font: str,
        code: str,
        profile: TwoSumVisualProfile | None = None,
    ) -> None:
        self.scene = scene
        self.colors = colors
        self.font = font
        self.code_font = code_font
        self.code = code
        self.profile = profile or TwoSumVisualProfile()
        self.assembler = VisualAssembler(default_registry)
        self.visual_plan: VisualPlan | None = None
        self.assembly: AssemblyResult | None = None
        self.animation_trace: Trace | None = None
        self.current_case_id: str | None = None
        self.current_step_index = 0
        self.group = VGroup()
        self.array_visualizer: VisualComponent | None = None
        self.hash_visualizer: VisualComponent | None = None
        self.variable_visualizer: VariableVisualizer | None = None
        self.code_visualizer: VisualComponent | None = None
        self._built = False

    # ------------------------------------------------------------------ 构建
    def build(self, state: VisualState) -> None:
        frame_w = float(config.frame_width)
        frame_h = float(config.frame_height)
        self.visual_plan = self.profile.build_visual_plan()
        base_context = ComponentContext(
            area=LayoutBox(x=0.0, y=0.0, width=1.0, height=1.0),
            theme=self.colors,
            cn_font=self.font,
            code_font=self.code_font,
            language="python",
            code=self.code,
            frame_width=frame_w,
            frame_height=frame_h,
        )
        self.assembly = self.assembler.assemble(
            self.visual_plan,
            self,
            base_context,
            state,
        )
        missing = [component_id for component_id in self.REQUIRED_IDS if component_id not in self.assembly]
        if missing:
            raise RuntimeError("TwoSumVisualProfile 缺少组件：" + "、".join(missing))
        self.array_visualizer = self.assembly.get("array")
        self.hash_visualizer = self.assembly.get("hash_map")
        self.variable_visualizer = self.assembly.get("variables")  # type: ignore[assignment]
        self.code_visualizer = self.assembly.get("code")
        self.variable_visualizer.set_rows(
            self.profile.project_variables(state, None),
            animate=False,
        )
        self.animation_trace = None
        self.current_case_id = None
        self.current_step_index = 0
        self._built = True
        self.scene.play(FadeIn(self.group, shift=np.array([0, 0.05, 0])), run_time=0.28)

    # ------------------------------------------------------------------ 多用例切换
    def load_case(self, case_run: CaseRun) -> None:
        if self.assembly is None or self.variable_visualizer is None:
            raise CaseLoadError("Stage 尚未 build，不能加载 CaseRun")
        trace = case_run.animation_trace
        if trace is None or not trace.steps:
            raise CaseLoadError(f"CaseRun {case_run.run_id} 没有有效 AnimationTrace")
        self.animation_trace = trace
        self.current_case_id = case_run.case_id
        self._load_initial_step(trace.steps[0])

    def reset(self) -> None:
        if self.animation_trace is None or not self.animation_trace.steps:
            raise CaseLoadError("当前没有可重置的 AnimationTrace")
        self._load_initial_step(self.animation_trace.steps[0])

    def _load_initial_step(self, step: AnimationStep) -> None:
        # 所有组件都从目标轨迹的 step 0 状态重建；不重新装配组件。
        self.show_step(step, duration=0.01, animate=False)

    def show_step(
        self,
        step: AnimationStep,
        *,
        duration: float = 0.22,
        animate: bool = True,
    ) -> None:
        """把舞台同步到任意真实 step（教师跳转/自动播放共用这一个入口）。"""
        if self.array_visualizer is not None:
            self.array_visualizer.update(step, 0.01 if not animate else duration)
        if self.hash_visualizer is not None:
            self.hash_visualizer.update(step, 0.01 if not animate else duration)
        if self.variable_visualizer is not None:
            self.variable_visualizer.set_rows(
                self.profile.project_variables(step.state_after, step),
                animate=animate,
            )
            if animate:
                self.variable_visualizer.update(step, duration)
        if self.code_visualizer is not None:
            self.code_visualizer.update(step, 0.01 if not animate else duration)
        self.current_step_index = step.step_id

    # ------------------------------------------------------------------ 场景窄接口
    def add(self, *mobjects: Any) -> None:
        for mob in mobjects:
            self.group.add(mob)
            self.scene.add(mob)

    def remove(self, *mobjects: Any) -> None:
        for mob in mobjects:
            if mob in self.group:
                self.group.remove(mob)
            self.scene.remove(mob)

    def play(self, *animations: Any, run_time: float = 0.25) -> None:
        self.scene.play(*animations, run_time=run_time)

    def wait(self, duration: float) -> None:
        self.scene.wait(duration)

    def bring_to_front(self, *mobjects: Any) -> None:
        self.scene.bring_to_front(*mobjects)

    # ------------------------------------------------------------------ 分发
    def play_step(self, step: AnimationStep, duration: float) -> None:
        self.show_step(step, duration=duration, animate=True)

    def cleanup(self, run_time: float = 0.25) -> None:
        if len(self.group) > 0:
            self.scene.play(FadeOut(self.group), run_time=run_time)
            self.scene.remove(self.group)
        self.group = VGroup()
        self.visual_plan = None
        self.assembly = None
        self.animation_trace = None
        self.current_case_id = None
        self.current_step_index = 0
        self.array_visualizer = None
        self.hash_visualizer = None
        self.variable_visualizer = None
        self.code_visualizer = None
        self._built = False
