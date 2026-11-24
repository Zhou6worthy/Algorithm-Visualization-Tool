# M5 实施报告：第二算法纵向闭环与 VisualPlan 动态装配

> 本轮完成 M5：在不破坏 Two Sum 的前提下，新增二分查找的完整执行、语义适配、Profile 注册、VisualPlan 动态组件、GUI 多用例执行、课堂播放与教学提示。  
> 未进入 M6，未实现第三个算法、自动识别、AI Profile/用例生成、TTS 或 Java/C++。

## 1. 文件树与清理结果

本轮先清理了工程目录，再开始 M5 开发。

### 根目录

```text
algoviz/          Python 后端
frontend/         Vue 3 + TypeScript + Vite 工作台
tests/            pytest 测试
scripts/          回归、演示、Edge E2E 脚本
docs/             需求、架构审查、历史报告、M5 报告
output/           生成产物与回归证据（gitignore）
.venv/            本地 Python 环境（gitignore）
.env              本地配置/密钥（gitignore，未读取/展示）
.env.example
.gitignore
readme.md         唯一的产品级 README
pyproject.toml
requirements.txt
```

### docs

```text
docs/
  README.md
  project_brief.md
  research_notes.md
  architecture/
    M5_ARCHITECTURE_REVIEW.md
    M3_ARCHITECTURE.md
    PROJECT.md
  requirements/
    M5.md
    M3_5.md
  reports/
    M1_REPORT.md
    M2_REPORT.md
    M3_IMPLEMENTATION_REPORT.md
    M3_3_IMPLEMENTATION_REPORT.md
    M3_4_IMPLEMENTATION_REPORT.md
    M3_5_IMPLEMENTATION_REPORT.md
    M3_6_TO_M3_8_IMPLEMENTATION_REPORT.md
    M4_IMPLEMENTATION_REPORT.md
    M5_IMPLEMENTATION_REPORT.md
  legacy/tasks/
    demo.json / polish.json / retry.json
```

### 实际清理

- 将根目录历史报告与需求移入 `docs/`；
- 根目录只保留一份产品级 `readme.md`；
- 删除 `research/vendor/` 外部克隆与 `media/` 临时 SVG；
- 删除 `algoviz.egg-info/`、`.pytest_cache/`、`__pycache__/`；
- 删除旧 `output/jobs/`、`output/videos/`、`output/_m2_gl/`、旧 GUI 截图和旧 SQLite；
- 删除 M2 `render/`、`audio/`、`qc/`、WAV 中间音频，只保留最终 MP4/HTML/JSON/SRT 回归证据；
- 删除 `_m5_probe.py` 等临时调试文件；
- 保留 M2/M3/M4/M5 回归证据和截图。

### Git 基线建议

当前项目**仍不是 Git 仓库**（`git status` 返回 `fatal: not a git repository`）。本轮没有擅自执行 `git init` 或破坏性 Git 操作。

建议后续：

```powershell
git init
git add readme.md pyproject.toml requirements.txt .env.example .gitignore algoviz frontend tests scripts docs
git status
# 确认后建立 M5 baseline commit
```

`.gitignore` 已覆盖：

- `.env`
- `.venv/`
- `frontend/node_modules/`
- `frontend/dist/`
- `output/`
- `__pycache__/`、`*.py[cod]`
- `.pytest_cache/`
- `media/`
- `*.log`

注意：`algoviz/api/static/workbench/` 是可直接由 FastAPI 提供的前端生产构建产物；若希望仓库只保留源码，可改为发布时构建，但当前“一条命令启动”的体验依赖该目录。

## 2. 架构审查（完整版见 docs/architecture/M5_ARCHITECTURE_REVIEW.md）

M4 的真实问题：

1. 没有通用 AlgorithmProfile 注册机制；
2. `M1Executor.run_two_sum` 固定 Two Sum semantic/trace adapter；
3. `CaseRunner` 固定 `nums/target` 和 `two_sum` 入口；
4. `ClassroomDeck` builder 默认 Two Sum hints/profile；
5. `WorkbenchRunService` 显式拒绝 `algorithm != two_sum`；
6. Vue 视觉区固定 Array/HashMap/Variable/Code 四块，VisualPlan 只被读取了标题；
7. 算法示例和算法下拉以 Two Sum 为主；
8. Python PlaybackController 与 Vue 播放器职责清晰，但没有第二算法 Profile。

## 3. 第二算法选择：二分查找

选择二分查找，而不是简单的 Two Sum 变体：

- 真实用户代码需要循环、分支、边界移动和提前返回；
- 视觉状态是 `[left, right]` 区间、mid 指针和每轮缩半；
- 不需要哈希表，需要新的 `SEARCH_RANGE` 组件；
- 可验证 VisualPlan 从 4 个固定组件切换为不同组件组合；
- 比图/树算法所需的新执行协议、图组件和布局改造更小，适合作为第一纵向验证。

不选择 BFS/链表/排序，因为本轮要求最小范围第二算法，而不是一次扩展多个视觉体系。

## 4. 实际数据链路

```text
Vue GUI 输入
  → POST /api/v1/workbench/projects/{id}/runs
  → WorkbenchRunService
  → AlgorithmProfile 注册表
  → ProfileCaseRunner
  → M1Executor.run_function()
  → LocalSandbox + GenericTrace（真实执行）
  → BinarySearchSemanticTracer / TwoSumSemanticTracer
  → ExecutionTrace
  → BinarySearchTraceAdapter / TwoSumTraceAdapter
  → AnimationTrace
  → AlgorithmProfile.build_visual_plan()
  → VisualPlan
  → build_classroom_deck()
  → ClassroomDeck（StepHint + step_views）
  → FastAPI JSON
  → Vue VisualHost + Component Registry
  → 按 kind 渲染 Array / SearchRange / Variables / Code
  → Vue usePlayback / PlaybackControls
```

Python `PlaybackController` 继续服务 Python/Manim 侧；浏览器使用 `usePlayback`，两者共享同一套语义，但不共享运行时实例。

## 5. 后端实现

### 5.1 新增

| 文件 | 职责 |
|---|---|
| `algoviz/algorithms/profiles.py` | 最小 AlgorithmProfile / Registry；Two Sum + 二分查找注册 |
| `algoviz/execution/profile_case_runner.py` | Profile 驱动的多 case 真实执行 |
| `algoviz/execution/binary_search_semantic.py` | 二分查找 Semantic Tracer |
| `algoviz/execution/binary_search_trace_adapter.py` | ExecutionTrace → AnimationTrace |
| `algoviz/teaching/binary_search_hints.py` | 二分查找课堂提示 |
| `algoviz/teaching/binary_search_visual_profile.py` | 二分查找 VisualPlan + 变量投影 |

### 5.2 修改

| 文件 | 改动 |
|---|---|
| `algoviz/execution/orchestrator.py` | 新增通用 `run_function()`；`run_two_sum()` 委托同一管线；新增 `M1TraceAdapterError` |
| `algoviz/workbench/service.py` | 从 Profile Registry 取算法，不再硬编码 two_sum |
| `algoviz/teaching/classroom.py` | ClassroomDeck 接收 AlgorithmProfile；保留 TwoSumVisualProfile 兼容回退 |
| `algoviz/protocol/visual.py` | 新增 `ComponentKind.SEARCH_RANGE` |
| `algoviz/protocol/hints.py` | 新增二分查找 HintKind |
| `algoviz/algorithms/__init__.py` | 导出 Profile Registry |

### 5.3 Profile 能力

每个 Profile 提供：

- 算法 key / title / category；
- SemanticAdapter 工厂；
- TraceAdapter 工厂；
- 输入解析；
- 函数/类版入口；
- VisualPlan；
- 变量投影；
- StepHint 生成器。

两个已注册 Profile：

```text
two_sum       → array, hash_map, variables, code
binary_search → array, search_range, variables, code
```

未注册算法由 WorkbenchRunService 明确标记 run failed；未产生伪轨迹。

### 5.4 二分查找语义

`BinarySearchSemanticTracer` 基于真实事件、AST 分支/循环和局部变量证据生成：

- INIT：区间 `[left, right]`；
- VISIT：`mid` 与 `nums[mid]`；
- COMPARE：命中 / 小于 / 大于；
- POINTER_MOVE：left/right 实际变化；
- RETURN / COMPLETE。

`BinarySearchTraceAdapter` 把这些操作转换为：

- `active_range`；
- `left/right/mid` pointers；
- `found_indices`；
- 二分查找变量行；
- 课堂步骤描述。

若只有 generic line、没有可识别语义，adapter 明确失败；ProfileCaseRunner 返回 ERROR，不生成伪造 AnimationTrace。

## 6. 前端动态组件装配

### 新增

- `frontend/src/components/registry.ts`
- `frontend/src/components/VisualHost.vue`
- `frontend/src/components/SearchRangeView.vue`
- `frontend/src/components/UnknownView.vue`
- `frontend/src/components/registry.test.ts`

### 修改

- `App.vue`：不再固定渲染四块视觉面板，而是：

```vue
<VisualHost
  v-for="spec in deck.visual_plan.components"
  :spec="spec"
  :step="currentStep"
  :view="currentStepView"
  :code="currentCode"
/>
```

- 组件 kind 到 Vue 组件的映射集中在 registry：
  - `array` → `ArrayView`
  - `hash_map` → `HashMapView`
  - `variables` → `VariableView`
  - `code` → `CodeView`
  - `search_range` → `SearchRangeView`
- 未知 kind → `UnknownView`，显示明确错误而不是静默空白；
- `ArrayView` 根据 `active_range` 将区间外元素弱化；
- `SearchRangeView` 显示当前 `[left, right]`、候选数量和 left/right/mid；
- App 增加二分查找算法选项、示例源码和 6 个示例用例；
- `source_style` 标签随算法切换。

真实浏览器截图显示：

- 二分查找组件：`array / search_range / variables / code`；
- Two Sum 组件：`array / hash_map / variables / code`；
- 两个算法切换后 DOM 组件集合随之改变。

## 7. 测试报告

### 7.1 pytest

```text
pytest -q
119 passed
```

M5 新增 8 项：

```text
tests/test_m5_binary_search.py
  test_profiles_register_two_algorithms_and_distinct_visual_plans
  test_binary_search_real_trace_has_range_pointers_and_hints
  test_binary_search_mismatch_invalid_and_independent_cases
  test_binary_search_execution_exception_is_case_error
  test_binary_search_trace_adapter_rejects_unsupported_source
  test_binary_search_classroom_deck_uses_profile_hints_and_views
  test_binary_search_workbench_api_end_to_end
  test_unsupported_algorithm_run_fails_clearly
```

覆盖：

- Profile 注册与不同 VisualPlan；
- 二分查找真实执行；
- 多 case 独立 CaseRun/trace；
- 命中、未命中、空数组；
- 不匹配；
- 输入错误；
- 代码执行异常；
- 语义适配失败不伪造 AnimationTrace；
- 不支持的算法 run failed；
- ClassroomDeck、StepHint、step_views；
- 后端 API 端到端。

既有 M1/M2/M3/M4 测试全部保留，未删除、未跳过、未降低断言。

### 7.2 前端 unit / typecheck / build

```text
npm run test:unit  → 2 tests passed
npm run typecheck  → passed
npm run build      → passed
```

Vitest 覆盖：

- registry 含 array/hash_map/variables/code/search_range；
- 未注册 kind 返回 null，UI 可显示明确错误。

构建产物：

```text
algoviz/api/static/workbench/
```

仅保留常规 chunk 体积警告（约 582KB / gzip 199KB，主要来自 CodeMirror）。

### 7.3 真实浏览器 E2E

脚本：`scripts/m5_browser_check.py`

环境：真实 FastAPI、独立 SQLite、headless Edge 158 + CDP。

```text
27 checks passed
7 screenshots
0 JavaScript errors
elapsed 14.78s
```

真实流程：

1. 打开 GUI；
2. 通过 GUI 创建二分查找示例项目；
3. 确认 6 个测试用例、源码、算法下拉；
4. 编辑项目名和 CodeMirror 源码；
5. 保存；
6. 从 GUI 发起真实执行；
7. 6 个用例全部成功；
8. 动态组件集合为 array/search_range/variables/code；
9. 数组、区间、mid、target、代码行和提示同步；
10. 手动下一步到 mid、再上一步回初始化；
11. 时间轴跳到命中步骤；
12. 展开参考答案；
13. 自动播放推进、暂停、继续；
14. 2× 速度；
15. 播放中切换二分查找用例；
16. 新用例从 step 0 开始，旧 timer 不推进；
17. 刷新页面，项目/最近 run/动态组件恢复；
18. 注入未知组件 kind，显示明确错误态；
19. 通过 GUI 新建并填入 Two Sum 示例，保存并执行；
20. Two Sum 使用 hash_map，不出现 search_range；
21. 后端持久化两个算法项目；
22. 二分查找 Run/CaseRun/ClassroomDeck 完整；
23. 独立 execution trace；
24. 0 浏览器错误。

机器结果：

- [browser_check.json](../../output/m5/browser_check.json)

### 7.4 M4 回归

重新运行 M4 E2E：

```text
33 checks passed
6 screenshots
0 JavaScript errors
```

M4 的 Two Sum 创建、编辑、多用例执行、播放、切换、刷新全部仍通过。

### 7.5 M3-8 回归

重新生成 M3-8 classroom demo，并重跑：

```text
37 checks passed
7 screenshots
0 external HTTP(S) requests
```

### 7.6 M2 MP4 回归

实际运行：

```powershell
.\.venv\Scripts\python.exe scripts\m2_two_sum.py --forms function,class --output-root output/m2
```

| 形态 | overview | step_by_step | QC |
|---|---|---|---|
| 函数版 | 75.71s | 126.48s | true |
| 类版 | 75.76s | 126.53s | true |

关键帧 vs M3-5 后基线：

```text
mean RGB diff = [0.0, 0.0, 0.0]
diff bbox = null
```

证据：[m2_regression.json](../../output/m5/m2_regression.json)

## 8. 真实使用截图

- [01 二分查找项目 · VisualPlan](../../output/m5/screenshots/01_binary_project.png)
- [02 真实执行 · 搜索区间](../../output/m5/screenshots/02_binary_execution.png)
- [03 命中步骤 · 教学提示](../../output/m5/screenshots/03_binary_hint.png)
- [04 切换二分用例 · step 0](../../output/m5/screenshots/04_binary_case_switch.png)
- [05 刷新恢复 · 动态组件](../../output/m5/screenshots/05_binary_after_refresh.png)
- [06 回到 Two Sum · hash_map](../../output/m5/screenshots/06_two_sum_regression.png)
- [07 未知组件 · 明确错误](../../output/m5/screenshots/07_unknown_component.png)
- [关键截图拼图](../../output/m5/screenshots/contact_sheet.png)

![Binary Search 动态装配](../../output/m5/screenshots/02_binary_execution.png)

![Two Sum 回归](../../output/m5/screenshots/06_two_sum_regression.png)

## 9. 已实现 / 已测试 / 已浏览器验证 / 未实现

### 已实现

- 二分查找真实执行；
- 二分查找独立 Semantic Tracer / Trace Adapter；
- AlgorithmProfile 最小注册机制；
- ProfileCaseRunner；
- VisualPlan `SEARCH_RANGE`；
- Vue Component Registry / VisualHost / SearchRangeView；
- 未知组件错误态；
- 算法项目切换；
- 二分查找课堂提示；
- 二分查找 GUI 多用例执行；
- 刷新恢复。

### 已自动化测试

- 119 个 pytest；
- 8 个 M5 后端测试；
- 2 个前端 registry unit test；
- 前端 typecheck/build；
- M3-8 37 项浏览器回归；
- M4 33 项浏览器回归。

### 已真实浏览器验证

- 二分查找 GUI 项目创建、编辑、保存；
- 真实执行 6 用例；
- 动态组件组合；
- 搜索区间、mid、变量、代码行；
- 单步、跳转、自动播放、暂停、速度；
- 切换用例与 timer 隔离；
- 刷新恢复；
- 未知组件错误；
- 回到 Two Sum。

### 未实现

- 第三个算法；
- 自动识别算法；
- AI 自动生成 Profile / VisualPlan / 测试用例；
- 实时 LLM 教学提示；
- TTS；
- Java/C++；
- Docker 生产沙箱；
- 账号/权限/协作/云部署；
- M6 及以后。

## 10. 已知限制与安全边界

1. 当前只支持 Two Sum 和 Binary Search 两个算法，不是通用算法平台。
2. AlgorithmProfile 注册表是最小机制，没有插件发现、热加载或版本管理。
3. 前端算法示例和少量 UI 选项仍包含两个算法的显式数据；执行、语义适配和视觉装配没有在组件里写 `if algorithm == ...`。
4. VisualPlan 动态选择组件和标题；布局仍由 CSS 的 `data-slot` 规则承担。新增一个全新 slot 可能需要相应布局样式。
5. 测试用例输入仍是通用 JSON 文本，不是每种算法的专用表单。
6. `LocalSandbox` 只适合本机可信代码；不是生产级隔离。监听 `127.0.0.1` 不等于代码安全。
7. SQLite 是本地持久化，单 worker 执行队列；服务重启不会续跑进行中的 run。
8. 前端单元测试目前只覆盖 Component Registry；播放行为主要由真实浏览器 E2E 覆盖。
9. 浏览器 E2E 只在 Windows Edge 验证，未做跨浏览器矩阵。
10. M2 视频工厂仍保留在原 `/legacy` 与脚本中，未整合进新工作台 UI。
11. M3-8 离线课堂 HTML 与 Vue Renderer 是两套前端渲染，共享后端 ClassroomDeck 语义，不共享 DOM。

## 11. 阶段结论

1. **第二算法是否完成完整端到端闭环？**  
   **是。** 二分查找从 GUI 输入、真实执行、SemanticAdapter、AnimationTrace、Profile/VisualPlan、ClassroomDeck、Vue 动态组件到教师播放与刷新恢复全部跑通。

2. **是否真正实现了基于 Profile / VisualPlan 的组件动态装配？**  
   **是。** Vue Registry + VisualHost 按 `visual_plan.components` 的 kind 装配；Two Sum 显示 hash_map，二分查找显示 search_range；未知 kind 有明确错误态。

3. **接入新算法是否仍需修改大量核心代码？**  
   **不需要大规模修改。** 新增算法主要提供 Profile、Semantic Adapter、Trace Adapter、Visual Profile、提示生成器；M1 只增加通用执行入口。本次没有重写 M2、M3-8 或前端播放状态机。

4. **是否证明当前架构具备初步多算法扩展能力？**  
   **是，范围限定在已实现的两个算法和现有组件体系内。** 第三个算法需要自己的语义、组件和样式，但不需要复制 Two Sum 的执行/播放逻辑。

5. **当前是否适合进入下一阶段？**  
   **可以进入下一阶段的功能设计与审查，但前提是继续把 LocalSandbox 当成本机可信代码工具，而不是生产级多用户代码执行服务。** 若下一阶段开放外部用户提交代码，必须优先完成真实执行隔离。

M5 完成，停止，不自动进入 M6。
