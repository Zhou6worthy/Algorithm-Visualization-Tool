# M3-6～M3-8 合并实施报告：Two Sum 课堂交互演示系统

> 本轮将 M3-6（教师控制 + 自动演示）、M3-7（教学提示 + 课堂提问）、M3-8（HTML 组件化 + 课堂交互）合并实施。  
> 未进入 M3-9，未增加第二算法，未重写 M1/M2，未实现 AI 自动生成用例或 Docker 生产沙箱。

## 1. 实际完成结论

| 交付项 | 状态 |
|---|---|
| 统一 `PlaybackController` | **已实现、已自动化测试** |
| 教师手动控制（next/previous/seek/reset/switch/speed） | **已实现、已测试** |
| 自动播放（play/pause/resume/end/speed） | **已实现、已测试** |
| 手动与自动共享同一 trace / step_index / 状态入口 | **已实现、已测试** |
| `StepHint` 数据模型 | **已实现** |
| Two Sum 分步教学提示与课堂提问 | **已实现、已测试** |
| `ClassroomDeck` 多用例课堂数据 | **已实现、已测试** |
| 离线组件化 HTML 播放器 | **已实现** |
| 10 个真实用例的课堂 HTML | **已生成、已浏览器验证** |
| 多用例演示脚本 | **已实现并实际运行** |
| headless Edge 真实交互测试 | **37 项检查通过** |
| M2 函数版/类版回归 | **通过，关键帧零差异** |
| M3-9 / 第二算法 / AI 用例生成 / TTS 课堂接入 | **未实现** |

测试基线：

```text
修改前：93 passed
修改后：106 passed
新增：13 个自动化测试
```

## 2. 开发前实际代码核对结论

本轮实现前实际检查了：

- `algoviz/protocol/cases.py`
- `algoviz/execution/case_runner.py`
- `algoviz/execution/case_store.py`
- `algoviz/protocol/m2.py`
- `algoviz/teaching/two_sum_profile.py`
- `algoviz/teaching/two_sum_planner.py`
- `algoviz/render/two_sum_visuals.py`
- `algoviz/render/components/`
- `algoviz/teaching/html_player.py`
- `scripts/m3_5_multi_case_demo.py`
- `scripts/m2_two_sum.py`
- 现有 M1～M3 测试

核对结果：

1. `CaseRun` 直接保存该用例真实执行得到的 `ExecutionTrace` 和独立 `AnimationTrace`；
2. `TwoSumStage.load_case()` 已能把 stage 切到某条真实 `AnimationTrace` 的 step 0，并复用 `VisualPlan` / `Assembly` / 四个组件；
3. 旧 `html_player.py` 只嵌入单条 `Trace`，数组、哈希表、变量和代码内容在 JavaScript 中直接针对 Two Sum 编写；
4. `TeachingPlan` 主要服务 M2 的五段式视频与字幕时间轴，不适合直接充当课堂播放器的每步提示；
5. M3-5 的 demo 使用 FakeScene 验证切换，没有播放控制器，也没有课堂 UI。

因此本轮没有在旧 HTML 模板上继续堆条件分支，而是新增独立的课堂 deck + HTML renderer；旧 M2 `interactive.html` 保持原样。

## 3. 总体架构

```text
TestCaseSpec
    │
    ▼
CaseRunner（复用 M1Executor）
    │
    ├── ExecutionTrace
    └── TwoSumTraceAdapter → AnimationTrace
                │
                ▼
            CaseRun
                │
                ▼
          CaseRunStore
                │ latest_pairs()
                ▼
          ClassroomDeck
          ├── VisualPlan（一份，跨 case 复用）
          ├── ClassroomCase[]
          │   ├── AnimationTrace
          │   ├── StepHint[]
          │   └── step_views（服务端投影后的变量行）
          └── code / title
                │
        ┌───────┴────────┐
        ▼                ▼
PlaybackController   ClassroomPlayback（HTML JS）
（Python）            （离线浏览器）
        │                │
        └──── 同一份 AnimationTrace / step_id / VisualState ────┘
                         │
                         ▼
            Array / HashMap / Variables / Code
            + TeachingHint + PlaybackControls
```

关键边界：

- `PlaybackController` 不执行算法；
- `StepHint` 不写回 `AnimationTrace`；
- JSON 中的 `step_views` 只由 `TwoSumVisualProfile.project_variables()` 预投影，HTML 不推断 Two Sum 变量；
- HTML 只用 `VisualPlan` 决定组件、标题和槽位；
- 切换 case 只替换 trace、step_index 和视图数据，不重建 VisualPlan / 组件实例。

## 4. M3-6：教师控制与自动播放

### 4.1 Python `PlaybackController`

文件：`algoviz/teaching/playback.py`

核心 API：

```python
controller.load_case(case_run, hints=...)
controller.next_step()
controller.previous_step()
controller.seek(3)
controller.reset()
controller.play()
controller.pause()
controller.resume()
controller.set_speed(1.5)
controller.snapshot()
```

状态包含：

- `current_case_id`
- `current_animation_trace`
- `current_step_index`
- `playback_mode`（`TEACHER` / `AUTO`）
- `playback_speed`
- `is_playing`
- `is_at_end`
- `current_hint`

一致性设计：

- 手动 `next/previous/seek/reset` 与定时 Auto 推进都经过同一个 `_apply_index()`；
- 边界 clamp 到 `0 .. len(steps)-1`，不越界；
- 自动播放结束自动停止并回到 `TEACHER`；
- 暂停取消当前 timer，并将模式切换为教师手动；
- `resume` 从当前位置继续；
- `set_speed` 在播放中重新调度 timer；
- 每次调度使用递增 token，旧 timer 即使晚触发也无法推进新用例；
- `load_case` 停止旧 timer、切换 trace、回到 step 0，并调用统一步骤回调。

`on_step` 可以接到 `TwoSumStage.show_step()`，因此 Python 侧教师跳转与自动推进也共享同一视觉状态入口。`TwoSumStage.play_step()` 也改为经过 `show_step()`，并维护 `current_step_index`。

### 4.2 HTML `ClassroomPlayback`

HTML 内的 `ClassroomPlayback` 遵循同一规则：

```text
loadCase / next / prev / seek / reset
play / autoPlay / pause / resume / setSpeed
```

`next/prev/seek` 和 `setTimeout` 自动推进都调用 `manual()` 或同一个 `render()`，共享 `this.index`。

- 切换 case：`loadCase()` 取消 timer，`caseId` 改变，`index=0`，重新 render；
- 旧 timer：`cancelTimer()` 递增 token，`onTimer` 检查 token；
- 自动播放结束：停止，`playing=false`，`mode='teacher'`；
- 组件 DOM 不重建。

### 4.3 M3-6 实际测试

`tests/test_m3_6_playback.py` 共 7 项：

- 手动 next/previous/seek/reset 和边界；
- 自动播放推进到末尾并停止；
- pause/resume 与速度重调度；
- 手动控制接管自动播放；
- 播放中切换 case 取消旧 timer；
- 提示按 step 索引且校验非法 step；
- 控制器与 `TwoSumStage.show_step()` 共享状态，切换后不重新装配组件。

## 5. M3-7：教学提示与课堂提问

### 5.1 数据模型

文件：`algoviz/protocol/hints.py`

```python
StepHint(
    hint_id="two_sum_step_05_hit",
    related_step_id=5,
    kind=HintKind.COMPLEMENT_HIT,
    title="计算补数并查询：命中",
    explanation="当前数字是 7。为了凑成 9，需要 target - x = 2……",
    common_mistake="先插入当前元素再查询，可能把当前元素自己当成搭档。",
    question="为什么找到补数后就可以返回？如果数组中有重复数字，算法还能正常工作吗？",
    answer="……重复数字如 [3, 3] 时，第二次遇到 3 才会命中；先查后插保证不会用同一个下标。",
    concepts=["计算补数", "查询哈希表", "查询 hit"],
)
```

### 5.2 Two Sum 提示生成

文件：`algoviz/teaching/step_hints.py`

按真实 step 类型和状态生成：

| 执行节点 | 提示内容 |
|---|---|
| init | 为什么需要哈希表；暴力解法与空间换时间 |
| visit | 当前元素、target 与补数；seen 当前大小 |
| compare miss | 计算补数、查询未命中、当前元素暂不能成对 |
| compare hit | 计算补数、命中下标、为何可以返回、重复数字 |
| update | key=数字、value=下标；为什么保存下标 |
| found（非空） | 返回哪两个下标、为什么提前结束 |
| found（空） | 遍历结束无解，空列表是合法结果 |
| complete | 平均 O(n)/O(n²) 最坏、O(n) 空间、双指针/暴力替代 |

实际普通用例生成 **8 条提示**，覆盖 **14 个教学概念**，包括：

- 为什么需要哈希表
- 遍历元素 / 当前元素与 target
- 计算补数
- 查询哈希表 / 查询 miss / 查询 hit
- 插入元素 / 哈希表保存内容
- 完成返回 / 为什么可以返回
- 完成 / 复杂度

不是每个 step 都强行生成提示：未识别的 `NOTE` step 返回空列表，界面显示“本步骤暂无教学提示”。

提示生成是只读操作；测试验证生成前后 `AnimationTrace.model_dump_json()` 完全一致。

### 5.3 HTML 提示 UI

`TeachingHintComponent` 负责：

- 当前知识点标题；
- 原理解释；
- 常见错误；
- 课堂提问；
- “显示/收起参考答案”；
- 切换 step/case 时自动收起旧答案；
- 没有提示的 step 显示空态。

参考答案展开/收起只改变 UI 状态，不改变播放位置或 `AnimationTrace`。

## 6. M3-8：HTML 组件化与课堂交互

### 6.1 数据装配

文件：`algoviz/teaching/classroom.py`

`ClassroomDeck` 包含：

- `visual_plan`：一份，跨所有 case 复用；
- `code`；
- `cases`：每个 case 对应一个 `CaseRun`；
- `trace`：真实 `AnimationTrace`；
- `hints`：按 `related_step_id` 对齐；
- `step_views`：服务端预投影的变量行；
- `active_case_id`；
- `default_step_duration`。

`CaseRunStore.latest_pairs()` 提供按 case 添加顺序的 `(TestCaseSpec, 最近一次 CaseRun)`，实现 `Store → Deck` 的清晰衔接。

### 6.2 HTML 组件

文件：`algoviz/teaching/classroom_html.py`

实际拆出的浏览器类：

- `ArrayComponent`：数组值、索引、指针、target、found；
- `HashMapComponent`：entries、lookup hit/miss、插入高亮；
- `VariableComponent`：只消费预投影的 `step_views`；
- `CodeComponent`：源码行与当前行高亮；
- `TeachingHintComponent`：教学提示与参考答案；
- `PlaybackControls`：按钮、时间轴、速度、键盘；
- `ClassroomPlayback`：HTML 播放状态机。

每个组件在页面启动时 mount 一次；后续步骤只更新文本、class 和 keyed 子节点，不重建整个页面。浏览器测试通过对象引用探针验证：切换 case 后数组组件的根 DOM 节点和 JS 组件实例仍是同一个。

### 6.3 用例切换

每个 case 卡片显示：

- 用例名称；
- 用户提供 / AI 补充；
- 输入数据；
- 执行状态；
- 当前 case 的 expected / actual / 错误信息。

点击后：

1. 停止旧自动播放；
2. 加载目标 `AnimationTrace`；
3. `step_index=0`；
4. 更新数组、哈希表、变量、代码行；
5. 更新教学提示和元数据；
6. 更新 expected/actual/status；
7. 不重装 `VisualPlan` 或组件。

无 trace 的 error 用例显示“不可播放”，禁用播放按钮，不生成假轨迹。

### 6.4 播放控制

实际提供：

- 上一步；
- 下一步；
- 播放；
- 暂停；
- 继续；
- 从头演示；
- 重置；
- 步骤时间轴；
- 0.5× / 1× / 1.5× / 2×；
- 键盘 ← / → / Space / Home / End。

时间轴按真实步骤跳转，显示 `步骤 x / n` 与基于步骤时长估算的秒数。

### 6.5 离线

- 单文件 HTML；
- CSS、JS、trace、提示、VisualPlan 全部内嵌；
- 无 CDN、无后端、无视频依赖；
- 浏览器测试以 `file://` 打开，没有 HTTP(S) 资源请求。

## 7. 自动化测试

完整测试：

```text
pytest -q
106 passed
```

构成：

- 旧算法与旧功能：43；
- M1：9；
- M2：8；
- M3-2：8；
- M3-3：10；
- M3-4：7；
- M3-5：8；
- M3-6：7；
- M3-7：3；
- M3-8：3。

本轮新增 13 项：

```text
tests/test_m3_6_playback.py
  test_manual_controls_share_one_index_and_boundaries
  test_auto_play_advances_to_end_and_stops
  test_pause_resume_and_speed_reschedule
  test_manual_controls_take_over_auto
  test_switch_case_cancels_old_timer_and_starts_from_zero
  test_hints_are_indexed_by_step_and_validated
  test_controller_and_stage_share_steps_without_reassembling_components

tests/test_m3_7_hints.py
  test_hints_align_with_real_steps_and_cover_required_teaching_nodes
  test_no_hint_is_forced_for_unknown_note_step
  test_step_hint_keeps_question_and_answer_independent

tests/test_m3_8_classroom.py
  test_deck_builds_from_real_runs_and_reuses_one_visual_plan
  test_html_is_offline_componentized_and_embeds_every_case
  test_classroom_models_reject_mismatched_views_and_duplicate_cases
```

专项回归：

```text
tests/test_tracers.py                 25 passed
tests/test_m1_execution.py tests/test_m2_teaching.py  17 passed
```

未删除、跳过或降低任何旧测试断言。

## 8. 真实 10 用例 Demo

脚本：`scripts/m3_8_classroom_demo.py`

命令：

```powershell
.\.venv\Scripts\python.exe scripts\m3_8_classroom_demo.py
```

实际结果：

| case | source | status | expected | actual | steps |
|---|---|---|---|---|---|
| normal | user | success | `[0, 1]` | `[0, 1]` | 8 |
| first | user | success | `[0, 1]` | `[0, 1]` | 8 |
| last | user | success | `[2, 3]` | `[2, 3]` | 14 |
| none | user | success | `[]` | `[]` | 13 |
| duplicate | user | success | `[0, 1]` | `[0, 1]` | 8 |
| empty | user | success | `[]` | `[]` | 3 |
| single | user | success | `[]` | `[]` | 7 |
| mismatch | user | failed | `[1, 2]` | `[0, 2]` | 11 |
| invalid | user | error | — | — | 0 |
| ai_supplemented | ai_generated | success | `[1, 2]` | `[1, 2]` | 11 |

- `CaseRunStore`：10 cases / 10 runs；
- 9 条真实 AnimationTrace，invalid 不生成假轨迹；
- 不同用例 step 数不同：3、7、8、11、13、14；
- mismatch 保留真实 trace，状态为 failed；
- AI 用例来源正确标记为 `ai_generated`。

生成产物：

- [classroom.html](<../../output/m3_8/classroom.html>)
- [classroom_deck.json](<../../output/m3_8/classroom_deck.json>)
- [summary.json](<../../output/m3_8/summary.json>)

## 9. 浏览器真实交互验证

脚本：`scripts/m3_8_browser_check.py`

环境：

- Windows headless Microsoft Edge 158.0.4370.33；
- CDP（WebSocket）真实点击、真实读取 DOM / 控制器状态；
- 页面以 `file://` 加载。

实际结果：

```text
37 checks passed
7 screenshots
0 browser errors
0 external HTTP(S) requests
elapsed 13.35s
```

验证流程：

1. 打开 HTML，确认 10 个用例；
2. 默认选择 normal；
3. 手动 next ×2，到 miss step；
4. 手动 prev；
5. 拖动步骤时间轴，直接跳到 found step；
6. 验证代码高亮第 6 行、hash hit、found 单元格、命中提示；
7. 展开/收起参考答案；
8. 播放并暂停，确认旧 timer 不推进；
9. 切换 2×；
10. 自动播放中切到 Case 2，确认从 step 0 开始、旧 timer 失效；
11. Case 2 自动播放、暂停、继续；
12. 切回 Case 1，确认数组 `[2,7,11,15]`、target=9、hash 空、代码行 2；
13. 自动播放到末尾，确认停止在步骤 8/8；
14. 无效用例显示错误且禁用播放；
15. 逐个切换全部 10 个用例，确认步数、nums、target 不串台；
16. 组件对象/根 DOM 引用探针，确认切换复用同一批组件；
17. 确认无浏览器异常、无外部请求。

关键截图：

- [正常用例 · 查询未命中](<../../output/m3_8/screenshots/01_normal_miss.png>)
- [命中返回 · 展开参考答案](<../../output/m3_8/screenshots/02_normal_hit_hint.png>)
- [播放中切到 Case 2 · 初始状态](<../../output/m3_8/screenshots/03_case2_initial_after_switch.png>)
- [Case 2 自动播放](<../../output/m3_8/screenshots/04_case2_auto_playing.png>)
- [切回 Case 1 · 状态恢复](<../../output/m3_8/screenshots/05_case1_restored.png>)
- [自动播放到末尾 · 复杂度提示](<../../output/m3_8/screenshots/06_auto_complete.png>)
- [无轨迹用例 · 错误但不伪造](<../../output/m3_8/screenshots/07_invalid_case.png>)
- [关键截图拼图](<../../output/m3_8/screenshots/contact_sheet.png>)

机器可读结果：

- [browser_check.json](<../../output/m3_8/browser_check.json>)

## 10. M2 单用例兼容性回归

实际重新运行：

```powershell
.\.venv\Scripts\python.exe scripts\m2_two_sum.py --forms function,class --output-root output/m2
```

结果：

| 形态 | overview | step_by_step | QC |
|---|---|---|---|
| 函数版 | 75.71s | 126.48s | true |
| 类版 | 75.76s | 126.53s | true |

两版 overview / step_by_step 均为 1920×1080、30 FPS、H.264 + AAC，QC 无警告、无错误。

M2 产物仍有效：

- [函数版 interactive.html](<../../output/m2/two_sum_function/interactive.html>)
- [函数版 overview.mp4](<../../output/m2/two_sum_function/overview.mp4>)
- [函数版 step_by_step.mp4](<../../output/m2/two_sum_function/step_by_step.mp4>)
- [类版 interactive.html](<../../output/m2/two_sum_class/interactive.html>)
- [类版 overview.mp4](<../../output/m2/two_sum_class/overview.mp4>)
- [类版 step_by_step.mp4](<../../output/m2/two_sum_class/step_by_step.mp4>)
- [M2 summary.json](<../../output/m2/summary.json>)

关键帧对比：

- 新帧：[function step6](<../../output/m3_8/m2_after/function_step6.png>)、[function step7](<../../output/m3_8/m2_after/function_step7.png>)、[class step6](<../../output/m3_8/m2_after/class_step6.png>)、[class step7](<../../output/m3_8/m2_after/class_step7.png>)
- 零像素差异证据：[m2_regression.json](<../../output/m3_8/m2_regression.json>)

实际比较结果：

| 关键帧 | mean RGB diff | diff bbox |
|---|---|---|
| function step6 | `[0.0, 0.0, 0.0]` | `null` |
| function step7 | `[0.0, 0.0, 0.0]` | `null` |
| class step6 | `[0.0, 0.0, 0.0]` | `null` |
| class step7 | `[0.0, 0.0, 0.0]` | `null` |

四个关键帧与 M3-5 后基线完全一致；旧 `interactive.html` 未被课堂播放器替换。

## 11. 新增 / 修改文件

### 新增

| 文件 | 内容 |
|---|---|
| `algoviz/protocol/hints.py` | `HintKind`、`StepHint` |
| `algoviz/teaching/playback.py` | Python `PlaybackController` |
| `algoviz/teaching/step_hints.py` | Two Sum 分步提示生成 |
| `algoviz/teaching/classroom.py` | `ClassroomDeck` / `ClassroomCase` / 装配 |
| `algoviz/teaching/classroom_html.py` | 离线组件化课堂 HTML |
| `scripts/m3_8_classroom_demo.py` | 10 用例真实演示 |
| `scripts/m3_8_browser_check.py` | headless Edge/CDP 交互测试 |
| `tests/test_m3_6_playback.py` | 7 项播放测试 |
| `tests/test_m3_7_hints.py` | 3 项提示测试 |
| `tests/test_m3_8_classroom.py` | 3 项 deck/HTML 测试 |

### 修改

| 文件 | 改动 |
|---|---|
| `algoviz/execution/case_store.py` | 增加 `case_ids` / `run_ids` / `latest_pairs()` |
| `algoviz/render/two_sum_visuals.py` | 增加 `show_step()`；`play_step()` 统一经 `show_step()`；维护 `current_step_index` |
| `algoviz/protocol/__init__.py` | 导出 `HintKind` / `StepHint` |

### 明确未修改

- M1 ExecutionTrace / ExecutionEvent 字段；
- M1/M2 AnimationTrace / VisualState 字段；
- M2 `TeachingPlan` 五段结构；
- 旧 `algoviz/teaching/html_player.py`；
- `TwoSumScene`；
- 旧 18 个 tracer；
- 旧 `visuals.py` / `pipeline.py`；
- M3-5 产物与数据模型语义。

## 12. 已实现 / 已验证 / 仅设计 / 未实现

### 已实现

- 统一播放控制器；
- 教师手动控制；
- 自动播放；
- 用例切换与旧 timer 取消；
- 分步教学提示；
- 课堂提问与参考答案；
- VisualPlan 驱动的组件化 HTML；
- 多用例 deck；
- 离线单文件课堂播放器；
- 10 用例演示脚本；
- 浏览器自动化检查脚本。

### 自动化测试通过

- 106 个完整 pytest；
- 13 个本轮新测试；
- 25 个 tracer 测试；
- 17 个 M1/M2 联合测试；
- 无旧测试删除或跳过。

### 浏览器真实交互验证

- 37 项检查通过；
- 真实 headless Edge + CDP；
- 7 张关键截图；
- 0 外部请求、0 浏览器异常；
- 覆盖手动、自动、暂停、继续、时间轴、速度、切换、提示、代码高亮、错误用例和全部 10 个用例。

### 仅完成设计，未实现

- 实时 LLM 生成教学提示；
- 课堂播放器接入 TTS 旁白；
- 第二个算法的课堂 deck；
- 通用多算法 LessonScene / 自动 Profile；
- Java/C++/stdin 执行；
- AI 自动生成测试用例；
- 持久化 CaseRunStore / 数据库；
- Docker 生产沙箱。

### 尚未实现

- M3-9 及以后任何功能；
- 完整通用算法自动识别与自动生成教学视频；
- 完整生产级教师后台。

## 13. 已知限制

1. 课堂播放器仍以 Two Sum 为唯一端到端算法；组件是通用的，但 deck 装配仍是 Two Sum 流程。
2. `CaseRunStore` 只在内存中；课堂 HTML 是某个时刻的静态快照，不连接后端。
3. 每个用例在课堂 deck 中只展示最近一次 CaseRun；多次重复执行的历史 run 仍保存在 Store 中但未进入 UI。
4. 课堂 HTML 的自动播放按步骤时长推进，不与 TTS 音频对齐；本轮未接入课堂旁白。
5. 教学提示是结构化预置素材，不是实时大模型生成；每个 step 最多一条提示。
6. Python `PlaybackController` 已实现，但本轮实际课堂产品界面是 HTML；未新增 Manim GUI 控件窗口。
7. 浏览器自动化在 Windows Edge 上完成，未做 Chrome/Firefox/Safari 和移动端矩阵测试。
8. 无 trace 的 error 用例只能查看错误，不能播放；这是有意设计，避免伪造轨迹。
9. 用例较多时右侧列表需要滚动；界面已实现当前用例自动滚入可视区域。
10. M2 `interactive.html` 仍是单用例旧播放器；课堂多用例播放器是独立新产物，不是替换。

## 14. 验收结论

本轮完成后，实际可以：

1. 准备一个 Two Sum AC 代码；
2. 提供 10 个测试用例；
3. 为每个用例生成独立真实执行轨迹；
4. 打开离线课堂 HTML；
5. 自由切换用例；
6. 手动上一步/下一步/跳转；
7. 一键自动播放；
8. 暂停并接管；
9. 查看当前代码行、数组、哈希表、变量；
10. 在当前步骤查看教学解释和课堂提问；
11. 展开参考答案；
12. 切换用例后不残留旧数组、旧哈希表、旧提示或旧 timer。

本轮完成，停止，不自动开始 M3-9。
