"""组件注册表：ComponentKind -> 可创建组件实例的工厂。"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from ...protocol.visual import ComponentKind
from .base import VisualComponent


class ComponentRegistryError(RuntimeError):
    pass


class UnknownComponentError(ComponentRegistryError):
    pass


ComponentFactory = Callable[..., VisualComponent]


class ComponentRegistry:
    def __init__(self) -> None:
        self._factories: dict[ComponentKind, ComponentFactory] = {}

    def register(
        self,
        kind: ComponentKind,
        factory: ComponentFactory,
        *,
        replace: bool = False,
    ) -> None:
        if not isinstance(kind, ComponentKind):
            raise ComponentRegistryError("kind 必须是 ComponentKind")
        if not callable(factory):
            raise ComponentRegistryError("factory 必须可调用")
        if kind in self._factories and not replace:
            raise ComponentRegistryError(f"组件已注册：{kind.value}")
        self._factories[kind] = factory

    def unregister(self, kind: ComponentKind) -> None:
        if kind not in self._factories:
            raise UnknownComponentError(f"组件未注册：{kind.value}")
        del self._factories[kind]

    def get(self, kind: ComponentKind) -> ComponentFactory:
        try:
            return self._factories[kind]
        except KeyError as exc:
            raise UnknownComponentError(f"组件未注册：{kind.value}") from exc

    def create(self, kind: ComponentKind, **kwargs: Any) -> VisualComponent:
        component = self.get(kind)(**kwargs)
        actual = getattr(component, "kind", None)
        if actual != kind:
            raise ComponentRegistryError(
                f"工厂返回的组件 kind={actual!r}，期望 {kind.value!r}"
            )
        return component

    def has(self, kind: ComponentKind) -> bool:
        return kind in self._factories

    def kinds(self) -> Iterator[ComponentKind]:
        return iter(self._factories)

    def __contains__(self, kind: object) -> bool:
        return kind in self._factories

    def __len__(self) -> int:
        return len(self._factories)
