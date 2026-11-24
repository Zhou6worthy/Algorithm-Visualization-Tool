# M2 交付报告：Two Sum 教学可视化闭环

> 范围：M2-1 至 M2-5，只做 Two Sum。  
> 继承 M1：没有重新执行用户代码，没有修改 `ExecutionTrace` / `ExecutionEvent` / `SemanticOperation` / `AnimationTrace` 的字段语义；没有修改旧 18 个 tracer、旧 `scene.py` / `visuals.py` / `pipeline.py`。

## 1. 验收结论

| 形态 | 真实 trace | 输出 | 步骤 | overview | step_by_step | HTML |
|---|---|---|---|---|---|---|
| 普通函数 `two_sum` | `trace_two_sum_function_9d966b1a` | `[0, 1]` | 8 | 75.71s | 126.48s | 通过 |
| LeetCode 类 `Solution.two_sum` | `trace_two_sum_class_a457aeac` | `[0, 1]` | 8 | 75.76s | 126.53s | 通过 |

两个视频均为 **1920×1080、30 FPS、H.264 + AAC 中文配音**。四个 MP4 的 QC 全部 `ok=true`，分辨率、时长、音轨、关键帧非空白检查全部通过。

产物：

- `output/m2/summary.json`
- `output/m2/two_sum_function/{overview.mp4, step_by_step.mp4, interactive.html, execution.json, animation_events.json, teaching_plan.json, manifest.json}`
- `output/m2/two_sum_class/{overview.mp4, step_by_step.mp4, interactive.html, execution.json, animation_events.json, teaching_plan.json, manifest.json}`

## 2. 新增 / 修改文件

### 新增

| 文件 | 作用 |
|---|---|
| `algoviz/protocol/m2.py` | M2 独立的 `TeachingPlan`、五段式 `Section`、`VideoTimeline`、`RenderPlan`、复杂度三分解模型 |
| `algoviz/teaching/__init__.py` | 教学层 package |
| `algoviz/teaching/two_sum_planner.py` | 只读 M1 产物，生成五段式计划、逐步旁白、两条时间轴、复杂度统计 |
| `algoviz/teaching/two_sum_pipeline.py` | TTS、Manim、FFmpeg、SRT、HTML、manifest 编排 |
| `algoviz/teaching/html_player.py` | 内嵌 AnimationTrace 的独立 HTML 播放器 |
| `algoviz/render/two_sum_visuals.py` | 数组 / seen 哈希表 / 当前元素 / need / 查找状态 / 代码 / 变量组件 |
| `algoviz/render/two_sum_scene.py` | Two Sum 专用 Manim 教学场景 |
| `algoviz/render/m2_renderer.py` | 复用 Manim CLI 的 M2 渲染器；不改旧 `ManimRenderer` |
| `tests/test_m2_teaching.py` | 8 个 M2 单元测试 |
| `scripts/m2_two_sum.py` | 函数版 + 类版端到端验收脚本 |
| `M2_REPORT.md` | 本报告 |

### 修改

- 本轮没有修改旧 18 个 tracer、旧 `render/scene.py`、旧 `render/visuals.py`、旧 `pipeline.py`、`protocol/events.py`、`protocol/execution.py`。
- M2 的所有新字段都在 `algoviz/protocol/m2.py` 中，M1 数据协议保持原样。

## 3. 五段式 TeachingPlan

`teaching_plan.json` 固定按顺序包含：

1. `complete_demo`：完整演示
2. `idea`：算法思想
3. `stepwise`：逐步讲解（8 个真实 step）
4. `complexity`：复杂度三分解
5. `replay`：完整回放

`overview.mp4` 对应的视频由 `complete_demo + idea + complexity + replay` 组成；`step_by_step` 由五段全部组成。

| 视频 | 章节 | 时长 |
|---|---|---|
| function overview | 完整演示 / 思想 / 复杂度 / 回放 | 12.26 + 14.04 + 38.88 + 10.53 |
| function step_by_step | 完整演示 / 思想 / 逐步 / 复杂度 / 回放 | 12.26 + 14.04 + 50.77 + 38.88 + 10.53 |
| class overview | 完整演示 / 思想 / 复杂度 / 回放 | 75.76 总计 |
| class step_by_step | 完整五段 | 126.53 总计 |

完整演示与逐步讲解引用同一组 step_id（0..7），并使用相同的 `state_before/state_after`。两者只改变：
- `overview` 不渲染 `stepwise` 章节，按 1.8x / 2.2x 快速展示；
- `step_by_step` 对每个 step 使用独立旁白和动画时长；
- 教学分组、讲解文案和速度不同，算法事实完全相同。

## 4. 同一份真实轨迹的证据

每个形态的 `teaching_plan.json` / `manifest.json` 包含：

```text
trace_id
execution_sha256
animation_sha256
step_state_sha256[0..7]
```

函数版：

```text
execution  f4f053406d03b6ce122c2202901d92746d164269d1e166a32a60645adfdc2408
animation  ee9f761e281a63133e29280c528194826d98b192e138fa118b7de511ad709377
```

类版：

```text
execution  e5b586251a762b5a3b0ec602bc30eb27f0749ff216efa1b23a612089293a6d45
animation  128d4f163ef99dcc6657e86c9271fb5a543151d37c020d93d2c52532d21e1aaa
```

`algoviz/teaching/two_sum_planner.py::verify_plan` 会检查：

- `trace_id` 与 AnimationTrace 的 `metadata.execution_trace_id` 一致；
- 每个教学 step 的状态摘要与真实 `AnimationStep.state_after` 一致；
- 每个 step 的代码行与真实 trace 一致；
- `overview` 和 `step_by_step` 都覆盖全部真实 step；
- `overview` 不含 `stepwise`，`step_by_step` 必须含 `stepwise`；
- 时间轴单调、章节内步骤不越界。

## 5. Two Sum 可视化组件

`TwoSumStage` 严格消费 AnimationStep 状态：

1. **原始数组**：显示 `nums`、下标、target；
2. **哈希表 seen**：显示 `key → index`、空表 `{ }`、命中行高亮；
3. **当前元素和索引**：来自 `state_after.array.pointers["i"]` 和 `array.values[i]`；
4. **need 补数**：直接读取 `state_after.variables["need"]`，缺失显示 `—`；
5. **查找状态**：直接读取 `DictState.lookup_key` / `lookup_status`，显示 `HIT` / `MISS`；
6. **当前代码行**：直接读取 `AnimationStep.code_line`，高亮对应行；
7. **关键变量**：i / x / need / target / seen.size；当 M1 state 只提供指针时，i/x 由数组指针补全，不生成新算法操作；found/complete 显示 step.meta 中的真实返回值。

关键状态验证：

| step | 类型 | seen | lookup | 代码行 |
|---|---|---|---|---|
| 0 | init | `{}` | — | 2（函数）/ 3（类） |
| 1 | visit | `{}` | — | 3 / 4 |
| 2 | compare | `{}` | 7 → MISS | 5 / 6 |
| 3 | update | `{2: 0}` | — | 7 / 8 |
| 4 | visit | `{2: 0}` | — | 3 / 4 |
| 5 | compare | `{2: 0}` | 2 → HIT | 5 / 6 |
| 6 | found | `{2: 0}` | HIT | 6 / 7 |
| 7 | complete | `{2: 0}` | HIT | 6 / 7 |

命中后立即 return，`seen` 峰值始终为 1；没有第二次插入 `7 → 1`。

## 6. 中文配音与字幕

- 默认 Edge TTS：`zh-CN-XiaoxiaoNeural`，`+0%`；
- 函数版 14 段旁白、类版 14 段旁白；
- 每个 stepwise step 使用独立旁白、独立音轨片段，形成真实 TTS 时长；
- SRT 与旁白 cue 同步，例如函数版 stepwise：
  - `00:00:26,798 → 00:00:32,846` 初始化
  - `00:01:01,280 → 00:01:07,448` 命中补数
  - `00:01:07,898 → 00:01:13,778` 返回
- 最终 MP4 的 AAC 音轨已通过 `ffprobe` 验证；函数版 overview 音轨 mean volume `-23.2 dB`、max `-5.6 dB`。

## 7. MP4 实际结果

| 形态 | 视频 | 时长 | 大小 | 编码 |
|---|---|---|---|---|
| function | `overview.mp4` | 75.71s | 7.22 MB | H.264 1920×1080 30fps / AAC |
| function | `step_by_step.mp4` | 126.48s | 10.43 MB | H.264 1920×1080 30fps / AAC |
| class | `overview.mp4` | 75.76s | 7.38 MB | H.264 1920×1080 30fps / AAC |
| class | `step_by_step.mp4` | 126.53s | 10.65 MB | H.264 1920×1080 30fps / AAC |

QC 关键项全部通过：

- 固定 1920×1080；
- 实际时长与计划差 0.00s；
- 有 AAC 音轨；
- 关键帧非空白；
- 算法校验 `verified=true`。

实际抽帧人工检查：

- 完整演示 step 4 高亮 `seen[x] = i`；
- 逐步讲解 step 6 高亮 `if need in seen`，哈希显示 `2 → 0` + `HIT`；
- step 7 高亮 `return [seen[need], i]`，数组 0/1 绿色，变量显示 `返回 [0, 1]`；
- 类版代码高亮为类版行号（3/4/6/8/...），没有错用函数版行号。

## 8. HTML Event Player

`interactive.html` 完全离线，内嵌 `animation_events.json` 和 `teaching_plan.json`，不请求后端、不依赖 MP4。

支持：

- 播放 / 暂停；
- 上一步 / 下一步；
- 时间轴拖动跳转；
- 0.5x / 1x / 1.5x / 2x 速度；
- 代码同步高亮；
- 数组、seen 哈希表、lookup 状态重建；
- i / x / need / target / seen.size 变量；
- 点击步骤 chip 直接跳转；
- 空格 / 左右方向键 / Home / End 键盘操作。

实际用 headless Edge + CDP 验证（函数版）：

```text
初始：步骤 1 / 8，代码行 2
点击第 6 个 chip：步骤 6 / 8，lookup=HIT，dict=2→0，代码行 5
时间轴 70%：步骤 6 / 8，lookup=HIT，代码行 5
下一步：步骤 7 / 8，代码行 6
上一步：步骤 6 / 8，代码行 5
速度：2x
播放 3 秒：时间 00:03 / 00:49，暂停按钮正常
暂停：播放按钮恢复
```

类版：

```text
点击第 6 个 chip：步骤 6 / 8，lookup=HIT，dict=2→0，代码行 6（类版），代码文本含 class Solution
```

## 9. 复杂度三分解

每个 `teaching_plan.json` 的 `complexity` 包含：

- `theory_time` / `theory_space` / `theory_note`：理论复杂度；
- `code_time` / `code_space` / `code_note` / `code_features`：用户 AC 代码静态结构估算；
- `observed`：当前样例真实统计。

函数版实测：

```text
n=4
访问 2 次
查找 2 次（1 命中 / 1 未命中）
插入 1 次
seen 峰值 1
真实事件 11
执行耗时 1.999 ms
输出 [0, 1]
```

类版实测：

```text
n=4
访问 2 次
查找 2 次（1 命中 / 1 未命中）
插入 1 次
seen 峰值 1
真实事件 11
执行耗时 3.007 ms
输出 [0, 1]
```

理论 / 用户代码 / 实测三张卡片在视频中分三段旁白依次点亮，没有把“单样例实测”冒充复杂度证明。

## 10. 测试结果

```text
pytest -q
60 passed
```

包含：

- 旧算法与旧功能：43 个；
- M1：9 个；
- M2：8 个。

M2 测试清单：

```text
test_plan_has_fixed_five_sections_and_shared_trace
test_overview_and_stepwise_use_same_real_steps
test_hash_states_and_code_lines_are_from_trace
test_timelines_cover_sections_steps_and_subtitles
test_complexity_is_three_way_separated
test_class_plan_is_same_semantic_execution
test_html_is_standalone_and_embeds_unified_trace
test_html_contains_controls_for_arbitrary_step_jump
```

旧 18 算法回归：

```text
pytest -q tests/test_tracers.py
25 passed
```

其中参数化覆盖 18 个注册算法；M1/M2 联合测试：

```text
pytest -q tests/test_m1_execution.py tests/test_m2_teaching.py
17 passed
```

## 11. 复现命令

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\m2_two_sum.py --forms function,class --output-root output/m2
```

## 12. 已知限制

1. **M2 只实现 Two Sum 教学语义**；其他算法仍是旧路径，不提前扩展。
2. **LocalSandbox 仍只信任代码**；M2 不改变 M1 的执行安全边界，生产 Docker 在 M3。
3. **HTML 不包含配音播放**；它只播放教学状态，MP4 才是带配音版本。
4. **复杂度是静态估算 + 单样例实测**；不声称证明复杂度，代码特征只描述静态结构。
5. **未接入 GUI/API 任务队列**；M2 通过 `scripts/m2_two_sum.py` 生成，GUI 集成留到 M3。
6. **视频渲染使用本机字体/Edge TTS**；换机器需保证中文字体与 TTS 可用，失败时 TTS 会降级并记录 warning。
7. **M2 没有修改 M1 的字段**；如果后续要支持 stdin/Java/C++，需要另做 source map 与语言适配。
8. `overview` 是有意省略 `stepwise` 的 4 段版本；完整五段只出现在 `step_by_step`，两者仍共享同一 trace。
