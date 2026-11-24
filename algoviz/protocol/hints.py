"""教学提示协议：与真实 AnimationStep 绑定，但不修改执行轨迹。"""
from __future__ import annotations

from enum import Enum

from pydantic import Field

from .events import StrictModel


class HintKind(str, Enum):
    INITIALIZE = "initialize"
    VISIT = "visit"
    COMPLEMENT_MISS = "complement_miss"
    COMPLEMENT_HIT = "complement_hit"
    INSERT = "insert"
    RETURN = "return"
    NOT_FOUND = "not_found"
    COMPLETE = "complete"
    # Binary search
    RANGE_INIT = "range_init"
    PROBE = "probe"
    COMPARE_LESS = "compare_less"
    COMPARE_GREATER = "compare_greater"
    FOUND = "found"
    SEARCH_COMPLETE = "search_complete"


class StepHint(StrictModel):
    """一条课堂提示。

    ``related_step_id`` 必须指向某条真实 AnimationTrace 的步骤；提示文本是
    教学素材，不能作为算法事实来源，也不能写回 AnimationTrace。
    """

    hint_id: str = Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")
    related_step_id: int = Field(ge=0)
    kind: HintKind
    title: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    common_mistake: str = ""
    question: str = ""
    answer: str = ""
    concepts: list[str] = Field(default_factory=list)
