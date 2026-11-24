# M3 实施报告：VisualPlan 协议与 CodeVisualizer 抽取

> 本轮范围严格限制为 **M3-1 + M3-2**。  
> 没有实现课堂播放器、多测试用例、通用 LessonScene、Array/HashMap/Variable 组件、HTML 组件化或第二个算法 Profile。

## 1. 实际完成结论

| 项目 | 状态 |
|---|---|
| M3-1 VisualPlan / LayoutBox / ComponentSpec / ComponentContext / SceneHost / VisualComponent / Registry | **已实现、已测试** |
| M3-2 `CodeVisualizer` 抽取 | **已实现、已测试、已实际渲染验证** |
| TwoSumStage 委托 CodeVisualizer | **已实现** |
| M2 函数版/类版产物重新生成 | **已完成** |
| M2 关键帧前后对比 | **已完成** |
| 通用 LessonScene / 课堂播放器 / 多用例 | **未实现，仅设计** |

修改前基线：

```text
pytest -q
60 passed
```

修改后：

```text
pytest -q
68 passed
```

新增 8 项 M3 测试。

## 2. 新增 / 修改文件

### 新增

| 文件 | 内容 |
|---|---|
| `algoviz/protocol/visual.py` | `ComponentKind`、`LayoutBox`、`ComponentSpec`、`VisualPlan` |
| `algoviz/render/components/__init__.py` | 默认组件注册表，注册 `CODE` |
| `algoviz/render/components/base.py` | `ComponentContext`、`SceneHost`、`VisualComponent` |
| `algoviz/render/components/registry.py` | `ComponentRegistry`、注册/查找/创建与异常 |
| `algoviz/render/components/code.py` | `CodeWindow`、`CodeVisualizer` |
| `tests/test_m3_components.py` | 8 个 M3 协议/Registry/CodeVisualizer/Stage 集成测试 |
| `M3_IMPLEMENTATION_REPORT.md` | 本报告 |

### 修改

| 文件 | 改动 |
|---|---|
| `algoviz/render/two_sum_visuals.py` | 删除内嵌代码面板绘制；通过 `ComponentContext` + Registry 创建 `CodeVisualizer`；增加窄 `SceneHost` 方法；`play_step` 委托代码更新 |
| `M2` 产物 | 函数版、类版 `overview.mp4`、`step_by_step.mp4`、`interactive.html`、`teaching_plan.json` 重新生成 |

### 未修改

- `algoviz/protocol/events.py`；
- `algoviz/protocol/execution.py`；
- `algoviz/protocol/m2.py`；
- `algoviz/teaching/two_sum_planner.py`；
- `algoviz/teaching/html_player.py`；
- `algoviz/render/two_sum_scene.py`；
- `algoviz/render/visuals.py`；
- `algoviz/pipeline.py`；
- 旧 18 个 tracer；
- M1/M2 字段语义。

## 3. M3-1 已实现接口

### 3.1 `protocol/visual.py`

- `ComponentKind`：`array`、`hash_map`、`code`、`variables`、`tree`、`graph`、`dp_table`、`call_stack`、`custom`。
- `LayoutBox`：0..1 归一化坐标，原点在左下角；校验 `x+width <= 1`、`y+height <= 1`。
- `ComponentSpec`：`component_id`、`kind`、`slot`、`title`、`options`；`options` 只放视觉配置。
- `VisualPlan`：组件列表 + 槽位表 + 主题；校验：
  - `component_id` 唯一；
  - 每个 `component.slot` 必须存在于 `slots`；
  - `slot` 名不能为空。

### 3.2 `components/base.py`

- `ComponentContext`：
  - `area: LayoutBox`；
  - `theme`、`cn_font`、`code_font`；
  - `language`、`code`；
  - `frame_width`、`frame_height`；
  - `manim_box()` 负责把归一化框换算为 Manim 坐标。
- `SceneHost`：只暴露 `add/remove/play/wait/bring_to_front`，不依赖完整 Manim `Scene`。
- `VisualComponent`：`mount / update / unmount`，输入只有 `VisualState`、`AnimationStep`、`ComponentContext`。

### 3.3 `components/registry.py`

`ComponentRegistry` 支持：

- `register(kind, factory, replace=False)`；
- 重复注册报错，`replace=True` 覆盖；
- `get(kind)`；
- `create(kind, **kwargs)`，并校验工厂返回对象的 `kind`；
- `unregister`、`has`、`kinds`、`in`、`len`；
- 未知组件类型抛 `UnknownComponentError`。

默认注册表只注册 `ComponentKind.CODE -> CodeVisualizer`，没有为未来组件提前造空实现。

## 4. M3-2 CodeVisualizer

### 4.1 独立能力

`CodeVisualizer` 独立实现：

1. 显示源代码；
2. 显示行号；
3. 按 `AnimationStep.code_line` 高亮当前行；
4. 代码窗口；
5. 当前行不在窗口时自动重算窗口；
6. 语言标题 `CODE · python`；
7. 字体、颜色、行号、窗口大小、标题通过 Context/options 配置；
8. 不读取 `VisualState.array/dict_state/variables`，不导入 `ExecutionTrace`、`SemanticOperation`、Two Sum adapter/planner。

`CodeWindow` 是纯 Python 窗口逻辑，可独立测试：

```python
CodeWindow(line_count=30, size=10).visible(25)  # (19, 29)
CodeWindow(line_count=30, size=10).visible(30)  # (20, 30)
```

### 4.2 TwoSumStage 委托方式

`TwoSumStage` 仍保留原代码面板槽位：

```text
x = 5.2
width = 3.7
top = 2.55
bottom = -2.95
```

把它换算为归一化 `LayoutBox` 后交给 `CodeVisualizer`。`CodeVisualizer.manim_box()` 再换回原来的 Manim 坐标，因此位置、宽度、行号、字体、行高和高亮颜色不变。

`TwoSumStage` 新增窄 `SceneHost` 方法：

```python
add / remove / play / wait / bring_to_front
```

`CodeVisualizer` 通过这组方法访问场景，不接触 `M2Scene` 或完整 Scene 生命周期。

`TwoSumStage` 不再保留：

- `_build_code_panel`
- `_render_code_window`
- `highlight_code`
- `_code_*` 面板字段

数组、哈希表、变量逻辑仍在 `TwoSumStage`，符合本轮边界。

## 5. 测试结果

```text
pytest -q
68 passed
```

分解：

- 旧算法与旧功能：43；
- M1：9；
- M2：8；
- M3 新增：8。

M3 测试：

```text
test_layout_box_is_normalized_and_bounded
test_visual_plan_checks_unique_ids_and_slots
test_registry_register_lookup_create_and_errors
test_code_window_boundaries_and_auto_scroll
test_code_visualizer_highlights_without_full_scene
test_code_visualizer_language_title_and_unmount
test_code_component_source_has_no_algorithm_semantics
test_two_sum_stage_delegates_code_panel
```

这些测试：

- 不实例化完整 Manim Scene；
- 使用 `FakeHost`/`FakeScene` 记录 `add/remove/play/wait`；
- 直接验证代码窗口、高亮位置、自动滚动和 Stage 委托；
- 静态检查 `code.py` 不含 `two_sum` / `seen` / `need` / ExecutionTrace 语义。

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

## 6. M2 重新生成与视觉回归

### 6.1 重新生成

已运行：

```powershell
.\.venv\Scripts\python.exe scripts\m2_two_sum.py --forms function,class --output-root output/m2
```

函数版：

- `trace_two_sum_function_9d966b1a`；
- `overview.mp4` 75.71s；
- `step_by_step.mp4` 126.48s；
- QC `ok=true`。

类版：

- `trace_two_sum_class_a457aeac`；
- `overview.mp4` 75.76s；
- `step_by_step.mp4` 126.53s；
- QC `ok=true`。

两个形态均重新生成 `interactive.html`、`teaching_plan.json`、`manifest.json` 和 SRT。

### 6.2 关键帧对比

改造前关键帧：

- `output/m3/before/function_step6.png`
- `output/m3/before/function_step7.png`
- `output/m3/before/class_step6.png`
- `output/m3/before/class_step7.png`

改造后关键帧：

- `output/m3/after/function_step6.png`
- `output/m3/after/function_step7.png`
- `output/m3/after/class_step6.png`
- `output/m3/after/class_step7.png`

全图 / 代码面板区域 RGB 平均差异：

| 形态 | 全图 mean | 代码面板 mean |
|---|---|---|
| function step 6 | 0.020 / 0.018 / 0.034 | 0.078 / 0.070 / 0.135 |
| function step 7 | 0.017 / 0.017 / 0.036 | 0.048 / 0.050 / 0.134 |
| class step 6 | 0.010 / 0.011 / 0.024 | 0.036 / 0.038 / 0.094 |
| class step 7 | 0.017 / 0.016 / 0.041 | 0.068 / 0.064 / 0.164 |

差异来自 H.264 重编码与抗锯齿，不是布局/文本/高亮结构变化。人工检查：

- 代码面板位置、宽度、行号、字体、行高一致；
- step 6 高亮第 5 行；
- step 6 哈希 `2 → 0`、`HIT`；
- step 7 高亮第 6 行，数组 0/1 绿色，变量/返回结果正确；
- 类版使用类版代码行号（step 6 第 6 行），没有错用函数版行号。

文件大小与旧版有差异（函数版 overview/stepwise 从约 7.2/10.4 MB 变为约 6.6/9.5 MB；类版约 6.7/9.7 MB），原因是抽取后去掉了每步对同一高亮矩形重复执行的无效 `set_fill` 动画，并重新编码；时长、布局和关键帧内容保持。

## 7. 课堂辅助模式设计说明（未实现）

本轮不实现课堂播放器，但 M3-1/M3-2 的协议为后续预留了边界。

### 7.1 教师控制模式

未来需要一个只操作“指针”的控制器：

```python
class PlaybackController:
    step_index: int
    mode: Literal["teacher", "auto"]
    def next(self): ...
    def prev(self): ...
    def seek(self, step_id: int): ...
    def pause(self): ...
    def resume(self): ...
    def set_speed(self, speed: float): ...
```

教师控制和自动演示共享：

- 同一个 `Trace`；
- 同一个 `AnimationStep.state_before/state_after`；
- 同一个 `step_index`；
- 同一个 `VisualState` 重建逻辑。

自动模式只是定时推进 `step_index`；暂停/速度改变只影响计时，不生成新执行逻辑。

### 7.2 多测试用例

未来建议新增：

```python
class CaseSource(str, Enum):
    USER = "user"
    AI_SUPPLEMENTED = "ai_supplemented"

class TestCaseSpec(StrictModel):
    case_id: str
    input: dict[str, Any]
    expected_output: Any
    source: CaseSource
    note: str = ""

class CaseRun(StrictModel):
    case_id: str
    execution_trace_id: str
    execution_file: str
    animation_file: str
    verified: bool
```

切换用例时必须：

1. 根据 `case_id` 加载对应 `CaseRun`；
2. 加载该用例的 `ExecutionTrace` 和 `AnimationTrace`；
3. 重置 `step_index`；
4. 用新 trace 的 `steps` 重建播放器/场景。

不能只替换输入文本后继续播放旧 trace。

### 7.3 教学提示

未来 `StepHint` 按 `step_id` 关联：

```python
class StepHint(StrictModel):
    step_id: int
    principle: str
    pitfall: str
    question: str
```

它属于教学层，不属于视觉组件；组件只显示当前状态。

### 7.4 与现有协议的关系

- `VisualPlan` 描述组件与槽位，不描述用例；
- `AnimationTrace` 才是每个用例的执行事实；
- `TeachingPlan` 是教学编排，不是执行逻辑；
- 课堂控制只改播放指针，不改 trace；
- 多用例是 `CaseRun` 层，不塞进 `VisualState`。

## 8. 本轮已实现 / 已测试 / 已验证 / 仅设计

### 已实现

- M3-1 协议与 Registry；
- `CodeWindow` / `CodeVisualizer`；
- `TwoSumStage` 代码面板委托；
- 窄 `SceneHost`；
- 默认代码组件注册。

### 已测试

- 68 个完整测试通过；
- 8 个 M3 单元/集成测试；
- M2 的 8 个测试；
- 18 算法 25 个 tracer 测试；
- M1 9 个测试。

### 已实际验证产物

- 函数版 M2 两个 MP4、HTML；
- 类版 M2 两个 MP4、HTML；
- M2 QC 分辨率、时长、音轨、关键帧；
- 改造前后关键帧截图。

### 仅完成设计

- 教师控制/自动演示控制器；
- 多测试用例 `TestCaseSpec` / `CaseRun`；
- 教学提示 `StepHint`；
- 通用 LessonScene；
- Array/HashMap/Variable 组件抽取；
- HTML 组件化；
- 第二算法 Profile。

## 9. 已知限制

1. `VisualPlan` 目前只是协议，**尚未被 `TwoSumScene` 使用**；TwoSumStage 仍是固定布局的 composer。
2. `ComponentRegistry` 已实际用于 `CODE`，但还没有通用 Scene 按 plan 批量实例化。
3. 数组、哈希表、变量仍是 `TwoSumStage` 内部实现，没有抽取。
4. `TwoSumStage` 仍直接接收完整 Manim scene，只是通过窄 host 方法把 CodeVisualizer 隔离。
5. 没有课堂播放器、多用例、教学提示、HTML 组件 registry。
6. `CodeVisualizer` 目前只支持 Python 代码高亮，没有语言解析/语法着色；语言标题可配置，但不是语法高亮器。
7. 没有 Tree/Graph/DP/CallStack 组件；没有提前造空接口。
8. 视频重新编码导致文件大小变化；关键帧结构检查通过，但不是严格的 zero-pixel diff。
9. 测试只证明组件和 M2 回归，不等同于完整产品验收。

## 10. 后续计划

| 阶段 | 目标 | 前置条件 |
|---|---|---|
| M3-3 | ArrayVisualizer / HashMapVisualizer / VariableVisualizer | M3-1/M3-2 本报告审查通过 |
| M3-4 | TwoSumVisualProfile + VisualPlan 装配 | M3-3 组件稳定 |
| M3-5 | 多测试用例管理与真实 trace 切换 | CaseRun 协议、UI 控制器 |
| M3-6 | 教师控制 + 自动演示 | M3-5 trace 切换稳定 |
| M3-7 | 教学提示 / 课堂提问 | 教学计划扩展 |
| M3-8 | HTML 组件化与课堂交互整合 | 视觉计划稳定 |
| M3-9 | 第二个算法 Profile 验证 | 不新增 tracer，复用现有组件 |

本轮不自动进入下一阶段。建议先审查：
- `VisualPlan` 是否需要引入 `CaseRun` 级别的绑定；
- `CodeVisualizer` 是否保持当前“无语法解析、仅行级高亮”的范围；
- 是否批准 M3-3 抽取 Array/HashMap/Variable。
