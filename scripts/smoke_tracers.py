from algoviz.protocol.teaching import TaskSpec
from algoviz.algorithms.registry import execute_task, list_algorithms

print([s.key for s in list_algorithms()])
samples = [
    TaskSpec(algorithm="bubble_sort", params={"array": [5, 3, 8, 1]}),
    TaskSpec(algorithm="quick_sort", params={"array": [8, 3, 5, 1, 9, 2], "pivot": "first"}),
    TaskSpec(algorithm="merge_sort", params={"array": [8, 3, 5, 1, 9, 2]}),
    TaskSpec(algorithm="binary_search", params={"array": [1, 3, 5, 7, 9, 11], "target": 7}),
    TaskSpec(algorithm="bst_build", params={"values": [8, 3, 10, 1, 6, 14, 4, 7, 13]}),
    TaskSpec(algorithm="tree_inorder", params={"values": [8, 3, 10, 1, 6, 14, 4, 7, 13]}),
    TaskSpec(algorithm="bfs", params={}),
    TaskSpec(algorithm="dfs", params={}),
    TaskSpec(algorithm="dijkstra", params={}),
    TaskSpec(algorithm="knapsack_01", params={}),
    TaskSpec(algorithm="lcs", params={}),
]
for task in samples:
    try:
        out = execute_task(task)
        t = out.trace
        print(
            f"OK {t.metadata.algorithm:16s} steps={len(t.steps):3d} verified={t.verified} "
            f"notes={t.verification_notes[:1]} warnings={out.warnings[:1]}"
        )
    except Exception as e:
        import traceback

        traceback.print_exc()
        print("FAIL", task.algorithm, e)
