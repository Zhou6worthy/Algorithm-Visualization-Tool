"""通用视觉组件与默认注册表。"""
from __future__ import annotations

from ...protocol.visual import ComponentKind
from .array import ArrayVisualizer
from .assembler import (
    AssembledComponent,
    AssemblyResult,
    VisualAssembler,
    VisualAssemblyError,
)
from .base import ComponentContext, SceneHost, VisualComponent
from .code import CodeVisualizer, CodeWindow
from .hash_map import HashMapVisualizer
from .registry import (
    ComponentRegistry,
    ComponentRegistryError,
    UnknownComponentError,
)
from .variables import VariableRow, VariableVisualizer

default_registry = ComponentRegistry()
default_registry.register(ComponentKind.ARRAY, ArrayVisualizer)
default_registry.register(ComponentKind.HASH_MAP, HashMapVisualizer)
default_registry.register(ComponentKind.VARIABLES, VariableVisualizer)
default_registry.register(ComponentKind.CODE, CodeVisualizer)

__all__ = [
    "ArrayVisualizer",
    "AssembledComponent",
    "AssemblyResult",
    "CodeVisualizer",
    "CodeWindow",
    "ComponentContext",
    "ComponentKind",
    "ComponentRegistry",
    "ComponentRegistryError",
    "HashMapVisualizer",
    "SceneHost",
    "UnknownComponentError",
    "VariableRow",
    "VariableVisualizer",
    "VisualAssembler",
    "VisualAssemblyError",
    "VisualComponent",
    "default_registry",
]
