"""算法正确性校验：用独立参考实现核对追踪结果，防止“动画对了但算法错了”。"""
from __future__ import annotations

import bisect
import heapq
import itertools
import math
from collections import deque
from typing import Any


def verify_sort(original: list[Any], result: list[Any]) -> tuple[bool, list[str]]:
    notes: list[str] = []
    try:
        expected = sorted(original)
    except TypeError:
        return False, ["数组元素类型不可比较，无法排序"]
    if list(result) != expected:
        notes.append(f"排序结果与参考实现不一致：得到 {result}，期望 {expected}")
    from collections import Counter

    try:
        if Counter(result) != Counter(original):
            notes.append("排序结果元素多重集合与原数组不一致（出现元素丢失或重复）")
    except TypeError:
        notes.append("元素不可哈希，跳过多重集校验")
    return not notes, notes


def verify_binary_search(array: list[Any], target: Any, index: int) -> tuple[bool, list[str]]:
    notes: list[str] = []
    expected = bisect.bisect_left(array, target)
    if expected < len(array) and array[expected] == target:
        if index != expected and not (0 <= index < len(array) and array[index] == target):
            notes.append(f"二分查找返回下标 {index}，但目标值实际在 {expected}")
    else:
        if index != -1:
            notes.append(f"目标值不存在，函数应返回 -1，实际返回 {index}")
    return not notes, notes


def verify_linear_search(array: list[Any], target: Any, index: int) -> tuple[bool, list[str]]:
    notes: list[str] = []
    expected = -1
    for i, value in enumerate(array):
        if value == target:
            expected = i
            break
    if index != expected:
        notes.append(f"线性查找返回 {index}，参考实现返回 {expected}")
    return not notes, notes


def verify_tree(values: list[Any], inorder: list[Any], order: str) -> tuple[bool, list[str]]:
    notes: list[str] = []
    expected_inorder = sorted(set(values))
    if order == "inorder" and list(inorder) != expected_inorder:
        notes.append(f"中序遍历结果不是升序：{inorder}，期望 {expected_inorder}")
    if order in {"inorder", "preorder", "postorder"}:
        if sorted(inorder) != expected_inorder:
            notes.append("遍历结果没有覆盖全部节点或有重复")
    if order == "levelorder":
        if sorted(inorder) != expected_inorder:
            notes.append("层序遍历结果没有覆盖全部节点或有重复")
    return not notes, notes


def _adjacency(
    nodes: list[str], edges: list[tuple[str, str, float]], directed: bool
) -> dict[str, list[tuple[str, float]]]:
    adj: dict[str, list[tuple[str, float]]] = {n: [] for n in nodes}
    for u, v, w in edges:
        adj.setdefault(u, []).append((v, w))
        if not directed:
            adj.setdefault(v, []).append((u, w))
    return adj


def reference_bfs(
    nodes: list[str], edges: list[tuple[str, str, float]], start: str, directed: bool = False
) -> list[str]:
    adj = _adjacency(nodes, edges, directed)
    visited = {start}
    queue = deque([start])
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for neighbor, _ in adj.get(node, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return order


def verify_bfs(order: list[str], reference: list[str]) -> tuple[bool, list[str]]:
    if list(order) != reference:
        return False, [f"BFS 访问顺序 {order} 与参考实现 {reference} 不一致"]
    return True, []


def reference_dfs(
    nodes: list[str], edges: list[tuple[str, str, float]], start: str, directed: bool = False
) -> list[str]:
    adj = _adjacency(nodes, edges, directed)
    visited: set[str] = set()
    stack = [start]
    order: list[str] = []
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        order.append(node)
        for neighbor, _ in reversed(adj.get(node, [])):
            if neighbor not in visited:
                stack.append(neighbor)
    return order


def verify_dfs(order: list[str], reference: list[str]) -> tuple[bool, list[str]]:
    if list(order) != reference:
        return False, [f"DFS 访问顺序 {order} 与参考实现 {reference} 不一致"]
    return True, []


def reference_dijkstra(
    nodes: list[str], edges: list[tuple[str, str, float]], start: str, directed: bool = False
) -> dict[str, float]:
    adj = _adjacency(nodes, edges, directed)
    dist: dict[str, float] = {start: 0.0}
    pq = [(0.0, start)]
    while pq:
        d, node = heapq.heappop(pq)
        if d > dist.get(node, math.inf):
            continue
        for neighbor, weight in adj.get(node, []):
            nd = d + weight
            if nd < dist.get(neighbor, math.inf):
                dist[neighbor] = nd
                heapq.heappush(pq, (nd, neighbor))
    return dist


def verify_dijkstra(result: dict[str, float], reference: dict[str, float], target: str | None) -> tuple[bool, list[str]]:
    notes: list[str] = []
    for node, expected in reference.items():
        actual = result.get(node)
        if actual is None or not math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9):
            notes.append(f"节点 {node} 最短距离为 {actual}，参考实现为 {expected}")
    if target is not None:
        if target not in reference:
            notes.append(f"目标节点 {target} 不可达")
    return not notes, notes


def brute_knapsack(weights: list[int], values: list[int], capacity: int) -> tuple[int, list[int]]:
    n = len(weights)
    best = 0
    best_subset: list[int] = []
    for mask in range(1 << n):
        total_w = 0
        total_v = 0
        subset: list[int] = []
        for i in range(n):
            if mask & (1 << i):
                total_w += weights[i]
                total_v += values[i]
                subset.append(i)
        if total_w <= capacity and total_v > best:
            best = total_v
            best_subset = subset
    return best, best_subset


def verify_knapsack(
    weights: list[int], values: list[int], capacity: int, max_value: int, chosen: list[int]
) -> tuple[bool, list[str]]:
    notes: list[str] = []
    ref_value, _ = brute_knapsack(weights, values, capacity)
    if max_value != ref_value:
        notes.append(f"背包最大价值 {max_value}，穷举参考值 {ref_value}")
    total_w = sum(weights[i] for i in chosen)
    total_v = sum(values[i] for i in chosen)
    if total_w > capacity:
        notes.append(f"回溯选择的物品总重量 {total_w} 超过容量 {capacity}")
    if total_v != max_value:
        notes.append(f"回溯解的总价值 {total_v} 不等于最大价值 {max_value}")
    return not notes, notes


def reference_lcs(s1: str, s2: str) -> int:
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[m][n]


def is_subsequence(candidate: str, text: str) -> bool:
    it = iter(text)
    return all(ch in it for ch in candidate)


def verify_lcs(s1: str, s2: str, length: int, subsequence: str) -> tuple[bool, list[str]]:
    notes: list[str] = []
    expected = reference_lcs(s1, s2)
    if length != expected:
        notes.append(f"LCS 长度 {length}，参考 DP 长度 {expected}")
    if len(subsequence) != length:
        notes.append(f"回溯出的子序列长度 {len(subsequence)} 与 LCS 长度 {length} 不一致")
    if not is_subsequence(subsequence, s1) or not is_subsequence(subsequence, s2):
        notes.append(f"回溯结果 \"{subsequence}\" 不是两个字符串的公共子序列")
    return not notes, notes


def reference_bst_insert(values: list[Any]) -> dict[str, Any]:
    """独立实现：返回 {value: (left, right)}，用于核对构建结果。"""

    class N:
        __slots__ = ("v", "l", "r")

        def __init__(self, v: Any) -> None:
            self.v = v
            self.l: N | None = None
            self.r: N | None = None

    root: N | None = None
    for value in values:
        if root is None:
            root = N(value)
            continue
        node = root
        while True:
            if value < node.v:
                if node.l is None:
                    node.l = N(value)
                    break
                node = node.l
            elif value > node.v:
                if node.r is None:
                    node.r = N(value)
                    break
                node = node.r
            else:
                break
    result: dict[str, Any] = {}
    if root is not None:
        stack = [root]
        while stack:
            node = stack.pop()
            result[node.v] = (node.l.v if node.l else None, node.r.v if node.r else None)
            if node.l:
                stack.append(node.l)
            if node.r:
                stack.append(node.r)
    return result


def verify_bst_build(values: list[Any], nodes: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    notes: list[str] = []
    reference = reference_bst_insert(values)
    built: dict[Any, tuple[Any, Any]] = {}
    for node in nodes:
        left_value = None
        right_value = None
        children = node.get("children", {})
        if children.get("left") is not None:
            left_value = children["left"].get("value")
        if children.get("right") is not None:
            right_value = children["right"].get("value")
        built[node["value"]] = (left_value, right_value)
    if built != reference:
        notes.append("二叉搜索树结构与参考实现不一致")
    if len(reference) != len(values):
        notes.append("输入中存在重复值，二叉搜索树只保留一个")
    return not notes, notes
