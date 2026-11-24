"""算法注册表：参数规范化、执行、独立校验、元数据。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .. import verify
from ..protocol.events import Complexity, InputSource, Trace, TraceMetadata, VisualKind
from ..protocol.teaching import TaskSpec
from ..tracers.base import BaseTracer
from ..tracers.dp import KNAPSACK_CODE, LCS_CODE, KnapsackTracer, LCSTracer
from ..tracers.graph import BFS_CODE, DFS_CODE, DIJKSTRA_CODE, BFSTracer, DFSTracer, DijkstraTracer
from ..tracers.search import BINARY_SEARCH_CODE, LINEAR_SEARCH_CODE, BinarySearchTracer, LinearSearchTracer
from ..tracers.sort import (
    BUBBLE_CODE,
    INSERTION_CODE,
    MERGE_CODE,
    QUICK_CODE,
    SELECTION_CODE,
    BubbleSortTracer,
    InsertionSortTracer,
    MergeSortTracer,
    QuickSortTracer,
    SelectionSortTracer,
)
from ..tracers.tree import (
    BST_INSERT_CODE,
    BST_SEARCH_CODE,
    INORDER_CODE,
    LEVEL_ORDER_CODE,
    POSTORDER_CODE,
    PREORDER_CODE,
    BSTBuildTracer,
    BSTSearchTracer,
    TreeTraversalTracer,
)


class TaskValidationError(ValueError):
    """任务参数不合法（面向用户的中文错误）。"""


# --------------------------------------------------------------------------- 参数解析
def _number(value: Any, name: str = "数值") -> int | float:
    if isinstance(value, bool):
        raise TaskValidationError(f"{name} 不能是布尔值")
    if isinstance(value, (int, float)):
        return int(value) if float(value).is_integer() else float(value)
    if isinstance(value, str):
        try:
            f = float(value.strip())
        except ValueError as exc:
            raise TaskValidationError(f"{name} “{value}” 不是合法数字") from exc
        return int(f) if f.is_integer() else f
    raise TaskValidationError(f"{name} 类型不支持：{type(value).__name__}")


def parse_number_list(raw: Any, name: str = "数组") -> list[int | float]:
    if isinstance(raw, str):
        text = raw.strip().strip("[]（）()")
        parts = [p for p in re.split(r"[,，;；\s]+", text) if p]
        values = [_number(p, name) for p in parts]
    elif isinstance(raw, (list, tuple)):
        values = [_number(v, name) for v in raw]
    else:
        raise TaskValidationError(f"{name} 必须是数字列表，例如 [5, 3, 8, 1]")
    return values


def parse_str_list(raw: Any, name: str = "列表") -> list[str]:
    if isinstance(raw, str):
        parts = [p for p in re.split(r"[,，;；\s]+", raw.strip().strip("[]")) if p]
    elif isinstance(raw, (list, tuple)):
        parts = [str(v).strip() for v in raw]
    else:
        raise TaskValidationError(f"{name} 必须是字符串列表")
    if not parts:
        raise TaskValidationError(f"{name} 不能为空")
    return parts


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TaskValidationError(message)


def normalize_array(raw: Any, *, name: str = "array", min_len: int = 2, max_len: int = 16) -> list[int | float]:
    values = parse_number_list(raw, name)
    _require(min_len <= len(values) <= max_len, f"{name} 长度需在 {min_len}~{max_len} 之间，当前 {len(values)} 个元素")
    for v in values:
        _require(-999 <= v <= 999, f"{name} 中元素 {v} 超出演示范围 [-999, 999]")
    return values


def normalize_graph_params(params: dict[str, Any]) -> tuple[list[str], list[tuple[str, str, float]], str, bool, dict[str, tuple[float, float]] | None, str | None]:
    nodes = parse_str_list(params.get("nodes", []), "nodes")
    _require(2 <= len(nodes) <= 10, "图节点数量需在 2~10 之间")
    _require(len(set(nodes)) == len(nodes), "图节点 id 不能重复")
    raw_edges = params.get("edges") or []
    if not isinstance(raw_edges, (list, tuple)):
        raise TaskValidationError("edges 必须是边的列表，例如 [[\"A\",\"B\",2]]")
    edges: list[tuple[str, str, float]] = []
    for index, edge in enumerate(raw_edges):
        if isinstance(edge, dict):
            u, v, w = edge.get("source"), edge.get("target"), edge.get("weight", 1)
        elif isinstance(edge, (list, tuple)) and len(edge) >= 2:
            u, v = edge[0], edge[1]
            w = edge[2] if len(edge) > 2 else 1
        else:
            raise TaskValidationError(f"第 {index + 1} 条边格式错误，应为 [起点, 终点, 权重]")
        u, v = str(u), str(v)
        _require(u in nodes and v in nodes, f"边 {u}→{v} 引用了不存在的节点")
        _require(u != v, f"边 {u}→{v} 是自环，暂不支持")
        weight = float(_number(w, "边权重"))
        _require(weight >= 0, "Dijkstra/BFS 仅支持非负边权")
        edges.append((u, v, weight))
    _require(len(edges) > 0, "图至少需要一条边")
    directed = bool(params.get("directed", False))
    start = str(params.get("start") or nodes[0])
    _require(start in nodes, f"起点 {start} 不在节点列表中")
    target = params.get("target")
    if target is not None:
        target = str(target)
        _require(target in nodes, f"目标节点 {target} 不在节点列表中")
    positions_raw = params.get("positions")
    positions: dict[str, tuple[float, float]] | None = None
    if positions_raw:
        positions = {}
        for node, pos in dict(positions_raw).items():
            node = str(node)
            if node in nodes:
                positions[node] = (float(pos[0]), float(pos[1]))
    return nodes, edges, start, directed, positions, target


# --------------------------------------------------------------------------- 运行结果
@dataclass
class RunOutcome:
    tracer: BaseTracer
    result: dict[str, Any]
    expected: dict[str, Any]
    verified: bool
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _sort_run(values: list[Any], tracer_cls: type[BaseTracer], **kwargs: Any) -> RunOutcome:
    tracer = tracer_cls(values, **kwargs)
    final = tracer.run()
    ok, notes = verify.verify_sort(list(values), list(final))
    return RunOutcome(
        tracer=tracer,
        result={"array": final, "summary": f"排序结果：{final}"},
        expected={"array": sorted(values)},
        verified=ok,
        notes=notes,
    )


def run_bubble(params: dict[str, Any]) -> RunOutcome:
    return _sort_run(normalize_array(params.get("array"), name="array"), BubbleSortTracer)


def run_selection(params: dict[str, Any]) -> RunOutcome:
    return _sort_run(normalize_array(params.get("array"), name="array"), SelectionSortTracer)


def run_insertion(params: dict[str, Any]) -> RunOutcome:
    return _sort_run(normalize_array(params.get("array"), name="array"), InsertionSortTracer)


def run_quick(params: dict[str, Any]) -> RunOutcome:
    strategy = str(params.get("pivot") or params.get("pivot_strategy") or "last").lower()
    if strategy in {"first", "首元素", "第一个", "left"}:
        strategy = "first"
    else:
        strategy = "last"
    return _sort_run(normalize_array(params.get("array"), name="array"), QuickSortTracer, pivot_strategy=strategy)


def run_merge(params: dict[str, Any]) -> RunOutcome:
    return _sort_run(normalize_array(params.get("array"), name="array"), MergeSortTracer)


def _search_params(params: dict[str, Any], *, auto_sorted: bool = False) -> tuple[list[Any], Any, list[str]]:
    values = normalize_array(params.get("array"), name="array")
    target = _number(params.get("target"), "target")
    warnings: list[str] = []
    if auto_sorted and values != sorted(values):
        values = sorted(values)
        warnings.append("输入数组不是升序，为演示二分查找已自动排序")
    return values, target, warnings


def run_binary_search(params: dict[str, Any]) -> RunOutcome:
    values, target, warnings = _search_params(params, auto_sorted=True)
    tracer = BinarySearchTracer(values, target)
    index = tracer.run()
    ok, notes = verify.verify_binary_search(values, target, index)
    return RunOutcome(
        tracer=tracer,
        result={"index": index, "target": target, "array": values, "summary": f"target={target} 的下标为 {index}"},
        expected={"index": bisect_index(values, target)},
        verified=ok,
        notes=notes,
        warnings=warnings,
    )


def bisect_index(values: list[Any], target: Any) -> int:
    import bisect

    pos = bisect.bisect_left(values, target)
    if pos < len(values) and values[pos] == target:
        return pos
    return -1


def run_linear_search(params: dict[str, Any]) -> RunOutcome:
    values, target, warnings = _search_params(params)
    tracer = LinearSearchTracer(values, target)
    index = tracer.run()
    ok, notes = verify.verify_linear_search(values, target, index)
    return RunOutcome(
        tracer=tracer,
        result={"index": index, "target": target, "array": values, "summary": f"target={target} 的下标为 {index}"},
        expected={"index": index},
        verified=ok,
        notes=notes,
        warnings=warnings,
    )


def _tree_values(params: dict[str, Any]) -> tuple[list[Any], list[str]]:
    raw = params.get("values", params.get("array"))
    values = normalize_array(raw, name="values", min_len=1, max_len=15)
    warnings: list[str] = []
    unique: list[Any] = []
    for v in values:
        if v in unique:
            warnings.append(f"二叉搜索树不支持重复值，已忽略重复的 {v}")
            continue
        unique.append(v)
    _require(len(unique) >= 2, "构建二叉搜索树至少需要 2 个互不相同的值")
    return unique, warnings


def run_bst_build(params: dict[str, Any]) -> RunOutcome:
    values, warnings = _tree_values(params)
    tracer = BSTBuildTracer(values)
    tracer.run()
    payload = []
    for node in tracer.nodes.values():
        children: dict[str, Any] = {"left": None, "right": None}
        if node.left:
            children["left"] = {"value": tracer.nodes[node.left].value}
        if node.right:
            children["right"] = {"value": tracer.nodes[node.right].value}
        payload.append({"value": node.value, "children": children})
    ok, notes = verify.verify_bst_build(values, payload)
    return RunOutcome(
        tracer=tracer,
        result={"values": values, "node_count": len(tracer.nodes), "summary": f"共构建 {len(tracer.nodes)} 个节点"},
        expected={"nodes": len(verify.reference_bst_insert(values))},
        verified=ok,
        notes=notes,
        warnings=warnings,
    )


def _traversal_run(params: dict[str, Any], order: str) -> RunOutcome:
    values, warnings = _tree_values(params)
    tracer = TreeTraversalTracer(values, order=order)
    result_order = tracer.run()
    ok, notes = verify.verify_tree(values, result_order, order)
    return RunOutcome(
        tracer=tracer,
        result={"order": result_order, "values": values, "summary": f"遍历结果：{result_order}"},
        expected={"order": sorted(set(values))},
        verified=ok,
        notes=notes,
        warnings=warnings,
    )


def run_inorder(params: dict[str, Any]) -> RunOutcome:
    return _traversal_run(params, "inorder")


def run_preorder(params: dict[str, Any]) -> RunOutcome:
    return _traversal_run(params, "preorder")


def run_postorder(params: dict[str, Any]) -> RunOutcome:
    return _traversal_run(params, "postorder")


def run_levelorder(params: dict[str, Any]) -> RunOutcome:
    return _traversal_run(params, "levelorder")


def run_bst_search(params: dict[str, Any]) -> RunOutcome:
    values, warnings = _tree_values(params)
    target = _number(params.get("target"), "target")
    tracer = BSTSearchTracer(values, target)
    found = tracer.run()
    ok = found == (target in set(values))
    notes = [] if ok else [f"查找结果 {found} 与参考结果 {target in set(values)} 不一致"]
    return RunOutcome(
        tracer=tracer,
        result={"found": found, "target": target, "values": values, "summary": f"target={target} {'存在' if found else '不存在'}"},
        expected={"found": target in set(values)},
        verified=ok,
        notes=notes,
        warnings=warnings,
    )


def run_bfs(params: dict[str, Any]) -> RunOutcome:
    nodes, edges, start, directed, positions, target = normalize_graph_params(params)
    tracer = BFSTracer(nodes, edges, start, BFS_CODE, directed=directed, positions=positions, target=target)
    order = tracer.run()
    reference = verify.reference_bfs(nodes, edges, start, directed)
    ok, notes = verify.verify_bfs(order, reference)
    return RunOutcome(
        tracer=tracer,
        result={"order": order, "summary": f"BFS 访问顺序：{order}"},
        expected={"order": reference},
        verified=ok,
        notes=notes,
    )


def run_dfs(params: dict[str, Any]) -> RunOutcome:
    nodes, edges, start, directed, positions, target = normalize_graph_params(params)
    tracer = DFSTracer(nodes, edges, start, DFS_CODE, directed=directed, positions=positions, target=target)
    order = tracer.run()
    reference = verify.reference_dfs(nodes, edges, start, directed)
    ok, notes = verify.verify_dfs(order, reference)
    return RunOutcome(
        tracer=tracer,
        result={"order": order, "summary": f"DFS 访问顺序：{order}"},
        expected={"order": reference},
        verified=ok,
        notes=notes,
    )


def run_dijkstra(params: dict[str, Any]) -> RunOutcome:
    nodes, edges, start, directed, positions, target = normalize_graph_params(params)
    tracer = DijkstraTracer(nodes, edges, start, DIJKSTRA_CODE, directed=directed, positions=positions, target=target)
    distances = tracer.run()
    reference = verify.reference_dijkstra(nodes, edges, start, directed)
    ok, notes = verify.verify_dijkstra(distances, reference, target)
    return RunOutcome(
        tracer=tracer,
        result={**tracer.steps[-1].meta, "distances": distances, "summary": tracer.steps[-1].description},
        expected={"distances": reference},
        verified=ok,
        notes=notes,
    )


def run_knapsack(params: dict[str, Any]) -> RunOutcome:
    weights = parse_number_list(params.get("weights"), "weights")
    values = parse_number_list(params.get("values"), "values")
    capacity = _number(params.get("capacity"), "capacity")
    _require(isinstance(capacity, int) or float(capacity).is_integer(), "capacity 必须是整数")
    capacity = int(capacity)
    _require(len(weights) == len(values), "weights 与 values 长度必须一致")
    _require(1 <= len(weights) <= 6, "0-1 背包演示支持 1~6 个物品")
    _require(1 <= capacity <= 12, "背包容量需在 1~12 之间（演示用）")
    _require(all(float(w) >= 1 and float(w).is_integer() for w in weights), "物品重量需为正整数")
    _require(all(float(v) >= 0 and float(v).is_integer() for v in values), "物品价值需为非负整数")
    weights = [int(w) for w in weights]
    values = [int(v) for v in values]
    tracer = KnapsackTracer(weights, values, capacity)
    result = tracer.run()
    ok, notes = verify.verify_knapsack(weights, values, capacity, result["max_value"], result["chosen"])
    return RunOutcome(
        tracer=tracer,
        result=result,
        expected={"max_value": verify.brute_knapsack(weights, values, capacity)[0]},
        verified=ok,
        notes=notes,
    )


def run_lcs(params: dict[str, Any]) -> RunOutcome:
    s1 = str(params.get("s1") or params.get("string1") or "").strip()
    s2 = str(params.get("s2") or params.get("string2") or "").strip()
    _require(1 <= len(s1) <= 8 and 1 <= len(s2) <= 8, "LCS 演示要求两个字符串长度在 1~8 之间")
    tracer = LCSTracer(s1, s2)
    result = tracer.run()
    ok, notes = verify.verify_lcs(s1, s2, result["length"], result["subsequence"])
    return RunOutcome(
        tracer=tracer,
        result=result,
        expected={"length": verify.reference_lcs(s1, s2)},
        verified=ok,
        notes=notes,
    )


# --------------------------------------------------------------------------- 注册表
@dataclass(frozen=True)
class AlgorithmSpec:
    key: str
    title: str
    category: str
    visual_kind: VisualKind
    aliases: tuple[str, ...]
    time_complexity: str
    space_complexity: str
    complexity_note: str
    code: str
    description: str
    idea: tuple[str, ...]
    summary: tuple[str, ...]
    defaults: dict[str, Any] = field(default_factory=dict)
    runner: Callable[[dict[str, Any]], RunOutcome] = run_bubble
    priority: int = 0

    @property
    def complexity(self) -> Complexity:
        return Complexity(time=self.time_complexity, space=self.space_complexity, note=self.complexity_note)


SORT_IDEA = (
    "每一轮只处理局部的一对或一段元素，通过比较决定它们的位置",
    "随着比较次数增加，有序区间不断变大，无序区间不断缩小",
    "循环不变量保证已处理部分始终有序，最终整个数组有序",
)

SORT_SUMMARY = (
    "排序的核心是“比较 + 移动”，不同算法的差别在于比较与移动的组织方式",
    "时间复杂度描述数据量增大时比较/移动次数的增长趋势",
    "实际工程中常使用语言内置的 Timsort 等混合排序",
)

ALGORITHMS: dict[str, AlgorithmSpec] = {
    "bubble_sort": AlgorithmSpec(
        key="bubble_sort",
        title="冒泡排序",
        category="sort",
        visual_kind=VisualKind.ARRAY,
        aliases=("bubble_sort", "bubblesort", "bubble", "冒泡排序", "冒泡", "起泡排序"),
        time_complexity="O(n²)",
        space_complexity="O(1)",
        complexity_note="最好情况 O(n)（已有序且提前结束），平均和最坏 O(n²)",
        code=BUBBLE_CODE,
        description="相邻元素两两比较，逆序就交换，每一轮把最大值“冒泡”到末尾。",
        idea=(
            "从左到右比较相邻的两个元素，逆序就交换",
            "每完成一轮，当前未排序区间的最大值会被推到最右端",
            "如果某一轮没有发生任何交换，说明数组已经有序，可以提前结束",
        ),
        summary=SORT_SUMMARY,
        defaults={"array": [5, 3, 8, 1, 9, 2]},
        runner=run_bubble,
    ),
    "selection_sort": AlgorithmSpec(
        key="selection_sort",
        title="选择排序",
        category="sort",
        visual_kind=VisualKind.ARRAY,
        aliases=("selection_sort", "selectionsort", "selection", "选择排序", "选择"),
        time_complexity="O(n²)",
        space_complexity="O(1)",
        complexity_note="无论数据如何都需要 O(n²) 次比较，但交换次数最多 n-1 次",
        code=SELECTION_CODE,
        description="每轮从未排序区间选出最小值，放到未排序区间的首位。",
        idea=(
            "把数组分成“已排序”和“未排序”两部分",
            "每一轮扫描未排序区间，记录最小值的位置",
            "把最小值与未排序区间的第一个元素交换，有序区间扩大一位",
        ),
        summary=SORT_SUMMARY,
        defaults={"array": [8, 3, 5, 1, 9, 2]},
        runner=run_selection,
    ),
    "insertion_sort": AlgorithmSpec(
        key="insertion_sort",
        title="插入排序",
        category="sort",
        visual_kind=VisualKind.ARRAY,
        aliases=("insertion_sort", "insertionsort", "insertion", "插入排序", "插入"),
        time_complexity="O(n²)",
        space_complexity="O(1)",
        complexity_note="最好情况 O(n)（数据基本有序），最坏 O(n²)",
        code=INSERTION_CODE,
        description="像整理扑克牌一样，把每个新元素插入到前面已有序序列的正确位置。",
        idea=(
            "把第一个元素看作已有序的序列",
            "依次取出后面的元素 key，与前面的元素从右往左比较",
            "比 key 大的元素依次右移，最后把 key 放到空出的位置",
        ),
        summary=SORT_SUMMARY,
        defaults={"array": [7, 3, 9, 1, 5, 2]},
        runner=run_insertion,
    ),
    "quick_sort": AlgorithmSpec(
        key="quick_sort",
        title="快速排序",
        category="sort",
        visual_kind=VisualKind.ARRAY,
        aliases=("quick_sort", "quicksort", "quick", "快速排序", "快排", "快速"),
        time_complexity="O(n log n)",
        space_complexity="O(log n)",
        complexity_note="平均 O(n log n)，最坏 O(n²)（枢轴选择极不均衡时），递归栈 O(log n)",
        code=QUICK_CODE,
        description="选择枢轴，把数组划分为“小于等于枢轴”和“大于枢轴”两部分，再递归处理。",
        idea=(
            "从区间中选择一个元素作为枢轴 pivot",
            "扫描区间，把不大于 pivot 的元素交换到左区，大于的留在右区",
            "把 pivot 放到左右分界点，此时 pivot 已归位，再递归处理左右两个子区间",
        ),
        summary=(
            "快速排序是分治思想的典型应用：划分 + 递归",
            "平均性能优秀，是许多语言标准库排序的基础",
            "枢轴选择会影响最坏情况，可用随机化或三数取中优化",
        ),
        defaults={"array": [8, 3, 5, 1, 9, 2], "pivot": "last"},
        runner=run_quick,
        priority=5,
    ),
    "merge_sort": AlgorithmSpec(
        key="merge_sort",
        title="归并排序",
        category="sort",
        visual_kind=VisualKind.ARRAY,
        aliases=("merge_sort", "mergesort", "merge", "归并排序", "归并", "合并排序"),
        time_complexity="O(n log n)",
        space_complexity="O(n)",
        complexity_note="任何情况下都是 O(n log n)，需要额外的 O(n) 合并缓冲空间",
        code=MERGE_CODE,
        description="把区间不断二分，直到每个子区间只有一个元素，再两两合并成有序区间。",
        idea=(
            "分：把当前区间从中间拆成两半，递归拆分直到只剩一个元素",
            "治：把两个已经有序的子区间合并成一个有序区间",
            "合并时每次取两个子区间头部较小的元素，依次写入原数组",
        ),
        summary=(
            "归并排序是稳定排序，适合处理链表和外部排序",
            "时间复杂度稳定为 O(n log n)，代价是需要额外空间",
            "“拆分 + 合并”是理解分治算法的经典范例",
        ),
        defaults={"array": [8, 3, 5, 1, 9, 2, 7, 4]},
        runner=run_merge,
    ),
    "binary_search": AlgorithmSpec(
        key="binary_search",
        title="二分查找",
        category="search",
        visual_kind=VisualKind.ARRAY,
        aliases=("binary_search", "binarysearch", "bsearch", "二分查找", "二分搜索", "折半查找", "二分"),
        time_complexity="O(log n)",
        space_complexity="O(1)",
        complexity_note="每次比较把候选区间缩小一半，最多约 log₂n 次",
        code=BINARY_SEARCH_CODE,
        description="在有序数组中，每次取中间元素与目标比较，排除一半区间。",
        idea=(
            "维护候选区间 [left, right]，初始为整个数组",
            "取中点 mid，比较 a[mid] 与 target",
            "根据大小关系把 left 或 right 移到 mid 的另一侧，直到命中或区间为空",
        ),
        summary=(
            "二分查找依赖“有序”这一前提",
            "每次排除一半候选，因此复杂度是对数级",
            "注意边界：循环条件 left <= right，区间收缩时 ±1",
        ),
        defaults={"array": [1, 3, 5, 7, 9, 11, 13], "target": 7},
        runner=run_binary_search,
        priority=10,
    ),
    "linear_search": AlgorithmSpec(
        key="linear_search",
        title="线性查找",
        category="search",
        visual_kind=VisualKind.ARRAY,
        aliases=("linear_search", "linearsearch", "线性查找", "顺序查找", "遍历查找"),
        time_complexity="O(n)",
        space_complexity="O(1)",
        complexity_note="最坏需要比较 n 次，不要求数组有序",
        code=LINEAR_SEARCH_CODE,
        description="从数组头到尾逐个比较，直到找到目标或遍历结束。",
        idea=(
            "从下标 0 开始依次看每个元素",
            "如果当前元素等于 target，立即返回下标",
            "遍历结束仍未命中，返回 -1 表示不存在",
        ),
        summary=(
            "线性查找实现简单，对数据是否有序没有要求",
            "数据量大时效率低于二分查找和哈希表",
            "适合小规模数据或只查找一次的场景",
        ),
        defaults={"array": [4, 2, 9, 7, 5, 1], "target": 7},
        runner=run_linear_search,
        priority=8,
    ),
    "bst_build": AlgorithmSpec(
        key="bst_build",
        title="二叉搜索树构建",
        category="tree",
        visual_kind=VisualKind.TREE,
        aliases=("bst_build", "bst_insert", "bst", "二叉搜索树", "二叉排序树", "二叉查找树"),
        time_complexity="O(n log n)",
        space_complexity="O(n)",
        complexity_note="平均每次插入 O(log n)，最坏（退化成链）O(n)；建树总代价平均 O(n log n)",
        code=BST_INSERT_CODE,
        description="按“左小右大”的规则，把序列中的元素依次插入二叉搜索树。",
        idea=(
            "空树时，第一个元素成为根节点",
            "新元素从根开始比较：更小走左子树，更大走右子树",
            "走到空位置时创建新节点，因此中序遍历一定是升序",
        ),
        summary=(
            "二叉搜索树通过比较关系组织数据，支持高效查找",
            "插入顺序会影响树的高度，甚至退化成链表",
            "平衡二叉树（AVL、红黑树）通过旋转控制高度",
        ),
        defaults={"values": [8, 3, 10, 1, 6, 14, 4, 7, 13]},
        runner=run_bst_build,
        priority=4,
    ),
    "bst_search": AlgorithmSpec(
        key="bst_search",
        title="二叉搜索树查找",
        category="tree",
        visual_kind=VisualKind.TREE,
        aliases=("bst_search", "二叉搜索树查找", "二叉搜索树搜索", "bst查找"),
        time_complexity="O(log n)",
        space_complexity="O(1)",
        complexity_note="平均 O(log n)，最坏 O(n)（树退化成链表时）",
        code=BST_SEARCH_CODE,
        description="从根节点出发，按“左小右大”不断缩小搜索范围。",
        idea=(
            "从根节点开始，把 target 与当前节点值比较",
            "target 更小进入左子树，更大进入右子树",
            "节点为空说明不存在；相等即命中",
        ),
        summary=(
            "查找路径长度等于树高",
            "树越平衡，查找越快",
            "删除节点需要分情况讨论，是二叉搜索树的难点",
        ),
        defaults={"values": [8, 3, 10, 1, 6, 14, 4, 7, 13], "target": 7},
        runner=run_bst_search,
        priority=9,
    ),
    "tree_inorder": AlgorithmSpec(
        key="tree_inorder",
        title="二叉树中序遍历",
        category="tree",
        visual_kind=VisualKind.TREE,
        aliases=("tree_inorder", "inorder", "中序遍历", "中序"),
        time_complexity="O(n)",
        space_complexity="O(h)",
        complexity_note="每个节点访问一次，递归栈深度为树高 h",
        code=INORDER_CODE,
        description="按“左子树 → 根 → 右子树”的顺序访问每个节点。",
        idea=(
            "先递归遍历左子树",
            "再访问根节点，把值加入输出序列",
            "最后递归遍历右子树；对二叉搜索树而言结果天然升序",
        ),
        summary=(
            "中序遍历是二叉搜索树有序性的直接体现",
            "递归版代码简洁，迭代版需要显式栈",
            "遍历顺序：左 → 根 → 右",
        ),
        defaults={"values": [8, 3, 10, 1, 6, 14, 4, 7, 13]},
        runner=run_inorder,
        priority=12,
    ),
    "tree_preorder": AlgorithmSpec(
        key="tree_preorder",
        title="二叉树前序遍历",
        category="tree",
        visual_kind=VisualKind.TREE,
        aliases=("tree_preorder", "preorder", "前序遍历", "先序遍历", "前序", "先序"),
        time_complexity="O(n)",
        space_complexity="O(h)",
        complexity_note="每个节点访问一次，递归栈深度为树高 h",
        code=PREORDER_CODE,
        description="按“根 → 左子树 → 右子树”的顺序访问每个节点。",
        idea=(
            "先访问根节点并输出",
            "再递归遍历左子树",
            "最后递归遍历右子树；常用于复制树或生成表达式前缀",
        ),
        summary=(
            "前序遍历第一个访问的总是根节点",
            "与中序遍历配合可以唯一确定一棵二叉树",
            "遍历顺序：根 → 左 → 右",
        ),
        defaults={"values": [8, 3, 10, 1, 6, 14, 4, 7, 13]},
        runner=run_preorder,
        priority=11,
    ),
    "tree_postorder": AlgorithmSpec(
        key="tree_postorder",
        title="二叉树后序遍历",
        category="tree",
        visual_kind=VisualKind.TREE,
        aliases=("tree_postorder", "postorder", "后序遍历", "后序"),
        time_complexity="O(n)",
        space_complexity="O(h)",
        complexity_note="每个节点访问一次，递归栈深度为树高 h",
        code=POSTORDER_CODE,
        description="按“左子树 → 右子树 → 根”的顺序访问每个节点。",
        idea=(
            "先递归遍历左子树",
            "再递归遍历右子树",
            "最后访问根节点；适合释放树或计算子树结果",
        ),
        summary=(
            "后序遍历最后访问根节点",
            "常用于自底向上的计算，例如树的高度、表达式求值",
            "遍历顺序：左 → 右 → 根",
        ),
        defaults={"values": [8, 3, 10, 1, 6, 14, 4, 7, 13]},
        runner=run_postorder,
        priority=11,
    ),
    "tree_levelorder": AlgorithmSpec(
        key="tree_levelorder",
        title="二叉树层序遍历",
        category="tree",
        visual_kind=VisualKind.TREE,
        aliases=("tree_levelorder", "levelorder", "level_order", "层序遍历", "层次遍历", "广度遍历树"),
        time_complexity="O(n)",
        space_complexity="O(w)",
        complexity_note="每个节点访问一次，队列中最多保存一层的节点，w 为最大层宽",
        code=LEVEL_ORDER_CODE,
        description="借助队列，从上到下、从左到右逐层访问节点。",
        idea=(
            "把根节点放入队列",
            "每次取出队首节点并访问，再把它的左右孩子依次入队",
            "队列为空时，所有节点都访问完毕",
        ),
        summary=(
            "层序遍历是 BFS 在树上的特例",
            "队列保证了“先入先出”，从而逐层扩展",
            "可用于求树的宽度、按层打印等",
        ),
        defaults={"values": [8, 3, 10, 1, 6, 14, 4, 7, 13]},
        runner=run_levelorder,
        priority=11,
    ),
    "bfs": AlgorithmSpec(
        key="bfs",
        title="广度优先搜索 BFS",
        category="graph",
        visual_kind=VisualKind.GRAPH,
        aliases=("bfs", "breadth_first_search", "广度优先", "广度优先搜索", "宽度优先搜索"),
        time_complexity="O(V + E)",
        space_complexity="O(V)",
        complexity_note="V 为顶点数，E 为边数；队列最多保存一层顶点",
        code=BFS_CODE,
        description="用队列从起点逐层扩展，先访问距离近的节点。",
        idea=(
            "起点入队并标记已访问",
            "每次取出队首节点，访问它并把未访问的邻居入队",
            "队列为空时结束；在无权图中得到按距离分层的访问顺序",
        ),
        summary=(
            "BFS 使用队列，保证按层访问",
            "无权图最短路、连通分量、迷宫最短步数都可用 BFS",
            "复杂度为 O(V + E)",
        ),
        defaults={
            "nodes": ["A", "B", "C", "D", "E", "F"],
            "edges": [["A", "B"], ["A", "C"], ["B", "D"], ["C", "E"], ["D", "F"], ["E", "F"]],
            "start": "A",
        },
        runner=run_bfs,
        priority=7,
    ),
    "dfs": AlgorithmSpec(
        key="dfs",
        title="深度优先搜索 DFS",
        category="graph",
        visual_kind=VisualKind.GRAPH,
        aliases=("dfs", "depth_first_search", "深度优先", "深度优先搜索"),
        time_complexity="O(V + E)",
        space_complexity="O(V)",
        complexity_note="V 为顶点数，E 为边数；栈最多保存一条路径上的顶点",
        code=DFS_CODE,
        description="用栈沿一条路径尽量走到底，走不通再回溯。",
        idea=(
            "起点入栈",
            "弹出栈顶节点，若未访问则访问它，并把未访问邻居压栈",
            "栈为空时结束；优先深入而不是逐层扩展",
        ),
        summary=(
            "DFS 使用栈（递归或显式栈）",
            "适合连通性判断、拓扑排序、回溯搜索",
            "复杂度为 O(V + E)",
        ),
        defaults={
            "nodes": ["A", "B", "C", "D", "E", "F"],
            "edges": [["A", "B"], ["A", "C"], ["B", "D"], ["C", "E"], ["D", "F"], ["E", "F"]],
            "start": "A",
        },
        runner=run_dfs,
        priority=7,
    ),
    "dijkstra": AlgorithmSpec(
        key="dijkstra",
        title="Dijkstra 最短路径",
        category="graph",
        visual_kind=VisualKind.GRAPH,
        aliases=("dijkstra", "dijkstras", "迪杰斯特拉", "迪克斯特拉", "最短路径"),
        time_complexity="O((V + E) log V)",
        space_complexity="O(V)",
        complexity_note="使用优先队列，V 为顶点数，E 为边数；要求边权非负",
        code=DIJKSTRA_CODE,
        description="用优先队列每次确定当前距离最小的节点，再松弛它的邻边。",
        idea=(
            "起点距离设为 0，其余节点距离设为无穷大",
            "每次从优先队列取出距离最小的未确定节点，它的最短距离就此确定",
            "用该节点松弛邻居：若经过它能得到更短距离，就更新并入队",
        ),
        summary=(
            "Dijkstra 适用于非负权图",
            "优先队列让每次都能确定当前最近的节点",
            "负权边需要使用 Bellman-Ford 等算法",
        ),
        defaults={
            "nodes": ["A", "B", "C", "D", "E", "F"],
            "edges": [
                ["A", "B", 4],
                ["A", "C", 2],
                ["B", "C", 1],
                ["B", "D", 5],
                ["C", "D", 8],
                ["C", "E", 10],
                ["D", "E", 2],
                ["D", "F", 6],
                ["E", "F", 3],
            ],
            "start": "A",
            "target": "F",
        },
        runner=run_dijkstra,
        priority=9,
    ),
    "knapsack_01": AlgorithmSpec(
        key="knapsack_01",
        title="0-1 背包问题",
        category="dp",
        visual_kind=VisualKind.MATRIX,
        aliases=("knapsack_01", "knapsack", "0_1_knapsack", "0-1背包", "01背包", "零一背包", "背包问题", "背包"),
        time_complexity="O(n · W)",
        space_complexity="O(n · W)",
        complexity_note="n 为物品数，W 为容量；滚动数组可把空间优化到 O(W)",
        code=KNAPSACK_CODE,
        description="用二维 DP 表记录“前 i 个物品、容量 w”时的最大价值。",
        idea=(
            "dp[i][w] 表示只考虑前 i 个物品、容量为 w 时的最大价值",
            "不选第 i 个物品：dp[i][w] = dp[i-1][w]",
            "选第 i 个物品：dp[i][w] = dp[i-1][w-wᵢ] + vᵢ，二者取较大值",
        ),
        summary=(
            "0-1 背包是二维动态规划的经典问题",
            "状态定义和转移方程来自“选或不选”的决策",
            "通过回溯 DP 表可以得到具体选择了哪些物品",
        ),
        defaults={
            "weights": [2, 3, 4, 5],
            "values": [3, 4, 5, 6],
            "capacity": 8,
        },
        runner=run_knapsack,
        priority=6,
    ),
    "lcs": AlgorithmSpec(
        key="lcs",
        title="最长公共子序列 LCS",
        category="dp",
        visual_kind=VisualKind.MATRIX,
        aliases=("lcs", "longest_common_subsequence", "最长公共子序列", "公共子序列"),
        time_complexity="O(m · n)",
        space_complexity="O(m · n)",
        complexity_note="m、n 为两个字符串长度；滚动数组可优化到 O(min(m,n))",
        code=LCS_CODE,
        description="用二维 DP 表比较两个字符串前缀的最长公共子序列长度。",
        idea=(
            "dp[i][j] 表示 s1 前 i 个字符与 s2 前 j 个字符的 LCS 长度",
            "若 s1[i-1] == s2[j-1]，则 dp[i][j] = dp[i-1][j-1] + 1",
            "否则 dp[i][j] = max(dp[i-1][j], dp[i][j-1])，从两个方向继承",
        ),
        summary=(
            "LCS 描述了两个序列的相似程度",
            "状态转移来自“末尾字符是否相同”的分类讨论",
            "回溯 DP 表即可还原出一条最长公共子序列",
        ),
        defaults={"s1": "ABCBDAB", "s2": "BDCABA"},
        runner=run_lcs,
        priority=6,
    ),
}

_ALIAS_TO_KEY: dict[str, str] = {}
for _key, _spec in ALGORITHMS.items():
    _ALIAS_TO_KEY[_key] = _key
    for _alias in _spec.aliases:
        _ALIAS_TO_KEY[_normalized := re.sub(r"[\s_\-]+", "", _alias.lower())] = _key


def _normalize_name(name: str) -> str:
    return re.sub(r"[\s_\-]+", "", name.strip().lower())


def resolve_algorithm(name: str | None) -> AlgorithmSpec | None:
    if not name:
        return None
    key = _ALIAS_TO_KEY.get(_normalize_name(name))
    if key:
        return ALGORITHMS[key]
    return None


def detect_algorithms(text: str) -> list[AlgorithmSpec]:
    """从自然语言中检测算法，按优先级 + 别名长度排序。"""
    normalized = _normalize_name(text)
    matches: list[tuple[int, int, AlgorithmSpec]] = []
    for spec in ALGORITHMS.values():
        best = 0
        for alias in spec.aliases:
            a = _normalize_name(alias)
            if a and a in normalized:
                best = max(best, len(a))
        if best:
            matches.append((spec.priority, best, spec))
    matches.sort(key=lambda item: (item[0], item[1]), reverse=True)
    seen: set[str] = set()
    result: list[AlgorithmSpec] = []
    for _, _, spec in matches:
        if spec.key not in seen:
            seen.add(spec.key)
            result.append(spec)
    return result


def list_algorithms() -> list[AlgorithmSpec]:
    return sorted(ALGORITHMS.values(), key=lambda s: (["sort", "search", "tree", "graph", "dp"].index(s.category), s.title))


# --------------------------------------------------------------------------- 执行
@dataclass
class ExecutionOutcome:
    trace: Trace
    spec: TaskSpec
    warnings: list[str] = field(default_factory=list)


def execute_task(task: TaskSpec) -> ExecutionOutcome:
    """根据任务参数执行真实算法并生成完整事件流。"""
    algorithm = resolve_algorithm(task.algorithm)
    if algorithm is None:
        hint = "、".join(a.title for a in list_algorithms()[:6])
        raise TaskValidationError(f"暂不支持算法“{task.algorithm}”，当前可用：{hint} 等")
    params = dict(algorithm.defaults)
    params.update({k: v for k, v in task.params.items() if v is not None})
    outcome = algorithm.runner(params)
    tracer = outcome.tracer
    title = task.title or algorithm.title
    source = task.source
    try:
        input_source = InputSource(source)
    except ValueError:
        input_source = InputSource.PRESET
    metadata = TraceMetadata(
        algorithm=algorithm.key,
        title=title,
        category=algorithm.category,
        visual_kind=algorithm.visual_kind,
        language="python",
        source=input_source,
        input={k: v for k, v in params.items()},
        expected_output=outcome.expected,
        complexity=algorithm.complexity,
        code=algorithm.code,
        code_language="python",
        description=algorithm.description,
        idea=list(algorithm.idea),
        summary=list(algorithm.summary),
        tags=[algorithm.category, algorithm.key],
    )
    trace = tracer.build_trace(metadata, outcome.result, outcome.verified, outcome.notes)
    return ExecutionOutcome(trace=trace, spec=task, warnings=outcome.warnings)
