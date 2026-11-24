"""VisualPlan 驱动的通用组件装配器。

装配器只做：
- 遍历 ComponentSpec；
- 校验槽位/ID/Registry；
- 通过 Registry 创建组件；
- 用对应 ComponentContext 调用 mount。

它不知道算法名字，也不直接操作 Manim 之外的协议。
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from ...protocol.events import VisualState
from ...protocol.visual import ComponentSpec, LayoutBox, VisualPlan
from .base import ComponentContext, SceneHost, VisualComponent
from .registry import ComponentRegistry, ComponentRegistryError, UnknownComponentError


class VisualAssemblyError(RuntimeError):
    pass


@dataclass(frozen=True)
class AssembledComponent:
    spec: ComponentSpec
    component: VisualComponent
    slot: LayoutBox
    context: ComponentContext


@dataclass(frozen=True)
class AssemblyResult:
    components: dict[str, VisualComponent]
    specs: dict[str, ComponentSpec]
    slots: dict[str, LayoutBox]
    contexts: dict[str, ComponentContext]

    def get(self, component_id: str) -> VisualComponent:
        try:
            return self.components[component_id]
        except KeyError as exc:
            raise VisualAssemblyError(f"组件未装配：{component_id}") from exc

    def __contains__(self, component_id: object) -> bool:
        return component_id in self.components


class VisualAssembler:
    def __init__(self, registry: ComponentRegistry) -> None:
        self.registry = registry

    def assemble(
        self,
        plan: VisualPlan,
        host: SceneHost,
        base_context: ComponentContext,
        state: VisualState,
    ) -> AssemblyResult:
        ids = [spec.component_id for spec in plan.components]
        if len(ids) != len(set(ids)):
            raise VisualAssemblyError("component_id 重复")

        components: dict[str, VisualComponent] = {}
        specs: dict[str, ComponentSpec] = {}
        slots: dict[str, LayoutBox] = {}
        contexts: dict[str, ComponentContext] = {}
        for spec in plan.components:
            if spec.component_id in components:
                raise VisualAssemblyError(f"component_id 重复：{spec.component_id}")
            slot = plan.slots.get(spec.slot)
            if slot is None:
                raise VisualAssemblyError(f"组件 {spec.component_id} 引用了不存在的槽位 {spec.slot}")
            if not self.registry.has(spec.kind):
                raise VisualAssemblyError(f"组件类型未注册：{spec.kind.value}")
            context = replace(base_context, area=slot)
            try:
                component = self.registry.create(
                    spec.kind,
                    host=host,
                    context=context,
                    options=dict(spec.options),
                )
            except (ComponentRegistryError, UnknownComponentError) as exc:
                raise VisualAssemblyError(str(exc)) from exc
            try:
                component.mount(host, context, state)
            except Exception as exc:  # noqa: BLE001 - 装配阶段统一报错
                raise VisualAssemblyError(
                    f"组件 {spec.component_id} mount 失败：{type(exc).__name__}: {exc}"
                ) from exc
            components[spec.component_id] = component
            specs[spec.component_id] = spec
            slots[spec.component_id] = slot
            contexts[spec.component_id] = context
        return AssemblyResult(
            components=components,
            specs=specs,
            slots=slots,
            contexts=contexts,
        )
