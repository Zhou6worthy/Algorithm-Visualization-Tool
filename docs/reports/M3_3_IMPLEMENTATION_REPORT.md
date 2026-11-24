# M3-3 实施报告：Array / HashMap / Variable 组件抽取

> 本轮只完成 M3-3。  
> 未实现 TwoSumVisualProfile 完整体系、VisualPlan 批量装配、通用 LessonScene、多测试用例、课堂播放器、HTML 组件化、第二算法或新 Tracer。

## 1. 实际完成结论

| 项目 | 状态 |
|---|---|
| ArrayVisualizer | **已实现、已测试、已实际渲染** |
| HashMapVisualizer | **已实现、已测试、已实际渲染** |
| VariableVisualizer + VariableRow | **已实现、已测试、已实际渲染** |
| Two Sum 变量投影独立层 | **已实现** |
| Registry 注册 ARRAY / HASH_MAP / VARIABLES / CODE | **已实现** |
| TwoSumStage 组件组合化 | **已实现** |
| M2 函数版/类版重新生成 | **已完成** |
| 关键帧前后对比 | **已完成** |
| 完整课堂播放器/多用例/Profile | **未实现，仅设计** |

修改前基线：

```text
pytest -q
68 passed
```

修改后：

```text
pytest -q
78 passed
```

新增 M3-3 测试 10 项。

## 2. 新增 / 修改文件

### 新增

| 文件 | 内容 |
|---|---|
| `algoviz/render/components/array.py` | `ArrayVisualizer` |
| `algoviz/render/components/hash_map.py` | `HashMapVisualizer` |
| `algoviz/render/components/variables.py` | `VariableRow`、`VariableVisualizer` |
| `algoviz/render/components/primitives.py` | 通用卡片/文本 primitive |
| `algoviz/teaching/two_sum_variables.py` | Two Sum 专用变量投影（非组件） |
| `tests/test_m3_3_components.py` | 10 个 M3-3 测试 |
| `M3_3_IMPLEMENTATION_REPORT.md` | 本报告 |

### 修改

| 文件 | 改动 |
|---|---|
| `algoviz/render/components/__init__.py` | 默认 Registry 注册 ARRAY / HASH_MAP / VARIABLES / CODE |
| `algoviz/render/two_sum_visuals.py` | `TwoSumStage` 改为固定布局组合器；删除数组/哈希/变量/代码直接绘制逻辑；变量通过独立投影层 |
| `output/m2/...` | 函数版/类版 M2 产物重新生成 |

### 未修改

- M1 `ExecutionTrace` / `ExecutionEvent` / `SemanticOperation`；
- M1/M2 `AnimationTrace` / `VisualState` 协议；
- `two_sum_scene.py`；
- `two_sum_planner.py`；
- `html_player.py`；
- `visuals.py`；
- `pipeline.py`；
- 旧 18 个 tracer；
- `CodeVisualizer` 的既有接口和视觉实现。

## 3. M3-3.1 ArrayVisualizer

`ArrayVisualizer` 消费：

- `VisualState.array`；
- `AnimationStep.state_before/state_after`；
- `ComponentContext`；
- options。

实现：

- 数组元素显示；
- 所有索引显示；
- 指针展示（任意 pointer 名称，不只 i）；
- 当前元素高亮（`active_pointer` option，默认 `i`）；
- `found_indices` 高亮；
- 空数组状态；
- 状态变化时更新值、指针、found；
- 卡片样式/字体/颜色来自 context/options。

组件不包含：

- 补数；
- 查找；
- 循环；
- Two Sum 文案；
- 算法正确性判断。

空数组、索引、指针、found、值更新均有独立测试。

## 4. M3-3.2 HashMapVisualizer

`HashMapVisualizer` 消费：

- `VisualState.dict_state`；
- `AnimationStep`；
- options。

实现：

- 多个 key/value 显示；
- 当前查询 key；
- `lookup_status` 的 hit/miss 展示；
- `highlighted` 条目高亮；
- 新增/更新条目高亮（通过比较 step.state_before/after 的通用 entry diff，不涉及题目的业务规则）；
- 空哈希表；
- 最大显示行数；
- 标题、列标题、空状态、hit/miss 文案均可配置。

组件不包含 `seen`、`need`、`target`、Two Sum 查询/插入规则或返回逻辑。

## 5. M3-3.3 VariableVisualizer

### 通用展示数据

```python
@dataclass(frozen=True)
class VariableRow:
    label: str
    value: str
    changed: bool = False
```

`VariableVisualizer` 只负责：

- 变量名称；
- 变量值；
- changed 颜色；
- 空状态；
- 最大行数。

它不包含 `i`、`x`、`need`、`target`、`seen.size`、`return`。

`set_rows(rows)` 是组件接收投影数据的入口；`update(step, duration)` 不猜测算法变量。

### Two Sum 投影

新增 `algoviz/teaching/two_sum_variables.py`：
`project_two_sum_variables(state, step) -> list[VariableRow]`。

Two Sum 的 `i/x/need/target/seen.size/返回` 全部在投影层生成，组件只显示 Generic `VariableRow`。

## 6. TwoSumStage 组合化

`TwoSumStage` 现在只负责：

1. 创建 Array/HashMap/Variable/Code 四个组件；
2. 将原有固定布局换算为 `LayoutBox`；
3. 将当前 `VisualState/AnimationStep` 分发给组件；
4. 管理组件在现有布局槽位中的位置；
5. 实现窄 `SceneHost` 方法。

它不再直接绘制：

- 数组；
- 哈希表；
- 变量卡片；
- 代码面板。

原有布局槽位保持：

- 数组：center `(-2.0, 1.55)`，width `8.2`，height `1.85`；
- 哈希表：center `(-4.75, -0.95)`，width `4.2`，height `2.35`；
- 变量：center `(-0.45, -0.95)`，width `4.2`，height `2.35`；
- 代码：center `(5.2, -0.2)`，width `3.7`，height `5.5`。

## 7. 默认注册表

`default_registry` 现在注册：

- `ARRAY -> ArrayVisualizer`
- `HASH_MAP -> HashMapVisualizer`
- `VARIABLES -> VariableVisualizer`
- `CODE -> CodeVisualizer`

没有注册 Tree / Graph / DP_TABLE / CALL_STACK 空组件。

## 8. 测试结果

```text
pytest -q
78 passed
```

构成：

- 旧算法与旧功能：43；
- M1：9；
- M2：8；
- M3-2：8；
- M3-3：10。

M3-3 测试：

```text
test_array_visualizer_builds_values_pointers_and_found
test_array_visualizer_empty_and_update
test_hash_visualizer_hit_miss_and_multiple_entries
test_hash_visualizer_empty_and_new_entry
test_variable_visualizer_generic_rows_changed_and_empty
test_variable_visualizer_max_rows
test_default_registry_has_m3_components_and_no_future_empty_components
test_two_sum_projection_is_separate_from_variable_component
test_component_sources_do_not_contain_two_sum_semantics
test_two_sum_stage_composes_all_components
```

独立测试使用 `FakeHost` / `FakeScene`，不依赖完整 Manim Scene。

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

## 9. M2 重新生成

已运行：

```powershell
.\.venv\Scripts\python.exe scripts\m2_two_sum.py --forms function,class --output-root output/m2
```

实际结果以 `output/m2/summary.json` 和两个 `manifest.json` 为准：

- 函数版 `trace_two_sum_function_9d966b1a`：overview 75.71s、step_by_step 126.48s；
- 类版 `trace_two_sum_class_a457aeac`：overview 75.76s、step_by_step 126.53s；
- 两个形态都重新生成 overview / step_by_step / interactive.html / teaching_plan.json / SRT；
- QC 分辨率、时长、AAC 音轨、关键帧非空白全部为 true。

## 10. 关键帧对比

修改前：

- `output/m3_3/before/function_step6.png`
- `output/m3_3/before/function_step7.png`
- `output/m3_3/before/class_step6.png`
- `output/m3_3/before/class_step7.png`

修改后：

- `output/m3_3/after/function_step6.png`
- `output/m3_3/after/function_step7.png`
- `output/m3_3/after/class_step6.png`
- `output/m3_3/after/class_step7.png`

人工检查：

- 数组元素/索引/指针/当前元素与旧版一致；
- seen 哈希表 `2 → 0`、`HIT`；
- 变量 `i/x/need/target/seen.size` 与旧版一致；
- 代码面板位置/行号/高亮一致；
- step 7 数组 0/1 绿色、返回 `[0, 1]`；
- 类版使用类版行号。

全图差异均值约 `0.15–0.16`，代码面板区域差异约 `0.01`；差异来自 Manim 重新绘制、文本抗锯齿和 H.264 重编码，不是布局或状态变化。详细数值见最终报告与截图像素对比。

## 11. 已实现 / 已验证 / 仅设计

### 已实现

- 三个通用组件；
- 通用变量行模型；
- Two Sum 变量投影层；
- Registry 注册；
- TwoSumStage 组合化；
- 独立测试。

### 已测试

- 78 个完整测试；
- 10 个 M3-3 测试；
- 8 个 M3-2 测试；
- 8 个 M2 测试；
- M1 9 个；
- 18 算法 25 个 tracer 测试。

### 已验证产物

- 函数版/类版 M2 四个 MP4；
- 两个 HTML；
- 两个 TeachingPlan；
- M3-3 前后关键帧。

### 仅完成设计

- TwoSumVisualProfile 完整体系；
- VisualPlan 批量组件装配；
- 通用 LessonScene；
- 多测试用例；
- PlaybackController；
- 教师控制/自动演示；
- HTML 组件化；
- 第二算法；
- Tree/Graph/DP/CallStack；
- Docker 生产沙箱。

## 12. 已知限制

1. `VisualPlan` 仍未接入 `TwoSumScene`；当前 TwoSumStage 是固定布局组合器。
2. `TwoSumStage` 仍由 Two Sum 专用 options 配置标题/文案；组件不包含算法语义。
3. `VariableVisualizer` 的 `set_rows` 是投影入口，`update` 本身不推导变量。
4. 没有完整 Profile 体系；变量投影暂时独立在 `two_sum_variables.py`。
5. 没有多用例、课堂播放器、HTML 组件化。
6. 组件测试使用 FakeHost，不等同于完整产品验收。
7. 视频大小变化来自重新渲染/编码和绘制顺序，不是算法状态变化。
8. 本轮没有实现 Tree/Graph/DP/CallStack 空组件。

## 13. 后续计划

| 阶段 | 目标 |
|---|---|
| M3-4 | TwoSumVisualProfile + VisualPlan 装配 |
| M3-5 | 多测试用例与真实 trace 切换 |
| M3-6 | 教师控制 + 自动演示 |
| M3-7 | 教学提示与课堂提问 |
| M3-8 | HTML 组件化与课堂交互 |
| M3-9 | 第二算法 Profile 验证 |

本轮完成后停止，等待阶段审查，不自动进入 M3-4。
