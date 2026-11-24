"""无副作用变量序列化。

原则：
- 精确内置类型优先；
- 不调用用户的 __repr__ / __str__ / property / __iter__ / __len__；
- 自定义对象默认不读取属性，只保留类型名；
- TreeNode / ListNode 使用专用字段读取；
- 循环引用、大对象、不可序列化对象都有显式标记。
"""
from __future__ import annotations

import math
from dataclasses import fields as dataclass_fields, is_dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..protocol.events import StrictModel


class SerializerLimits(BaseModel):
    max_depth: int = 5
    max_items: int = 100
    max_string: int = 4096
    max_total_bytes: int = 32768


class SerializedValue(StrictModel):
    kind: Literal[
        "primitive",
        "list",
        "tuple",
        "dict",
        "set",
        "tree_node",
        "list_node",
        "object",
        "cycle",
        "unsupported",
        "truncated",
    ]
    type_name: str
    value: Any = None
    items: list["SerializedValue"] = Field(default_factory=list)
    fields: dict[str, "SerializedValue"] = Field(default_factory=dict)
    ref_id: int | None = None
    truncated: bool = False


SerializedValue.model_rebuild()


def _is_exact(value: Any, typ: type) -> bool:
    return type(value) is typ


class SafeSerializer:
    def __init__(self, limits: SerializerLimits | None = None) -> None:
        self.limits = limits or SerializerLimits()
        self._active: set[int] = set()
        self._budget = self.limits.max_total_bytes
        self._hit_budget = False

    # ------------------------------------------------------------------ 预算
    def _consume(self, amount: int) -> None:
        self._budget -= amount
        if self._budget < 0:
            self._hit_budget = True

    def _truncated(self, type_name: str) -> SerializedValue:
        return SerializedValue(kind="truncated", type_name=type_name, truncated=True)

    # ------------------------------------------------------------------ 入口
    def serialize(self, value: Any) -> SerializedValue:
        self._active = set()
        self._budget = self.limits.max_total_bytes
        self._hit_budget = False
        return self._serialize(value, depth=0)

    def serialize_locals(self, mapping: dict[str, Any]) -> dict[str, Any]:
        """返回可直接写入 JSON 的 locals 快照。"""
        result: dict[str, Any] = {}
        for name in list(mapping.keys())[: self.limits.max_items]:
            if name.startswith("__"):
                continue
            value = mapping[name]
            if callable(value) or type(value) is type:
                continue
            serialized = self._serialize(value, depth=0)
            result[name] = self.to_native(serialized)
        return result

    # ------------------------------------------------------------------ 核心
    def _serialize(self, value: Any, depth: int) -> SerializedValue:
        if self._hit_budget:
            return self._truncated(type(value).__name__)
        if depth > self.limits.max_depth:
            return self._truncated(type(value).__name__)

        value_id = id(value)
        if value_id in self._active:
            return SerializedValue(kind="cycle", type_name=type(value).__name__, ref_id=value_id)

        if value is None or _is_exact(value, bool):
            self._consume(8)
            return SerializedValue(kind="primitive", type_name=type(value).__name__, value=value)
        if _is_exact(value, int):
            self._consume(24)
            return SerializedValue(kind="primitive", type_name="int", value=value)
        if _is_exact(value, float):
            if math.isnan(value):
                return SerializedValue(kind="primitive", type_name="float", value="nan")
            if math.isinf(value):
                return SerializedValue(kind="primitive", type_name="float", value="inf" if value > 0 else "-inf")
            self._consume(24)
            return SerializedValue(kind="primitive", type_name="float", value=value)
        if _is_exact(value, str):
            text = value
            if len(text) > self.limits.max_string:
                text = text[: self.limits.max_string] + "…"
                self._consume(len(text) + 4)
                return SerializedValue(kind="primitive", type_name="str", value=text, truncated=True)
            self._consume(len(text) + 8)
            return SerializedValue(kind="primitive", type_name="str", value=text)
        if _is_exact(value, bytes):
            self._consume(24)
            return SerializedValue(kind="primitive", type_name="bytes", value=f"<bytes:{len(value)}>")

        # 精确内置容器；子类不走这里，避免触发自定义迭代器
        if _is_exact(value, list) or _is_exact(value, tuple):
            return self._serialize_sequence(value, depth, "list" if _is_exact(value, list) else "tuple")
        if _is_exact(value, dict):
            return self._serialize_dict(value, depth)
        if _is_exact(value, set) or _is_exact(value, frozenset):
            return self._serialize_set(value, depth)

        # 专用节点序列化
        type_name = type(value).__name__
        if type_name in {"TreeNode", "ListNode"}:
            return self._serialize_node(value, type_name, depth)

        # dataclass：只读字段名；字段值从实例 __dict__ 取，不触发 property
        # 注意：不要对任意实例调用 dataclasses.is_dataclass，它会访问 __class__/
        # __getattribute__；只对 type(value) 做判断。
        if is_dataclass(type(value)) and type(value) is not type:
            return self._serialize_dataclass(value, depth)

        # 自定义对象：默认不读取任何属性
        return SerializedValue(kind="unsupported", type_name=type_name)

    def _serialize_sequence(self, value: Any, depth: int, kind: str) -> SerializedValue:
        self._active.add(id(value))
        try:
            items = []
            for index, item in enumerate(value):
                if index >= self.limits.max_items:
                    items.append(self._truncated(type(value).__name__))
                    break
                items.append(self._serialize(item, depth + 1))
            self._consume(sum(len(self.to_json(item)) for item in items))
            return SerializedValue(
                kind=kind,  # type: ignore[arg-type]
                type_name=kind,
                items=items,
                truncated=self._hit_budget or len(value) > self.limits.max_items,
            )
        finally:
            self._active.discard(id(value))

    def _serialize_dict(self, value: dict[Any, Any], depth: int) -> SerializedValue:
        self._active.add(id(value))
        try:
            fields: dict[str, SerializedValue] = {}
            for index, (key, item) in enumerate(value.items()):
                if index >= self.limits.max_items:
                    fields["…"] = self._truncated("dict")
                    break
                if not (key is None or type(key) in {bool, int, float, str}):
                    continue
                fields[str(key)] = self._serialize(item, depth + 1)
            self._consume(sum(len(self.to_json(item)) for item in fields.values()))
            return SerializedValue(
                kind="dict",
                type_name="dict",
                fields=fields,
                truncated=self._hit_budget or len(value) > self.limits.max_items,
            )
        finally:
            self._active.discard(id(value))

    def _serialize_set(self, value: Any, depth: int) -> SerializedValue:
        self._active.add(id(value))
        try:
            items = []
            for index, item in enumerate(value):
                if index >= self.limits.max_items:
                    items.append(self._truncated("set"))
                    break
                items.append(self._serialize(item, depth + 1))
            import json

            items.sort(
                key=lambda item: (
                    item.type_name,
                    json.dumps(item.value, ensure_ascii=False, default=str)
                    if item.kind == "primitive"
                    else item.kind,
                )
            )
            self._consume(sum(len(self.to_json(item)) for item in items))
            return SerializedValue(
                kind="set", type_name="set", items=items, truncated=self._hit_budget
            )
        finally:
            self._active.discard(id(value))

    def _safe_instance_dict(self, value: Any) -> dict[str, Any] | None:
        try:
            import inspect

            descriptor = inspect.getattr_static(value, "__dict__", None)
            if descriptor is None:
                return None
            data = object.__getattribute__(value, "__dict__")
            return data if type(data) is dict else None
        except Exception:  # noqa: BLE001 - 任何失败都视为不可安全读取
            return None

    def _serialize_node(self, value: Any, type_name: str, depth: int) -> SerializedValue:
        data = self._safe_instance_dict(value)
        if data is None:
            return SerializedValue(kind="unsupported", type_name=type_name)
        self._active.add(id(value))
        try:
            if type_name == "ListNode":
                fields = {
                    "val": self._serialize(data.get("val"), depth + 1),
                    "next": self._serialize(data.get("next"), depth + 1),
                }
            else:
                fields = {
                    "val": self._serialize(data.get("val"), depth + 1),
                    "left": self._serialize(data.get("left"), depth + 1),
                    "right": self._serialize(data.get("right"), depth + 1),
                }
            return SerializedValue(
                kind="list_node" if type_name == "ListNode" else "tree_node",
                type_name=type_name,
                fields=fields,
            )
        finally:
            self._active.discard(id(value))

    def _serialize_dataclass(self, value: Any, depth: int) -> SerializedValue:
        data = self._safe_instance_dict(value)
        if data is None:
            return SerializedValue(kind="unsupported", type_name=type(value).__name__)
        self._active.add(id(value))
        try:
            fields = {}
            for field in dataclass_fields(value):
                if field.name in data:
                    fields[field.name] = self._serialize(data[field.name], depth + 1)
            return SerializedValue(kind="object", type_name=type(value).__name__, fields=fields)
        finally:
            self._active.discard(id(value))

    # ------------------------------------------------------------------ 转换
    def to_native(self, value: SerializedValue) -> Any:
        if value.kind == "primitive":
            return value.value
        if value.kind in {"list", "tuple", "set"}:
            return [self.to_native(item) for item in value.items]
        if value.kind == "dict":
            return {key: self.to_native(item) for key, item in value.fields.items()}
        if value.kind in {"tree_node", "list_node", "object"}:
            return {key: self.to_native(item) for key, item in value.fields.items()}
        if value.kind == "cycle":
            return {"$cycle": value.ref_id}
        if value.kind == "truncated":
            return {"$truncated": value.type_name}
        return {"$unsupported": value.type_name}

    def to_json(self, value: SerializedValue) -> str:
        import json

        return json.dumps(self.to_native(value), ensure_ascii=False)
