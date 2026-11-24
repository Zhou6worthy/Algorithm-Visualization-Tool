import pytest

from algoviz.ai.client import AIClient
from algoviz.ai.parser import TaskParser
from algoviz.algorithms.registry import TaskValidationError
from algoviz.config import get_settings


@pytest.fixture()
def parser() -> TaskParser:
    settings = get_settings()
    settings.ai_mode = "off"
    return TaskParser(AIClient(settings), settings)


def test_quick_sort_prompt(parser: TaskParser) -> None:
    task = parser.parse(
        "请生成快速排序的教学视频，选择第一个元素作为 Pivot，使用数组 [8, 3, 5, 1, 9, 2]。"
    )
    assert task.algorithm == "quick_sort"
    assert task.params["array"] == [8, 3, 5, 1, 9, 2]
    assert task.params["pivot"] == "first"
    assert task.source == "natural_language"


def test_binary_search_prompt(parser: TaskParser) -> None:
    task = parser.parse("二分查找，数组 [1, 3, 5, 7, 9]，目标值为 7")
    assert task.algorithm == "binary_search"
    assert task.params["array"] == [1, 3, 5, 7, 9]
    assert task.params["target"] == 7


def test_tree_traversal_preferred_over_build(parser: TaskParser) -> None:
    task = parser.parse("对二叉搜索树 [8, 3, 10, 1, 6] 进行中序遍历")
    assert task.algorithm == "tree_inorder"
    assert task.params["values"] == [8, 3, 10, 1, 6]


def test_graph_prompt(parser: TaskParser) -> None:
    task = parser.parse("用 BFS 遍历图，起点 A，边 A-B、B-C、A-C")
    assert task.algorithm == "bfs"
    assert task.params["nodes"] == ["A", "B", "C"]
    assert ["A", "B"] in task.params["edges"]
    assert task.params["start"] == "A"


def test_knapsack_prompt(parser: TaskParser) -> None:
    task = parser.parse("0-1 背包，重量 [2, 3, 4]，价值 [3, 4, 5]，容量 6")
    assert task.algorithm == "knapsack_01"
    assert task.params["weights"] == [2, 3, 4]
    assert task.params["values"] == [3, 4, 5]
    assert task.params["capacity"] == 6


def test_lcs_prompt(parser: TaskParser) -> None:
    task = parser.parse("求 ABCBDAB 和 BDCABA 的最长公共子序列")
    assert task.algorithm == "lcs"
    assert task.params["s1"] == "ABCBDAB"
    assert task.params["s2"] == "BDCABA"


def test_unknown_prompt_raises(parser: TaskParser) -> None:
    with pytest.raises(TaskValidationError):
        parser.parse("帮我做一个好看的视频")


def test_pseudocode_source(parser: TaskParser) -> None:
    task = parser.parse(
        "BinarySearch(A, target):\n    left = 0\n    right = n - 1\n"
        "    while left <= right:\n        mid = (left + right) // 2\n"
    )
    assert task.algorithm == "binary_search"
    assert task.source == "pseudocode"
