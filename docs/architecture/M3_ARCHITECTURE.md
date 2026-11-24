# M3 前置架构审查：从 Two Sum 专用可视化到通用组件

> 本文件是**架构分析与最小修改方案**，不是“已经实现通用组件库”的声明。  
> 本轮不重构 M1/M2 代码；已实现、未实现和计划项在文中明确区分。

## 0. 结论摘要

当前 M2 已经把“真实执行事实 → AnimationTrace → 教学计划 → MP4/HTML”跑通，但 Two Sum 的**视觉表达、布局、变量选择和教学文案**仍然集中在三个文件里：

- `algoviz/render/two_sum_visuals.py`：布局 + 数组 + 哈希表 + 变量 + 代码，一个 `TwoSumStage` 全包；
- `algoviz/render/two_sum_scene.py`：场景时间轴 + 教学段落 + Two Sum 公式/复杂度卡片；
- `algoviz/teaching/two_sum_planner.py`：Five-section 计划 + Two Sum 旁白 + 复杂度统计。

正确方向不是“再写一个算法就再写一个 Stage”，而是：

```text
M1 ExecutionTrace / AnimationTrace（事实）
        ↓
AlgorithmSemanticAdapter（算法语义 → 统一 Trace）
        ↓
AlgorithmProfile（选择组件、布局、变量投影、教学素材）
        ↓
LessonPlanner（时间轴、旁白、分组）
        ↓
SceneDirector / HTMLPlayer（组件组合与播放）
```

其中**组件只消费 `VisualState`/`AnimationStep`**，不读取 `ExecutionTrace`，不感知 Two Sum、seen、need 等算法语义。

最小落地顺序建议：

1. 只新增协议 + 组件 skeleton（不改变输出）；
2. 先抽取 `CodeVisualizer`（最纯、风险最低）；
3. 再抽取 `ArrayVisualizer` + `HashMapVisualizer` + `VariableVisualizer`；
4. 用 `TwoSumVisualProfile` 组合这些组件，保留 `TwoSumScene`；
5. 通过回归和 golden frame 后，才讨论通用 `LessonScene`；
6. 下一个算法只写 Adapter + Profile，不写新 Stage。

## 1. 当前 M2 组件耦合分析

### 1.1 `two_sum_visuals.py`

| 现状 | 位置 | 可复用性 | 问题 |
|---|---|---|---|
| 卡片背景/标题/分隔线 | `_card`，104–126 | 高 | 通用 UI primitive，却被包在 Two Sum Stage 内 |
| 小标签 pill | `_pill`，128–139 | 高 | 通用 UI primitive |
| 数组卡片 | `_build_array_card`，159–195 | 中高 | 读取 `state.array`，但标题 `数组 nums`、当前元素文案、固定坐标、固定 target 位置都硬编码 |
| 数组高亮/指针 | `_paint_array` / `_refresh_pointers`，197–251 | 高 | 基本只依赖 `ArrayState.pointers`、`found_indices`、`target`；可以独立 |
| 哈希表卡片 | `_build_hash_card` / `_make_dict_body`，254–309 | 中高 | 依赖 `DictState`，但标题 `哈希表 seen`、`key → index`、`HIT/MISS`、`等待下一次查找`、最多 4 行都硬编码 |
| 变量卡片 | `_build_vars_card` / `_make_vars_body`，312–363 | 低 | 硬编码 `i/x/need/target/seen.size`、`返回`、数组指针回退逻辑；这是 Two Sum 业务 |
| 代码面板 | `_build_code_panel` / `_render_code_window` / `highlight_code`，366–444 | 高 | 通用代码高亮；但位置、宽度、`CODE · python`、14 行窗口硬编码 |
| 状态更新合并 | `_apply_state`，453–480 | 低 | 一次更新 Array、Dict、Vars、Count；没有组件接口 |
| 单步动画 | `play_step`，482–489 | 低 | Stage 直接调用 scene.play/wait，动画节奏和场景时间轴耦合 |

结论：

- **数组、代码、哈希表的视觉主体可以抽取**；
- **变量卡片的大部分内容是 Two Sum profile 的投影**，不是通用组件；
- `TwoSumStage` 本质是“固定布局的专用组合器”，不是组件；
- 组件直接持有 `scene`，并在内部 `play/wait`，会让未来 `SceneComposer` 很难控制节奏。

### 1.2 `two_sum_scene.py`

| 部分 | 位置 | 责任 | 评价 |
|---|---|---|---|
| Header / subtitle / section label | 84–153 | 通用场景 chrome | 可以进 `LessonDirector` |
| `_ensure_stage` | 172–184 | 直接实例化 `TwoSumStage` | 与算法绑定 |
| `_show_steps` | 187–206 | 消费 `SectionTimeline` 和真实 step | 基本通用，但强依赖 `TwoSumStage` |
| `_show_idea` | 209–261 | Two Sum 公式、哈希表讲解、3 张卡片 | 算法教学素材，应进 Profile/TeachingBlock |
| `_show_complexity` | 269–360 | 固定“哈希表平均 O(1) / seen 峰值”三卡 | 算法指标硬编码，应该由 Profile 提供 metrics |
| `construct` | 363–379 | 固定 `M2SectionKind` handler | 教学导演的雏形，但和 Two Sum 内容混在一起 |

结论：

- `M2Scene` 同时是**教学导演**、**Two Sum 内容模板**、**组件宿主**；
- 未来应该拆成 `LessonDirector`（通用）+ `TwoSumProfile`（算法素材）+ `SceneComposer`（布局）；
- 当前不要一次性重写 `M2Scene`，先把舞台内部组件抽出来，Scene 仅保留段落调度。

### 1.3 `two_sum_planner.py`

| 部分 | 位置 | 是否通用 |
|---|---|---|
| `load_m1_pair` / `file_sha256` / `step_state_digest` / `verify_plan` | 68–84、604–634 | 通用，可提升为 `teaching/trace_guard.py` |
| `_step_narration` | 196–226 | 完全 Two Sum 语义 |
| `build_complexity` | 170–192 | hash-specific：lookups、hits、misses、inserts、seen 峰值 |
| `build_sections` | 229–349 | 固定五段 + Two Sum 文案 + 单步旁白 |
| `_section_timeline` / `build_timelines` | 437–594 | 基本通用（按 section kind 分配时间），但 `M2SectionKind` 固定 |
| `render_plan` | 597–601 | 通用 |
| `verify_plan` | 604–634 | 通用 + stepwise 结构约束 |

结论：

- 时间轴算法可以复用；
- **旁白、复杂度指标、教学素材**必须进 `AlgorithmProfile`；
- `M2SectionKind` 的固定五段对 Two Sum 合理，但不应该成为所有算法的强制结构。

### 1.4 `protocol/m2.py`

- `TeachingPlan.algorithm` 默认 `two_sum`；
- `RenderPlan` docstring 写死 “交给 TwoSumScene”；
- `ObservedComplexity` 字段是 hash-specific：`lookups/hits/misses/inserts/peak_seen`；
- `VideoTimeline` 固定 1920×1080（这是 M2 产品要求，可保留）；
- 没有 `visual_plan` / `ComponentSpec`。

结论：

- M2 协议可以**原样保留**；
- 新增 M3 `protocol/visual.py`，不要让 M1/M2 的旧模型承担通用组件职责；
- `ObservedComplexity` 未来可以增加通用的 `metrics: list[Metric]`，但本轮不做。

### 1.5 `html_player.py`

当前 HTML 已经是“从 trace 重建状态”，方向正确，但仍是 Two Sum 专用 DOM：

- `renderArray` 只处理 `state.array`；
- `renderDict` 只处理 `state.dict_state`；
- `renderVars` 硬编码 `i/x/need/target/seen.size`；
- `renderCode` 硬编码代码面板；
- `renderComplexity` 硬编码 `seen` 指标；
- 标题和布局是 Two Sum。

结论：

- HTML 不需要新的算法执行逻辑；
- 可以复用 M2 的 `state` 数据，但要把四个 render 函数改成**Web Component registry**；
- HTML 的通用化应晚于 Manim 组件边界稳定，避免同时改两套渲染器。

### 1.6 旧 `visuals.py` 与 M2 的关系

旧 `ArrayVisual` / `TreeVisual` / `GraphVisual` / `MatrixVisual` 已经具有“状态驱动”的雏形：

```python
class VisualBase:
    def build(self, state: VisualState, animate: bool = True) -> None: ...
    def step(self, step: AnimationStep, run_time: float) -> None: ...
```

但它们：

- 绑定旧 `AlgoVizScene`；
- 只支持 array/tree/graph/matrix 四种主类型；
- 没有 hash/code/variables；
- 与 `TwoSumStage` 有重复实现。

不建议现在删除旧组件。应该把旧 `ArrayVisual` 视为**迁移来源/兼容实现**，新 `ArrayVisualizer` 逐步替换，旧场景保持可运行。

## 2. 算法语义与视觉的边界

### 2.1 算法语义（必须留在 Adapter/Profile）

这些不是组件逻辑：

- Two Sum 的 `need = target - x`；
- `seen[need]` 查询与 `seen[x] = i` 插入；
- 命中后 `return [seen[need], i]`；
- `seen` 峰值、lookup 次数、命中/未命中；
- “空间换时间”的讲解；
- 哪个 step 是查找、插入、返回。

它们属于：

```text
TwoSumTraceAdapter  （ExecutionTrace → Trace）
TwoSumProfile       （VisualPlan / 变量投影 / 复杂度 metrics / 教学素材）
```

### 2.2 视觉呈现（应该进通用组件）

这些不知道算法名字：

- 给一组 values 和 indexes 画数组；
- 高亮某个 index、显示 pointer chips、显示 found indices；
- 给 key/value 列表画哈希表，显示 lookup key + hit/miss；
- 按 code_line 高亮源码；
- 显示一组 label/value 变量行；
- 根据状态差异做颜色/位置/透明度变化。

### 2.3 教学编排（应该进 LessonPlanner/Director）

- 五段式或未来可配置的 section；
- 旁白段落与 TTS 时长；
- 章节切换、字幕、总时间轴；
- 选择组件、布局槽位、组件顺序。

**组件不负责**选择自己何时出现，也不负责讲解。

## 3. 目标最小架构

```text
ExecutionTrace (M1)
   │
   ├─ AlgorithmSemanticAdapter (已有 TwoSumTraceAdapter)
   │        ↓
   │   AnimationTrace (M1)
   │
   └─ AlgorithmProfile (新)
            ├─ VisualPlan
            ├─ 变量投影 / 教学素材 / 复杂度 metrics
            └─ TeachingPlan sections
                     ↓
Network          LessonPlanner (从 two_sum_planner 提炼)
                     ↓
             RenderPlan (M2 兼容)
                     ↓
        ┌────────────┴────────────┐
   SceneDirector                 HTMLPlayer
   + ComponentRegistry           + WebComponentRegistry
        ↓                              ↓
     MP4                             HTML
```

### 3.1 协议：`algoviz/protocol/visual.py`（计划中）

不修改 `VisualState` / `AnimationStep` / `Trace`。

```python
class ComponentKind(str, Enum):
    ARRAY = "array"
    HASH_MAP = "hash_map"
    TREE = "tree"
    GRAPH = "graph"
    DP_TABLE = "dp_table"
    CODE = "code"
    VARIABLES = "variables"
    CALL_STACK = "call_stack"
    CUSTOM = "custom"


class LayoutBox(StrictModel):
    """0..1 归一化坐标；Manim 和 HTML 各自映射到自己的画布。"""
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)


class ComponentSpec(StrictModel):
    component_id: str
    kind: ComponentKind
    slot: str
    title: str = ""
    options: dict[str, Any] = Field(default_factory=dict)


class VisualPlan(StrictModel):
    schema_version: Literal["0.1"] = "0.1"
    components: list[ComponentSpec]
    slots: dict[str, LayoutBox]
    theme: str = "dark"

    @model_validator(mode="after")
    def _check_slots(self) -> "VisualPlan":
        # 每个 component.slot 必须存在；component_id 不重复
        ...
```

要点：

- `LayoutBox` 用 0..1，避免把 Manim 单位写死；
- `ComponentSpec.options` 是组件配置，不是算法逻辑；
- `VisualPlan` 不知道 `Two Sum`，只描述“画什么、在哪个槽”；
- 旧 `VisualKind` 不改；它仍服务于旧渲染器。

### 3.2 组件协议：`algoviz/render/components/base.py`（计划中）

```python
@dataclass(frozen=True)
class ComponentContext:
    area: LayoutBox              # 已按当前画布换算
    theme: Mapping[str, str]
    cn_font: str
    code_font: str
    language: str = "python"
    code: str = ""


class VisualComponent(Protocol):
    kind: ComponentKind

    def mount(self, host: "SceneHost", ctx: ComponentContext,
              state: VisualState) -> None: ...

    def update(self, step: AnimationStep, duration: float) -> None: ...

    def unmount(self, run_time: float = 0.2) -> None: ...
```

`SceneHost` 是窄接口（`add/remove/play/wait/bring_to_front`），不是完整 Manim `Scene`。组件只通过 Host 操作，避免直接操纵全局场景。

组件规则：

- 只读 `VisualState`/`AnimationStep`/`ComponentContext`；
- 不导入 `ExecutionTrace`、`SemanticOperation`、算法 adapter；
- 不包含 `two_sum`、`seen`、`need` 等业务词；
- 不在组件内决定章节/时间轴；
- 颜色、字体、行高来自 context/options；
- 缺失数据显式空状态，不推断未提供的算法操作。

### 3.3 组件接口细节

#### ArrayVisualizer

```python
options = {
    "title": "数组 nums",
    "show_target": True,
    "pointer_labels": {"i": "i"},
    "show_current": True,
}
```

消费 `state.array`：

- `values`、`sorted_indices`、`active_range`、`pointers`、`target`、`found_indices`、`aux`；
- 只做视觉，不解释“补数”或“区间”。

#### HashMapVisualizer

```python
options = {
    "title": "哈希表 seen",
    "key_header": "key",
    "value_header": "index",
    "max_rows": 4,
    "empty_text": "{}  空哈希表",
    "lookup_labels": {"hit": "HIT", "miss": "MISS"},
}
```

消费 `state.dict_state`：`entries`、`lookup_key`、`lookup_status`、`highlighted_keys`。

#### CodeVisualizer

```python
options = {
    "title": "CODE",
    "window": 14,
    "line_numbers": True,
}
```

消费：

- `ComponentContext.code`；
- `ComponentContext.language`；
- `AnimationStep.code_line`。

这是最纯的组件，不依赖任何算法状态块。

#### VariableVisualizer

```python
options = {"title": "关键变量", "max_rows": 6}
```

消费一组已投影的显示行，而不是直接猜 `i/x/need`：

```python
class VariableRow(StrictModel):
    label: str
    value: str
    changed: bool = False
```

Two Sum 的 `i/x/need/target/seen.size/返回` 由 `TwoSumProfile.project_variables(state, step)` 生成；组件不知道 `seen`。

#### 未来的 Tree/Graph/DP/CallStack

- `TreeVisualizer` 消费 `state.tree`；
- `GraphVisualizer` 消费 `state.graph`；
- `DPTableVisualizer` 消费 `state.matrix`，但只在语义适配器确认它是 DP 时启用；
- `CallStackVisualizer` 需要新增 `call_stack` 状态块；当前 `VisualState` 没有，属于未来。
- 旧 `TreeVisual`/`GraphVisual`/`MatrixVisual` 可作为实现参考，不要求本轮迁移。

### 3.4 算法 Profile

```python
class AlgorithmProfile(Protocol):
    algorithm: str

    def build_visual_plan(self, trace: Trace) -> VisualPlan: ...

    def project_variables(
        self, state: VisualState, step: AnimationStep
    ) -> list[VariableRow]: ...

    def complexity_metrics(
        self, execution: ExecutionTrace, trace: Trace
    ) -> list[Metric]: ...

    def teaching_sections(
        self, execution: ExecutionTrace, trace: Trace
    ) -> list[Section]: ...
```

Two Sum 的 Profile 负责：

- `VisualPlan`：array + hash + variables + code 四个组件和槽位；
- 变量投影：i/x/need/target/seen.size/返回；
- 复杂度 metrics：lookups/hits/misses/inserts/seen peak；
- 教学文案：完整演示、思想、逐步、复杂度、回放。

它不画图，不播放动画。

### 3.5 SceneDirector / LessonPlanner

```python
class SceneDirector:
    def __init__(self, host, registry, plan): ...
    def build(self, visual_plan: VisualPlan) -> None: ...
    def play(self, video: VideoTimeline, trace: Trace) -> None: ...
```

职责：

- 根据 `VisualPlan` 实例化组件；
- 按 `SectionTimeline` 调度；
- 处理字幕、章节、step 时长；
- 不出现 `TwoSumStage` 或“哈希表”等算法词；
- `TwoSumScene` 在迁移期作为它的薄 wrapper，不删除。

`LessonPlanner` 负责 section/时间轴/旁白；它调用 Profile 提供的教学素材与复杂度 metrics。

## 4. Two Sum 迁移方案（最小改动）

### 阶段 0：冻结基线（本轮已完成）

- 现有 M2 产物已生成：函数版/类版各 2 个 MP4、HTML、TeachingPlan；
- 当前回归 `pytest -q` 为 `60 passed`；
- 记录 M2 `trace_id`、视频时长、关键帧作为后续对比基线；
- 不修改 `two_sum_visuals.py`、`two_sum_scene.py`、`two_sum_planner.py`。

### 阶段 1：只加接口，不改渲染

新增：

- `algoviz/protocol/visual.py`
- `algoviz/render/components/base.py`
- `algoviz/render/components/registry.py`

测试：

- `VisualPlan` 槽位/组件校验；
- 组件注册表按 `ComponentKind` 查找；
- 不实例化 Manim，不跑视频。

验收：现有 60 tests 仍通过；M2 产物不变。

### 阶段 2：抽取 `CodeVisualizer`（第一个通用化验证）

- 从 `TwoSumStage` 把代码面板逻辑移到 `components/code.py`；
- `TwoSumStage` 保留代码面板的**槽位**，但内部委托 `CodeVisualizer`；
- 不改变布局、字号、行号、高亮颜色；
- 测试：给定 code + step.code_line，正确高亮、窗口滚动、语言标题；
- 渲染一帧 step 6 与改造前对比；再跑 M2 函数/类回归。

为什么先做 Code：

- 它不依赖 Array/Dict/Variables 的算法状态；
- 旧 18 算法和新 Two Sum 都可以复用；
- 出错时容易定位，风险最低。

### 阶段 3：抽取 `ArrayVisualizer` / `HashMapVisualizer` / `VariableVisualizer`

- `ArrayVisualizer` 以 `state.array` 为唯一输入；
- `HashMapVisualizer` 以 `state.dict_state` 为唯一输入；
- `VariableVisualizer` 以 `list[VariableRow]` 为唯一输入；
- `TwoSumProfile.project_variables` 负责 i/x/need/target/seen.size/return；
- `TwoSumStage` 变成：
  - 固定槽位/布局；
  - 创建 4 个组件；
  - 把 `step` 分发到组件；
  - 不再包含数组/哈希/变量/代码绘制细节。

验收：

- M2 关键帧文字/高亮/哈希状态一致；
- 组件源码不出现 `two_sum` / `seen` / `need`；
- 60 tests + M2 8 tests 通过。

### 阶段 4：引入 `VisualPlan` 与 `TwoSumProfile`

- `TwoSumProfile.build_visual_plan()` 返回 array/hash/vars/code 的 specs 和 slots；
- `TwoSumScene` 的 `_ensure_stage` 改为从 `VisualPlan` 装配组件；
- 仍保留 `M2Scene` 的现有五段调度；
- 教学文案暂不迁移，避免一次改太多。

验收：

- `teaching_plan.json` 增加 `visual_plan`（可选字段）；
- 函数版 + 类版重新生成一次 MP4，关键帧/Qc 通过；
- `overview` / `step_by_step` 时长不因迁移漂移。

### 阶段 5：通用 `LessonScene`（在阶段 4 稳定后再做）

- 抽 header/subtitle/section/timeline 到 `LessonDirector`；
- `M2Scene` 变为 Two Sum wrapper；
- idea/complexity 改为 `TeachingBlock`/Profile 提供的内容；
- 旧 `M2Scene` 保留，作为 canary/fallback。

**这一阶段才需要改 `two_sum_scene.py` 的主体。** 本轮不做。

### 阶段 6：HTML 组件化（最后）

- 把 `renderArray` / `renderDict` / `renderVars` / `renderCode` 变成 `WEB_COMPONENTS` registry；
- 用同一个 `VisualPlan` 决定 DOM 组件与槽位；
- 保持单文件、无后端、无外部依赖；
- 继续从 `AnimationStep.state_after` 重建，不引入第二套执行逻辑。

### 阶段 7：第二个算法验证

- 选 `binary_search` 或 `bubble_sort`，不新增 tracer；
- 只写 `BinarySearchProfile` / `BubbleSortProfile`；
- 复用 `ArrayVisualizer` + `CodeVisualizer` + `VariableVisualizer`；
- 如果必须改组件才能支持，说明组件边界设计失败，先修协议。

## 5. 建议文件结构

```text
algoviz/
  protocol/
    visual.py                    # 新增：VisualPlan / ComponentSpec / LayoutBox
    events.py                    # 保持；只作为统一状态/事件协议
    execution.py                 # 保持；M1 事实
    m2.py                        # 保持；M2 教学计划
  render/
    components/
      __init__.py
      base.py                    # ComponentContext / SceneHost / VisualComponent
      registry.py                # ComponentKind -> factory
      primitives.py              # 卡片、pill、标题等通用 UI
      code.py                    # CodeVisualizer（第一个迁移）
      array.py                   # ArrayVisualizer
      hash_map.py                # HashMapVisualizer
      variables.py               # VariableVisualizer
      # tree.py / graph.py / dp_table.py / call_stack.py  # 未来
    lesson_scene.py              # 未来：通用 SceneDirector
    visual_profiles.py           # 未来：profile registry
    two_sum_visuals.py           # 迁移期 composer；最终可删除
    two_sum_scene.py             # 迁移期 Two Sum wrapper
    visuals.py                   # 旧组件，保持不动
  teaching/
    profiles/
      __init__.py
      base.py                    # AlgorithmProfile / VariableRow / Metric
      two_sum.py                 # TwoSumProfile
    two_sum_planner.py           # 保持；逐步把通用部分移到 planner
    html_player.py               # 阶段 6 再改
tests/
  test_visual_plan.py
  test_visual_components.py
  test_two_sum_profile.py
```

## 6. 测试与回归门槛

每个阶段都必须满足：

1. `pytest -q` 当前 **60 passed** 不回退；
2. M1/M2 现有 17 个测试通过；
3. 旧 18 算法回归 `tests/test_tracers.py` 25 passed；
4. M2 函数版/类版 `teaching_plan.json` 的 `trace_id` 不变；
5. 关键帧人工检查：
   - step 6 代码行、`HIT`、`2 → 0`；
   - step 7 返回 `[0, 1]`、数组 0/1 绿色；
6. 新增组件测试不依赖 Manim 场景：
   - 用真实 `VisualState` 构造；
   - 断言高亮 index、hash 行、变量行、代码行；
7. 静态边界测试：
   - `components/array.py`、`hash_map.py`、`code.py`、`variables.py` 不得出现 `two_sum`/`seen`/`need`；
   - 组件不得 import `execution`/`two_sum_planner`/`two_sum_scene`。

不建议用全像素 diff 作为唯一门槛（字体/抗锯齿会漂移）；用**结构快照 + 关键帧人工/抽样检查 + 视频 QC**。

## 7. 已实现 vs 未来设计（重要）

### 已经实现（当前 M2）

- 真实执行与状态协议：`ExecutionTrace`、`AnimationStep`、`VisualState`；
- Two Sum 语义适配器：`TwoSumTraceAdapter`；
- M2 五段式 `TeachingPlan`；
- `TwoSumStage`：数组 + 哈希表 + 变量 + 代码组合；
- `M2Scene`：Two Sum 视频时间轴、字幕、章节；
- `two_sum_planner.py`：Two Sum 旁白/复杂度/时间轴；
- `two_sum_pipeline.py`、`m2_renderer.py`、`html_player.py`；
- 函数版/类版 MP4 与 HTML，QC 通过；
- 60 个测试通过。

### 只是设计，尚未实现

- `VisualPlan` / `ComponentSpec` / `LayoutBox` 协议；
- 通用 `ComponentRegistry`；
- `CodeVisualizer`、`ArrayVisualizer`、`HashMapVisualizer`、`VariableVisualizer` 的独立实现；
- 通用 `LessonScene` / `SceneDirector`；
- 算法 `Profile` 体系；
- 第二个算法的 Profile；
- Tree/Graph/DP/CallStack 的 M2 通用组件；
- 通用 HTML component registry；
- 自动选择组件、自动布局、自动教学编排；
- 新的算法语义 tracer；
- Docker / M3 生产隔离。

### 已有但与目标不是同一层

- `algoviz/render/visuals.py` 已有 `ArrayVisual`、`TreeVisual`、`GraphVisual`、`MatrixVisual`；
- 它们是旧 `AlgoVizScene` 的状态驱动组件，不是新的 `VisualPlan` 组件；
- 不能直接宣称“通用组件库已经完成”。

## 8. 风险与不做的事

- **不要**直接把 `TwoSumScene` 重写成通用 Scene；先把舞台拆组件。
- **不要**在组件中加 `if algorithm == "two_sum"`。
- **不要**修改 M1 `ExecutionTrace`/`ExecutionEvent` 字段。
- **不要**为了 Tree/Graph/CallStack 提前造一堆空接口。
- **不要**同时改 Manim 和 HTML 两套渲染；先 Manim，后 Web。
- **不要**删除旧 `visuals.py` 和旧 `two_sum_scene.py`；迁移期要能回退。
- 最大风险是 `VisualState` 的“主 kind + 次要块”语义；保持旧 `VisualKind` 不变，由 `VisualPlan` 决定组合，不要强行把 hash/code 塞进 `VisualKind`。

## 9. 最小可执行开发计划

| 阶段 | 修改 | 交付 | 验收 |
|---|---|---|---|
| M3-0 | 本文件 | 架构边界、接口、迁移顺序 | 本轮 60 tests 基线 |
| M3-1 | 新增 `protocol/visual.py`、`components/base.py`、`registry.py` | 协议/registry 单测 | 60 tests + 新增协议测试 |
| M3-2 | 抽取 `CodeVisualizer` | 代码组件 + `TwoSumStage` 委托 | 关键帧一致、M2 回归 |
| M3-3 | 抽取 Array/HashMap/Variables | 3 个组件 + `TwoSumProfile` 变量投影 | 组件单测 + M2 关键帧 |
| M3-4 | `TwoSumVisualProfile` + `VisualPlan` | Two Sum 从 plan 装配组件 | MP4/HTML 重新生成并 QC |
| M3-5 | 通用 `LessonScene` | 仅在 M3-4 稳定后 | 全量回归 + 两形态视频 |
| M3-6 | HTML component registry | 同 plan 驱动 Web | 跳转/状态重建回归 |
| M3-7 | 第二个算法 Profile | 复用 Array/Code/Vars | 无新 Stage、无新 Tracer |

**建议本轮只批准 M3-1 + M3-2**。它们能验证“抽取组件不改变 M2 成品”，风险最小；M3-3 之后再做一次架构复核。

## 10. 直接回答五个审查问题

1. **哪些视觉元素可以抽取？**  
   卡片/pill/文本等 primitive；数组主体；哈希表主体；代码高亮；变量行展示。布局和教学编排不应塞进组件。

2. **数组、哈希表、代码、变量能否独立于 Two Sum？**  
   数组、哈希表、代码基本可以；变量展示可以，但 `i/x/need/target/seen.size` 必须由 `TwoSumProfile.project_variables` 先投影，组件只显示 `VariableRow`。

3. **哪些逻辑属于 Two Sum 特有语义？**  
   `need = target - x`、`seen` 的查找/插入、命中后返回、`seen` 峰值/命中统计、Two Sum 公式和“空间换时间”讲解。它们应留在 Adapter/Profile，不进通用组件。

4. **`TwoSumStage` / `TwoSumScene` 与未来通用 Scene 如何划分？**  
   `TwoSumStage` 迁移为“固定槽位 + 组件组合”的临时 composer；`TwoSumScene` 迁移为 `LessonDirector` 的 Two Sum wrapper。通用 Scene 只负责时间轴/章节/组件调度，不包含 Two Sum 公式或指标。

5. **如何让不同算法消费统一状态/事件？**  
   继续使用 `AnimationStep.state_before/state_after` 和 `VisualState`；组件只读这些字段；算法 Adapter 负责把 ExecutionTrace 变成统一事件；Profile 只做组件选择、布局、变量投影、教学素材和复杂度 metrics；MP4/HTML 都消费同一份 Trace/VisualPlan，不重新实现算法逻辑。
