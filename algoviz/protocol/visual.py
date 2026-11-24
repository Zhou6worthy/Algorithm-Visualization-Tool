"""M3 通用视觉协议：组件组合、槽位和归一化布局。

这一层只描述“画哪些组件、放在哪里”，不包含任何算法语义。
真实状态仍来自 M1 的 ``VisualState``，动画步骤仍来自 ``AnimationStep``。
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import Field, model_validator

from .events import StrictModel


class ComponentKind(str, Enum):
    """可复用的视觉组件类型。"""

    ARRAY = "array"
    HASH_MAP = "hash_map"
    CODE = "code"
    VARIABLES = "variables"
    SEARCH_RANGE = "search_range"
    TREE = "tree"
    GRAPH = "graph"
    DP_TABLE = "dp_table"
    CALL_STACK = "call_stack"
    CUSTOM = "custom"


class LayoutBox(StrictModel):
    """0..1 归一化布局框，原点在画布左下角。

    Manim 和 HTML 各自把归一化坐标映射到自己的画布，避免协议绑定
    Manim 单位或浏览器像素。
    """

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_bounds(self) -> "LayoutBox":
        if self.x + self.width > 1.0 + 1e-6:
            raise ValueError("LayoutBox 的 x + width 不能超过 1")
        if self.y + self.height > 1.0 + 1e-6:
            raise ValueError("LayoutBox 的 y + height 不能超过 1")
        return self


class ComponentSpec(StrictModel):
    """一个组件实例的声明。

    ``options`` 只能放视觉配置（标题、窗口大小、颜色覆盖等），不能放
    算法业务逻辑或执行轨迹。
    """

    component_id: str = Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")
    kind: ComponentKind
    slot: str = Field(min_length=1)
    title: str = ""
    options: dict[str, Any] = Field(default_factory=dict)


class VisualPlan(StrictModel):
    """一次教学演示的组件组合与槽位声明。"""

    schema_version: Literal["0.1"] = "0.1"
    components: list[ComponentSpec] = Field(min_length=1)
    slots: dict[str, LayoutBox] = Field(min_length=1)
    theme: str = "dark"

    @model_validator(mode="after")
    def _check_references(self) -> "VisualPlan":
        ids = [component.component_id for component in self.components]
        if len(ids) != len(set(ids)):
            raise ValueError("VisualPlan.component_id 必须唯一")
        if any(not name for name in self.slots):
            raise ValueError("VisualPlan.slot 名称不能为空")
        missing = sorted({component.slot for component in self.components} - set(self.slots))
        if missing:
            raise ValueError("组件引用了不存在的槽位：" + "、".join(missing))
        return self
