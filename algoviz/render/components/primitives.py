"""通用视觉 primitive：卡片、文本样式。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from manim import Line, RoundedRectangle, Text, VGroup

from .base import ComponentContext


@dataclass(frozen=True)
class CardFrame:
    panel: VGroup
    left: float
    bottom: float
    width: float
    height: float
    left_x: float
    top_y: float
    center_x: float
    center_y: float


def make_text(
    context: ComponentContext,
    text: Any,
    size: int,
    color: str,
    *,
    weight: str = "NORMAL",
    code: bool = False,
) -> Text:
    return Text(
        str(text),
        font=context.code_font if code else context.cn_font,
        font_size=size,
        color=color,
        weight=weight,
    )


def make_card(
    context: ComponentContext,
    title: str,
    *,
    title_size: int = 17,
) -> CardFrame:
    left, bottom, width, height = context.manim_box()
    center_x = left + width / 2
    center_y = bottom + height / 2
    top = bottom + height
    colors = context.theme
    bg = RoundedRectangle(
        width=width,
        height=height,
        corner_radius=0.12,
        fill_color=colors["panel"],
        fill_opacity=0.92,
        stroke_color=colors["border"],
        stroke_width=1.1,
    ).move_to(np.array([center_x, center_y, 0]))
    title_mob = make_text(context, title, title_size, colors["muted"], weight="BOLD")
    title_mob.move_to(
        np.array([left + 0.18, top - 0.25, 0]),
        aligned_edge=np.array([-1, 0, 0]),
    )
    rule = Line(
        np.array([left + 0.12, top - 0.48, 0]),
        np.array([left + width - 0.12, top - 0.48, 0]),
        stroke_color=colors["border"],
        stroke_width=0.7,
    )
    return CardFrame(
        panel=VGroup(bg, title_mob, rule),
        left=left,
        bottom=bottom,
        width=width,
        height=height,
        left_x=left,
        top_y=top,
        center_x=center_x,
        center_y=center_y,
    )
