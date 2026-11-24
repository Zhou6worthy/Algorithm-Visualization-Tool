# M3-5 实施报告：多测试用例与真实 Trace 切换

> 本轮只完成 M3-5。  
> 未实现 PlaybackController、教师控制、自动播放、教学提示、HTML 多用例、HTML 组件化、通用 LessonScene、第二算法或新 Tracer。

## 1. 实际完成结论

| 项目 | 状态 |
|---|---|
| `TestCaseSpec` / `CaseSource` / `CaseRun` | **已实现** |
| 多用例真实执行 `CaseRunner` | **已实现** |
| 每个用例独立 ExecutionTrace + AnimationTrace | **已实现、已测试** |
| `CaseRunStore` | **已实现** |
| `TwoSumStage.load_case` / `reset` | **已实现、已测试** |
| VisualPlan / 组件实例切换复用 | **已实现、已验证** |
| Case 1 → Case 2 → Case 1 状态切换 | **已验证** |
| 原有单用例 M2 MP4/HTML 流程 | **已回归** |
| 完整课堂播放器 / 多用例 HTML | **未实现** |

修改前基线：

```text
pytest -q
85 passed
```

修改后：

```text
pytest -q
93 passed
```

新增 M3-5 测试 8 项。

## 2. 新增 / 修改文件

### 新增

| 文件 | 内容 |
|---|---|
| `algoviz/protocol/cases.py` | `CaseSource`、`TestCaseSpec`、`CaseRun`、`CaseRunStatus` |
| `algoviz/execution/case_runner.py` | 多用例真实执行、CaseRun 生成 |
| `algoviz/execution/case_store.py` | `CaseRunStore` |
| `tests/test_m3_5_multi_case.py` | 8 个多用例/切换测试 |
| `scripts/m3_5_multi_case_demo.py` | 可运行的多用例演示脚本 |
| `M3_5_IMPLEMENTATION_REPORT.md` | 本报告 |

### 修改

| 文件 | 改动 |
|---|---|
| `algoviz/execution/validator.py` | 增加 `verify_output` 开关；不提供 expected 时不做输出比较 |
| `algoviz/execution/orchestrator.py` | 增加 `check_output` 参数；默认行为保持 |
| `algoviz/render/two_sum_visuals.py` | 增加 `load_case/reset/current_case_id/current_step_index`；加载真实 AnimationTrace 初始状态，不重新装配组件 |
| `output/m2/...` | 单用例 M2 流程重新生成 |

### 未修改

- M1 ExecutionTrace / ExecutionEvent 字段；
- M1/M2 AnimationTrace / VisualState 字段；
- TwoSumScene；
- TwoSumVisualProfile / VisualPlan；
- 组件内部算法边界；
- 旧 18 个 tracer；
- 旧 visuals.py / pipeline.py。

## 3. 数据模型

### TestCaseSpec

```python
TestCaseSpec(
    case_id="normal",
    name="正常查找",
    input_data={"nums": [2, 7, 11, 15], "target": 9},
    expected_output=[0, 1],
    source=CaseSource.USER,
)
```

- `case_id` 唯一；
- `source` 区分 `USER` / `AI_GENERATED`；
- `expected_output` 可省略；
- `metadata` 预留。

### CaseRun

```python
CaseRun(
    run_id="run_normal_...",
    case_id="normal",
    status=CaseRunStatus.SUCCESS,
    execution_trace=...,
    animation_trace=...,
    actual_output=[0, 1],
    expected_output=[0, 1],
    error=None,
    execution_metadata={...},
)
```

- 一次执行一个 `run_id`；
- 重复执行同一个 `TestCaseSpec` 会生成新的 `run_id`，旧记录不覆盖；
- `SUCCESS` 必须有 ExecutionTrace 和 AnimationTrace；
- `FAILED` 表示真实执行成功但输出不等于 expected；
- `ERROR` 表示输入/执行/追踪错误；
- `execution_metadata.case_snapshot` 保留原始用例快照，保证可追溯。

### CaseRunStatus

`PENDING`、`RUNNING`、`SUCCESS`、`FAILED`、`ERROR`。

本轮实际会产生 `SUCCESS`、`FAILED`、`ERROR`；`PENDING/RUNNING` 为未来异步执行预留。

## 4. CaseRunner

`algoviz/execution/case_runner.py`

复用现有 `M1Executor.run_two_sum`，没有重新实现执行引擎。

流程：

```text
TestCaseSpec
  → 输入校验（nums/target）
  → M1Executor.run_two_sum
  → ExecutionTrace
  → TwoSumTraceAdapter
  → AnimationTrace
  → CaseRun
```

关键点：

- 每个用例使用独立 `run_id` 和独立工作目录；
- 每个用例独立调用 `M1Executor`；
- 不共享可变 ExecutionTrace/AnimationTrace；
- 单用例失败不覆盖其他用例；
- 默认继续执行其他用例；
- `expected_output` 提供时比较，不提供时仍执行并保留 actual_output，但不做输出比较；
- 无 expected 的 `animation_trace.verified` 可能为 false（因为未做输出校验），但它是真实执行产生的轨迹，不是伪造。

## 5. CaseRunStore

`CaseRunStore` 支持：

- `add_case`；
- `add_run`；
- `get_case` / `get_run`；
- `runs_for_case`；
- `select_case`（取该 case 最近一次 run）；
- `select_run`；
- `current_case_id` / `current_run`；
- case/run 不存在、重复、未执行等错误。

## 6. TwoSumStage 切换

新增：

```python
stage.load_case(case_run)
stage.reset()
stage.current_case_id
stage.current_step_index
```

`load_case`：

1. 检查 `CaseRun.animation_trace` 有效且非空；
2. 替换 `self.animation_trace`；
3. 设置 `current_case_id`；
4. 使用目标 trace 的 step 0 重新更新：
   - ArrayVisualizer；
   - HashMapVisualizer；
   - VariableVisualizer；
   - CodeVisualizer；
5. 重置 `current_step_index = 0`；
6. 不重新创建 VisualPlan；
7. 不重新创建 Assembler；
8. 不重新创建组件。

`reset()` 将当前 trace 恢复到 step 0 初始状态。

### 复用验证

测试和演示脚本均验证：

- `stage.visual_plan` 对象 ID 在切换前后相同；
- `stage.assembly` 对象 ID 相同；
- 四个组件实例 ID 相同；
- 数组、哈希表、变量、代码行均随目标 CaseRun 更新；
- 切回 Case 1 后状态正确，不保留 Case 2 的哈希或变量。

## 7. 实际测试结果

```text
pytest -q
93 passed
```

构成：

- 旧算法与旧功能：43；
- M1：9；
- M2：8；
- M3-2：8；
- M3-3：10；
- M3-4：7；
- M3-5：8。

M3-5 测试：

```text
test_case_models_and_sources
test_case_runner_edge_cases
test_case_runner_leetcode_class_shape
test_case_runner_mismatch_optional_and_input_error
test_repeated_case_run_creates_new_run_and_store_keeps_both
test_case_store_errors
test_stage_switch_reuses_assembly_and_visual_plan
test_stage_rejects_case_without_animation_trace
```

专项回归：

```text
pytest -q tests/test_tracers.py
25 passed

pytest -q tests/test_m1_execution.py tests/test_m2_teaching.py
17 passed
```

## 8. 多用例实际结果

`scripts/m3_5_multi_case_demo.py` 实际输出：

| case | source | status | actual | events | steps |
|---|---|---|---|---|---|
| normal | user | success | `[0, 1]` | 11 | 8 |
| first | user | success | `[0, 1]` | 11 | 8 |
| last | user | success | `[2, 3]` | 19 | 14 |
| none | user | success | `[]` | 17 | 13 |
| duplicate | user | success | `[0, 1]` | 11 | 8 |
| empty | user | success | `[]` | 5 | 3 |
| single | user | success | `[]` | 9 | 7 |
| mismatch | user | failed | `[0, 2]` | 15 | 11 |
| invalid | user | error | — | 0 | 0 |
| ai_supplemented | ai_generated | success | `[1, 2]` | 15 | 11 |

实际证明：

- 不同用例 step 数不同（3、7、8、11、13、14）；
- 每个成功用例有独立 `trace_id`；
- mismatch 保留真实 trace，但状态为 FAILED；
- invalid 不生成伪造 trace；
- AI 补充用例来源为 `ai_generated`。

## 9. 切换验证

实际 `Case 1 → Case 2 → Case 1`：

| 状态 | case | array | target | visual_plan_same | assembly_same |
|---|---|---|---|---|---|
| 1 | normal | `[2, 7, 11, 15]` | 9 | true | true |
| 2 | first | `[3, 2, 4]` | 5 | true | true |
| 3 | normal | `[2, 7, 11, 15]` | 9 | true | true |

组件 ID 始终为：

```text
["array", "code", "hash_map", "variables"]
```

测试还覆盖了：

- normal 执行到插入后 `seen` 有 `2`；
- 切换到 first 后 `seen` 为空；
- 再切回 normal 后轨迹完整，不保留 first 状态。

## 10. M2 单用例兼容性

已实际运行：

```powershell
.\.venv\Scripts\python.exe scripts\m2_two_sum.py --forms function,class --output-root output/m2
```

函数版/类版 overview、step_by_step、interactive.html、teaching_plan.json 均重新生成；QC 检查通过，原单用例流程未被 M3-5 破坏。

关键帧：

- `output/m3_5/before/...`
- `output/m3_5/after/...`

实际像素差异：

| 形态 | 全图 mean |
|---|---|
| function step6 | 0.000 |
| function step7 | 0.000 |
| class step6 | 0.000 |
| class step7 | 0.000 |

四个关键帧零像素差异；M3-5 只新增 `load_case/reset` 和可选 expected 校验，未改教学时间轴。

## 11. 已实现 / 已验证 / 仅设计

### 已实现

- 多用例数据模型；
- CaseRunner；
- CaseRunStore；
- Stage 切换；
- 真实 trace 隔离；
- 示例脚本。

### 已测试

- 93 个完整测试；
- 8 个 M3-5 测试；
- 18 算法 25 个 tracer 测试；
- M1/M2 17 个联合测试。

### 已验证产物

- 多用例执行结果与 `case_summary.json`；
- Case 1 → Case 2 → Case 1 切换；
- VisualPlan/Assembly/组件实例复用；
- M2 单用例回归产物。

### 仅设计，未实现

- PlaybackController；
- 教师控制模式；
- 自动播放；
- 上一步/下一步/跳转；
- 教学提示；
- HTML 多用例切换；
- HTML 组件化；
- 通用 LessonScene；
- 第二算法；
- AI 用例自动生成；
- Docker 生产沙箱。

## 12. 已知限制

1. 无 expected 的用例会成功执行，但 `animation_trace.verified` 可能为 false；这是“未做输出校验”，不是失败或伪造。
2. `CaseRunner` 仍只支持当前 Two Sum function/class 形态，不支持 Java/C++/stdin。
3. `CaseRunStore` 只在内存中保存，未持久化到 SQLite。
4. 切换只加载 trace 初始状态，没有完整教师播放器。
5. 没有 HTML 多用例 UI。
6. 多用例演示脚本使用 FakeScene，不是 GUI。
7. 没有 AI 自动生成用例。
8. M3-5 没有实现完整课堂交互。

## 13. 后续计划

| 阶段 | 目标 |
|---|---|
| M3-6 | 教师控制 + 自动演示 |
| M3-7 | 教学提示与课堂提问 |
| M3-8 | HTML 组件化与课堂交互 |
| M3-9 | 第二算法 Profile 验证 |

本轮完成后停止，等待审查，不自动进入 M3-6。
