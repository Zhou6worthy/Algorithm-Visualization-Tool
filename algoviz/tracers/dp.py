"""动态规划追踪器：0-1 背包、最长公共子序列。"""
from __future__ import annotations

from typing import Any

from ..protocol.events import MatrixState, StepType, VisualKind, VisualState
from .base import BaseTracer

KNAPSACK_CODE = '''def knapsack(weights, values, capacity):
    n = len(weights)
    dp = [[0] * (capacity + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for w in range(capacity + 1):
            dp[i][w] = dp[i - 1][w]
            if weights[i - 1] <= w:
                take = dp[i - 1][w - weights[i - 1]] + values[i - 1]
                dp[i][w] = max(dp[i][w], take)
    return dp[n][capacity]


def reconstruct(dp, weights, values, capacity):
    i, w = len(weights), capacity
    chosen = []
    while i > 0:
        if dp[i][w] != dp[i - 1][w]:
            chosen.append(i - 1)
            w -= weights[i - 1]
        i -= 1
    return chosen
'''

LCS_CODE = '''def lcs(s1, s2):
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[m][n]


def reconstruct(s1, s2, dp):
    i, j = len(s1), len(s2)
    chars = []
    while i > 0 and j > 0:
        if s1[i - 1] == s2[j - 1]:
            chars.append(s1[i - 1])
            i -= 1
            j -= 1
        elif dp[i - 1][j] >= dp[i][j - 1]:
            i -= 1
        else:
            j -= 1
    return "".join(reversed(chars))
'''


class MatrixTracer(BaseTracer):
    visual_kind = VisualKind.MATRIX
    category = "dp"

    def __init__(
        self,
        table: list[list[Any]],
        code: str,
        row_headers: list[str],
        col_headers: list[str],
        legend: list[str] | None = None,
    ) -> None:
        self.table = table
        self.rows = len(table)
        self.cols = len(table[0]) if table else 0
        self.row_headers = row_headers
        self.col_headers = col_headers
        self.legend = legend or []
        self.current: list[int] | None = None
        self.dependencies: list[list[int]] = []
        self.path: list[list[int]] = []
        self.highlight: list[list[int]] = []
        self.cell_notes: dict[str, str] = {}
        self.note_text: str | None = None
        super().__init__(code)

    def snapshot(self) -> VisualState:
        return VisualState(
            kind=VisualKind.MATRIX,
            matrix=MatrixState(
                rows=self.rows,
                cols=self.cols,
                table=[list(row) for row in self.table],
                row_headers=list(self.row_headers),
                col_headers=list(self.col_headers),
                current=list(self.current) if self.current else None,
                dependencies=[list(d) for d in self.dependencies],
                path=[list(p) for p in self.path],
                highlight=[list(h) for h in self.highlight],
                legend=list(self.legend),
                cell_notes=dict(self.cell_notes),
            ),
            note=self.note_text,
        )


class KnapsackTracer(MatrixTracer):
    def __init__(self, weights: list[Any], values: list[Any], capacity: int, code: str = KNAPSACK_CODE) -> None:
        self.weights = list(weights)
        self.values = list(values)
        self.capacity = int(capacity)
        n = len(self.weights)
        table = [[0 for _ in range(self.capacity + 1)] for _ in range(n + 1)]
        row_headers = ["∅"] + [str(i + 1) for i in range(n)]
        col_headers = [str(w) for w in range(self.capacity + 1)]
        legend = [f"物品{i + 1}：重量 {self.fmt(self.weights[i])}, 价值 {self.fmt(self.values[i])}" for i in range(n)]
        super().__init__(table, code, row_headers, col_headers, legend)

    def run(self) -> dict[str, Any]:
        n = len(self.weights)
        self.note_text = f"0-1 背包 · 容量 {self.capacity}"
        self.init(
            f"初始化 dp 表：行为物品数量（{n}），列为容量（0~{self.capacity}），所有格子先置 0"
        )
        self.at("dp = [[0] * (capacity + 1) for _ in range(n + 1)]")
        for i in range(1, n + 1):
            weight = self.weights[i - 1]
            value = self.values[i - 1]
            self.at("for w in range(capacity + 1)")
            for w in range(self.capacity + 1):
                self.current = [i, w]
                not_take = self.table[i - 1][w]
                deps = [[i - 1, w]]
                best = not_take
                choice = "不选"
                if weight <= w:
                    take = self.table[i - 1][w - weight] + value
                    deps.append([i - 1, w - weight])
                    if take > best:
                        best = take
                        choice = "选"
                    detail = (
                        f"不选：dp[{i - 1}][{w}]={self.fmt(not_take)}；"
                        f"选：dp[{i - 1}][{w - weight}]+{self.fmt(value)}={self.fmt(take)}"
                    )
                else:
                    detail = f"物品{i}重量 {self.fmt(weight)} > 容量 {w}，只能不选"
                self.table[i][w] = best
                self.dependencies = deps
                if choice == "选":
                    self.cell_notes[f"{i},{w}"] = "选"
                self.at("if weights[i - 1] <= w")
                self.emit(
                    StepType.UPDATE,
                    f"dp[{i}][{w}] = {self.fmt(best)}（{detail}）",
                    targets=[i, w],
                    code_line=self.line("dp[i][w] = max(dp[i][w], take)") if choice == "选" else self.line("dp[i][w] = dp[i - 1][w]"),
                    visual_action="fill",
                    meta={
                        "i": i,
                        "w": w,
                        "value": best,
                        "choice": choice,
                        "take": take if weight <= w else None,
                        "not_take": not_take,
                    },
                )
        self.current = None
        self.dependencies = []
        answer = self.table[n][self.capacity]
        self.note_text = f"最优价值 = {self.fmt(answer)}"
        self.at("return dp[n][capacity]")
        self.emit(
            StepType.NOTE,
            f"dp[{n}][{self.capacity}] = {self.fmt(answer)} 就是背包能装下的最大价值",
            targets=[n, self.capacity],
            visual_action="answer",
        )
        # 回溯
        chosen: list[int] = []
        path: list[list[int]] = []
        i, w = n, self.capacity
        self.at("while i > 0")
        while i > 0:
            if self.table[i][w] != self.table[i - 1][w]:
                chosen.append(i - 1)
                path.append([i, w])
                w -= self.weights[i - 1]
            i -= 1
        chosen.reverse()
        path.reverse()
        self.path = path
        self.at("chosen.append(i - 1)")
        self.emit(
            StepType.BACKTRACK,
            "回溯 dp 表："
            + ("、".join(f"物品 {idx + 1}" for idx in chosen) if chosen else "没有物品被选中"),
            targets=[p[0] for p in path] if path else [],
            visual_action="traceback",
            meta={
                "chosen": chosen,
                "items": [
                    {
                        "index": idx + 1,
                        "weight": self.weights[idx],
                        "value": self.values[idx],
                    }
                    for idx in chosen
                ],
                "value": answer,
            },
        )
        self.note_text = f"最优解：选物品 {'、'.join(str(c + 1) for c in chosen) or '无'}，总价值 {self.fmt(answer)}"
        result = {
            "max_value": answer,
            "chosen": chosen,
            "summary": self.note_text,
        }
        self.complete(f"0-1 背包完成：最大价值 {self.fmt(answer)}，选择物品 {[c + 1 for c in chosen]}")
        return result


class LCSTracer(MatrixTracer):
    def __init__(self, s1: str, s2: str, code: str = LCS_CODE) -> None:
        self.s1 = str(s1)
        self.s2 = str(s2)
        m, n = len(self.s1), len(self.s2)
        table = [[0 for _ in range(n + 1)] for _ in range(m + 1)]
        row_headers = ["∅"] + list(self.s1)
        col_headers = ["∅"] + list(self.s2)
        super().__init__(table, code, row_headers, col_headers, [])

    def run(self) -> dict[str, Any]:
        s1, s2 = self.s1, self.s2
        m, n = len(s1), len(s2)
        self.note_text = f"最长公共子序列 · {s1} 与 {s2}"
        self.init(f"初始化 dp 表：行对应 \"{s1}\"，列对应 \"{s2}\"，首行首列置 0")
        self.at("dp = [[0] * (n + 1) for _ in range(m + 1)]")
        for i in range(1, m + 1):
            self.at("for i in range(1, m + 1)")
            for j in range(1, n + 1):
                self.current = [i, j]
                c1, c2 = s1[i - 1], s2[j - 1]
                if c1 == c2:
                    value = self.table[i - 1][j - 1] + 1
                    self.table[i][j] = value
                    self.dependencies = [[i - 1, j - 1]]
                    self.at("dp[i][j] = dp[i - 1][j - 1] + 1")
                    self.emit(
                        StepType.UPDATE,
                        f"字符 \"{c1}\" 与 \"{c2}\" 相同：dp[{i}][{j}] = dp[{i - 1}][{j - 1}] + 1 = {value}",
                        targets=[i, j],
                        visual_action="match",
                        meta={"i": i, "j": j, "value": value, "match": True},
                    )
                else:
                    up, left = self.table[i - 1][j], self.table[i][j - 1]
                    value = max(up, left)
                    self.table[i][j] = value
                    self.dependencies = [[i - 1, j], [i, j - 1]]
                    self.at("dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])")
                    self.emit(
                        StepType.UPDATE,
                        f"字符 \"{c1}\" 与 \"{c2}\" 不同：dp[{i}][{j}] = max({up}, {left}) = {value}",
                        targets=[i, j],
                        visual_action="fill",
                        meta={"i": i, "j": j, "value": value, "match": False},
                    )
                self.table[i][j] = value
        self.current = None
        self.dependencies = []
        length = self.table[m][n]
        self.note_text = f"LCS 长度 = {length}"
        self.at("return dp[m][n]")
        self.emit(
            StepType.NOTE,
            f"dp[{m}][{n}] = {length}，即最长公共子序列的长度",
            targets=[m, n],
            visual_action="answer",
        )
        # 回溯
        i, j = m, n
        chars: list[str] = []
        path: list[list[int]] = []
        self.at("while i > 0 and j > 0")
        while i > 0 and j > 0:
            if s1[i - 1] == s2[j - 1]:
                chars.append(s1[i - 1])
                path.append([i, j])
                i -= 1
                j -= 1
            elif self.table[i - 1][j] >= self.table[i][j - 1]:
                i -= 1
            else:
                j -= 1
        chars.reverse()
        path.reverse()
        self.path = path
        subsequence = "".join(chars)
        self.at("chars.append(s1[i - 1])")
        self.emit(
            StepType.BACKTRACK,
            f"回溯得到最长公共子序列：\"{subsequence}\"，长度 {length}",
            targets=[p[0] for p in path] if path else [],
            visual_action="traceback",
            meta={"subsequence": subsequence, "length": length, "cells": path},
        )
        self.note_text = f"最长公共子序列：\"{subsequence}\""
        result = {"length": length, "subsequence": subsequence, "summary": self.note_text}
        self.complete(f"LCS 完成：最长公共子序列为 \"{subsequence}\"，长度 {length}")
        return result
