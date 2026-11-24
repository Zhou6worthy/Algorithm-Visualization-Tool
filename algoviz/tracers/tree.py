"""树结构追踪器：二叉搜索树构建、遍历、查找。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..protocol.events import StepType, TreeNodeState, TreeState, VisualKind, VisualState
from .base import BaseTracer

BST_INSERT_CODE = '''class TreeNode:
    def __init__(self, value):
        self.value = value
        self.left = None
        self.right = None


def bst_insert(root, value):
    if root is None:
        return TreeNode(value)
    if value < root.value:
        root.left = bst_insert(root.left, value)
    elif value > root.value:
        root.right = bst_insert(root.right, value)
    return root
'''

BST_SEARCH_CODE = '''def bst_search(root, target):
    node = root
    while node is not None:
        if target == node.value:
            return node
        if target < node.value:
            node = node.left
        else:
            node = node.right
    return None
'''

INORDER_CODE = '''def inorder(root, out):
    if root is None:
        return
    inorder(root.left, out)
    out.append(root.value)
    inorder(root.right, out)
'''

PREORDER_CODE = '''def preorder(root, out):
    if root is None:
        return
    out.append(root.value)
    preorder(root.left, out)
    preorder(root.right, out)
'''

POSTORDER_CODE = '''def postorder(root, out):
    if root is None:
        return
    postorder(root.left, out)
    postorder(root.right, out)
    out.append(root.value)
'''

LEVEL_ORDER_CODE = '''def level_order(root):
    if root is None:
        return []
    queue = [root]
    order = []
    while queue:
        node = queue.pop(0)
        order.append(node.value)
        if node.left is not None:
            queue.append(node.left)
        if node.right is not None:
            queue.append(node.right)
    return order
'''


@dataclass
class _Node:
    id: str
    value: Any
    left: str | None = None
    right: str | None = None
    parent: str | None = None


class _TreeTracer(BaseTracer):
    visual_kind = VisualKind.TREE
    category = "tree"

    def __init__(self, values: list[Any], code: str = "") -> None:
        self.nodes: dict[str, _Node] = {}
        self.root_id: str | None = None
        self.visited: list[str] = []
        self.current: str | None = None
        self.frontier: list[str] = []
        self.note_text: str | None = None
        self._counter = 0
        super().__init__(code)

    # ---------------------------------------------------------------- 构建
    def build_silent(self, values: list[Any]) -> None:
        for value in values:
            self._insert(value, record=False)

    def _insert(self, value: Any, record: bool = True) -> str | None:
        new_id = f"n{self._counter}"
        if self.root_id is None:
            node = _Node(id=new_id, value=value)
            self.nodes[new_id] = node
            self.root_id = new_id
            self._counter += 1
            if record:
                self.at("return TreeNode(value)")
                self.current = new_id
                self.emit(
                    StepType.CREATE,
                    f"以 {self.fmt(value)} 创建根节点",
                    targets=[new_id],
                    visual_action="create",
                    meta={"value": value, "depth": 0},
                )
            return new_id
        current_id = self.root_id
        depth = 0
        while True:
            current = self.nodes[current_id]
            depth += 1
            if value == current.value:
                if record:
                    self.current = current_id
                    self.at("elif value > root.value")
                    self.emit(
                        StepType.NOTE,
                        f"{self.fmt(value)} 与节点 {self.fmt(current.value)} 相等，二叉搜索树中不重复插入",
                        targets=[current_id],
                        visual_action="duplicate",
                        meta={"value": value, "node": current_id},
                    )
                return None
            if record:
                self.current = current_id
                relation = "小于" if value < current.value else "大于"
                side = "left" if value < current.value else "right"
                if value < current.value:
                    self.at("if value < root.value")
                else:
                    self.at("elif value > root.value")
                self.emit(
                    StepType.COMPARE,
                    f"比较 {self.fmt(value)} 与节点 {self.fmt(current.value)}：{relation}，进入{('左' if side == 'left' else '右')}子树",
                    targets=[current_id],
                    visual_action="compare",
                    meta={"value": value, "node": current_id, "depth": depth},
                )
            side = "left" if value < current.value else "right"
            child_id = current.left if side == "left" else current.right
            if child_id is None:
                new_node = _Node(id=new_id, value=value, parent=current_id)
                self.nodes[new_id] = new_node
                setattr(current, side, new_id)
                self._counter += 1
                if record:
                    self.current = new_id
                    self.emit(
                        StepType.CREATE,
                        f"在节点 {self.fmt(current.value)} 的{('左' if side == 'left' else '右')}侧创建新节点 {self.fmt(value)}",
                        targets=[new_id],
                        visual_action="create",
                        meta={"value": value, "parent": current_id, "depth": depth},
                    )
                return new_id
            current_id = child_id

    # ---------------------------------------------------------------- 布局 / 快照
    def _layout(self) -> tuple[dict[str, float], dict[str, int]]:
        xs: dict[str, float] = {}
        counter = 0

        def walk(node_id: str | None) -> None:
            nonlocal counter
            if node_id is None:
                return
            node = self.nodes[node_id]
            walk(node.left)
            xs[node_id] = float(counter)
            counter += 1
            walk(node.right)

        walk(self.root_id)
        depths: dict[str, int] = {}
        if self.root_id is not None:
            stack = [(self.root_id, 0)]
            while stack:
                node_id, depth = stack.pop()
                depths[node_id] = depth
                node = self.nodes[node_id]
                if node.left:
                    stack.append((node.left, depth + 1))
                if node.right:
                    stack.append((node.right, depth + 1))
        return xs, depths

    def snapshot(self) -> VisualState:
        xs, depths = self._layout()
        nodes = [
            TreeNodeState(
                id=node.id,
                value=node.value,
                left=node.left,
                right=node.right,
                parent=node.parent,
                depth=depths.get(node.id, 0),
                x=xs.get(node.id, 0.0),
            )
            for node in sorted(self.nodes.values(), key=lambda n: xs.get(n.id, 0.0))
        ]
        return VisualState(
            kind=VisualKind.TREE,
            tree=TreeState(
                nodes=nodes,
                root=self.root_id,
                visited=list(self.visited),
                current=self.current,
                frontier=list(self.frontier),
            ),
            note=self.note_text,
        )

    def tree_text(self) -> str:
        return "、".join(self.fmt(n.value) for n in self.nodes.values())


class BSTBuildTracer(_TreeTracer):
    def run(self) -> list[Any]:
        values = []
        self.note_text = "二叉搜索树：左小右大"
        self.init("二叉搜索树构建：依次插入序列中的每个元素")
        values = getattr(self, "_values", [])
        self.at("if root is None")
        for index, value in enumerate(values):
            self._insert(value, record=True)
        self.current = None
        self.note_text = "构建完成"
        self.complete(f"二叉搜索树构建完成，共 {len(self.nodes)} 个节点")
        return values

    def __init__(self, values: list[Any], code: str = BST_INSERT_CODE) -> None:
        self._values = list(values)
        super().__init__(values, code)


class TreeTraversalTracer(_TreeTracer):
    def __init__(self, values: list[Any], order: str = "inorder", code: str | None = None) -> None:
        self.order = order if order in {"inorder", "preorder", "postorder", "levelorder"} else "inorder"
        codes = {
            "inorder": INORDER_CODE,
            "preorder": PREORDER_CODE,
            "postorder": POSTORDER_CODE,
            "levelorder": LEVEL_ORDER_CODE,
        }
        self._values = list(values)
        super().__init__(values, code or codes[self.order])

    def run(self) -> list[Any]:
        self.build_silent(self._values)
        labels = {
            "inorder": "中序遍历",
            "preorder": "前序遍历",
            "postorder": "后序遍历",
            "levelorder": "层序遍历",
        }
        self.note_text = labels[self.order]
        self.init(f"{labels[self.order]}：共 {len(self.nodes)} 个节点")
        out: list[Any] = []
        if self.order == "levelorder":
            self._level_order(out)
        else:
            if self.root_id is not None:
                getattr(self, f"_{self.order}")(self.root_id, out, 0)
        self.current = None
        self.frontier = []
        self.note_text = f"{labels[self.order]}完成"
        self.complete(f"{labels[self.order]}结果：{out}")
        return out

    def _visit(self, node_id: str, out: list[Any], depth: int = 0) -> None:
        node = self.nodes[node_id]
        self.visited.append(node_id)
        self.current = node_id
        out.append(node.value)
        self.emit(
            StepType.VISIT,
            f"访问节点 {self.fmt(node.value)}，输出序列变为 {out}",
            targets=[node_id],
            visual_action="visit",
            meta={"value": node.value, "depth": depth, "step": len(out)},
        )

    def _inorder(self, node_id: str, out: list[Any], depth: int) -> None:
        node = self.nodes[node_id]
        if node.left:
            self._inorder(node.left, out, depth + 1)
        self.at("out.append(root.value)")
        self._visit(node_id, out, depth)
        if node.right:
            self._inorder(node.right, out, depth + 1)

    def _preorder(self, node_id: str, out: list[Any], depth: int) -> None:
        node = self.nodes[node_id]
        self.at("out.append(root.value)")
        self._visit(node_id, out, depth)
        if node.left:
            self._preorder(node.left, out, depth + 1)
        if node.right:
            self._preorder(node.right, out, depth + 1)

    def _postorder(self, node_id: str, out: list[Any], depth: int) -> None:
        node = self.nodes[node_id]
        if node.left:
            self._postorder(node.left, out, depth + 1)
        if node.right:
            self._postorder(node.right, out, depth + 1)
        self.at("out.append(root.value)")
        self._visit(node_id, out, depth)

    def _level_order(self, out: list[Any]) -> None:
        if self.root_id is None:
            return
        self.frontier = [self.root_id]
        self.at("while queue")
        while self.frontier:
            node_id = self.frontier.pop(0)
            self.at("node = queue.pop(0)")
            node = self.nodes[node_id]
            self.emit(
                StepType.DEQUEUE,
                f"队首节点 {self.fmt(node.value)} 出队",
                targets=[node_id],
                visual_action="dequeue",
                meta={"value": node.value, "queue": list(self.frontier)},
            )
            self._visit(node_id, out)
            for child_id in (node.left, node.right):
                if child_id:
                    self.frontier.append(child_id)
                    self.at("queue.append(node.left)")
                    self.emit(
                        StepType.ENQUEUE,
                        f"把子节点 {self.fmt(self.nodes[child_id].value)} 加入队列",
                        targets=[child_id],
                        visual_action="enqueue",
                        meta={"value": self.nodes[child_id].value},
                    )
        self.frontier = []


class BSTSearchTracer(_TreeTracer):
    def __init__(self, values: list[Any], target: Any, code: str = BST_SEARCH_CODE) -> None:
        self._values = list(values)
        self.target = target
        super().__init__(values, code)

    def run(self) -> bool:
        self.build_silent(self._values)
        self.note_text = f"二叉搜索树查找 · target={self.fmt(self.target)}"
        self.init(f"在二叉搜索树中查找 target={self.fmt(self.target)}")
        node_id = self.root_id
        depth = 0
        self.at("while node is not None")
        while node_id is not None:
            node = self.nodes[node_id]
            self.visited.append(node_id)
            self.current = node_id
            self.emit(
                StepType.VISIT,
                f"访问节点 {self.fmt(node.value)}，与 target={self.fmt(self.target)} 比较",
                targets=[node_id],
                visual_action="visit",
                meta={"value": node.value, "target": self.target, "depth": depth},
            )
            if node.value == self.target:
                self.at("return node")
                self.emit(
                    StepType.FOUND,
                    f"命中！target={self.fmt(self.target)} 在节点 {node_id}",
                    targets=[node_id],
                    visual_action="found",
                    meta={"value": node.value},
                )
                self.complete(f"查找成功：找到节点 {self.fmt(node.value)}")
                return True
            if self.target < node.value:
                node_id = node.left
                self.at("if target < node.value")
                self.emit(
                    StepType.NOTE,
                    f"target={self.fmt(self.target)} < {self.fmt(node.value)}，进入左子树",
                    targets=[node_id] if node_id else [],
                    visual_action="descend",
                    meta={"direction": "left"},
                )
            else:
                node_id = node.right
                self.at("node = node.right")
                self.emit(
                    StepType.NOTE,
                    f"target={self.fmt(self.target)} > {self.fmt(node.value)}，进入右子树",
                    targets=[node_id] if node_id else [],
                    visual_action="descend",
                    meta={"direction": "right"},
                )
            depth += 1
        self.current = None
        self.at("return None")
        self.complete(f"查找失败：树中不存在 {self.fmt(self.target)}")
        return False
