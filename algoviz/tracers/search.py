"""查找算法追踪器：二分查找、线性查找。"""
from __future__ import annotations

from typing import Any

from ..protocol.events import ArrayState, StepType, VisualKind, VisualState
from .base import BaseTracer

BINARY_SEARCH_CODE = '''def binary_search(arr, target):
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        if arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1
'''

LINEAR_SEARCH_CODE = '''def linear_search(arr, target):
    for i, value in enumerate(arr):
        if value == target:
            return i
    return -1
'''


class _ArraySearchTracer(BaseTracer):
    visual_kind = VisualKind.ARRAY
    category = "search"

    def __init__(self, values: list[Any], target: Any, code: str = "") -> None:
        self.values = list(values)
        self.target = target
        self.pointers: dict[str, int] = {}
        self.active_range: list[int] | None = None
        self.found_index: int | None = None
        self.note_text: str | None = None
        super().__init__(code)

    def snapshot(self) -> VisualState:
        return VisualState(
            kind=VisualKind.ARRAY,
            array=ArrayState(
                values=list(self.values),
                active_range=list(self.active_range) if self.active_range else None,
                pointers=dict(self.pointers),
                target=self.target,
                found_index=self.found_index,
            ),
            note=self.note_text,
        )

    def arr_text(self) -> str:
        return "[" + ", ".join(self.fmt(v) for v in self.values) + "]"


class BinarySearchTracer(_ArraySearchTracer):
    def __init__(self, values: list[Any], target: Any, code: str = BINARY_SEARCH_CODE) -> None:
        super().__init__(values, target, code)

    def run(self) -> int:
        a = self.values
        target = self.target
        n = len(a)
        self.note_text = "二分查找：每轮排除一半区间"
        self.init(f"有序数组 {self.arr_text()}，目标值 target={self.fmt(target)}")
        left, right = 0, n - 1
        self.active_range = [left, right]
        self.pointers = {"left": left, "right": right}
        self.at("left, right = 0, len(arr) - 1")
        while left <= right:
            self.active_range = [left, right]
            self.at("while left <= right")
            mid = (left + right) // 2
            self.pointers = {"left": left, "right": right, "mid": mid}
            self.at("mid = (left + right) // 2")
            self.emit(
                StepType.VISIT,
                f"计算中点 mid={mid}，比较 a[{mid}]={self.fmt(a[mid])} 与 target={self.fmt(target)}",
                targets=[mid],
                visual_action="visit",
                meta={"mid": mid, "range": [left, right]},
            )
            self.at("if arr[mid] == target")
            self.emit(
                StepType.COMPARE,
                f"比较 a[{mid}]={self.fmt(a[mid])} 与 target={self.fmt(target)}",
                targets=[mid],
                visual_action="compare",
                meta={"values": [a[mid], target], "mid": mid},
            )
            if a[mid] == target:
                self.found_index = mid
                self.pointers = {"mid": mid}
                self.at("return mid")
                self.emit(
                    StepType.FOUND,
                    f"命中！target={self.fmt(target)} 位于下标 {mid}",
                    targets=[mid],
                    visual_action="found",
                    meta={"index": mid, "target": target},
                )
                self.complete(f"查找成功：target={self.fmt(target)} 的下标为 {mid}")
                return mid
            if a[mid] < target:
                left = mid + 1
                self.active_range = [left, right] if left <= right else None
                self.pointers = {"left": left, "right": right, "mid": mid}
                self.at("left = mid + 1")
                self.emit(
                    StepType.NOTE,
                    f"a[{mid}]={self.fmt(a[mid])} < target={self.fmt(target)}，目标在右半区，区间缩小为 [{left}, {right}]",
                    targets=[mid],
                    visual_action="shrink",
                    meta={"range": [left, right], "excluded": [0, mid]},
                )
            else:
                right = mid - 1
                self.active_range = [left, right] if left <= right else None
                self.pointers = {"left": left, "right": right, "mid": mid}
                self.at("right = mid - 1")
                self.emit(
                    StepType.NOTE,
                    f"a[{mid}]={self.fmt(a[mid])} > target={self.fmt(target)}，目标在左半区，区间缩小为 [{left}, {right}]",
                    targets=[mid],
                    visual_action="shrink",
                    meta={"range": [left, right], "excluded": [mid, n - 1]},
                )
        self.found_index = None
        self.active_range = None
        self.pointers = {}
        self.note_text = "查找失败：区间为空"
        self.at("return -1")
        self.complete(f"查找结束：target={self.fmt(target)} 不在数组中，返回 -1")
        return -1


class LinearSearchTracer(_ArraySearchTracer):
    def __init__(self, values: list[Any], target: Any, code: str = LINEAR_SEARCH_CODE) -> None:
        super().__init__(values, target, code)

    def run(self) -> int:
        a = self.values
        target = self.target
        n = len(a)
        self.note_text = "线性查找：从前往后逐个比较"
        self.init(f"数组 {self.arr_text()}，目标值 target={self.fmt(target)}")
        self.at("for i, value in enumerate(arr)")
        for i, value in enumerate(a):
            self.pointers = {"i": i}
            self.active_range = [0, n - 1]
            self.at("if value == target")
            self.emit(
                StepType.COMPARE,
                f"比较 a[{i}]={self.fmt(value)} 与 target={self.fmt(target)}",
                targets=[i],
                visual_action="compare",
                meta={"index": i, "value": value, "target": target},
            )
            if value == target:
                self.found_index = i
                self.at("return i")
                self.emit(
                    StepType.FOUND,
                    f"命中！target={self.fmt(target)} 位于下标 {i}",
                    targets=[i],
                    visual_action="found",
                    meta={"index": i, "target": target},
                )
                self.complete(f"查找成功：target={self.fmt(target)} 的下标为 {i}")
                return i
        self.found_index = None
        self.pointers = {}
        self.note_text = "查找失败"
        self.at("return -1")
        self.complete(f"查找结束：target={self.fmt(target)} 不在数组中，返回 -1")
        return -1
