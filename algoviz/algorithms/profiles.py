"""Minimal algorithm profile registry shared by Two Sum and Binary Search.

The registry is intentionally small: two profiles exercise the extension seam.
It is not a speculative plugin framework.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from ..protocol.events import AnimationStep, Trace, VisualState
from ..protocol.hints import StepHint
from ..protocol.visual import VisualPlan
from ..render.components.variables import VariableRow


class AlgorithmProfileError(KeyError):
    pass


@dataclass(frozen=True)
class AlgorithmProfile:
    key: str
    title: str
    category: str
    visual_profile: Any
    semantic_factory: Callable[[], Any]
    trace_adapter_factory: Callable[[], Any]
    prepare_case: Callable[[dict[str, Any]], tuple[list[Any], dict[str, Any]]]
    hints_builder: Callable[[Trace], list[StepHint]]
    function_entry_point: str
    class_entry_point: str | None = None
    description: str = ""

    def entry_point_for(self, style: str) -> str:
        if style == "leetcode_class":
            if not self.class_entry_point:
                raise ValueError(f"{self.key} 不支持 LeetCode 类版源码形态")
            return self.class_entry_point
        return self.function_entry_point

    def build_visual_plan(self) -> VisualPlan:
        return self.visual_profile.build_visual_plan()

    def project_variables(self, state: VisualState, step: AnimationStep | None = None) -> list[VariableRow]:
        return self.visual_profile.project_variables(state, step)

    def build_hints(self, trace: Trace) -> list[StepHint]:
        return self.hints_builder(trace)

    def prepare_input(self, input_data: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
        return self.prepare_case(input_data)


class AlgorithmProfileRegistry:
    def __init__(self) -> None:
        self._profiles: dict[str, AlgorithmProfile] = {}

    def register(self, profile: AlgorithmProfile, *, replace: bool = False) -> None:
        if not profile.key:
            raise ValueError("AlgorithmProfile.key 不能为空")
        if profile.key in self._profiles and not replace:
            raise ValueError(f"AlgorithmProfile 已注册：{profile.key}")
        self._profiles[profile.key] = profile

    def get(self, key: str) -> AlgorithmProfile:
        try:
            return self._profiles[key]
        except KeyError as exc:
            raise AlgorithmProfileError(f"未注册的算法：{key}") from exc

    def has(self, key: str) -> bool:
        return key in self._profiles

    def keys(self) -> list[str]:
        return list(self._profiles)

    def values(self) -> Iterable[AlgorithmProfile]:
        return self._profiles.values()


def _check_nums_target(input_data: dict[str, Any]) -> tuple[list[int], int]:
    nums = input_data.get("nums")
    target = input_data.get("target")
    if not isinstance(nums, list) or not all(isinstance(item, int) and not isinstance(item, bool) for item in nums):
        raise ValueError("nums 必须是整数列表")
    if not isinstance(target, int) or isinstance(target, bool):
        raise ValueError("target 必须是整数")
    return list(nums), target


def _two_sum_prepare(input_data: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    nums, target = _check_nums_target(input_data)
    return [nums, target], {"nums": nums, "target": target}


def _binary_search_prepare(input_data: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    nums, target = _check_nums_target(input_data)
    return [nums, target], {"nums": nums, "target": target}


def build_default_registry() -> AlgorithmProfileRegistry:
    from ..execution.binary_search_semantic import BinarySearchSemanticTracer
    from ..execution.binary_search_trace_adapter import BinarySearchTraceAdapter
    from ..execution.semantic import TwoSumSemanticTracer
    from ..execution.trace_adapter import TwoSumTraceAdapter
    from ..teaching.binary_search_hints import build_binary_search_hints
    from ..teaching.binary_search_visual_profile import BinarySearchVisualProfile
    from ..teaching.step_hints import build_two_sum_hints
    from ..teaching.two_sum_profile import TwoSumVisualProfile

    registry = AlgorithmProfileRegistry()
    registry.register(
        AlgorithmProfile(
            key="two_sum",
            title="Two Sum · 哈希表",
            category="hash",
            visual_profile=TwoSumVisualProfile(),
            semantic_factory=TwoSumSemanticTracer,
            trace_adapter_factory=TwoSumTraceAdapter,
            prepare_case=_two_sum_prepare,
            hints_builder=build_two_sum_hints,
            function_entry_point="two_sum",
            class_entry_point="Solution.two_sum",
            description="使用哈希表记录已见数字和下标。",
        )
    )
    registry.register(
        AlgorithmProfile(
            key="binary_search",
            title="Binary Search · 二分查找",
            category="search",
            visual_profile=BinarySearchVisualProfile(),
            semantic_factory=BinarySearchSemanticTracer,
            trace_adapter_factory=BinarySearchTraceAdapter,
            prepare_case=_binary_search_prepare,
            hints_builder=build_binary_search_hints,
            function_entry_point="binary_search",
            class_entry_point="Solution.binary_search",
            description="维护有序数组的搜索区间，通过 mid 比较每次排除一半。",
        )
    )
    return registry


_default_registry: AlgorithmProfileRegistry | None = None


def get_registry() -> AlgorithmProfileRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = build_default_registry()
    return _default_registry


def get_profile(key: str) -> AlgorithmProfile:
    return get_registry().get(key)


def list_profiles() -> list[AlgorithmProfile]:
    return list(get_registry().values())
