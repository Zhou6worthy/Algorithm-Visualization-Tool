"""通用哈希表/键值/查询状态组件。

只消费 ``VisualState.dict_state`` 和当前 ``AnimationStep`` 的变化；
不包含任何题目的 key 名称、查询规则或返回规则。
"""
from __future__ import annotations

from typing import Any

import numpy as np
from manim import FadeIn, FadeOut, RoundedRectangle, VGroup

from ...protocol.events import AnimationStep, VisualState
from ...protocol.visual import ComponentKind
from .base import ComponentContext, SceneHost
from .primitives import make_card, make_text


class HashMapVisualizer:
    kind = ComponentKind.HASH_MAP

    def __init__(
        self,
        *,
        host: SceneHost | None = None,
        context: ComponentContext | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        self.host = host
        self.context = context
        self.options = dict(options or {})
        self.title = str(self.options.get("title", "哈希表"))
        self.key_header = str(self.options.get("key_header", "key"))
        self.value_header = str(self.options.get("value_header", "value"))
        self.max_rows = max(1, int(self.options.get("max_rows", 4)))
        self.empty_text = str(self.options.get("empty_text", "{ }  空哈希表"))
        self.hit_text = str(self.options.get("hit_text", "HIT"))
        self.miss_text = str(self.options.get("miss_text", "MISS"))
        self.waiting_text = str(self.options.get("waiting_text", "等待下一次查找"))
        self.group = VGroup()
        self._panel = VGroup()
        self._body = VGroup()
        self._frame = None
        self._count_mob: Any = None
        self._entries: list[Any] = []
        self._lookup_key: str | None = None
        self._lookup_status: str | None = None
        self._highlighted_keys: set[str] = set()

    # ------------------------------------------------------------------ 协议
    def mount(
        self,
        host: SceneHost,
        context: ComponentContext,
        state: VisualState,
    ) -> None:
        self.host = host
        self.context = context
        self._frame = make_card(context, self.title)
        self._panel = self._frame.panel
        self._add(self._panel)
        self._count_mob = make_text(context, "0 项", 13, context.theme["muted"])
        self._count_mob.move_to(
            np.array([self._frame.left_x + self._frame.width - 0.16, self._frame.top_y - 0.25, 0]),
            aligned_edge=np.array([1, 0, 0]),
        )
        self._add(self._count_mob)
        self._body = self._make_body(state)
        self._add(self._body)
        self._update_count()

    def update(self, step: AnimationStep, duration: float) -> None:
        assert self.host is not None
        before = step.state_before.dict_state
        after = step.state_after.dict_state
        changed = set()
        if before is not None and after is not None:
            old = {entry.key: entry.value for entry in before.entries}
            new = {entry.key: entry.value for entry in after.entries}
            changed = {key for key, value in new.items() if key not in old or old[key] != value}
        old_body = self._body
        new_body = self._make_body(step.state_after, changed_keys=changed)
        self._add(new_body)
        rt = max(0.12, min(0.26, duration * 0.3))
        self.host.play(FadeOut(old_body), FadeIn(new_body), run_time=rt)
        if len(old_body) > 0:
            self._remove(old_body)
        self._body = new_body
        self._update_count()

    def unmount(self, run_time: float = 0.2) -> None:
        if self.host is not None and len(self.group) > 0:
            self.host.play(FadeOut(self.group), run_time=max(0.05, run_time))
            self.host.remove(self.group)
        self.group = VGroup()
        self._body = VGroup()
        self._entries = []

    # ------------------------------------------------------------------ 查询
    @property
    def displayed_keys(self) -> list[str]:
        return [entry.key for entry in self._entries]

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    @property
    def lookup_status(self) -> str | None:
        return self._lookup_status

    @property
    def lookup_key(self) -> str | None:
        return self._lookup_key

    @property
    def highlighted_keys(self) -> list[str]:
        return sorted(self._highlighted_keys)

    @property
    def is_empty(self) -> bool:
        return not self._entries

    # ------------------------------------------------------------------ 构建
    def _add(self, *mobjects: Any) -> None:
        assert self.host is not None
        for mob in mobjects:
            self.group.add(mob)
            self.host.add(mob)

    def _remove(self, *mobjects: Any) -> None:
        assert self.host is not None
        for mob in mobjects:
            if mob in self.group:
                self.group.remove(mob)
            self.host.remove(mob)

    def _make_body(
        self,
        state: VisualState,
        *,
        changed_keys: set[str] | None = None,
    ) -> VGroup:
        assert self.context is not None and self._frame is not None
        changed = changed_keys or set()
        d = state.dict_state
        self._entries = list(d.entries) if d else []
        self._lookup_key = d.lookup_key if d else None
        self._lookup_status = d.lookup_status if d else None
        self._highlighted_keys = set()
        body = VGroup()
        frame = self._frame
        if not self._entries:
            empty = make_text(self.context, self.empty_text, 17, self.context.theme["muted"])
            empty.move_to(np.array([frame.center_x, frame.center_y, 0]))
            body.add(empty)
        else:
            header = make_text(
                self.context,
                f"{self.key_header}  →  {self.value_header}",
                13,
                self.context.theme["muted"],
            )
            header.move_to(
                np.array([frame.left_x + 0.2, frame.top_y - 0.62, 0]),
                aligned_edge=np.array([-1, 0, 0]),
            )
            body.add(header)
            for row, entry in enumerate(self._entries[: self.max_rows]):
                y = frame.top_y - 0.985 - row * 0.30
                is_hit = entry.highlighted or (
                    d is not None
                    and d.lookup_status == "hit"
                    and d.lookup_key == entry.key
                )
                is_changed = entry.key in changed
                color = (
                    self.context.theme["accent"]
                    if is_hit or is_changed
                    else self.context.theme["text"]
                )
                if is_hit or is_changed:
                    self._highlighted_keys.add(entry.key)
                    glow = RoundedRectangle(
                        width=frame.width - 0.5,
                        height=0.25,
                        corner_radius=0.05,
                        fill_color=self.context.theme["accent"],
                        fill_opacity=0.14,
                        stroke_width=0,
                    ).move_to(np.array([frame.center_x, y, 0]))
                    body.add(glow)
                key = make_text(
                    self.context,
                    entry.key,
                    16,
                    color,
                    weight="BOLD" if is_hit or is_changed else "NORMAL",
                )
                key.move_to(np.array([frame.left_x + 0.4, y, 0]), aligned_edge=np.array([-1, 0, 0]))
                arrow = make_text(self.context, "→", 14, self.context.theme["muted"])
                arrow.move_to(np.array([frame.left_x + 1.1, y, 0]))
                value = make_text(
                    self.context,
                    entry.value,
                    16,
                    color,
                )
                value.move_to(np.array([frame.left_x + 1.6, y, 0]), aligned_edge=np.array([-1, 0, 0]))
                body.add(key, arrow, value)
        if self._lookup_key is not None:
            label = make_text(
                self.context,
                f"查找 {self._lookup_key}",
                14,
                self.context.theme["muted"],
            )
            label.move_to(
                np.array([frame.left_x + 0.2, frame.top_y - 2.12, 0]),
                aligned_edge=np.array([-1, 0, 0]),
            )
            body.add(label)
            if self._lookup_status == "hit":
                body.add(self._pill(self.hit_text, self.context.theme["sorted"]).move_to(
                    np.array([frame.center_x + 0.6, frame.top_y - 2.12, 0])
                ))
            elif self._lookup_status == "miss":
                body.add(self._pill(self.miss_text, self.context.theme["danger"]).move_to(
                    np.array([frame.center_x + 0.6, frame.top_y - 2.12, 0])
                ))
        else:
            waiting = make_text(
                self.context,
                self.waiting_text,
                13,
                self.context.theme["muted"],
            )
            waiting.move_to(
                np.array([frame.left_x + 0.2, frame.top_y - 2.12, 0]),
                aligned_edge=np.array([-1, 0, 0]),
            )
            body.add(waiting)
        return body

    def _update_count(self) -> None:
        assert self.context is not None and self._count_mob is not None
        count = make_text(
            self.context,
            f"{len(self._entries)} 项",
            13,
            self.context.theme["muted"],
        )
        count.move_to(self._count_mob.get_center())
        self._count_mob.become(count)

    def _pill(self, text: str, color: str, width: float = 1.25) -> VGroup:
        assert self.context is not None
        rect = RoundedRectangle(
            width=width,
            height=0.32,
            corner_radius=0.1,
            fill_color=color,
            fill_opacity=0.22,
            stroke_color=color,
            stroke_width=1.0,
        )
        label = make_text(self.context, text, 12, color, weight="BOLD")
        return VGroup(rect, label).move_to(rect.get_center())
