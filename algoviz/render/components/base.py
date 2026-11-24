"""组件基础设施：上下文、窄场景接口和组件协议。

组件只负责视觉呈现；它不读取 ExecutionTrace，也不判断算法名称。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from ...protocol.events import AnimationStep, VisualState
from ...protocol.visual import ComponentKind, LayoutBox


@dataclass(frozen=True)
class ComponentContext:
    """组件渲染所需的非算法上下文。

    ``area`` 使用 0..1 归一化坐标；``manim_box`` 负责转换到 Manim 单位。
    """

    area: LayoutBox
    theme: Mapping[str, str]
    cn_font: str
    code_font: str
    language: str = "python"
    code: str = ""
    frame_width: float = 14.222222222222221
    frame_height: float = 8.0

    def manim_box(self) -> tuple[float, float, float, float]:
        """返回 Manim 坐标中的 (left, bottom, width, height)。"""
        left = -self.frame_width / 2 + self.area.x * self.frame_width
        bottom = -self.frame_height / 2 + self.area.y * self.frame_height
        width = self.area.width * self.frame_width
        height = self.area.height * self.frame_height
        return left, bottom, width, height


class SceneHost(Protocol):
    """组件可使用的窄场景接口，避免依赖完整 Manim Scene 生命周期。"""

    def add(self, *mobjects: Any) -> None: ...

    def remove(self, *mobjects: Any) -> None: ...

    def play(self, *animations: Any, run_time: float = 0.25) -> None: ...

    def wait(self, duration: float) -> None: ...

    def bring_to_front(self, *mobjects: Any) -> None: ...


class VisualComponent(Protocol):
    """通用视觉组件协议。"""

    kind: ComponentKind

    def mount(
        self,
        host: SceneHost,
        context: ComponentContext,
        state: VisualState,
    ) -> None: ...

    def update(self, step: AnimationStep, duration: float) -> None: ...

    def unmount(self, run_time: float = 0.2) -> None: ...
