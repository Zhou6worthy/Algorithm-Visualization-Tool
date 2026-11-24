"""视觉主题与布局常量（Manim 坐标系，frame 默认 14.22 × 8）。"""
from __future__ import annotations

from dataclasses import dataclass

THEMES = {
    "dark": {
        "bg": "#0B1220",
        "panel": "#16233D",
        "panel_alt": "#1C2B49",
        "border": "#2A3B5E",
        "text": "#E8EEF9",
        "muted": "#9AA9C2",
        "accent": "#FBBF24",
        "compare": "#38BDF8",
        "swap": "#F472B6",
        "sorted": "#34D399",
        "current": "#FB923C",
        "edge": "#54657F",
        "subtitle_bg": "#0E1729",
        "danger": "#F87171",
        "grid": "#22314F",
    },
    "light": {
        "bg": "#F7F8FA",
        "panel": "#FFFFFF",
        "panel_alt": "#EEF2F7",
        "border": "#CBD5E1",
        "text": "#1E293B",
        "muted": "#64748B",
        "accent": "#D97706",
        "compare": "#2563EB",
        "swap": "#DB2777",
        "sorted": "#059669",
        "current": "#EA580C",
        "edge": "#94A3B8",
        "subtitle_bg": "#FFFFFF",
        "danger": "#DC2626",
        "grid": "#E2E8F0",
    },
}


@dataclass(frozen=True)
class Layout:
    frame_w: float
    frame_h: float
    margin: float
    header_y: float
    content_top: float
    content_bottom: float
    subtitle_y: float
    code_panel_x: float
    code_panel_w: float

    @property
    def visual_area(self) -> tuple[float, float, float, float]:
        """有代码面板时，左侧可视化区域 (xmin, xmax, ymin, ymax)。"""
        return (
            -self.frame_w / 2 + self.margin,
            self.code_panel_x - self.code_panel_w / 2 - 0.18,
            self.content_bottom,
            self.content_top,
        )

    @property
    def full_area(self) -> tuple[float, float, float, float]:
        return (
            -self.frame_w / 2 + self.margin,
            self.frame_w / 2 - self.margin,
            self.content_bottom,
            self.content_top,
        )


def layout_for(frame_w: float = 14.222, frame_h: float = 8.0) -> Layout:
    margin = 0.4
    return Layout(
        frame_w=frame_w,
        frame_h=frame_h,
        margin=margin,
        header_y=frame_h / 2 - 0.62,
        content_top=frame_h / 2 - 1.35,
        content_bottom=-frame_h / 2 + 1.05,
        subtitle_y=-frame_h / 2 + 0.58,
        code_panel_x=frame_w / 2 - 2.35,
        code_panel_w=4.15,
    )
