"""Binary Search visual configuration.

Profile owns component choice, layout, variable projection and algorithm title.
The Vue renderer consumes its VisualPlan; no algorithm condition belongs in the
workbench or in generic visual components.
"""
from __future__ import annotations

from ..protocol.events import AnimationStep, VisualState
from ..protocol.visual import ComponentKind, ComponentSpec, VisualPlan
from ..render.components.variables import VariableRow
from .two_sum_profile import _box


class BinarySearchVisualProfile:
    algorithm = "binary_search"

    def build_visual_plan(self) -> VisualPlan:
        slots = {
            "array": _box(-2.0, 1.55, 8.2, 1.85),
            "search_range": _box(-4.75, -0.95, 4.2, 2.35),
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
                    "active_pointer": "mid",
                    "empty_text": "空数组",
                },
            ),
            ComponentSpec(
                component_id="search_range",
                kind=ComponentKind.SEARCH_RANGE,
                slot="search_range",
                title="搜索区间",
                options={
                    "title": "搜索区间",
                    "empty_text": "搜索区间为空",
                    "range_label": "候选区间",
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
                    "note": "left / right / mid 来自真实执行状态",
                },
            ),
            ComponentSpec(
                component_id="code",
                kind=ComponentKind.CODE,
                slot="code",
                title="CODE",
                options={"title": "CODE", "window": 14, "line_numbers": True},
            ),
        ]
        return VisualPlan(components=components, slots=slots)

    def project_variables(
        self,
        state: VisualState,
        step: AnimationStep | None = None,
    ) -> list[VariableRow]:
        array = state.array
        pointers = dict(array.pointers) if array else {}
        before = step.state_before.array.pointers if step and step.state_before.array else {}
        rows = []
        for name in ("left", "right", "mid"):
            value = pointers.get(name)
            rows.append(
                VariableRow(
                    name,
                    str(value) if value is not None else "—",
                    changed=before.get(name) != value,
                )
            )
        target = array.target if array else None
        rows.append(VariableRow("target", str(target) if target is not None else "—"))
        active_range = array.active_range if array else None
        rows.append(
            VariableRow(
                "range",
                f"[{active_range[0]}, {active_range[1]}]" if active_range else "—",
            )
        )
        return rows

    def component_options(self) -> dict[str, dict]:
        return {component.component_id: dict(component.options) for component in self.build_visual_plan().components}
