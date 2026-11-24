# M3-4 实施报告：TwoSumVisualProfile 与 VisualPlan 驱动装配

> 本轮严格只完成 M3-4。  
> 未实现多测试用例、PlaybackController、教师控制、自动播放、教学提示、HTML 组件化、通用 LessonScene、第二算法或新 Tracer。

## 1. 实际完成结论

| 项目 | 状态 |
|---|---|
| TwoSumVisualProfile | **已实现、已测试** |
| VisualPlan 描述组件/槽位/options | **已实现** |
| VisualAssembler | **已实现、已测试** |
| TwoSumStage 使用 Profile + Assembler | **已实现** |
| TwoSumStage 不再手动创建四个组件 | **已实现** |
| Registry 被装配器实际调用 | **是** |
| Two Sum 变量投影留在 Profile/独立层 | **是** |
| M2 函数版/类版重新生成 | **已完成** |
| 关键帧前后对比 | **已完成** |
| 多用例/课堂播放器/HTML 组件化 | **未实现，仅设计** |

修改前基线：

```text
pytest -q
78 passed
```

修改后：

```text
pytest -q
85 passed
```

新增 M3-4 测试 7 项。

## 2. 新增 / 修改文件

### 新增

| 文件 | 内容 |
|---|---|
| `algoviz/teaching/two_sum_profile.py` | `TwoSumVisualProfile` |
| `algoviz/render/components/assembler.py` | `VisualAssembler`、`AssemblyResult`、`VisualAssemblyError` |
| `tests/test_m3_4_assembly.py` | 7 个 M3-4 测试 |
| `M3_4_IMPLEMENTATION_REPORT.md` | 本报告 |

### 修改

| 文件 | 改动 |
|---|---|
| `algoviz/render/components/__init__.py` | 导出 Assembler 相关类型 |
| `algoviz/render/two_sum_visuals.py` | 通过 Profile 获取 VisualPlan；通过 Assembler 创建/mount 组件；不再手动创建组件或定义 options |
| `output/m2/...` | 函数版/类版 M2 产物重新生成 |

### 未修改

- M1 `ExecutionTrace` / `ExecutionEvent` / `SemanticOperation`；
- M1/M2 `AnimationTrace` / `VisualState`；
- `two_sum_scene.py`；
- `two_sum_planner.py`；
- `html_player.py`；
- `visuals.py`；
- `pipeline.py`；
- 旧 18 个 tracer；
- 组件内部算法边界。

## 3. TwoSumVisualProfile

`algoviz/teaching/two_sum_profile.py` 提供：

- `build_visual_plan() -> VisualPlan`；
- `project_variables(state, step) -> list[VariableRow]`；
- `component_options()`（测试/调试用）。

### 组件配置

| component_id | kind | slot | options |
|---|---|---|---|
| `array` | `ARRAY` | `array` | 标题、数组名、target、active pointer、found/empty 文案 |
| `hash_map` | `HASH_MAP` | `hash_map` | 标题、key/value 列名、最大行、空状态、hit/miss/waiting |
| `variables` | `VARIABLES` | `variables` | 标题、最大行、空状态、note |
| `code` | `CODE` | `code` | 标题、窗口 14、行号 |

### 布局表达

Profile 使用 0..1 `LayoutBox`，由原 Manim 布局换算：

| 组件 | 原 center / size |
|---|---|
| array | `(-2.0, 1.55)` / `8.2 × 1.85` |
| hash_map | `(-4.75, -0.95)` / `4.2 × 2.35` |
| variables | `(-0.45, -0.95)` / `4.2 × 2.35` |
| code | `(5.2, -0.2)` / `3.7 × 5.5` |

Profile 源文件不直接导入 Manim/Scene、不创建 Manim 对象、不读取 ExecutionTrace/AnimationTrace、不绑定 TestCase/CaseRun。它通过通用 `VariableRow` 类型和独立投影层工作。

### 变量投影

Profile 调用：

`algoviz/teaching/two_sum_variables.py::project_two_sum_variables`

Two Sum 的 `i/x/need/target/seen.size/返回` 仍留在独立投影层，不进入 `VariableVisualizer`。

## 4. VisualAssembler

`VisualAssembler.assemble(plan, host, base_context, state) -> AssemblyResult`：

1. 遍历 `VisualPlan.components`；
2. 检查 `component_id` 唯一；
3. 检查 `component.slot` 存在于 `plan.slots`；
4. 检查 Registry 是否注册 `ComponentKind`；
5. 用 `ComponentContext(area=slot)` 创建组件；
6. 调用 `registry.create(...)`；
7. 调用 `component.mount(host, context, state)`；
8. 返回：

```python
AssemblyResult(
    components={"array": ..., "hash_map": ..., "variables": ..., "code": ...},
    specs={...},
    slots={...},
    contexts={...},
)
```

### 错误处理

- 缺失 Registry 注册项：`VisualAssemblyError`；
- 非法 slot：`VisualAssemblyError`；
- 重复 component_id：`VisualAssemblyError`（同时 VisualPlan 模型也会校验）；
- 工厂返回错误 kind：Registry 报错，装配器包装为 `VisualAssemblyError`；
- `AssemblyResult.get("missing")`：`VisualAssemblyError`。

Assembler 不包含任何 `two_sum` 分支，不导入 Manim、Scene 或 TeachingPlan。

## 5. TwoSumStage 改造

`TwoSumStage` 现在：

1. 持有 `TwoSumVisualProfile`；
2. 调用 `profile.build_visual_plan()`；
3. 构造基础 `ComponentContext`；
4. 调用 `VisualAssembler.assemble(...)`；
5. 从 `AssemblyResult.components` 取四个组件；
6. 保留 `array_visualizer/hash_visualizer/variable_visualizer/code_visualizer` 别名供现有测试和场景使用；
7. 在 `play_step()` 中分发状态/步骤；
8. 变量更新使用 `profile.project_variables(...)`；
9. 保留 `SceneHost` 窄接口和 `cleanup`。

`TwoSumStage` 中已不再出现：

- `ComponentSpec`；
- `ComponentKind`；
- 四个组件的 options 字典；
- 四个组件的布局计算。

布局、options 与变量投影由 Profile 提供。

## 6. 实际测试结果

```text
pytest -q
85 passed
```

分解：

- 旧算法与旧功能：43；
- M1：9；
- M2：8；
- M3-2：8；
- M3-3：10；
- M3-4：7。

M3-4 测试：

```text
test_profile_builds_four_component_plan_and_projects_variables
test_profile_does_not_import_manim_or_scene
test_assembler_creates_and_mounts_all_components
test_assembler_rejects_unregistered_kind_and_bad_lookup
test_visual_plan_rejects_duplicate_ids_and_unknown_slots
test_stage_uses_profile_and_assembler_not_manual_component_factory
test_stage_source_has_no_component_specs_or_options
```

旧 18 算法回归：

```text
pytest -q tests/test_tracers.py
25 passed
```

M1/M2 联合回归：

```text
pytest -q tests/test_m1_execution.py tests/test_m2_teaching.py
17 passed
```

## 7. M2 重新生成

已运行：

```powershell
.\.venv\Scripts\python.exe scripts\m2_two_sum.py --forms function,class --output-root output/m2
```

实际时长：

- 函数版：overview 75.71s，step_by_step 126.48s；
- 类版：overview 75.76s，step_by_step 126.53s。

实际 QC：

- 1920×1080；
- 30 FPS；
- H.264 + AAC；
- 两个形态 overview/step_by_step 均 `ok=true`。

产物路径：

- `output/m2/two_sum_function/overview.mp4`
- `output/m2/two_sum_function/step_by_step.mp4`
- `output/m2/two_sum_function/interactive.html`
- `output/m2/two_sum_function/teaching_plan.json`
- `output/m2/two_sum_class/overview.mp4`
- `output/m2/two_sum_class/step_by_step.mp4`
- `output/m2/two_sum_class/interactive.html`
- `output/m2/two_sum_class/teaching_plan.json`
- `output/m2/summary.json`

## 8. 关键帧对比

修改前：

- `output/m3_4/before/function_step6.png`
- `output/m3_4/before/function_step7.png`
- `output/m3_4/before/class_step6.png`
- `output/m3_4/before/class_step7.png`

修改后：

- `output/m3_4/after/function_step6.png`
- `output/m3_4/after/function_step7.png`
- `output/m3_4/after/class_step6.png`
- `output/m3_4/after/class_step7.png`

人工检查：

- 数组、索引、指针、当前元素一致；
- `seen` 哈希表 `2 → 0`、`HIT`；
- 变量 `i/x/need/target/seen.size` 一致；
- 代码面板位置、行号、高亮一致；
- step 7 返回 `[0, 1]`、数组 0/1 绿色；
- 类版使用类版代码行号。

实际像素差异：

| 形态 | 全图 mean | 代码面板 mean |
|---|---|---|
| function step6 | 0.000 | 0.000 |
| function step7 | 0.000 | 0.000 |
| class step6 | 0.000 | 0.000 |
| class step7 | 0.000 | 0.000 |

本轮关键帧达到零像素差异；M3-4 的 Profile/Assembler 改造没有改变这几个关键画面。

## 9. 边界确认

| 问题 | 结论 |
|---|---|
| VisualPlan 是否真正参与实例化 | **是**，Assembler 遍历 plan.components 并调用 Registry |
| TwoSumStage 是否仍手动创建四个组件 | **否**，只从 AssemblyResult 取别名并分发 |
| Registry 是否真正被调用 | **是**，`VisualAssembler` 调用 `registry.create` |
| Profile 是否包含算法专属变量投影 | **是**，调用 `project_two_sum_variables` |
| M1/M2 协议是否兼容 | **是**，未修改 |
| 是否新增 Manim 耦合 | Assembler/Profile 源文件不直接导入 Manim；Stage 仍是唯一 Manim 场景适配层 |

## 10. 已实现 / 已验证 / 仅设计

### 已实现

- `TwoSumVisualProfile`；
- `VisualAssembler`；
- Profile 提供四组件 VisualPlan；
- Stage 通过 Assembler 获取组件；
- 组件更新/状态分发；
- M3-4 独立测试。

### 已测试

- 85 个完整测试；
- 7 个 M3-4 测试；
- M3-3/M3-2/M2/M1 既有测试；
- 18 算法回归。

### 已验证产物

- 函数版/类版 M2 四个 MP4；
- 两个 HTML；
- 两个 TeachingPlan；
- M3-4 前后关键帧。

### 仅设计，未实现

- 完整 Profile 体系；
- 多用例 CaseRun；
- PlaybackController；
- 教师控制/自动播放；
- 教学提示；
- HTML 组件化；
- 通用 LessonScene；
- 第二算法；
- Tree/Graph/DP/CallStack；
- Docker 生产沙箱。

## 11. 已知限制

1. `TwoSumStage` 仍硬编码四个 component_id 用于别名/分发，但不再创建组件或定义 options。
2. `VisualPlan` 仍由 Two Sum Profile 静态生成，没有通用 Profile 注册表。
3. `TwoSumVisualProfile` 的 options 仍包含 Two Sum 展示标签；这是 Profile 的合法职责，不在通用组件中。
4. `VisualAssembler` 只负责创建/mount，不负责章节和时间轴。
5. 没有多测试用例、教师播放器、HTML 组件化。
6. 组件测试使用 FakeHost/FakeScene，不等同于完整产品验收。
7. 本轮不保证零像素视觉一致，只保证结构和状态一致。

## 12. 后续计划

| 阶段 | 目标 |
|---|---|
| M3-5 | 多测试用例与真实 trace 切换 |
| M3-6 | 教师控制 + 自动演示 |
| M3-7 | 教学提示与课堂提问 |
| M3-8 | HTML 组件化与课堂交互 |
| M3-9 | 第二算法 Profile 验证 |

本轮完成后停止，等待阶段审查，不自动进入 M3-5。
