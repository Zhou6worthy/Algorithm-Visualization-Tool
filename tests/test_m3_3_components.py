from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

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
from algoviz.protocol.visual import ComponentKind, LayoutBox
from algoviz.render.components import (
    ArrayVisualizer,
    ComponentContext,
    HashMapVisualizer,
    VariableRow,
    VariableVisualizer,
    default_registry,
)
from algoviz.render.two_sum_visuals import TwoSumStage
from algoviz.teaching.two_sum_variables import project_two_sum_variables

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
        area=LayoutBox(x=0.05, y=0.1, width=0.45, height=0.3),
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
        code="a\nb\n",
    )


def _array_state(
    values: list[Any],
    *,
    pointers: dict[str, int] | None = None,
    found: list[int] | None = None,
    target: Any = None,
) -> VisualState:
    return VisualState(
        kind=VisualKind.ARRAY,
        array=ArrayState(
            values=values,
            pointers=pointers or {},
            found_indices=found or [],
            target=target,
        ),
    )


def _dict_state(
    entries: list[tuple[str, Any]],
    *,
    lookup_key: str | None = None,
    lookup_status: str | None = None,
    highlighted: set[str] | None = None,
) -> VisualState:
    return VisualState(
        kind=VisualKind.ARRAY,
        array=ArrayState(values=[]),
        dict_state=DictState(
            entries=[
                DictEntryView(key=key, value=value, highlighted=key in (highlighted or set()))
                for key, value in entries
            ],
            lookup_key=lookup_key,
            lookup_status=lookup_status,  # type: ignore[arg-type]
        ),
    )


def _step(
    before: VisualState,
    after: VisualState,
    *,
    line: int | None = None,
    meta: dict | None = None,
    step_type: StepType = StepType.COMPARE,
) -> AnimationStep:
    return AnimationStep(
        step_id=0,
        type=step_type,
        targets=[],
        description="step",
        code_line=line,
        state_before=before,
        state_after=after,
        meta=meta or {},
    )


def test_array_visualizer_builds_values_pointers_and_found() -> None:
    host = FakeHost()
    state = _array_state([2, 7, 11, 15], pointers={"i": 1}, found=[0], target=9)
    visual = ArrayVisualizer(host=host, context=_context(), options={"title": "数组 nums", "array_name": "nums"})
    visual.mount(host, _context(), state)
    assert visual.displayed_values == [2, 7, 11, 15]
    assert visual.index_values == [0, 1, 2, 3]
    assert visual.cell_count == 4
    assert visual.pointer_texts == ["i = 1"]
    assert visual.found_indices == [0]
    assert not visual.is_empty


def test_array_visualizer_empty_and_update() -> None:
    host = FakeHost()
    empty = _array_state([])
    visual = ArrayVisualizer(host=host, context=_context())
    visual.mount(host, _context(), empty)
    assert visual.is_empty
    assert visual.cell_count == 0

    before = _array_state([1, 2], pointers={"i": 0})
    after = _array_state([1, 9], pointers={"i": 1}, found=[1])
    visual.mount(host, _context(), before)
    visual.update(_step(before, after), 1.0)
    assert visual.displayed_values == [1, 9]
    assert visual.pointer_texts == ["i = 1"]
    assert visual.found_indices == [1]


def test_hash_visualizer_hit_miss_and_multiple_entries() -> None:
    host = FakeHost()
    hit = _dict_state([("2", 0), ("7", 1)], lookup_key="2", lookup_status="hit")
    visual = HashMapVisualizer(host=host, context=_context(), options={"title": "哈希表"})
    visual.mount(host, _context(), hit)
    assert visual.displayed_keys == ["2", "7"]
    assert visual.entry_count == 2
    assert visual.lookup_key == "2"
    assert visual.lookup_status == "hit"
    assert visual.highlighted_keys == ["2"]
    assert not visual.is_empty

    miss = _dict_state([("2", 0)], lookup_key="9", lookup_status="miss")
    visual.update(_step(hit, miss), 1.0)
    assert visual.lookup_key == "9"
    assert visual.lookup_status == "miss"
    assert visual.highlighted_keys == []


def test_hash_visualizer_empty_and_new_entry() -> None:
    host = FakeHost()
    empty = _dict_state([])
    visual = HashMapVisualizer(host=host, context=_context())
    visual.mount(host, _context(), empty)
    assert visual.is_empty

    before = _dict_state([("2", 0)])
    after = _dict_state([("2", 0), ("7", 1)])
    visual.update(_step(before, after), 1.0)
    assert visual.displayed_keys == ["2", "7"]
    assert visual.entry_count == 2
    assert "7" in visual.highlighted_keys


def test_variable_visualizer_generic_rows_changed_and_empty() -> None:
    host = FakeHost()
    visual = VariableVisualizer(host=host, context=_context(), options={"max_rows": 3})
    visual.mount(host, _context(), _array_state([]))
    rows = [
        VariableRow("alpha", "10", True),
        VariableRow("beta", "ok"),
        VariableRow("gamma", "—"),
    ]
    visual.set_rows(rows, animate=False)
    assert visual.displayed_labels == ["alpha", "beta", "gamma"]
    assert visual.displayed_values == ["10", "ok", "—"]
    assert visual.changed_labels == ["alpha"]
    visual.set_rows([], animate=False)
    assert visual.is_empty
    assert visual.displayed_labels == []


def test_variable_visualizer_max_rows() -> None:
    host = FakeHost()
    visual = VariableVisualizer(host=host, context=_context(), options={"max_rows": 2})
    visual.mount(host, _context(), _array_state([]))
    visual.set_rows(
        [VariableRow("a", "1"), VariableRow("b", "2"), VariableRow("c", "3")],
        animate=False,
    )
    assert visual.displayed_labels == ["a", "b"]


def test_default_registry_has_m3_components_and_no_future_empty_components() -> None:
    assert ComponentKind.ARRAY in default_registry
    assert ComponentKind.HASH_MAP in default_registry
    assert ComponentKind.VARIABLES in default_registry
    assert ComponentKind.CODE in default_registry
    assert ComponentKind.TREE not in default_registry
    assert ComponentKind.GRAPH not in default_registry
    assert ComponentKind.DP_TABLE not in default_registry
    assert ComponentKind.CALL_STACK not in default_registry
    for kind in (ComponentKind.ARRAY, ComponentKind.HASH_MAP, ComponentKind.VARIABLES, ComponentKind.CODE):
        component = default_registry.create(
            kind,
            host=FakeHost(),
            context=_context(),
            options={},
        )
        assert component.kind == kind


def test_two_sum_projection_is_separate_from_variable_component() -> None:
    state = VisualState(
        kind=VisualKind.ARRAY,
        array=ArrayState(values=[2, 7], pointers={"i": 1}, target=9),
        dict_state=DictState(entries=[DictEntryView(key="2", value=0)]),
        variables=[VariableView(name="need", type="int", value="2")],
    )
    rows = project_two_sum_variables(state)
    assert [row.label for row in rows] == ["i", "x", "need", "target", "seen.size"]
    assert rows[0].value == "1"
    assert rows[1].value == "7"
    assert rows[2].value == "2"
    assert rows[3].value == "9"
    assert rows[4].value == "1"


def test_component_sources_do_not_contain_two_sum_semantics() -> None:
    for name in ("array.py", "hash_map.py", "variables.py"):
        source = (ROOT / "algoviz" / "render" / "components" / name).read_text(encoding="utf-8").lower()
        assert "two_sum" not in source
        assert "seen" not in source
        assert "need" not in source
        assert "executiontrace" not in source


def test_two_sum_stage_composes_all_components() -> None:
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
    state = VisualState(
        kind=VisualKind.ARRAY,
        array=ArrayState(values=[2, 7], pointers={"i": 0}, target=9),
        dict_state=DictState(entries=[DictEntryView(key="2", value=0)]),
        variables=[VariableView(name="i", type="int", value="0")],
    )
    stage = TwoSumStage(
        scene,
        colors=_context().theme,
        font="Microsoft YaHei",
        code_font="Consolas",
        code="def two_sum(nums, target):\n    seen = {}\n    return []\n",
    )
    stage.build(state)
    assert stage.array_visualizer is not None
    assert stage.hash_visualizer is not None
    assert stage.variable_visualizer is not None
    assert stage.code_visualizer is not None
    assert stage.array_visualizer.displayed_values == [2, 7]
    assert stage.hash_visualizer.displayed_keys == ["2"]
    assert stage.variable_visualizer.displayed_labels[:2] == ["i", "x"]
    assert stage.code_visualizer.current_line == 1

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
    step = _step(state, after, line=2, meta={"return": [0, 1]}, step_type=StepType.FOUND)
    stage.play_step(step, 2.0)
    assert stage.array_visualizer.found_indices == [1]
    assert stage.hash_visualizer.lookup_status == "hit"
    assert "返回" in stage.variable_visualizer.displayed_labels
    assert stage.code_visualizer.current_line == 2
    stage.cleanup()
    assert stage.array_visualizer is None
