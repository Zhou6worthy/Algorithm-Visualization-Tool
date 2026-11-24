"""图结构追踪器：BFS、DFS、Dijkstra。"""
from __future__ import annotations

import heapq
import math
from typing import Any

from ..protocol.events import (
    GraphEdgeState,
    GraphNodeState,
    GraphState,
    StepType,
    VisualKind,
    VisualState,
)
from .base import BaseTracer

BFS_CODE = '''from collections import deque


def bfs(graph, start):
    visited = {start}
    queue = deque([start])
    order = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for neighbor in graph[node]:
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return order
'''

DFS_CODE = '''def dfs(graph, start):
    visited = set()
    stack = [start]
    order = []
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        order.append(node)
        for neighbor in reversed(graph[node]):
            if neighbor not in visited:
                stack.append(neighbor)
    return order
'''

DIJKSTRA_CODE = '''import heapq


def dijkstra(graph, start):
    dist = {start: 0}
    prev = {}
    pq = [(0, start)]
    while pq:
        d, node = heapq.heappop(pq)
        if d > dist.get(node, float("inf")):
            continue
        for neighbor, weight in graph[node]:
            nd = d + weight
            if nd < dist.get(neighbor, float("inf")):
                dist[neighbor] = nd
                prev[neighbor] = node
                heapq.heappush(pq, (nd, neighbor))
    return dist, prev
'''


def circular_positions(nodes: list[str]) -> dict[str, tuple[float, float]]:
    n = max(1, len(nodes))
    positions: dict[str, tuple[float, float]] = {}
    for i, node in enumerate(nodes):
        angle = math.pi / 2 - 2 * math.pi * i / n
        positions[node] = (round(math.cos(angle), 4), round(math.sin(angle), 4))
    return positions


class GraphTracer(BaseTracer):
    visual_kind = VisualKind.GRAPH
    category = "graph"

    def __init__(
        self,
        nodes: list[str],
        edges: list[tuple[str, str, float]],
        start: str,
        code: str = "",
        directed: bool = False,
        positions: dict[str, tuple[float, float]] | None = None,
        target: str | None = None,
    ) -> None:
        self.node_ids = [str(n) for n in nodes]
        self.edges = [(str(u), str(v), float(w)) for u, v, w in edges]
        self.start = str(start)
        self.directed = directed
        self.edges_directed = directed
        self.positions = positions or circular_positions(self.node_ids)
        self.target = str(target) if target is not None else None
        self.visited: list[str] = []
        self.frontier: list[str] = []
        self.distances: dict[str, float] = {}
        self.current: str | None = None
        self.path: list[str] = []
        self.active_edge: tuple[str, str] | None = None
        self.note_text: str | None = None
        self.adj: dict[str, list[tuple[str, float]]] = {n: [] for n in self.node_ids}
        for u, v, w in self.edges:
            self.adj.setdefault(u, []).append((v, w))
            if not directed:
                self.adj.setdefault(v, []).append((u, w))
        super().__init__(code)

    # ---------------------------------------------------------------- 快照
    def snapshot(self) -> VisualState:
        nodes = [
            GraphNodeState(
                id=node,
                label=node,
                x=self.positions.get(node, (0.0, 0.0))[0],
                y=self.positions.get(node, (0.0, 0.0))[1],
            )
            for node in self.node_ids
        ]
        edges = [
            GraphEdgeState(
                source=u,
                target=v,
                weight=w,
                directed=self.edges_directed,
                active=(
                    self.active_edge is not None
                    and ((u, v) == self.active_edge or (v, u) == self.active_edge)
                ),
            )
            for u, v, w in self.edges
        ]
        return VisualState(
            kind=VisualKind.GRAPH,
            graph=GraphState(
                nodes=nodes,
                edges=edges,
                visited=list(self.visited),
                frontier=list(self.frontier),
                distances={k: v for k, v in self.distances.items() if math.isfinite(v)},
                current=self.current,
                path=list(self.path),
            ),
            note=self.note_text,
        )

    def dist_text(self) -> str:
        parts = []
        for node in self.node_ids:
            d = self.distances.get(node)
            parts.append(f"{node}={self.fmt(d) if d is not None and math.isfinite(d) else '∞'}")
        return "，".join(parts)

    def _mark_visited(self, node: str) -> None:
        if node not in self.visited:
            self.visited.append(node)

    def _finish(self, summary: str, result: dict[str, Any]) -> None:
        self.current = None
        self.active_edge = None
        self.frontier = []
        self.note_text = "执行完成"
        self.emit(StepType.COMPLETE, summary, visual_action="complete", meta=result)


class BFSTracer(GraphTracer):
    def run(self) -> list[str]:
        self.note_text = f"BFS 广度优先 · 起点 {self.start}"
        self.init(f"从起点 {self.start} 开始广度优先搜索，使用队列逐层扩展")
        order: list[str] = []
        visited = {self.start}
        self.frontier = [self.start]
        self.at("queue = deque([start])")
        self.emit(
            StepType.ENQUEUE,
            f"起点 {self.start} 入队",
            targets=[self.start],
            visual_action="enqueue",
            meta={"queue": list(self.frontier)},
        )
        self.at("while queue")
        while self.frontier:
            node = self.frontier.pop(0)
            self.current = node
            self._mark_visited(node)
            self.at("node = queue.popleft()")
            order.append(node)
            self.emit(
                StepType.VISIT,
                f"节点 {node} 出队并访问，访问序列：{order}",
                targets=[node],
                visual_action="visit",
                meta={"value": node, "order": list(order)},
            )
            for neighbor, _ in self.adj.get(node, []):
                self.at("if neighbor not in visited")
                self.active_edge = (node, neighbor)
                if neighbor not in visited:
                    visited.add(neighbor)
                    self.frontier.append(neighbor)
                    self.emit(
                        StepType.ENQUEUE,
                        f"发现未访问邻居 {neighbor}，加入队列",
                        targets=[neighbor],
                        visual_action="enqueue",
                        meta={"from": node, "to": neighbor, "queue": list(self.frontier)},
                    )
                else:
                    self.emit(
                        StepType.NOTE,
                        f"邻居 {neighbor} 已访问，跳过",
                        targets=[neighbor],
                        visual_action="skip",
                        meta={"from": node, "to": neighbor},
                    )
        self.active_edge = None
        self._finish(f"BFS 完成，访问顺序：{order}", {"order": order})
        return order


class DFSTracer(GraphTracer):
    def run(self) -> list[str]:
        self.note_text = f"DFS 深度优先 · 起点 {self.start}"
        self.init(f"从起点 {self.start} 开始深度优先搜索，使用栈回溯")
        order: list[str] = []
        visited: set[str] = set()
        stack = [self.start]
        self.frontier = list(stack)
        self.at("stack = [start]")
        self.emit(
            StepType.PUSH,
            f"起点 {self.start} 入栈",
            targets=[self.start],
            visual_action="push",
            meta={"stack": list(stack)},
        )
        self.at("while stack")
        while stack:
            node = stack.pop()
            self.frontier = list(stack)
            self.current = node
            self.at("node = stack.pop()")
            self.emit(
                StepType.POP,
                f"节点 {node} 出栈，准备访问",
                targets=[node],
                visual_action="pop",
                meta={"stack": list(stack)},
            )
            if node in visited:
                self.emit(
                    StepType.NOTE,
                    f"节点 {node} 已经访问过，跳过",
                    targets=[node],
                    visual_action="skip",
                )
                continue
            visited.add(node)
            self._mark_visited(node)
            order.append(node)
            self.at("order.append(node)")
            self.emit(
                StepType.VISIT,
                f"访问节点 {node}，访问序列：{order}",
                targets=[node],
                visual_action="visit",
                meta={"order": list(order)},
            )
            for neighbor, _ in reversed(self.adj.get(node, [])):
                if neighbor not in visited:
                    stack.append(neighbor)
                    self.frontier = list(stack)
                    self.active_edge = (node, neighbor)
                    self.at("stack.append(neighbor)")
                    self.emit(
                        StepType.PUSH,
                        f"把邻居 {neighbor} 压入栈",
                        targets=[neighbor],
                        visual_action="push",
                        meta={"from": node, "to": neighbor, "stack": list(stack)},
                    )
        self.active_edge = None
        self._finish(f"DFS 完成，访问顺序：{order}", {"order": order})
        return order


class DijkstraTracer(GraphTracer):
    def run(self) -> dict[str, float]:
        self.note_text = f"Dijkstra 最短路径 · 起点 {self.start}"
        self.init(f"从起点 {self.start} 出发，用优先队列按距离从小到大确定最短路径")
        dist: dict[str, float] = {self.start: 0.0}
        self.distances = {self.start: 0.0}
        prev: dict[str, str] = {}
        pq: list[tuple[float, str]] = [(0.0, self.start)]
        self.at("pq = [(0, start)]")
        while pq:
            d, node = heapq.heappop(pq)
            if d > dist.get(node, math.inf):
                continue
            self.current = node
            self._mark_visited(node)
            self.at("d, node = heapq.heappop(pq)")
            self.emit(
                StepType.VISIT,
                f"取出距离最小的节点 {node}（distance={self.fmt(d)}），它的最短距离已确定",
                targets=[node],
                visual_action="settle",
                meta={"dist": d, "distances": dict(self.distances)},
            )
            for neighbor, weight in self.adj.get(node, []):
                self.at("if nd < dist.get(neighbor, float(\"inf\"))")
                self.active_edge = (node, neighbor)
                nd = d + weight
                if nd < dist.get(neighbor, math.inf):
                    old = dist.get(neighbor)
                    dist[neighbor] = nd
                    prev[neighbor] = node
                    self.distances[neighbor] = nd
                    heapq.heappush(pq, (nd, neighbor))
                    self.emit(
                        StepType.RELAX,
                        f"经过边 {node}→{neighbor}(权重 {self.fmt(weight)}) 更新距离：{self.fmt(old) if old is not None else '∞'} → {self.fmt(nd)}",
                        targets=[node, neighbor],
                        visual_action="relax",
                        meta={
                            "from": node,
                            "to": neighbor,
                            "weight": weight,
                            "old": old,
                            "new": nd,
                            "distances": dict(self.distances),
                        },
                    )
                else:
                    self.emit(
                        StepType.NOTE,
                        f"经过 {node}→{neighbor} 的距离 {self.fmt(nd)} 没有更优，保持 {self.fmt(dist.get(neighbor, math.inf))}",
                        targets=[neighbor],
                        visual_action="skip",
                        meta={"from": node, "to": neighbor, "candidate": nd},
                    )
        self.active_edge = None
        self.current = None
        self.distances = dist
        result: dict[str, Any] = {"distances": {k: v for k, v in dist.items() if math.isfinite(v)}}
        summary = f"Dijkstra 完成，最短距离：{self.dist_text()}"
        if self.target and self.target in dist and math.isfinite(dist[self.target]):
            path = [self.target]
            cursor = self.target
            while cursor in prev:
                cursor = prev[cursor]
                path.append(cursor)
            path.reverse()
            self.path = path
            self.emit(
                StepType.BACKTRACK,
                f"回溯得到 {self.start} 到 {self.target} 的最短路径：{' → '.join(path)}，总距离 {self.fmt(dist[self.target])}",
                targets=path,
                visual_action="path",
                meta={"path": path, "distance": dist[self.target]},
            )
            result["path"] = path
            result["path_distance"] = dist[self.target]
            summary += f"；最短路径 {' → '.join(path)}"
        self._finish(summary, result)
        return dist
