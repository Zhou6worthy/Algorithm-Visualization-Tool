from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from algoviz.protocol.events import (
    AnimationStep,
    ArrayState,
    DictEntryView,
    DictState,
    StepType,
    VariableView,
    VisualKind,
    VisualState,
)
from algoviz.protocol.visual import (
    ComponentKind,
    ComponentSpec,
    LayoutBox,
    VisualPlan,
)
from algoviz.render.components import (
    CodeVisualizer,
    CodeWindow,
    ComponentContext,
    ComponentRegistry,
    ComponentRegistryError,
    UnknownComponentError,
)
from algoviz.render.two_sum_visuals import TwoSumStage


class FakeHost:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.removed: list[Any] = []
        self.played: list[Any] = []
        self.waits: list[float] = []
        self.front: list[Any] = []

    def add(self, *mobjects: Any) -> None:
        self.added.extend(mobjects)

    def remove(self, *mobjects: Any) -> None:
        self.removed.extend(mobjects)

    def play(self, *animations: Any, run_time: float = 0.25) -> None:
        self.played.append((animations, run_time))

    def wait(self, duration: float) -> None:
        self.waits.append(duration)

    def bring_to_front(self, *mobjects: Any) -> None:
        self.front.extend(mobjects)


def _context(code: str, *, language: str = "python") -> ComponentContext:
    return ComponentContext(
        area=LayoutBox(x=0.7, y=0.1, width=0.25, height=0.75),
        theme={
            "panel": "#16233D",
            "border": "#2A3B5E",
            "muted": "#9AA9C2",
            "text": "#E8EEF9",
            "accent": "#FBBF24",
        },
        cn_font="Microsoft YaHei",
        code_font="Consolas",
        language=language,
        code=code,
    )


def _state() -> VisualState:
    return VisualState(kind=VisualKind.ARRAY, array=ArrayState(values=[2, 7, 11, 15]))


def _step(line: int) -> AnimationStep:
    state = _state()
    return AnimationStep(
        step_id=0,
        type=StepType.COMPARE,
        targets=[],
        description="compare",
        code_line=line,
        state_before=state,
        state_after=state,
    )


def test_layout_box_is_normalized_and_bounded() -> None:
    box = LayoutBox(x=0.1, y=0.2, width=0.5, height=0.6)
    assert (box.x, box.y, box.width, box.height) == (0.1, 0.2, 0.5, 0.6)
    with pytest.raises(ValidationError):
        LayoutBox(x=0.8, y=0.1, width=0.4, height=0.2)
    with pytest.raises(ValidationError):
        LayoutBox(x=-0.01, y=0.1, width=0.2, height=0.2)


def test_visual_plan_checks_unique_ids_and_slots() -> None:
    plan = VisualPlan(
        components=[
            ComponentSpec(component_id="code", kind=ComponentKind.CODE, slot="right"),
            ComponentSpec(component_id="array", kind=ComponentKind.ARRAY, slot="left"),
        ],
        slots={
            "left": LayoutBox(x=0.0, y=0.0, width=0.6, height=1.0),
            "right": LayoutBox(x=0.6, y=0.0, width=0.4, height=1.0),
        },
    )
    restored = VisualPlan.model_validate_json(plan.model_dump_json())
    assert [item.component_id for item in restored.components] == ["code", "array"]

    with pytest.raises(ValidationError):
        VisualPlan(
            components=[
                ComponentSpec(component_id="same", kind=ComponentKind.CODE, slot="right"),
                ComponentSpec(component_id="same", kind=ComponentKind.ARRAY, slot="left"),
            ],
            slots={
                "left": LayoutBox(x=0, y=0, width=0.5, height=1),
                "right": LayoutBox(x=0.5, y=0, width=0.5, height=1),
            },
        )
    with pytest.raises(ValidationError):
        VisualPlan(
            components=[ComponentSpec(component_id="code", kind=ComponentKind.CODE, slot="missing")],
            slots={"right": LayoutBox(x=0.5, y=0, width=0.5, height=1)},
        )


def test_registry_register_lookup_create_and_errors() -> None:
    class Component:
        kind = ComponentKind.CUSTOM

        def __init__(self, value: int = 0) -> None:
            self.value = value

    registry = ComponentRegistry()
    registry.register(ComponentKind.CUSTOM, Component)
    assert registry.has(ComponentKind.CUSTOM)
    assert ComponentKind.CUSTOM in registry
    created = registry.create(ComponentKind.CUSTOM, value=7)
    assert created.value == 7
    assert list(registry.kinds()) == [ComponentKind.CUSTOM]
    with pytest.raises(ComponentRegistryError):
        registry.register(ComponentKind.CUSTOM, Component)
    registry.register(ComponentKind.CUSTOM, Component, replace=True)
    with pytest.raises(UnknownComponentError):
        registry.get(ComponentKind.CODE)
    with pytest.raises(UnknownComponentError):
        registry.create(ComponentKind.CODE)


def test_code_window_boundaries_and_auto_scroll() -> None:
    assert CodeWindow(0, 14).visible(1) == (0, 0)
    assert CodeWindow(3, 14).visible(2) == (0, 3)
    window = CodeWindow(30, 10)
    assert window.visible(1) == (0, 10)
    assert window.visible(25) == (19, 29)
    assert window.visible(30) == (20, 30)
    with pytest.raises(ValueError):
        CodeWindow(-1)
    with pytest.raises(ValueError):
        CodeWindow(3, 0)


def test_code_visualizer_highlights_without_full_scene() -> None:
    host = FakeHost()
    context = _context("\n".join(f"line {i}" for i in range(1, 21)))
    visual = CodeVisualizer(host=host, context=context, options={"window": 5})
    visual.mount(host, context, _state())
    assert visual.header_text == "CODE · python"
    assert visual.visible_range == (1, 5)
    assert visual.current_line == 1

    visual.update(_step(6), 1.0)
    assert visual.current_line == 6
    assert visual.visible_range == (4, 8)
    assert visual.line_y[6] < visual.line_y[4]
    assert visual.highlight_y == pytest.approx(visual.line_y[6])

    visual.update(_step(1), 1.0)
    assert visual.visible_range == (1, 5)
    visual.update(_step(20), 1.0)
    assert visual.visible_range == (16, 20)
    assert visual.line_y[20] < visual.line_y[16]


def test_code_visualizer_language_title_and_unmount() -> None:
    host = FakeHost()
    context = _context("a\nb", language="python")
    visual = CodeVisualizer(host=host, context=context, options={"title": "SOURCE"})
    visual.mount(host, context, _state())
    assert visual.header_text == "SOURCE · python"
    visual.unmount()
    assert host.played
    assert host.removed


def test_code_component_source_has_no_algorithm_semantics() -> None:
    path = Path(__file__).resolve().parent.parent / "algoviz" / "render" / "components" / "code.py"
    source = path.read_text(encoding="utf-8").lower()
    assert "two_sum" not in source
    assert "seen" not in source
    assert "need" not in source
    assert "executiontrace" not in source
    assert "semanticooperation" not in source


def test_two_sum_stage_delegates_code_panel() -> None:
    class FakeScene:
        def __init__(self) -> None:
            self.added: list[Any] = []
            self.played: list[Any] = []
            self.removed: list[Any] = []
            self.waits: list[float] = []

        @staticmethod
        def fmt(value: Any) -> str:
            return str(value)

        def add(self, *mobjects: Any) -> None:
            self.added.extend(mobjects)

        def remove(self, *mobjects: Any) -> None:
            self.removed.extend(mobjects)

        def play(self, *animations: Any, run_time: float = 0.25) -> None:
            self.played.append((animations, run_time))

        def wait(self, duration: float) -> None:
            self.waits.append(duration)

        def bring_to_front(self, *mobjects: Any) -> None:
            pass

    scene = FakeScene()
    state = VisualState(
        kind=VisualKind.ARRAY,
        array=ArrayState(values=[2, 7], pointers={"i": 0}, target=9),
        dict_state=DictState(entries=[DictEntryView(key="2", value=0)]),
        variables=[VariableView(name="i", type="int", value="0")],
    )
    stage = TwoSumStage(
        scene,
        colors={
            "panel": "#16233D",
            "panel_alt": "#1C2B49",
            "border": "#2A3B5E",
            "text": "#E8EEF9",
            "muted": "#9AA9C2",
            "accent": "#FBBF24",
            "compare": "#38BDF8",
            "sorted": "#34D399",
            "danger": "#F87171",
        },
        font="Microsoft YaHei",
        code_font="Consolas",
        code="def two_sum(nums, target):\n    seen = {}\n    return []\n",
    )
    stage.build(state)
    assert stage.code_visualizer is not None
    assert stage.code_visualizer.current_line == 1
    stage.play_step(_step(2), 2.0)
    assert stage.code_visualizer.current_line == 2
    stage.cleanup()
    assert stage.code_visualizer is None
