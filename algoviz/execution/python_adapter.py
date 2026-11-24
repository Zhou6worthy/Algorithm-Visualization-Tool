"""Python 代码适配：user_solution.py 原样保留，harness.py 独立调用。"""
from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, field
from typing import Any

from ..protocol.execution import ExecutionStyle, TraceLimits


class ExecutionAdapterError(ValueError):
    pass


HARNESS_SOURCE = '''\
"""AlgoViz harness：独立调用 user_solution.py，不修改用户源码。"""
from algoviz.execution.harness import main

if __name__ == "__main__":
    raise SystemExit(main())
'''


@dataclass
class PreparedProgram:
    language: str
    style: ExecutionStyle
    source: str
    source_hash: str
    entry_point: str
    user_filename: str
    harness_filename: str
    harness_source: str
    input_payload: dict[str, Any]
    source_map: dict[int, int | None] = field(default_factory=dict)
    wrapper_lines: list[int] = field(default_factory=list)

    def user_lines(self) -> int:
        return len(self.source.splitlines())


class PythonExecutionAdapter:
    language = "python"

    def __init__(self, limits: TraceLimits | None = None) -> None:
        self.limits = limits or TraceLimits()

    def prepare(
        self,
        source: str,
        *,
        style: ExecutionStyle | str = ExecutionStyle.FUNCTION,
        entry_point: str = "two_sum",
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> PreparedProgram:
        style = ExecutionStyle(style)
        if len(source.encode("utf-8")) > self.limits.max_source_bytes:
            raise ExecutionAdapterError(f"用户源码超过限制 {self.limits.max_source_bytes} bytes")
        try:
            tree = ast.parse(source, filename="user_solution.py")
        except SyntaxError as exc:
            raise ExecutionAdapterError(f"用户代码语法错误：{exc.msg} (line {exc.lineno})") from exc

        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}

        if style == ExecutionStyle.FUNCTION:
            if entry_point not in functions:
                raise ExecutionAdapterError(f"找不到入口函数：{entry_point}")
        elif style == ExecutionStyle.LEETCODE_CLASS:
            if "." not in entry_point:
                raise ExecutionAdapterError("LeetCode 类入口必须形如 Solution.two_sum")
            class_name, method_name = entry_point.split(".", 1)
            cls = classes.get(class_name)
            if cls is None:
                raise ExecutionAdapterError(f"找不到类：{class_name}")
            methods = {node.name for node in cls.body if isinstance(node, ast.FunctionDef)}
            if method_name not in methods:
                raise ExecutionAdapterError(f"类 {class_name} 中找不到方法：{method_name}")
        else:
            if style == ExecutionStyle.STDIN:
                raise ExecutionAdapterError("M1 暂不支持 stdin 风格；请使用 function 或 leetcode_class")
            raise ExecutionAdapterError(f"不支持的执行风格：{style}")

        source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        line_count = len(source.splitlines())
        source_map = {line: line for line in range(1, line_count + 1)}
        return PreparedProgram(
            language=self.language,
            style=style,
            source=source,
            source_hash=source_hash,
            entry_point=entry_point,
            user_filename="user_solution.py",
            harness_filename="harness.py",
            harness_source=HARNESS_SOURCE,
            input_payload={
                "style": style.value,
                "entry_point": entry_point,
                "args": list(args or []),
                "kwargs": dict(kwargs or {}),
            },
            source_map=source_map,
            wrapper_lines=[],
        )
