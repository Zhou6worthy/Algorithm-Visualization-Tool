"""AST 静态分析：只描述代码结构，不判断运行时实际发生了什么。"""
from __future__ import annotations

import ast
from typing import Iterable

from ..protocol.execution import (
    AssignmentFact,
    BranchArc,
    BranchFact,
    ExecutionEvent,
    FunctionFact,
    LoopFact,
    ReturnFact,
    StaticFacts,
)


class StaticAnalyzer:
    def analyze(self, source: str) -> StaticFacts:
        tree = ast.parse(source, filename="user_solution.py")
        functions: list[FunctionFact] = []
        loops: list[LoopFact] = []
        branches: list[BranchFact] = []
        assignments: list[AssignmentFact] = []
        returns: list[ReturnFact] = []
        imports: list[str] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(
                    FunctionFact(
                        name=node.name,
                        line=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        args=[arg.arg for arg in node.args.args],
                    )
                )
            elif isinstance(node, (ast.For, ast.While, ast.AsyncFor)):
                body_start = min((item.lineno for item in node.body), default=node.lineno)
                body_end = max((getattr(item, "end_lineno", item.lineno) for item in node.body), default=body_start)
                targets: list[str] = []
                if isinstance(node, (ast.For, ast.AsyncFor)) and isinstance(node.target, ast.Name):
                    targets = [node.target.id]
                elif isinstance(node, (ast.For, ast.AsyncFor)) and isinstance(node.target, ast.Tuple):
                    targets = [item.id for item in node.target.elts if isinstance(item, ast.Name)]
                loops.append(
                    LoopFact(
                        node_id=f"loop@{node.lineno}",
                        line=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        body_start=body_start,
                        body_end=body_end,
                        target_names=targets,
                    )
                )
            elif isinstance(node, ast.If):
                body_start = min((item.lineno for item in node.body), default=node.lineno)
                body_end = max((getattr(item, "end_lineno", item.lineno) for item in node.body), default=body_start)
                orelse_start = orelse_end = None
                if node.orelse:
                    orelse_start = min(item.lineno for item in node.orelse)
                    orelse_end = max(getattr(item, "end_lineno", item.lineno) for item in node.orelse)
                try:
                    condition = ast.unparse(node.test)
                except Exception:  # noqa: BLE001
                    condition = ""
                branches.append(
                    BranchFact(
                        node_id=f"if@{node.lineno}",
                        line=node.lineno,
                        condition=condition,
                        body_start=body_start,
                        body_end=body_end,
                        orelse_start=orelse_start,
                        orelse_end=orelse_end,
                    )
                )
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Subscript):
                        assignments.append(
                            AssignmentFact(line=node.lineno, target=ast.unparse(target), kind="subscript")
                        )
                    elif isinstance(target, ast.Name):
                        assignments.append(AssignmentFact(line=node.lineno, target=target.id, kind="assign"))
            elif isinstance(node, ast.AugAssign):
                assignments.append(AssignmentFact(line=node.lineno, target=ast.unparse(node.target), kind="augassign"))
            elif isinstance(node, ast.Return):
                returns.append(ReturnFact(line=node.lineno))
            elif isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        return StaticFacts(
            functions=functions,
            loops=loops,
            branches=branches,
            assignments=assignments,
            returns=returns,
            imports=sorted(set(filter(None, imports))),
            source_lines=len(source.splitlines()),
        )

    def annotate_arcs(
        self,
        events: list[ExecutionEvent],
        arcs: list[BranchArc],
        facts: StaticFacts,
    ) -> list[BranchArc]:
        """用 AST 结构 + 实际事件路径标注 if_true/if_false/loop_back。"""
        by_branch = {branch.line: branch for branch in facts.branches}
        loops = facts.loops
        annotated: list[BranchArc] = []
        for arc in arcs:
            branch = by_branch.get(arc.from_line)
            loop = next((item for item in loops if item.body_start <= arc.from_line <= item.body_end), None)
            if branch is not None:
                if branch.body_start is not None and branch.body_end is not None and branch.body_start <= arc.to_line <= branch.body_end:
                    arc = arc.model_copy(update={"kind": "if_true", "ast_node_id": branch.node_id, "condition_text": branch.condition})
                elif branch.orelse_start is not None and branch.orelse_end is not None and branch.orelse_start <= arc.to_line <= branch.orelse_end:
                    arc = arc.model_copy(update={"kind": "if_false", "ast_node_id": branch.node_id, "condition_text": branch.condition})
                elif arc.to_line > (branch.body_end or branch.line):
                    arc = arc.model_copy(update={"kind": "if_false", "ast_node_id": branch.node_id, "condition_text": branch.condition})
            elif loop is not None and arc.to_line <= loop.line:
                arc = arc.model_copy(update={"kind": "loop_back", "ast_node_id": loop.node_id})
            annotated.append(arc)
        return annotated
