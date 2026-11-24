"""Two Sum 专用的变量投影层。

这是算法适配代码，不属于 VariableVisualizer。它把真实 VisualState /
AnimationStep 投影成通用 VariableRow；变量组件本身不出现 i/x/need/target。
"""
from __future__ import annotations

import json
from typing import Any

from ..protocol.events import AnimationStep, VisualState
from ..render.components.variables import VariableRow


def _fmt(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def project_two_sum_variables(
    state: VisualState,
    step: AnimationStep | None = None,
) -> list[VariableRow]:
    values = {item.name: item for item in state.variables}
    target = state.array.target if state.array else None
    seen_size = len(state.dict_state.entries) if state.dict_state else 0
    pointer = state.array.pointers.get("i") if state.array else None
    fallback_x = None
    if pointer is not None and state.array and 0 <= int(pointer) < len(state.array.values):
        fallback_x = state.array.values[int(pointer)]
    returned = None
    if step is not None and step.type.value in {"found", "complete"}:
        returned = step.meta.get("return")
    rows: list[VariableRow] = [
        VariableRow(
            "i",
            values["i"].value if "i" in values else (str(pointer) if pointer is not None else "—"),
            values["i"].changed if "i" in values else False,
        ),
        VariableRow(
            "x",
            values["x"].value if "x" in values else (str(fallback_x) if fallback_x is not None else "—"),
            values["x"].changed if "x" in values else False,
        ),
    ]
    if returned is not None:
        rows.append(VariableRow("返回", _fmt(returned), True))
    else:
        rows.append(
            VariableRow(
                "need",
                values["need"].value if "need" in values else "—",
                values["need"].changed if "need" in values else False,
            )
        )
    rows.extend(
        [
            VariableRow("target", str(target) if target is not None else "—"),
            VariableRow("seen.size", str(seen_size)),
        ]
    )
    return rows
