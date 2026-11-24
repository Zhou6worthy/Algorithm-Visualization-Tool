"""教学脚本生成：把真实事件流组织成“引入-思想-执行-代码-复杂度-总结”六段式讲解。"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from typing import Any

from .ai.client import AIClient
from .ai.prompts import build_narration_prompt
from .algorithms.registry import AlgorithmSpec
from .protocol.events import AnimationStep, StepType, Trace
from .protocol.teaching import (
    RenderOptions,
    SegmentKind,
    TeachingScript,
    TeachingSegment,
)

log = logging.getLogger("algoviz.script")

MAX_GROUPS = 14
_MARKDOWN_RE = re.compile(r"[*#`_]{1,3}")
_COMPLEXITY_RE = re.compile(r"O\([^)]*\)")


@dataclass
class StepGroup:
    index: int
    steps: list[AnimationStep]

    @property
    def step_start(self) -> int:
        return self.steps[0].step_id

    @property
    def step_end(self) -> int:
        return self.steps[-1].step_id


def _clean(text: Any, limit: int = 120) -> str:
    value = _MARKDOWN_RE.sub("", str(text or ""))
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) > limit:
        cut = value[:limit]
        for sep in ("；", "。", "，", "、"):
            pos = cut.rfind(sep)
            if pos > limit * 0.55:
                cut = cut[: pos + 1]
                break
        value = cut.rstrip("，、；") + "。"
    return value


def _str_list(value: Any, *, max_items: int = 4, limit: int = 70) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            text = _clean(item, limit)
            if text:
                items.append(text)
        if len(items) >= max_items:
            break
    return items


def _complexity_allowed(spec_complexity: dict[str, str]) -> set[str]:
    tokens: set[str] = set()
    for value in spec_complexity.values():
        tokens.update(_COMPLEXITY_RE.findall(str(value)))
    return tokens


def _complexity_ok(text: str, allowed: set[str]) -> bool:
    tokens = set(_COMPLEXITY_RE.findall(text))
    return tokens.issubset(allowed) if tokens else True


def group_steps(
    steps: list[AnimationStep],
    *,
    target_groups: int = MAX_GROUPS,
    min_size: int = 2,
    max_size: int = 8,
    steps_per_segment: int = 3,
) -> list[StepGroup]:
    if not steps:
        return []
    size = max(min_size, steps_per_segment, math.ceil(len(steps) / max(1, target_groups)))
    size = min(size, max_size, len(steps))
    groups: list[StepGroup] = []
    for index, start in enumerate(range(0, len(steps), size)):
        chunk = steps[start : start + size]
        if chunk:
            groups.append(StepGroup(index=index, steps=chunk))
    return groups


def _input_summary(trace: Trace) -> str:
    meta = trace.metadata
    data = meta.input
    try:
        if meta.category in {"sort", "search"}:
            array = data.get("array", [])
            text = "输入数组 " + "[" + ", ".join(str(v) for v in array) + "]"
            if meta.category == "search" and "target" in data:
                text += f"，目标值 {data['target']}"
            return text
        if meta.category == "tree":
            values = data.get("values", data.get("array", []))
            text = "输入节点序列 " + "[" + ", ".join(str(v) for v in values) + "]"
            if meta.algorithm == "bst_search":
                text += f"，查找目标 {data.get('target')}"
            return text
        if meta.category == "graph":
            nodes = data.get("nodes", [])
            edges = data.get("edges", [])
            text = f"输入图有 {len(nodes)} 个节点、{len(edges)} 条边，起点 {data.get('start', nodes[0] if nodes else '')}"
            if data.get("target"):
                text += f"，目标节点 {data['target']}"
            return text
        if meta.algorithm == "knapsack_01":
            return f"有 {len(data.get('weights', []))} 个物品，背包容量为 {data.get('capacity')}"
        if meta.algorithm == "lcs":
            return f"两个字符串分别为 \"{data.get('s1')}\" 和 \"{data.get('s2')}\""
    except Exception:  # noqa: BLE001 - 输入展示失败不应中断
        pass
    return ""


def _fallback_group_narration(group: StepGroup) -> str:
    meaningful = [s for s in group.steps if s.type != StepType.COMPLETE]
    if not meaningful:
        meaningful = group.steps
    if len(meaningful) == 1:
        text = meaningful[0].narration or meaningful[0].description
    else:
        first = meaningful[0]
        last = next(
            (s for s in reversed(meaningful) if s.type not in {StepType.NOTE, StepType.INIT}),
            meaningful[-1],
        )
        first_text = (first.narration or first.description).rstrip("。；")
        last_text = (last.narration or last.description).rstrip("。；")
        if first_text == last_text:
            text = first_text
        else:
            text = f"{first_text}；随后，{last_text}"
    return _clean(text, 56)


def _input_phrase(trace: Trace) -> str:
    summary = _input_summary(trace)
    return summary.rstrip("。") + "。" if summary else ""


def build_teaching_script(
    trace: Trace,
    spec: AlgorithmSpec,
    options: RenderOptions,
    ai: AIClient | None = None,
) -> tuple[TeachingScript, list[str]]:
    """生成六段式教学脚本；DeepSeek 可用时润色讲解，否则使用严谨的本地模板。"""
    warnings: list[str] = []
    meta = trace.metadata
    groups = group_steps(trace.steps, steps_per_segment=options.steps_per_segment)
    complexity = meta.complexity
    allowed_tokens = _complexity_allowed(
        {"time": complexity.time, "space": complexity.space, "note": complexity.note}
    )

    title = meta.title
    problem = meta.description
    idea = list(meta.idea)
    summary = list(meta.summary)
    complexity_points = [complexity.note] if complexity.note else []
    intro_text = _clean(
        f"本视频用动画演示{title}。{meta.description}{_input_phrase(trace)}", 70
    )
    group_texts = {group.index: _fallback_group_narration(group) for group in groups}

    if ai is not None and ai.available and groups:
        payload_meta = {
            "algorithm": meta.algorithm,
            "title": meta.title,
            "category": meta.category,
            "description": meta.description,
            "input": meta.input,
            "expected_output": meta.expected_output,
            "result": trace.result,
            "complexity": complexity.model_dump(),
            "idea": idea,
            "summary": summary,
        }
        group_payload = [
            {
                "index": group.index,
                "step_start": group.step_start,
                "step_end": group.step_end,
                "steps": [
                    {
                        "step_id": step.step_id,
                        "type": step.type.value,
                        "description": step.description,
                        "targets": step.targets,
                    }
                    for step in group.steps
                ],
            }
            for group in groups
        ]
        system, user = build_narration_prompt(payload_meta, group_payload, max_groups=len(groups))
        data = ai.chat_json(
            system,
            user,
            temperature=0.35,
            max_tokens=6500,
            purpose="narration",
        )
        if data:
            if isinstance(data.get("title"), str) and data["title"].strip():
                title = _clean(data["title"], 24)
            if isinstance(data.get("problem"), str) and data["problem"].strip():
                problem = _clean(data["problem"], 80)
            ai_idea = _str_list(data.get("idea"), max_items=4, limit=60)
            if len(ai_idea) >= 2:
                idea = ai_idea
            ai_summary = _str_list(data.get("summary"), max_items=4, limit=60)
            if len(ai_summary) >= 2:
                summary = ai_summary
            ai_complexity = _str_list(data.get("complexity_points"), max_items=3, limit=80)
            if ai_complexity and all(_complexity_ok(text, allowed_tokens) for text in ai_complexity):
                complexity_points = ai_complexity
            if isinstance(data.get("intro"), str) and data["intro"].strip():
                candidate = _clean(data["intro"], 110)
                if _complexity_ok(candidate, allowed_tokens):
                    intro_text = candidate
            raw_groups = data.get("groups")
            if isinstance(raw_groups, list):
                for item in raw_groups:
                    if not isinstance(item, dict):
                        continue
                    try:
                        idx = int(item.get("index"))
                    except (TypeError, ValueError):
                        continue
                    narration = item.get("narration")
                    if idx in group_texts and isinstance(narration, str) and narration.strip():
                        cleaned = _clean(narration, 60)
                        if _complexity_ok(cleaned, allowed_tokens):
                            group_texts[idx] = cleaned
            else:
                warnings.append("AI 未返回 execution groups，已使用本地讲解模板")

    segments: list[TeachingSegment] = []

    def add(
        kind: SegmentKind,
        title_text: str,
        narration: str,
        *,
        step_start: int | None = None,
        step_end: int | None = None,
        subtitle: str | None = None,
    ) -> None:
        cleaned = _clean(narration, 300)
        segments.append(
            TeachingSegment(
                id=f"seg_{len(segments):02d}",
                kind=kind,
                title=title_text,
                narration=cleaned,
                subtitle=_clean(subtitle or cleaned, 120),
                step_start=step_start,
                step_end=step_end,
            )
        )

    add(SegmentKind.INTRO, "问题引入", intro_text, subtitle=_clean(intro_text, 64))
    add(
        SegmentKind.IDEA,
        "核心思想",
        "核心思想：" + "；".join(part.rstrip("。；") for part in idea) + "。",
        subtitle=_clean("核心思想：" + idea[0] if idea else "核心思想", 64),
    )
    for group in groups:
        add(
            SegmentKind.EXECUTION,
            f"执行过程 {group.index + 1}",
            group_texts[group.index],
            step_start=group.step_start,
            step_end=group.step_end,
        )
    add(
        SegmentKind.CODE,
        "代码对应",
        f"下面给出 {meta.code_language} 实现。动画里高亮的代码行，就对应正在发生的比较、交换或访问操作。",
        subtitle="动画中的操作与代码高亮行一一对应",
    )
    complexity_narration = f"时间复杂度为 {complexity.time}，空间复杂度为 {complexity.space}。"
    for point in complexity_points:
        if point and point not in complexity_narration:
            complexity_narration += point.rstrip("。") + "。"
    add(
        SegmentKind.COMPLEXITY,
        "复杂度分析",
        complexity_narration,
        subtitle=f"时间复杂度 {complexity.time} · 空间复杂度 {complexity.space}",
    )
    add(
        SegmentKind.SUMMARY,
        "总结",
        "总结一下：" + "；".join(part.rstrip("。；") for part in summary) + "。",
        subtitle=_clean("总结：" + summary[0] if summary else "总结", 64),
    )
    script = TeachingScript(
        title=title,
        problem=problem,
        idea=idea,
        complexity_points=complexity_points,
        summary=summary,
        segments=segments,
    )
    return script, warnings
