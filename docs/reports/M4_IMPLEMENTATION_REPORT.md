# M4 实施报告：AI Algorithm Visualizer 前端工作台与后端整合

> 本轮只完成 M4。产品以 Two Sum 为端到端验收算法，未进入 M5 / M3-9。  
> 原有 M1、M2、M3-1～M3-8 能力作为后端基础复用，没有重写执行引擎、AnimationTrace、CaseRunner 或课堂 HTML。

## 1. 实际完成结论

| 交付项 | 状态 |
|---|---|
| 统一前端工作台（Vue 3 + TypeScript + Vite） | **已实现** |
| FastAPI M4 项目 API | **已实现** |
| SQLite 项目 / 题目 / 用例 / Run / CaseRun 持久化 | **已实现** |
| GUI 创建、保存、读取、更新项目 | **已实现** |
| GUI 编辑题目、代码、多个测试用例 | **已实现** |
| GUI 发起真实 Two Sum 执行 | **已实现** |
| 多测试用例独立 CaseRun / ExecutionTrace / AnimationTrace | **已实现** |
| 复用 `ClassroomDeck` / `StepHint` / `VisualPlan` | **已实现** |
| Vue 数组 / 哈希表 / 变量 / 代码组件 | **已实现** |
| 手动播放、自动播放、暂停、继续、时间轴、速度 | **已实现** |
| 课堂提示与参考答案 | **已实现** |
| 刷新页面恢复项目与最近执行 | **已实现、浏览器验证** |
| 真实 headless Edge 端到端测试 | **33 项通过** |
| 完整 pytest | **111 passed** |
| M2 函数版 / 类版 MP4 回归 | **通过，关键帧零差异** |
| M3-8 多用例课堂 HTML 回归 | **通过，37 项浏览器检查** |
| 第二算法 / AI 用例生成 / AI 教学提示 / TTS 课堂旁白 | **未实现** |

## 2. 开发前真实工程核对

检查结果：

- 项目根目录：`D:\work\算法可视化工具`
- **没有 Git 仓库**：`git status` 返回 `fatal: not a git repository`，因此没有分支或提交状态可报告。
- 没有既有 Vue / React / Vite 前端工程；只有 `algoviz/api/static` 下的旧版原生 HTML 视频工厂界面。
- Python 3.12.14，FastAPI 已存在，入口为 `algoviz serve` / `algoviz.api.app:create_app`。
- 系统 PATH 默认 Node 为 v10.16.0；本机另有 `D:\Program_Files_\nvm\v24.19.0`，M4 前端使用 Node 24 构建。
- 已检查并复用：
  - `M1Executor`、`CaseRunner`、`CaseRunStore`；
  - `ExecutionTrace`、`AnimationTrace`、`TwoSumTraceAdapter`；
  - `TwoSumVisualProfile`、`VisualAssembler` 与通用组件；
  - `PlaybackController`、`StepHint`、`ClassroomDeck`；
  - M3-8 离线课堂 HTML；
  - M2 旧 HTML/MP4 流程；
  - 全部现有测试。

实际调用链保持为：

```text
用户 GUI 输入
  → Project / Problem / TestCase（SQLite）
  → POST run
  → CaseRunner（现有 M1 执行引擎）
  → 每个 case 独立 ExecutionTrace
  → TwoSumTraceAdapter
  → 每个 case 独立 AnimationTrace
  → CaseRun
  → build_classroom_deck
  → ClassroomDeck（VisualPlan + StepHint + step_views）
  → Vue Classroom Player
```

## 3. 前后端架构

```text
frontend/ (Vue 3 + TS + Vite)
  App.vue
    ├── Project / problem / test-case editor
    ├── CodeMirror 6 Python editor
    ├── ArrayView / HashMapView / VariableView / CodeView
    ├── TeachingHintPanel
    └── PlaybackControls
          │ HTTP JSON
          ▼
FastAPI
  └── /api/v1/workbench/*
        ├── WorkbenchStore (SQLite)
        └── WorkbenchRunService (ThreadPoolExecutor)
              └── CaseRunner (M1/M3, 现有实现)
                    └── ClassroomDeck (M3, 现有实现)
```

关键职责：

- 前端不执行算法，不生成轨迹，不修改算法事实；
- 前端只消费后端 `AnimationTrace`、`VisualPlan`、`StepHint`、`step_views`；
- 前端播放器有自己的 `step_index`、timer 和播放状态，不调用 Python `PlaybackController`；
- Python `PlaybackController` 继续服务 Python/Manim 侧；
- 后端执行使用项目创建 run 时的不可变快照；
- 一个 case 失败不会清空其他 case 的轨迹；
- 无 trace 的 error case 不伪造 `AnimationTrace`。

## 4. 后端实现

### 4.1 新增模块

| 文件 | 内容 |
|---|---|
| `algoviz/workbench/__init__.py` | 包入口 |
| `algoviz/workbench/models.py` | Pydantic 请求 / 响应模型 |
| `algoviz/workbench/store.py` | SQLite 持久化 |
| `algoviz/workbench/service.py` | 后台真实执行服务 |
| `algoviz/workbench/api.py` | FastAPI router |

### 4.2 数据模型

Pydantic：

- `ProblemPayload`；
- `TestCasePayload`；
- `ProjectPayload`；
- `ProjectSummary`；
- `RunRecord`；
- `CaseRunRecord`；
- `ClassroomEnvelope`。

SQLite 表：

```text
projects
problems
test_cases
runs
case_runs
```

职责区分：

| 表 | 职责 |
|---|---|
| `projects` | 项目 ID / 名称 / 时间 |
| `problems` | 标题、描述、解题思路、源码、语言、算法、代码形态 |
| `test_cases` | 归属项目的可编辑测试用例 |
| `runs` | 一次执行任务、状态、汇总、项目快照、ClassroomDeck JSON |
| `case_runs` | 该 run 内每个用例的 ExecutionTrace / AnimationTrace / 状态 / 输出 |

`runs` 保存创建 run 时的 project/problem/case 快照；之后修改项目不会改变历史执行的语义。

### 4.3 后台执行

`WorkbenchRunService` 使用单 worker `ThreadPoolExecutor`：

1. `POST /runs` 立即创建 `queued` run；
2. 后台线程读取 run 快照；
3. 校验算法/Python/源码；
4. 为每个用例再次通过现有 `CaseRunner` 执行；
5. 生成独立 `CaseRun`；
6. 用 `build_classroom_deck` 生成课堂数据；
7. 保存 `classroom_json` 和每个 `case_runs` 的完整 trace；
8. run 状态变为 `completed`；
9. 执行级异常变为 `failed`，单 case 错误仍保留其他 case 结果。

服务启动时会把遗留的 `queued/running` run 标记为 failed，避免伪运行状态。

### 4.4 API 清单

新增：

```text
GET    /api/v1/workbench/projects
POST   /api/v1/workbench/projects
GET    /api/v1/workbench/projects/{project_id}
PUT    /api/v1/workbench/projects/{project_id}
GET    /api/v1/workbench/projects/{project_id}/runs
POST   /api/v1/workbench/projects/{project_id}/runs
GET    /api/v1/workbench/runs
GET    /api/v1/workbench/runs/{run_id}
GET    /api/v1/workbench/runs/{run_id}/cases
GET    /api/v1/workbench/runs/{run_id}/cases/{case_id}
GET    /api/v1/workbench/runs/{run_id}/classroom
```

页面：

```text
/          → 新 M4 Vue 工作台
/legacy    → 旧版视频工厂 HTML GUI
/static/*  → 新工作台构建产物 + 旧静态资源
```

原有 `/api/v1/algorithms`、`/api/v1/generate`、`/api/v1/jobs`、`/gallery` 等接口保留。

错误处理：

- 项目 / run / case 不存在 → 404；
- 无测试用例、无源码等参数/执行前置错误 → 422；
- run 未完成时请求 classroom → 409；
- run failed → 409 并返回服务端执行错误。

## 5. 前端工作台

### 5.1 前端工程

```text
frontend/
  package.json
  package-lock.json
  vite.config.ts
  tsconfig*.json
  index.html
  src/
    main.ts
    App.vue
    api.ts
    playback.ts
    types.ts
    style.css
    components/
      CodeEditor.vue
      CodeView.vue
      ArrayView.vue
      HashMapView.vue
      VariableView.vue
      PlaybackControls.vue
      TeachingHintPanel.vue
      TestCaseEditor.vue
```

技术：

- Vue 3 Composition API；
- TypeScript；
- Vite；
- CodeMirror 6（Python 语法高亮、行号、可编辑、当前执行行）；
- 无 CDN、无外部字体依赖；
- 生产构建输出到 `algoviz/api/static/workbench/`。

### 5.2 布局

- 顶部导航：产品名、当前项目、新建、保存、执行、导出预留；
- 左侧：题目/思路/源码/CodeMirror/测试用例；
- 中央：数组、哈希表、变量、代码、当前步骤；
- 右侧：执行状态、运行历史、教学提示与参考答案；
- 底部：固定播放控制条。

中央可视化区域是页面视觉重点；左侧和右侧都可以独立滚动。

### 5.3 播放

前端 `src/playback.ts`：

- `loadCase`、`next`、`previous`、`seek`、`reset`；
- `play`、`autoPlay`、`pause`、`resume`、`setSpeed`；
- 同一个 `stepIndex` 服务手动与自动；
- 切换用例取消旧 timer、回到 step 0；
- 旧 timer 通过 token 校验，不能推进新用例；
- 自动播放结束停止；
- 速度 0.5× / 1× / 1.5× / 2×；
- 时间轴直接跳 step；
- 当前步骤对应 `step_views`、`StepHint`、代码行同步。

### 5.4 教学提示

`TeachingHintPanel.vue`：

- 标题；
- 原理解释；
- 常见错误；
- 课堂提问；
- 参考答案展开/收起；
- 切换 step 或 case 时自动收起旧答案；
- 无提示时显示空态。

提示来自后端 `StepHint`，前端不生成算法事实。

## 6. 自动化测试

完整测试：

```text
pytest -q
111 passed
```

本轮 M4 新增 5 项：

```text
tests/test_m4_workbench_api.py
  test_project_crud_persists_and_lists
  test_real_run_generates_independent_case_traces_and_classroom
  test_workbench_runs_leetcode_class_source
  test_run_without_expected_keeps_real_trace_but_is_unverified
  test_api_errors_for_missing_project_and_run
```

覆盖：

- 项目创建、查询、更新、列表；
- 服务重启后 SQLite 项目仍在；
- 多测试用例真实执行；
- case 状态 success / failed / error；
- 独立 ExecutionTrace 与 AnimationTrace；
- ClassroomDeck、VisualPlan、StepHint、step_views；
- 无 expected 时真实执行但 `animation_trace.verified=false`；
- LeetCode 类版源码形态；
- 无效/缺少 target 不生成 trace；
- 空项目执行 422；
- 多次执行记录保留；
- API 404/422 错误。

前端检查：

```text
npm run typecheck
npm run build
```

均通过。Vite 仅提示 CodeMirror 所在 chunk 约 576KB（gzip 约 197KB）的常规体积警告，不作为失败。

完整旧测试未删除、未跳过、未降低断言。

## 7. 真实浏览器端到端测试

脚本：`scripts/m4_browser_check.py`

环境：

- 真实 FastAPI 后端，端口 8766；
- 独立 SQLite 输出目录 `output/m4/e2e_data`；
- headless Microsoft Edge 158，CDP 真实点击/输入/滚动/刷新；
- 生产构建由 FastAPI 提供，不是只看 HTML 字符串。

实际结果：

```text
33 checks passed
6 screenshots
0 JavaScript errors
elapsed 18.22s
```

实际流程：

1. 打开 `/`，确认 Vue 工作台加载；
2. 点击“创建 Two Sum 示例项目”；
3. 确认项目名、题目、代码加载；
4. 编辑项目名/题目；
5. 在 CodeMirror 中真实输入注释；
6. 添加用例、删除用例、再次添加并编辑名称/input/expected；
7. 保存项目；
8. 点击执行，GUI 轮询后端 run；
9. 确认 7 个用例真实执行完成；
10. 第一个用例数组、target、代码行正确；
11. 手动下一步到 miss 步骤；
12. 上一步；
13. 时间轴跳到命中步骤；
14. 查看 HIT、完成返回、代码行、提示；
15. 展开/收起参考答案；
16. 自动播放、暂停、继续；
17. 速度切到 2×；
18. 播放中切到 Case 2，确认 step 0、状态隔离、旧 timer 不推进；
19. Case 2 自动播放、暂停、继续；
20. 切回 Case 1，数组和 target 恢复；
21. 自动播放到末尾停止；
22. 刷新页面；
23. 确认项目、7 个用例、最近执行和课堂可视化恢复；
24. 后端 HTTP 检查项目持久化、run 历史、独立 trace、ClassroomDeck；
25. 确认浏览器无 JS 错误。

后端实际执行结果：

```text
case_count = 7
success    = 5
failed     = 1
error      = 1
trace_count = 6
steps_total = 56
```

其中：

- invalid（缺少 target）没有 trace；
- mismatch 保留真实 trace，但状态 failed；
- 6 个可执行用例具有不同 ExecutionTrace ID 和 AnimationTrace ID；
- 7 个用例对应 7 个 CaseRun 记录；
- ClassroomDeck 包含 7 个 ClassroomCase 和 56 个真实动画步骤。

机器结果：

- [browser_check.json](<../../output/m4/browser_check.json>)

截图：

- [01 初始工作台](<../../output/m4/screenshots/01_welcome.png>)
- [02 题目、代码与测试用例](<../../output/m4/screenshots/02_problem_and_cases.png>)
- [03 真实执行完成](<../../output/m4/screenshots/03_after_execution.png>)
- [04 命中步骤与参考答案](<../../output/m4/screenshots/04_hit_and_hint.png>)
- [05 切换 Case 2](<../../output/m4/screenshots/05_case_switch.png>)
- [06 刷新后恢复](<../../output/m4/screenshots/06_after_refresh.png>)
- [关键截图拼图](<../../output/m4/screenshots/contact_sheet.png>)

## 8. 持久化与运行管理

- 默认数据库：`output/workbench.sqlite3`；
- E2E 数据库：`output/m4/e2e_data/workbench.sqlite3`；
- 项目在服务重启后仍可读取；
- 每个项目保留多次 run；
- UI 右侧显示最近执行历史，可点击加载历史 ClassroomDeck；
- 刷新页面通过 `localStorage` 记住项目 ID，并从服务器读取项目与最近 run；
- run 使用创建时快照，不依赖项目后续修改。

## 9. 与 M1～M3 的兼容性

### 回归测试

```text
pytest -q
111 passed
```

### M2 视频回归

实际运行：

```powershell
.\.venv\Scripts\python.exe scripts\m2_two_sum.py --forms function,class --output-root output/m2
```

| 形态 | overview | step_by_step | QC |
|---|---|---|---|
| 函数版 | 75.71s | 126.48s | true |
| 类版 | 75.76s | 126.53s | true |

关键帧与 M3-5 后基线比较全部：

```text
mean RGB diff = [0.0, 0.0, 0.0]
diff bbox = null
```

证据：[m2_regression.json](<../../output/m4/m2_regression.json>)

M2 产物仍存在：

- [函数版 overview.mp4](<../../output/m2/two_sum_function/overview.mp4>)
- [函数版 step_by_step.mp4](<../../output/m2/two_sum_function/step_by_step.mp4>)
- [函数版 interactive.html](<../../output/m2/two_sum_function/interactive.html>)
- [类版 overview.mp4](<../../output/m2/two_sum_class/overview.mp4>)
- [类版 step_by_step.mp4](<../../output/m2/two_sum_class/step_by_step.mp4>)
- [类版 interactive.html](<../../output/m2/two_sum_class/interactive.html>)

### M3-8 回归

重新运行 `scripts/m3_8_browser_check.py`：

```text
37 checks passed
7 screenshots
0 external HTTP(S) requests
```

M3-8 课堂 HTML 仍是独立离线文件：

- [output/m3_8/classroom.html](<../../output/m3_8/classroom.html>)

### 接口/页面兼容

- 原有 `/api/v1/*` 视频工厂 API 保留；
- 旧视频工厂页面从 `/` 移到 `/legacy`，仍可打开；
- 旧 `/static/app.css` / `/static/app.js` 保留；
- M2 `interactive.html` 保留；
- M3-8 课堂 HTML 保留；
- 新的 `/` 是 M4 Vue 工作台。

## 10. 启动方法

### 默认启动（已构建前端）

```powershell
cd D:\work\算法可视化工具
.\.venv\Scripts\python.exe -m uvicorn algoviz.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000/
```

旧视频工厂：

```text
http://127.0.0.1:8000/legacy
```

API 文档：

```text
http://127.0.0.1:8000/docs
```

### 前端开发模式

需要 Node.js 20+（本机使用 `D:\Program_Files_\nvm\v24.19.0`）：

```powershell
cd frontend
npm install
npm run dev
```

打开：

```text
http://127.0.0.1:5173/static/workbench/
```

Vite 将 `/api` 和 `/health` 代理到 `127.0.0.1:8000`。

### 构建

```powershell
cd frontend
npm run typecheck
npm run build
```

输出写入 `algoviz/api/static/workbench/`。

### 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe scripts\m4_browser_check.py
```

## 11. 已实现 / 已自动化测试 / 已浏览器验证 / 仅设计 / 未实现

### 已实现

- 统一 Vue 工作台；
- 项目/题目/测试用例管理；
- SQLite 持久化；
- CodeMirror 代码编辑；
- 后端真实执行与后台 run；
- 多 case 独立轨迹；
- ClassroomDeck API；
- Vue 课堂播放器；
- StepHint 与参考答案；
- 刷新恢复；
- 运行历史；
- M4 自动化测试与 E2E 脚本。

### 已自动化测试

- 111 个完整 pytest；
- 5 个 M4 后端测试；
- 原有 M1/M2/M3 测试；
- `npm run typecheck`；
- `npm run build`；
- M3-8 37 项浏览器回归。

### 已真实浏览器验证

- GUI 创建 Two Sum 示例项目；
- 编辑项目/题目/代码；
- 添加、删除、编辑用例；
- 保存；
- 真实执行 7 用例；
- 手动/自动播放；
- 暂停/继续/速度/时间轴；
- 切换用例；
- 教学提示与答案；
- 刷新恢复；
- 后端持久化与独立 trace；
- 0 JS 错误。

### 仅设计 / 预留

- 顶部“导出”按钮只有占位；
- 多算法扩展字段（`algorithm`）已保留，但没有第二个 Profile；
- 运行历史 UI 只显示最近 5 条；
- 未来可按 case 懒加载 trace（当前一次性 classroom 响应）。

### 未实现

- 第二算法端到端支持；
- 自动识别任意算法；
- AI 自动生成 AlgorithmProfile / VisualPlan / 测试用例；
- 实时 LLM 教学提示；
- TTS 课堂旁白；
- Java / C++；
- Docker 生产沙箱；
- 账号、权限、多人协作、云端部署；
- M5 / M3-9。

## 12. 已知问题与限制

1. 测试用例 input 使用 JSON 文本编辑；第一版没有专门的 Two Sum 图形化参数表单，但数据协议不是 Two Sum 固定结构。
2. 项目/用例/run 使用本地 SQLite；不是云端数据库。
3. 执行队列是单 worker，执行期间新 run 会排队。
4. 服务重启会把进行中的 run 标记为 failed，不自动续跑。
5. ClassroomDeck 一次性返回，7 个用例响应约 200KB 量级；尚未实现按 case 懒加载。
6. Vue 组件目前按 Two Sum 的四类视觉组件布局；`VisualPlan` 标题已消费，但动态组件注册表仍以当前四类为主。
7. 前端构建 chunk 约 576KB（gzip 197KB），主要来自 CodeMirror，未做代码分割。
8. 真实浏览器 E2E 只在 Windows Edge 完成；未做 Chrome/Firefox/Safari/移动端矩阵。
9. 旧 M2 视频生成 UI 与 M4 工作台没有整合到同一页面；M4 聚焦课堂执行/演示，M2 仍保留原入口和产物。
10. M3-8 离线课堂 HTML 与新 Vue 工作台是两套 Renderer，共享后端 ClassroomDeck 语义，但 DOM 不共享，这是设计要求。

## 13. 文件清单

### 新增（M4 后端）

- `algoviz/workbench/__init__.py`
- `algoviz/workbench/models.py`
- `algoviz/workbench/store.py`
- `algoviz/workbench/service.py`
- `algoviz/workbench/api.py`
- `tests/test_m4_workbench_api.py`

### 新增（前端）

- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/vite.config.ts`
- `frontend/tsconfig.json`
- `frontend/tsconfig.app.json`
- `frontend/tsconfig.node.json`
- `frontend/index.html`
- `frontend/README.md`
- `frontend/.nvmrc`
- `frontend/src/App.vue`
- `frontend/src/main.ts`
- `frontend/src/api.ts`
- `frontend/src/playback.ts`
- `frontend/src/types.ts`
- `frontend/src/style.css`
- `frontend/src/env.d.ts`
- `frontend/src/components/*.vue`
- `algoviz/api/static/workbench/`（生产构建产物）

### 新增（脚本 / 报告）

- `scripts/m4_browser_check.py`
- `M4_IMPLEMENTATION_REPORT.md`

### 修改

- `algoviz/api/app.py`：挂载 workbench router、lifespan、`/` 新工作台、`/legacy` 旧界面、API 信息；
- `algoviz/config.py`：增加 `workbench_db_path`；
- `pyproject.toml`：补充 workbench 静态资源 package data；
- `.gitignore`：排除 `frontend/node_modules/` 与 `frontend/dist/`。

### 未修改

- M1 执行引擎；
- M2 TeachingPlan / 视频流水线；
- M3 CaseRunner / ClassroomDeck / StepHint / M3-8 HTML；
- 旧 18 个 tracer；
- 旧 `visuals.py` / `pipeline.py`。

## 14. 最终验收状态

本轮实际做到了：

- 用户直接打开 GUI；
- 新建/保存项目；
- 输入题目、思路、AC Python 源码；
- 管理多个测试用例；
- 从 GUI 发起实际执行；
- 后端真实跑用户代码；
- 每个用例独立轨迹；
- 展示真实 AnimationTrace；
- 数组、哈希表、变量、代码同步；
- 切换用例；
- 单步、回退、跳转、自动播放；
- 暂停、继续、速度；
- 教学提示与课堂提问；
- 保存项目；
- 刷新恢复；
- 原有 M1～M3 回归通过。

M4 完成，停止。不自动进入 M5 或 M3-9。
