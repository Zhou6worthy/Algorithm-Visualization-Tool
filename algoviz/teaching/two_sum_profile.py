"""Two Sum 视觉配置 Profile。

Profile 只提供：
- VisualPlan（组件、槽位、options）；
- Two Sum 变量投影。

它不创建 Manim 对象、不执行代码、不控制教学时间轴。
"""
from __future__ import annotations

from typing import Any

from ..protocol.events import AnimationStep, VisualState
from ..protocol.visual import (
    ComponentKind,
    ComponentSpec,
    LayoutBox,
    VisualPlan,
)
from ..render.components.variables import VariableRow
from .two_sum_variables import project_two_sum_variables

# 与 M2/M3 原 Manim 画布一致：16:9、14.222... × 8.0 Manim 单位。
FRAME_WIDTH = 14.222222222222221
FRAME_HEIGHT = 8.0


def _box(cx: float, cy: float, width: float, height: float) -> LayoutBox:
    left = cx - width / 2
    bottom = cy - height / 2
    return LayoutBox(
        x=(left + FRAME_WIDTH / 2) / FRAME_WIDTH,
        y=(bottom + FRAME_HEIGHT / 2) / FRAME_HEIGHT,
        width=width / FRAME_WIDTH,
        height=height / FRAME_HEIGHT,
    )


class TwoSumVisualProfile:
    algorithm = "two_sum"

    def build_visual_plan(self) -> VisualPlan:
        slots = {
            "array": _box(-2.0, 1.55, 8.2, 1.85),
            "hash_map": _box(-4.75, -0.95, 4.2, 2.35),
            "variables": _box(-0.45, -0.95, 4.2, 2.35),
            "code": _box(5.2, -0.2, 3.7, 5.5),
        }
        components = [
            ComponentSpec(
                component_id="array",
                kind=ComponentKind.ARRAY,
                slot="array",
                title="数组 nums",
                options={
                    "title": "数组 nums",
                    "array_name": "nums",
                    "show_target": True,
                    "active_pointer": "i",
                    "found_text": "已命中，结果",
                    "empty_text": "空数组",
                },
            ),
            ComponentSpec(
                component_id="hash_map",
                kind=ComponentKind.HASH_MAP,
                slot="hash_map",
                title="哈希表 seen",
                options={
                    "title": "哈希表 seen",
                    "key_header": "key",
                    "value_header": "index",
                    "max_rows": 4,
                    "empty_text": "{ }  空哈希表",
                    "hit_text": "HIT",
                    "miss_text": "MISS",
                    "waiting_text": "等待下一次查找",
                },
            ),
            ComponentSpec(
                component_id="variables",
                kind=ComponentKind.VARIABLES,
                slot="variables",
                title="关键变量",
                options={
                    "title": "关键变量",
                    "max_rows": 5,
                    "empty_text": "暂无变量",
                    "note": "state_after + 数组指针补全 i/x",
                },
            ),
            ComponentSpec(
                component_id="code",
                kind=ComponentKind.CODE,
                slot="code",
                title="CODE",
                options={
                    "title": "CODE",
                    "window": 14,
                    "line_numbers": True,
                },
            ),
        ]
        return VisualPlan(components=components, slots=slots)

    def project_variables(
        self,
        state: VisualState,
        step: AnimationStep | None = None,
    ) -> list[VariableRow]:
        return project_two_sum_variables(state, step)

    def component_options(self) -> dict[str, dict[str, Any]]:
        """便于测试/调试读取配置；不参与渲染。"""
        return {component.component_id: dict(component.options) for component in self.build_visual_plan().components}
