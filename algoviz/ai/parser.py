"""自然语言 / 伪代码 → TaskSpec 解析（确定性提取 + DeepSeek 辅助）。"""
from __future__ import annotations

import logging
import re
from typing import Any

from ..algorithms.registry import (
    ALGORITHMS,
    AlgorithmSpec,
    TaskValidationError,
    detect_algorithms,
    list_algorithms,
)
from ..config import Settings, get_settings
from ..protocol.events import InputSource
from ..protocol.teaching import RenderOptions, TaskSpec
from .client import AIClient
from .prompts import build_parse_prompt

log = logging.getLogger("algoviz.parse")

_KNOWN_ACRONYMS = {"BFS", "DFS", "LCS", "DP", "AI", "API", "O", "LOG", "TTS", "MP4", "PDF", "HTML"}


def _looks_like_pseudocode(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()]
    code_markers = ("def ", "while ", "for ", "if ", "else", "return ", "left", "right", "mid =", "end for")
    marked = sum(1 for line in lines if any(marker in line.lower() for marker in code_markers))
    return len(lines) >= 2 and marked >= 2


def _extract_bracket_lists(text: str) -> list[list[float]]:
    lists: list[list[float]] = []
    for match in re.finditer(r"\[([^\[\]]{1,200})\]", text):
        body = match.group(1)
        if not re.search(r"\d", body):
            continue
        parts = [p for p in re.split(r"[,，;；\s]+", body.strip()) if p]
        numbers: list[float] = []
        ok = True
        for part in parts:
            try:
                numbers.append(float(part))
            except ValueError:
                ok = False
                break
        if ok and numbers:
            lists.append(numbers)
    return lists


def _extract_target(text: str) -> float | int | None:
    masked = re.sub(r"\[[^\[\]]*\]", " ", text)
    patterns = [
        r"(?:target|目标值|目标元素|目标数字|目标)\s*(?:为|是|=|:|：)?\s*(-?\d+(?:\.\d+)?)",
        r"(?:查找|搜索|寻找|查询)\s*(?:元素|值|数字)?\s*(-?\d+(?:\.\d+)?)",
        r"(?:值为|值等于)\s*(-?\d+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, masked, flags=re.IGNORECASE)
        if match:
            value = float(match.group(1))
            return int(value) if value.is_integer() else value
    return None


def _extract_pivot(text: str) -> str | None:
    if not re.search(r"pivot|枢轴|基准", text, flags=re.IGNORECASE):
        return None
    if re.search(r"(第一个|首个|首元素|最左|左边第一个)", text):
        return "first"
    if re.search(r"(最后一个|末元素|最右|右边最后一个)", text):
        return "last"
    return None


def _extract_quoted_strings(text: str) -> list[str]:
    found: list[str] = []
    for match in re.finditer(r"[\"“'‘]([A-Za-z0-9]{1,10})[\"”'’]", text):
        found.append(match.group(1))
    if len(found) < 2:
        for match in re.finditer(r"\b[A-Za-z]{2,8}\b", text):
            token = match.group(0)
            if token.upper() in _KNOWN_ACRONYMS:
                continue
            if token not in found:
                found.append(token)
    return found


def _numbers_after_label(text: str, labels: str, stop_labels: str) -> list[int] | None:
    pattern = re.compile(
        rf"(?:{labels})\s*(?:分别|分别有|为|是|=|:|：)?\s*(?:\[([^\]]+)\]|(.*?)(?=(?:{stop_labels})|$))",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return None
    body = match.group(1) if match.group(1) else match.group(2)
    numbers = re.findall(r"\d+(?:\.\d+)?", body or "")
    if not numbers:
        return None
    return [int(float(n)) for n in numbers]


def _extract_knapsack(text: str) -> dict[str, Any]:
    params: dict[str, Any] = {}
    labels_stop = r"values?|价值|物品价值|capacity|容量|背包容量"
    weights = _numbers_after_label(text, r"weights?|重量|物品重量", labels_stop)
    if weights:
        params["weights"] = weights
    values = _numbers_after_label(text, r"values?|价值|物品价值", r"capacity|容量|背包容量")
    if values:
        params["values"] = values
    match = re.search(r"(?:capacity|容量|背包容量)\s*(?:为|是|=|:|：)?\s*(\d+)", text, flags=re.IGNORECASE)
    if match:
        params["capacity"] = int(match.group(1))
    return params


def _extract_graph(text: str) -> dict[str, Any]:
    params: dict[str, Any] = {}
    edge_pattern = re.compile(
        r"(?<![A-Za-z0-9_])([A-Za-z0-9_]{1,4})\s*(?:->|→|—|－|\-|到)\s*([A-Za-z0-9_]{1,4})"
        r"(?:\s*[\(（]\s*(\d+(?:\.\d+)?)\s*[\)）])?"
    )
    edges: list[list[Any]] = []
    nodes: list[str] = []
    for match in edge_pattern.finditer(text):
        u, v = match.group(1), match.group(2)
        if u in {"的", "和", "与"} or v in {"的", "和", "与"}:
            continue
        weight = match.group(3)
        edge: list[Any] = [u, v]
        if weight:
            edge.append(float(weight))
        edges.append(edge)
        for node in (u, v):
            if node not in nodes:
                nodes.append(node)
    if not edges:
        return params
    params["edges"] = edges
    params["nodes"] = nodes
    start = re.search(r"(?:start|起点|从)\s*(?:节点)?\s*([A-Za-z0-9_]{1,4})", text, flags=re.IGNORECASE)
    if start and start.group(1) in nodes:
        params["start"] = start.group(1)
    target = re.search(r"(?:target|目标节点)\s*(?:为|是|=|:|：)?\s*([A-Za-z0-9_]{1,4})", text, flags=re.IGNORECASE)
    if target and target.group(1) in nodes:
        params["target"] = target.group(1)
    return params


def extract_deterministic_params(text: str, spec: AlgorithmSpec) -> dict[str, Any]:
    params: dict[str, Any] = {}
    bracket_lists = _extract_bracket_lists(text)
    if spec.category in {"sort", "search"}:
        if bracket_lists:
            params["array"] = bracket_lists[0]
        target = _extract_target(text)
        if target is not None:
            params["target"] = target
        if spec.key == "quick_sort":
            pivot = _extract_pivot(text)
            if pivot:
                params["pivot"] = pivot
    elif spec.category == "tree":
        if bracket_lists:
            params["values"] = bracket_lists[0]
        if spec.key == "bst_search":
            target = _extract_target(text)
            if target is not None:
                params["target"] = target
    elif spec.category == "graph":
        params.update(_extract_graph(text))
    elif spec.category == "dp":
        if spec.key == "knapsack_01":
            params.update(_extract_knapsack(text))
        elif spec.key == "lcs":
            strings = _extract_quoted_strings(text)
            if len(strings) >= 2:
                params["s1"], params["s2"] = strings[0], strings[1]
    return params


def _source_of(text: str) -> InputSource:
    if "```" in text:
        return InputSource.SOURCE_CODE
    if _looks_like_pseudocode(text):
        return InputSource.PSEUDOCODE
    return InputSource.NATURAL_LANGUAGE


class TaskParser:
    def __init__(self, ai: AIClient | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.ai = ai or AIClient(self.settings)

    def parse(self, prompt: str, options: RenderOptions | None = None) -> TaskSpec:
        text = prompt.strip()
        if not text:
            raise TaskValidationError("输入内容为空")
        options = options or RenderOptions(
            theme=self.settings.theme,
            resolution=self.settings.resolution,
            fps=self.settings.fps,
            max_seconds=self.settings.max_seconds,
            voice=self.settings.voice,
            tts_provider=self.settings.tts_provider,
            render_quality=self.settings.render_quality,
        )
        candidates = detect_algorithms(text)
        source = _source_of(text)
        chosen: AlgorithmSpec | None = candidates[0] if candidates else None
        ai_params: dict[str, Any] = {}
        ai_title: str | None = None
        notes: list[str] = []
        if self.ai.available:
            catalog = candidates if candidates else list_algorithms()
            system, user = build_parse_prompt(text, catalog, source.value)
            ai_data = self.ai.chat_json(
                system,
                user,
                temperature=0.1,
                max_tokens=3000,
                purpose="parse",
            )
            if ai_data:
                key = str(ai_data.get("algorithm", "")).strip().lower()
                ai_spec = ALGORITHMS.get(key)
                if ai_spec is None:
                    notes.append(f"模型返回了未知算法 {key!r}，已使用本地识别结果")
                else:
                    chosen = ai_spec
                params = ai_data.get("params")
                if isinstance(params, dict):
                    ai_params = {k: v for k, v in params.items() if v is not None}
                if ai_data.get("title"):
                    ai_title = str(ai_data["title"])[:40]
        if chosen is None:
            supported = "、".join(spec.title for spec in list_algorithms()[:8])
            raise TaskValidationError(
                f"未能从输入中识别算法。请明确说出算法名称（如：快速排序、二分查找、BFS、0-1 背包），当前支持：{supported} 等。"
            )
        local_params = extract_deterministic_params(text, chosen)
        allowed = set(chosen.defaults)
        merged = dict(local_params)
        for key, value in ai_params.items():
            if key in allowed and value is not None:
                merged[key] = value
        title = ai_title or f"{chosen.title}教学视频"
        return TaskSpec(
            algorithm=chosen.key,
            title=title,
            params=merged,
            prompt=text,
            source=source.value,
            options=options,
            notes=notes,
        )
