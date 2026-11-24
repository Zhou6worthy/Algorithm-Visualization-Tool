"""排序算法追踪器：冒泡、选择、插入、快速、归并。"""
from __future__ import annotations

from typing import Any

from ..protocol.events import ArrayState, StepType, VisualKind, VisualState
from .base import BaseTracer

BUBBLE_CODE = '''def bubble_sort(arr):
    n = len(arr)
    for i in range(n - 1):
        swapped = False
        for j in range(n - 1 - i):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
                swapped = True
        if not swapped:
            break
    return arr
'''

SELECTION_CODE = '''def selection_sort(arr):
    n = len(arr)
    for i in range(n):
        min_idx = i
        for j in range(i + 1, n):
            if arr[j] < arr[min_idx]:
                min_idx = j
        if min_idx != i:
            arr[i], arr[min_idx] = arr[min_idx], arr[i]
    return arr
'''

INSERTION_CODE = '''def insertion_sort(arr):
    for i in range(1, len(arr)):
        key = arr[i]
        j = i - 1
        while j >= 0 and arr[j] > key:
            arr[j + 1] = arr[j]
            j -= 1
        arr[j + 1] = key
    return arr
'''

QUICK_CODE = '''def quick_sort(arr, lo=0, hi=None, pivot_strategy="last"):
    if hi is None:
        hi = len(arr) - 1
    if lo >= hi:
        return
    if pivot_strategy == "first":
        arr[lo], arr[hi] = arr[hi], arr[lo]
    pivot = arr[hi]
    i = lo
    for j in range(lo, hi):
        if arr[j] <= pivot:
            arr[i], arr[j] = arr[j], arr[i]
            i += 1
    arr[i], arr[hi] = arr[hi], arr[i]
    quick_sort(arr, lo, i - 1, pivot_strategy)
    quick_sort(arr, i + 1, hi, pivot_strategy)
'''

MERGE_CODE = '''def merge_sort(arr, lo=0, hi=None):
    if hi is None:
        hi = len(arr) - 1
    if lo >= hi:
        return
    mid = (lo + hi) // 2
    merge_sort(arr, lo, mid)
    merge_sort(arr, mid + 1, hi)
    merge(arr, lo, mid, hi)


def merge(arr, lo, mid, hi):
    left = arr[lo:mid + 1]
    right = arr[mid + 1:hi + 1]
    i = j = 0
    k = lo
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            arr[k] = left[i]
            i += 1
        else:
            arr[k] = right[j]
            j += 1
        k += 1
    while i < len(left):
        arr[k] = left[i]
        i += 1
        k += 1
    while j < len(right):
        arr[k] = right[j]
        j += 1
        k += 1
'''


def normalize_value(value: Any) -> Any:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, bool):
        return int(value)
    return value


class ArraySortTracer(BaseTracer):
    visual_kind = VisualKind.ARRAY
    category = "sort"

    def __init__(self, values: list[Any], code: str = "") -> None:
        self.values: list[Any] = [normalize_value(v) for v in values]
        self.sorted_indices: set[int] = set()
        self.pointers: dict[str, int] = {}
        self.active_range: list[int] | None = None
        self.aux: list[Any] | None = None
        self.note_text: str | None = None
        self.round_label: str = ""
        super().__init__(code)

    def snapshot(self) -> VisualState:
        return VisualState(
            kind=VisualKind.ARRAY,
            array=ArrayState(
                values=list(self.values),
                sorted_indices=sorted(self.sorted_indices),
                active_range=list(self.active_range) if self.active_range else None,
                pointers={
                    k: v
                    for k, v in self.pointers.items()
                    if v is not None and 0 <= v < len(self.values)
                },
                aux=list(self.aux) if self.aux is not None else None,
            ),
            note=self.note_text,
        )

    def arr_text(self) -> str:
        return "[" + ", ".join(self.fmt(v) for v in self.values) + "]"

    def _set_note(self, text: str) -> None:
        self.note_text = text

    def _swap(self, i: int, j: int, reason: str, code_line: int | None = None) -> None:
        x, y = self.values[i], self.values[j]
        self.values[i], self.values[j] = y, x
        self.emit(
            StepType.SWAP,
            f"交换 a[{i}]={self.fmt(x)} 与 a[{j}]={self.fmt(y)}：{reason}",
            targets=[i, j],
            code_line=code_line,
            visual_action="swap",
            meta={"values": [x, y], "indices": [i, j]},
        )


class BubbleSortTracer(ArraySortTracer):
    def __init__(self, values: list[Any], code: str = BUBBLE_CODE) -> None:
        super().__init__(values, code)

    def run(self) -> list[Any]:
        a = self.values
        n = len(a)
        self._set_note(f"冒泡排序 · {n} 个元素")
        self.init(f"初始数组：{self.arr_text()}")
        self.at("for i in range")
        for i in range(n - 1):
            self._set_note(f"第 {i + 1} 轮：把剩余最大值冒泡到末尾")
            self.at("for j in range")
            for j in range(n - 1 - i):
                self.pointers = {"j": j, "j+1": j + 1}
                self.at("if arr[j] > arr[j + 1]")
                x, y = a[j], a[j + 1]
                self.emit(
                    StepType.COMPARE,
                    f"比较 a[{j}]={self.fmt(x)} 与 a[{j + 1}]={self.fmt(y)}",
                    targets=[j, j + 1],
                    visual_action="compare",
                    meta={"values": [x, y], "round": i + 1},
                )
                if x > y:
                    self._swap(
                        j,
                        j + 1,
                        f"{self.fmt(x)} > {self.fmt(y)}，需要交换",
                        code_line=self.line("arr[j], arr[j + 1] = arr[j + 1], arr[j]"),
                    )
                self.pointers = {}
            self.sorted_indices.add(n - 1 - i)
            self.at("if not swapped")
            self.emit(
                StepType.MARK,
                f"第 {i + 1} 轮结束，a[{n - 1 - i}]={self.fmt(a[n - 1 - i])} 已归位",
                targets=[n - 1 - i],
                visual_action="mark",
                meta={"round": i + 1},
            )
            if not any(
                a[k] > a[k + 1] for k in range(n - 1 - i) if k + 1 < n
            ):
                for k in range(n - 1 - i):
                    self.sorted_indices.add(k)
                self._set_note("提前结束（本轮无交换）")
                self.emit(
                    StepType.NOTE,
                    "本轮没有发生交换，说明剩余部分已经有序，可以提前结束",
                    visual_action="note",
                )
                break
        self.sorted_indices.update(range(n))
        self.pointers = {}
        self._set_note("排序完成")
        self.complete(f"排序完成：{self.arr_text()}")
        return list(a)


class SelectionSortTracer(ArraySortTracer):
    def __init__(self, values: list[Any], code: str = SELECTION_CODE) -> None:
        super().__init__(values, code)

    def run(self) -> list[Any]:
        a = self.values
        n = len(a)
        self._set_note(f"选择排序 · {n} 个元素")
        self.init(f"初始数组：{self.arr_text()}")
        self.at("for i in range")
        for i in range(n):
            min_idx = i
            self.pointers = {"i": i, "min": min_idx}
            self.at("min_idx = i")
            self.emit(
                StepType.NOTE,
                f"第 {i + 1} 轮：在未排序区间 [{i}, {n - 1}] 中寻找最小值",
                targets=[i],
                visual_action="scan",
                meta={"round": i + 1},
            )
            self.at("for j in range")
            for j in range(i + 1, n):
                self.pointers = {"i": i, "j": j, "min": min_idx}
                self.at("if arr[j] < arr[min_idx]")
                self.emit(
                    StepType.COMPARE,
                    f"比较 a[{j}]={self.fmt(a[j])} 与当前最小值 a[{min_idx}]={self.fmt(a[min_idx])}",
                    targets=[j, min_idx],
                    visual_action="compare",
                    meta={"values": [a[j], a[min_idx]]},
                )
                if a[j] < a[min_idx]:
                    min_idx = j
                    self.emit(
                        StepType.NOTE,
                        f"发现更小元素 a[{min_idx}]={self.fmt(a[min_idx])}，更新最小值位置",
                        targets=[min_idx],
                        visual_action="scan",
                    )
            if min_idx != i:
                self._swap(
                    i,
                    min_idx,
                    f"把最小值放到位置 {i}",
                    code_line=self.line("arr[i], arr[min_idx] = arr[min_idx], arr[i]"),
                )
            self.sorted_indices.add(i)
            self.at("if min_idx != i")
            self.emit(
                StepType.MARK,
                f"a[{i}]={self.fmt(a[i])} 已归位，前 {i + 1} 个元素有序",
                targets=[i],
                visual_action="mark",
                meta={"round": i + 1},
            )
        self.pointers = {}
        self._set_note("排序完成")
        self.complete(f"排序完成：{self.arr_text()}")
        return list(a)


class InsertionSortTracer(ArraySortTracer):
    def __init__(self, values: list[Any], code: str = INSERTION_CODE) -> None:
        super().__init__(values, code)

    def run(self) -> list[Any]:
        a = self.values
        n = len(a)
        self._set_note(f"插入排序 · {n} 个元素")
        self.init(f"初始数组：{self.arr_text()}")
        self.at("for i in range(1, len(arr))")
        for i in range(1, n):
            key = a[i]
            self.pointers = {"i": i, "key": i}
            self.at("key = arr[i]")
            self.emit(
                StepType.VISIT,
                f"取出 a[{i}]={self.fmt(key)} 作为待插入元素 key，前面 [0, {i - 1}] 已经有序",
                targets=[i],
                visual_action="pick",
                meta={"key": key, "round": i},
            )
            j = i - 1
            self.at("while j >= 0 and arr[j] > key")
            while j >= 0 and a[j] > key:
                self.pointers = {"j": j, "key": i}
                self.emit(
                    StepType.COMPARE,
                    f"a[{j}]={self.fmt(a[j])} > key={self.fmt(key)}，需要向右让位",
                    targets=[j, j + 1],
                    visual_action="compare",
                    meta={"values": [a[j], key]},
                )
                a[j + 1] = a[j]
                self.at("arr[j + 1] = arr[j]")
                self.emit(
                    StepType.UPDATE,
                    f"把 a[{j}]={self.fmt(a[j])} 后移到 a[{j + 1}]",
                    targets=[j + 1],
                    visual_action="move",
                    meta={"value": a[j + 1], "from": j},
                )
                j -= 1
            a[j + 1] = key
            self.at("arr[j + 1] = key")
            self.emit(
                StepType.UPDATE,
                f"把 key={self.fmt(key)} 插入到 a[{j + 1}]",
                targets=[j + 1],
                visual_action="move",
                meta={"value": key},
            )
            for k in range(i + 1):
                self.sorted_indices.add(k)
            self.emit(
                StepType.MARK,
                f"前 {i + 1} 个元素已经有序：{self.arr_text()}",
                targets=list(range(i + 1)),
                visual_action="mark",
                meta={"round": i},
            )
            self.pointers = {}
        self.sorted_indices.update(range(n))
        self._set_note("排序完成")
        self.complete(f"排序完成：{self.arr_text()}")
        return list(a)


class QuickSortTracer(ArraySortTracer):
    def __init__(self, values: list[Any], code: str = QUICK_CODE, pivot_strategy: str = "last") -> None:
        self.pivot_strategy = pivot_strategy if pivot_strategy in {"first", "last"} else "last"
        super().__init__(values, code)

    def run(self) -> list[Any]:
        n = len(self.values)
        self._set_note(f"快速排序 · {n} 个元素 · 枢轴策略：{'首元素' if self.pivot_strategy == 'first' else '末元素'}")
        self.init(f"初始数组：{self.arr_text()}")
        self._quick(0, n - 1, 0)
        self.sorted_indices.update(range(n))
        self.pointers = {}
        self.active_range = None
        self._set_note("排序完成")
        self.complete(f"排序完成：{self.arr_text()}")
        return list(self.values)

    def _quick(self, lo: int, hi: int, depth: int) -> None:
        a = self.values
        if lo > hi:
            return
        self.active_range = [lo, hi]
        self._set_note(f"处理区间 [{lo}, {hi}]")
        self.at("if lo >= hi")
        if lo == hi:
            self.sorted_indices.add(lo)
            self.emit(
                StepType.MARK,
                f"区间只剩 a[{lo}]={self.fmt(a[lo])}，自然有序",
                targets=[lo],
                visual_action="mark",
            )
            return
        if self.pivot_strategy == "first" and lo != hi:
            self.at("if pivot_strategy")
            self._swap(
                lo,
                hi,
                "选择首元素作为枢轴，先交换到区间末尾",
                code_line=self.line("arr[lo], arr[hi] = arr[hi], arr[lo]"),
            )
        pivot = a[hi]
        self.pointers = {"lo": lo, "hi": hi}
        self.at("pivot = arr[hi]")
        self.emit(
            StepType.VISIT,
            f"选择枢轴 pivot = a[{hi}] = {self.fmt(pivot)}",
            targets=[hi],
            visual_action="pivot",
            meta={"pivot": pivot, "range": [lo, hi], "depth": depth},
        )
        i = lo
        self.at("for j in range(lo, hi)")
        for j in range(lo, hi):
            self.pointers = {"lo": lo, "hi": hi, "i": i, "j": j}
            self.at("if arr[j] <= pivot")
            self.emit(
                StepType.COMPARE,
                f"比较 a[{j}]={self.fmt(a[j])} 与 pivot={self.fmt(pivot)}",
                targets=[j, hi],
                visual_action="compare",
                meta={"values": [a[j], pivot], "range": [lo, hi]},
            )
            if a[j] <= pivot:
                if i != j:
                    self._swap(
                        i,
                        j,
                        f"a[{j}] 不大于枢轴，交换到左区",
                        code_line=self.line("arr[i], arr[j] = arr[j], arr[i]"),
                    )
                i += 1
        if i != hi:
            self._swap(
                i,
                hi,
                "把枢轴移动到左右分界处",
                code_line=self.line("arr[i], arr[hi] = arr[hi], arr[i]"),
            )
        self.sorted_indices.add(i)
        self.at("quick_sort(arr, lo, i - 1")
        self.emit(
            StepType.MARK,
            f"枢轴 {self.fmt(pivot)} 归位到 a[{i}]，左区 ≤ 枢轴 ≤ 右区",
            targets=[i],
            visual_action="mark",
            meta={"pivot": pivot, "index": i, "depth": depth},
        )
        self._quick(lo, i - 1, depth + 1)
        self._quick(i + 1, hi, depth + 1)


class MergeSortTracer(ArraySortTracer):
    def __init__(self, values: list[Any], code: str = MERGE_CODE) -> None:
        super().__init__(values, code)

    def run(self) -> list[Any]:
        n = len(self.values)
        self._set_note(f"归并排序 · {n} 个元素")
        self.init(f"初始数组：{self.arr_text()}")
        self._ms(0, n - 1, 0)
        self.sorted_indices.update(range(n))
        self.pointers = {}
        self.active_range = None
        self.aux = None
        self._set_note("排序完成")
        self.complete(f"排序完成：{self.arr_text()}")
        return list(self.values)

    def _ms(self, lo: int, hi: int, depth: int) -> None:
        if lo >= hi:
            return
        mid = (lo + hi) // 2
        self.active_range = [lo, hi]
        self._set_note(f"拆分区间 [{lo}, {hi}]")
        self.at("mid = (lo + hi) // 2")
        self.emit(
            StepType.NOTE,
            f"把区间 [{lo}, {hi}] 拆成 [{lo}, {mid}] 和 [{mid + 1}, {hi}] 两半",
            targets=[lo, hi],
            visual_action="split",
            meta={"depth": depth, "mid": mid, "range": [lo, hi]},
        )
        self._ms(lo, mid, depth + 1)
        self._ms(mid + 1, hi, depth + 1)
        self._merge(lo, mid, hi, depth)

    def _merge(self, lo: int, mid: int, hi: int, depth: int) -> None:
        a = self.values
        left = a[lo : mid + 1]
        right = a[mid + 1 : hi + 1]
        self.aux = [None] * len(a)
        self.active_range = [lo, hi]
        self._set_note(f"合并 [{lo}, {mid}] 与 [{mid + 1}, {hi}]")
        self.emit(
            StepType.NOTE,
            f"合并两个有序区间：[{lo}, {mid}] 与 [{mid + 1}, {hi}]，逐次取较小元素写入",
            targets=[lo, hi],
            visual_action="merge",
            meta={"range": [lo, hi], "mid": mid, "left": left, "right": right},
        )
        i = j = 0
        k = lo
        self.at("while i < len(left) and j < len(right)")
        while i < len(left) and j < len(right):
            self.pointers = {"i": lo + i, "j": mid + 1 + j, "k": k}
            self.at("if left[i] <= right[j]")
            self.emit(
                StepType.COMPARE,
                f"比较左段 {self.fmt(left[i])} 与右段 {self.fmt(right[j])}",
                targets=[lo + i, mid + 1 + j],
                visual_action="compare",
                meta={"left": left[i], "right": right[j], "range": [lo, hi]},
            )
            if left[i] <= right[j]:
                value = left[i]
                i += 1
                self.at("arr[k] = left[i]")
            else:
                value = right[j]
                j += 1
                self.at("arr[k] = right[j]")
            a[k] = value
            self.aux[k] = value
            self.emit(
                StepType.UPDATE,
                f"把较小的 {self.fmt(value)} 写入 a[{k}]",
                targets=[k],
                visual_action="write",
                meta={"value": value, "range": [lo, hi]},
            )
            k += 1
        while i < len(left):
            value = left[i]
            a[k] = value
            self.aux[k] = value
            self.pointers = {"k": k}
            self.at("arr[k] = left[i]", 1)
            self.emit(
                StepType.UPDATE,
                f"左段剩余元素 {self.fmt(value)} 直接写入 a[{k}]",
                targets=[k],
                visual_action="write",
                meta={"value": value, "range": [lo, hi]},
            )
            i += 1
            k += 1
        while j < len(right):
            value = right[j]
            a[k] = value
            self.aux[k] = value
            self.pointers = {"k": k}
            self.at("arr[k] = right[j]", 1)
            self.emit(
                StepType.UPDATE,
                f"右段剩余元素 {self.fmt(value)} 直接写入 a[{k}]",
                targets=[k],
                visual_action="write",
                meta={"value": value, "range": [lo, hi]},
            )
            j += 1
            k += 1
        self.aux = None
        self.pointers = {}
        self.at("merge(arr, lo, mid, hi)")
        self.emit(
            StepType.MARK,
            f"区间 [{lo}, {hi}] 合并完成：{self.arr_text()}",
            targets=list(range(lo, hi + 1)),
            visual_action="mark",
            meta={"depth": depth, "range": [lo, hi]},
        )
