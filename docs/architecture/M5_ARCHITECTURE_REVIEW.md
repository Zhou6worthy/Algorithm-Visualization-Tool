# M5 架构审查与第二算法选择

## 1. 审查结论（基于实际源码）

### 1.1 是否已有通用 AlgorithmProfile 注册机制？

**没有。** 当前有 `TwoSumVisualProfile`，但它只负责 Two Sum 的 VisualPlan 和变量投影。执行链路上仍然是：

- `M1Executor.run_two_sum()`；
- `TwoSumSemanticTracer`；
- `TwoSumTraceAdapter`；
- `CaseRunner` 对 `nums/target` 和 `two_sum` 入口的硬编码；
- `WorkbenchRunService` 对 `two_sum` 的显式判断；
- `build_classroom_deck()` 默认使用 Two Sum 提示和 Profile。

需要新增一个最小 AlgorithmProfile 注册层，把执行适配、语义适配、变量投影、VisualPlan、提示和输入解析放在算法侧。

### 1.2 SemanticAdapter 是否可以独立接入？

**结构上可以，执行器接入还不可以。** `TwoSumTraceAdapter` 已经是独立类，`ExecutionTrace` 与 `AnimationTrace` 也是分离的；但 `M1Executor` 在编排中固定创建 Two Sum 的 semantic tracer 和 trace adapter。需要把“轨迹生成”参数化，而不重写 M1 的采集、沙箱和静态分析。

### 1.3 VisualPlan 是否真正控制前端装配？

**只控制了一部分。** 后端 VisualPlan 有组件、槽位和配置；前端 `App.vue` 实际仍硬编码了 Array/HashMap/Variable/Code 四块，并且只读取了组件标题。没有 Vue Component Registry，也没有按 VisualPlan 动态 `v-for` 装配组件。

### 1.4 前端是否存在 Two Sum 中心硬编码？

**存在。**

- 初始示例、算法下拉和示例源码都是 Two Sum；
- 视觉区固定为 array/hash_map/variables/code 四块；
- 布局类的 `array-panel`、`hash-panel`、`code-panel` 是固定 DOM；
- 变量投影由后端 `step_views` 提供，但前端没有按 Profile 改变组件集合。

通用组件本身没有读取 `i/x/need`，这一点是好的；问题在工作台装配层。

### 1.5 接入新算法是否必须改大量核心代码？

如果不改造，需要改：Executor、CaseRunner/Service、TraceAdapter、ClassroomDeck builder、StepHint builder、前端布局。  
因此 M5 需要做最小范围扩展：算法侧 Profile + 通用执行入口 + ClassroomDeck 接收 Profile + 前端动态组件注册。

### 1.6 AnimationTrace 是否足以表达不同算法？

**基本足够。** `VisualState` 已包含 array、tree、graph、matrix、dict、variables，`ArrayState` 已有 `active_range`、`pointers`、`target`、`found_indices`。本阶段无需改动 Trace 协议。需要新增的是“如何从 ExecutionTrace 生成这些状态”的 adapter。

### 1.7 教学提示是否与算法语义解耦？

**模型解耦，生成器未解耦。** `StepHint` 是通用协议；`build_two_sum_hints` 是 Two Sum 专属；`build_classroom_deck` 默认调用它。需要让 Profile 提供自己的提示生成器。

### 1.8 Python PlaybackController 与 Vue 播放器职责是否清晰？

**清晰。** Python `PlaybackController` 服务 Python/Manim 侧；Vue `usePlayback` 拥有自己的 `stepIndex` 和 timer。两者消费同一种 `AnimationTrace` 语义，但不共享运行时实例。M5 不需要把 Python 播放器塞进浏览器。

## 2. 第二算法选择：二分查找

### 为什么选择二分查找

1. 它需要真实循环、真实分支和真实边界收缩，不是只按数组值渲染。
2. 视觉状态与 Two Sum 明显不同：
   - 没有哈希表；
   - 需要 `left/right/mid` 指针；
   - 需要 `active_range` 搜索区间；
   - 命中时返回下标，未命中时返回 `-1`。
3. 可以新增独立的 `SearchRangeView`，验证 VisualPlan 真的能改变组件组合，而不是只复用 ArrayView。
4. 比 BFS/图算法所需的新执行语义、图组件、队列组件和布局改造成本低，适合作为“第二算法纵向闭环”的第一验证。
5. 它仍然能复用已验证的 Array / Variables / Code 组件和 M1 GenericTrace。

### 不选择的候选

- **BFS/DFS**：需要新的图状态、队列/栈组件和更复杂的输入协议，超出本轮最小验证。
- **链表反转**：需要节点/边组件，当前前端没有；改造成本高。
- **排序**：需要比较/交换语义和大规模数组布局，价值高但不是最小验证。
- **Two Sum 的变体**：不算第二算法，不能验证 Profile 扩展。

## 3. 最小改造方案

### 后端

新增：

- `algoviz/algorithms/profile.py`：最小 AlgorithmProfile 注册表；
- `algoviz/algorithms/two_sum_profile.py`：把现有 Two Sum 能力包装为 Profile；
- `algoviz/algorithms/binary_search_profile.py`：二分查找 Profile；
- `algoviz/execution/binary_search_semantic.py`：二分查找 Semantic Tracer；
- `algoviz/execution/binary_search_trace_adapter.py`：ExecutionTrace → AnimationTrace；
- `algoviz/execution/profile_case_runner.py`：统一调用 Profile 的 CaseRunner；
- `algoviz/teaching/binary_search_hints.py`：二分查找教学提示。

扩展：

- `M1Executor`：新增通用 `run_function()`；`run_two_sum()` 保持兼容并调用同一执行管线；
- `ClassroomDeck` builder：接收 AlgorithmProfile，不再固定使用 TwoSumProfile/TwoSum hints；
- Workbench service：按 `problem.algorithm` 从注册表取 Profile；
- `ComponentKind`：新增 `SEARCH_RANGE`；
- 前端：动态 VisualPlan 组件注册与 `SearchRangeView`。

不修改：

- M1 GenericTrace 采集；
- M2 TeachingPlan / 视频流水线；
- M3 VisualPlan / 组件协议的语义；
- M3-8 离线 HTML；
- 旧 18 个 tracer。

### 前端

新增：

- `frontend/src/components/registry.ts`：kind → Vue 组件；
- `frontend/src/components/VisualHost.vue`：按 ComponentSpec 渲染并传统一上下文；
- `frontend/src/components/SearchRangeView.vue`；
- `frontend/src/components/UnknownView.vue`：未知 kind 明确错误。

修改：

- `App.vue`：用 `v-for` 按 `deck.visual_plan.components` 渲染；
- 算法下拉和示例数据增加二分查找；
- 测试用例数据仍为通用 JSON input。

### 验收重点

- 二分查找真实执行、独立适配、Profile 注册；
- VisualPlan 的组件集合在 Two Sum 与二分查找间不同；
- Vue 注册表按 kind 动态装配；
- 二分查找拥有自己的 StepHint；
- 真实浏览器完成创建、执行、播放、切换、刷新，并回到 Two Sum 验证。
