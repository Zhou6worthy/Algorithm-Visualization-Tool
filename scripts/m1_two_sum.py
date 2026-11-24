"""M1 验收脚本：Two Sum 普通函数 + LeetCode Solution 类，生成真实产物。"""
from __future__ import annotations

import json
from pathlib import Path

from algoviz.execution.orchestrator import M1Executor

FUNCTION_SOURCE = '''def two_sum(nums, target):
    seen = {}
    for i, x in enumerate(nums):
        need = target - x
        if need in seen:
            return [seen[need], i]
        seen[x] = i
    return []
'''

CLASS_SOURCE = '''class Solution:
    def two_sum(self, nums, target):
        seen = {}
        for i, x in enumerate(nums):
            need = target - x
            if need in seen:
                return [seen[need], i]
            seen[x] = i
        return []
'''

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output" / "m1"


def main() -> int:
    executor = M1Executor(OUT)
    cases = [
        ("two_sum_function", FUNCTION_SOURCE, "function", "two_sum"),
        ("two_sum_class", CLASS_SOURCE, "leetcode_class", "Solution.two_sum"),
    ]
    summary = []
    ok = True
    for name, source, style, entry in cases:
        run = executor.run_two_sum(
            name=name,
            source=source,
            style=style,
            entry_point=entry,
            nums=[2, 7, 11, 15],
            target=9,
        )
        validation = run.execution.validation
        case = {
            "name": name,
            "style": style,
            "entry_point": entry,
            "status": run.execution.result.status.value,
            "actual_output": run.execution.result.actual_output,
            "expected_output": run.execution.expected_output,
            "events": len(run.execution.events),
            "semantic_ops": [op.kind.value for op in run.execution.semantic_ops],
            "validation": validation.model_dump(),
            "steps": len(run.trace.steps),
            "execution_json": str(run.work_dir / "execution.json"),
            "animation_events_json": str(run.work_dir / "animation_events.json"),
        }
        summary.append(case)
        ok = ok and validation.output_verified and validation.trace_verified and validation.structure_verified
        print(f"[{name}] status={case['status']} output={case['actual_output']} "
              f"events={case['events']} steps={case['steps']} "
              f"trace={validation.trace_verified} output_verified={validation.output_verified}")
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
