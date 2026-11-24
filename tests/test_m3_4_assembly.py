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
from algoviz.protocol.visual import ComponentKind, ComponentSpec, LayoutBox, VisualPlan
from algoviz.render.components import (
    ArrayVisualizer,
    CodeVisualizer,
    ComponentContext,
    HashMapVisualizer,
    VariableVisualizer,
    VisualAssembler,
    VisualAssemblyError,
    default_registry,
)
from algoviz.render.two_sum_visuals import TwoSumStage
from algoviz.teaching.two_sum_profile import TwoSumVisualProfile

ROOT = Path(__file__).resolve().parent.parent


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


def _context() -> ComponentContext:
    return ComponentContext(
        area=LayoutBox(x=0, y=0, width=1, height=1),
        theme={
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
        cn_font="Microsoft YaHei",
        code_font="Consolas",
        language="python",
        code="def two_sum(nums, target):\n    seen = {}\n    return []\n",
    )


def _state() -> VisualState:
    return VisualState(
        kind=VisualKind.ARRAY,
        array=ArrayState(values=[2, 7], pointers={"i": 0}, target=9),
        dict_state=DictState(entries=[DictEntryView(key="2", value=0)]),
        variables=[VariableView(name="i", type="int", value="0")],
    )


def test_profile_builds_four_component_plan_and_projects_variables() -> None:
    profile = TwoSumVisualProfile()
    plan = profile.build_visual_plan()
    assert [item.component_id for item in plan.components] == [
        "array",
        "hash_map",
        "variables",
        "code",
    ]
    assert [item.kind for item in plan.components] == [
        ComponentKind.ARRAY,
        ComponentKind.HASH_MAP,
        ComponentKind.VARIABLES,
        ComponentKind.CODE,
    ]
    assert set(plan.slots) == {"array", "hash_map", "variables", "code"}
    assert plan.components[0].options["title"] == "数组 nums"
    assert plan.components[1].options["title"] == "哈希表 seen"
    assert plan.components[2].options["max_rows"] == 5
    assert plan.components[3].options["window"] == 14

    rows = profile.project_variables(_state())
    assert [row.label for row in rows] == ["i", "x", "need", "target", "seen.size"]
    assert rows[0].value == "0"


def test_profile_does_not_import_manim_or_scene() -> None:
    source = (ROOT / "algoviz" / "teaching" / "two_sum_profile.py").read_text(encoding="utf-8").lower()
    assert "import manim" not in source
    assert "from manim" not in source
    assert "two_sum_scene" not in source


def test_assembler_creates_and_mounts_all_components() -> None:
    host = FakeHost()
    context = _context()
    plan = TwoSumVisualProfile().build_visual_plan()
    result = VisualAssembler(default_registry).assemble(plan, host, context, _state())
    assert set(result.components) == {"array", "hash_map", "variables", "code"}
    assert isinstance(result.components["array"], ArrayVisualizer)
    assert isinstance(result.components["hash_map"], HashMapVisualizer)
    assert isinstance(result.components["variables"], VariableVisualizer)
    assert isinstance(result.components["code"], CodeVisualizer)
    assert result.contexts["array"].area == plan.slots["array"]
    assert result.specs["array"].options["title"] == "数组 nums"
    assert result.get("array") is result.components["array"]
    assert host.added


def test_assembler_rejects_unregistered_kind_and_bad_lookup() -> None:
    plan = VisualPlan(
        components=[
            ComponentSpec(component_id="tree", kind=ComponentKind.TREE, slot="main"),
        ],
        slots={"main": LayoutBox(x=0, y=0, width=1, height=1)},
    )
    with pytest.raises(VisualAssemblyError, match="未注册"):
        VisualAssembler(default_registry).assemble(plan, FakeHost(), _context(), _state())

    good = TwoSumVisualProfile().build_visual_plan()
    result = VisualAssembler(default_registry).assemble(good, FakeHost(), _context(), _state())
    with pytest.raises(VisualAssemblyError):
        result.get("missing")


def test_visual_plan_rejects_duplicate_ids_and_unknown_slots() -> None:
    with pytest.raises(ValidationError):
        VisualPlan(
            components=[
                ComponentSpec(component_id="same", kind=ComponentKind.CODE, slot="main"),
                ComponentSpec(component_id="same", kind=ComponentKind.ARRAY, slot="main"),
            ],
            slots={"main": LayoutBox(x=0, y=0, width=1, height=1)},
        )
    with pytest.raises(ValidationError):
        VisualPlan(
            components=[ComponentSpec(component_id="code", kind=ComponentKind.CODE, slot="missing")],
            slots={"main": LayoutBox(x=0, y=0, width=1, height=1)},
        )


def test_stage_uses_profile_and_assembler_not_manual_component_factory() -> None:
    class FakeScene:
        def __init__(self) -> None:
            self.added: list[Any] = []
            self.played: list[Any] = []
            self.removed: list[Any] = []

        def add(self, *mobjects: Any) -> None:
            self.added.extend(mobjects)

        def remove(self, *mobjects: Any) -> None:
            self.removed.extend(mobjects)

        def play(self, *animations: Any, run_time: float = 0.25) -> None:
            self.played.append((animations, run_time))

        def wait(self, duration: float) -> None:
            pass

        def bring_to_front(self, *mobjects: Any) -> None:
            pass

    scene = FakeScene()
    stage = TwoSumStage(
        scene,
        colors=_context().theme,
        font="Microsoft YaHei",
        code_font="Consolas",
        code=_context().code,
    )
    stage.build(_state())
    assert stage.visual_plan is not None
    assert stage.assembly is not None
    assert set(stage.assembly.components) == {"array", "hash_map", "variables", "code"}
    assert stage.array_visualizer is stage.assembly.get("array")
    assert stage.variable_visualizer is stage.assembly.get("variables")
    assert stage.code_visualizer is stage.assembly.get("code")

    after = VisualState(
        kind=VisualKind.ARRAY,
        array=ArrayState(values=[2, 7], pointers={"i": 1}, found_indices=[1], target=9),
        dict_state=DictState(
            entries=[DictEntryView(key="2", value=0, highlighted=True)],
            lookup_key="2",
            lookup_status="hit",
        ),
        variables=[],
    )
    step = AnimationStep(
        step_id=0,
        type=StepType.FOUND,
        targets=[1],
        description="found",
        code_line=2,
        state_before=_state(),
        state_after=after,
        meta={"return": [0, 1]},
    )
    stage.play_step(step, 2.0)
    assert stage.array_visualizer.found_indices == [1]
    assert stage.hash_visualizer.lookup_status == "hit"
    assert "返回" in stage.variable_visualizer.displayed_labels
    assert stage.code_visualizer.current_line == 2
    stage.cleanup()
    assert stage.visual_plan is None
    assert stage.assembly is None


def test_stage_source_has_no_component_specs_or_options() -> None:
    source = (ROOT / "algoviz" / "render" / "two_sum_visuals.py").read_text(encoding="utf-8").lower()
    assert "componentspec" not in source
    assert "componentkind" not in source
    assert "options=" not in source
    assert "visualassembler" in source
    assert "twosumvisualprofile" in source
