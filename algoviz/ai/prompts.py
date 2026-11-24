"""提示词：只做“理解/提取/讲解”，执行步骤永远来自追踪器。"""
from __future__ import annotations

import json
from typing import Any

from ..algorithms.registry import AlgorithmSpec

PARSE_SYSTEM = """你是一个算法教学视频的任务解析器。你的唯一工作是：从用户的自然语言请求中，提取算法类型和算法参数。
严格规则：
1. 只输出 JSON 对象，不要输出 Markdown、解释或前后缀。
2. 绝对不要编造算法执行步骤、执行结果或复杂度结论，这些由真实程序执行产生。
3. algorithm 必须从给定的候选算法 key 中选择；如果用户没有说清算法，选择最接近的一个。
4. params 只填写用户明确给出的参数；没有给出的参数不要填写，系统会使用默认值。
5. 数值参数必须是数字，不要写成字符串；数组必须是数字数组。
6. source 取值：natural_language / pseudocode / source_code / preset。
7. title 可选，是适合作为视频标题的中文短语（≤ 20 字）。

输出格式：
{"algorithm": "quick_sort", "title": "快速排序教学视频", "params": {"array": [8, 3, 5, 1, 9, 2], "pivot": "first"}, "source": "natural_language"}
"""

NARRATION_SYSTEM = """你是一名严谨的中文算法教学视频编剧。系统已经把算法的真实执行过程记录为事件步骤（JSON 中的 groups 与 steps），你只能依据这些真实步骤撰写讲解。
严格要求：
1. 只输出 JSON 对象，不要 Markdown。
2. 不要编造事件列表之外的比较、交换、访问或数值；不要声称算法做了它没有做的操作。
3. 复杂度数值由系统给定，你只能复述，不得改写。
4. 语言是简体中文，口语化、简洁，适合 TTS 朗读：不要使用 Markdown、星号、井号、表情符号。
5. 执行步骤的讲解要与 groups 的 index 一一对应：每组一句，长度 20~80 个汉字。
6. 术语保持准确：数组、下标、枢轴、区间、入队、出队、松弛、动态规划表等。
7. 不要把代码原样念出来，用自然语言解释当前发生了什么。

输出格式：
{
  "title": "快速排序：分治法排序",
  "problem": "一句话说明要解决什么问题",
  "idea": ["核心思想 1", "核心思想 2", "核心思想 3"],
  "intro": "开场白，引出问题与输入",
  "groups": [{"index": 0, "narration": "第 1 组执行步骤的讲解"}],
  "complexity_points": ["如何理解时间复杂度", "空间代价从哪里来"],
  "summary": ["总结 1", "总结 2", "总结 3"]
}
"""


def _catalog(candidates: list[AlgorithmSpec]) -> list[dict[str, Any]]:
    return [
        {
            "key": spec.key,
            "title": spec.title,
            "category": spec.category,
            "params": spec.defaults,
            "params_hint": {
                "array": "数字数组，2~16 个元素（排序/查找）",
                "values": "数字数组，1~15 个互不相同的值（树）",
                "target": "要查找的数字或节点 id",
                "nodes": "图节点 id 列表，2~10 个",
                "edges": "边列表 [[起点, 终点, 权重]]，无权图可省略权重",
                "start": "BFS/DFS/Dijkstra 起点节点 id",
                "weights": "0-1 背包物品重量数组",
                "values(背包)": "0-1 背包物品价值数组（与 weights 等长）",
                "capacity": "背包容量，1~12",
                "s1": "第一个字符串，1~8 个字符",
                "s2": "第二个字符串，1~8 个字符",
                "pivot": "quick_sort 的枢轴策略，first 或 last",
            },
        }
        for spec in candidates
    ]


def build_parse_prompt(text: str, candidates: list[AlgorithmSpec], source_hint: str) -> tuple[str, str]:
    payload = {
        "user_request": text,
        "detected_candidates": [spec.key for spec in candidates],
        "expected_source": source_hint,
        "algorithms": _catalog(candidates),
    }
    user = (
        "请解析下面的用户请求，输出 JSON。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    return PARSE_SYSTEM, user


def build_narration_prompt(
    trace_meta: dict[str, Any],
    groups: list[dict[str, Any]],
    *,
    max_groups: int,
) -> tuple[str, str]:
    payload = {
        "algorithm": trace_meta["algorithm"],
        "title": trace_meta["title"],
        "category": trace_meta["category"],
        "description": trace_meta["description"],
        "input": trace_meta["input"],
        "expected_output": trace_meta["expected_output"],
        "result": trace_meta["result"],
        "complexity": trace_meta["complexity"],
        "idea_reference": trace_meta["idea"],
        "summary_reference": trace_meta["summary"],
        "groups": groups,
        "constraints": {
            "language": "zh-CN",
            "max_groups": max_groups,
            "group_narration_chars": "20-80",
        },
    }
    return NARRATION_SYSTEM, json.dumps(payload, ensure_ascii=False, indent=2)
