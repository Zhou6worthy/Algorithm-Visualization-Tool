# AlgoViz 实现说明（Project Guide）

> 设计依据：仓库根目录 `readme.md`。
> 本文记录**实际完成的实现**、使用方式、验收结果与已知边界。

## 1. 一句话说明

自然语言 / 伪代码 / 显式参数 → **真实执行追踪** → 统一 `Animation Event JSON` → **Manim 动画** → 中文配音 + 字幕 → **MP4**，支持批量并发、失败重试、FastAPI 服务与 SQLite 状态持久化。

## 2. 为什么不是「让大模型直接生成动画」

`readme.md` 的核心原则是「不要让大模型直接生成每一帧动画」。实现上分四层：

1. **执行器**（`algoviz/tracers/`）：真正运行算法，每步记录 `state_before / state_after`；
2. **校验**（`algoviz/verify.py`）：用独立参考实现复核结果，`Trace.verified` 不通过会被 QC 拦截；
3. **模板**（`algoviz/render/`）：数组 / 树 / 图 / DP 矩阵四套组件只消费事件，风格统一；
4. **大模型**（`algoviz/ai/`）：只负责识别算法、提取参数、润色讲解，输出受 JSON Schema 与复杂度白名单校验。

## 3. 目录结构

```text
algoviz/
├─ protocol/          # Pydantic 事件协议、教学脚本、任务模型
├─ tracers/           # 排序/查找/树/图/DP 五类追踪器
├─ algorithms/        # 算法注册表：默认参数、复杂度、源码、执行与校验
├─ ai/                # DeepSeek 客户端、任务解析、讲解 Prompt
├─ script.py          # 六段式教学脚本
├─ timeline.py        # TTS 时长 → 段落时长 → 逐步时间轴 → 字幕
├─ tts.py             # Edge TTS → Windows SAPI → 静音降级
├─ render/
│  ├─ scene.py        # 由 ScenePlan 驱动的 Manim 场景
│  ├─ visuals.py      # 数组/树/图/矩阵可视化组件
│  └─ renderer.py     # Manim CLI 调用与产物收集
├─ media.py           # FFmpeg/FFprobe 封装
├─ qc.py              # 视频质量检查
├─ pipeline.py        # 单任务完整流水线
├─ jobs/              # SQLite 任务库 + 线程池批处理
├─ batch.py           # 批量 JSON 解析
├─ api/app.py         # FastAPI 服务
└─ cli.py             # algoviz 命令行

tasks/demo.json       # 10 个算法的演示批次
tests/                # 43 个单元测试
scripts/              # 调试与验收脚本
research/             # 开源项目调研（克隆在 research/vendor/）
```

## 4. 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
copy .env.example .env       # 可选：填入 DEEPSEEK_API_KEY
algoviz doctor

# 启动中文 Web GUI（推荐）
algoviz serve --port 8000
# 浏览器打开 http://127.0.0.1:8000/
```

GUI 支持：自然语言/参数化建任务、画质与配音选项、实时进度、视频预览、字幕/事件下载、
批量 JSON 提交、失败重试、大模型状态与连通性测试，以及直接在浏览器里保存 DeepSeek Key。

```powershell
# 命令行：单条（自然语言）
algoviz generate "请生成快速排序的教学视频，选择第一个元素作为 Pivot，使用数组 [8, 3, 5, 1, 9, 2]" --quality medium

# 命令行：单条（显式参数）
algoviz generate --algorithm dijkstra --params "{\"nodes\":[\"A\",\"B\",\"C\"],\"edges\":[[\"A\",\"B\",4],[\"A\",\"C\",2]],\"start\":\"A\",\"target\":\"C\"}"

# 命令行：批量
algoviz batch tasks/demo.json --workers 3 --retries 1

# 检查 Key 是否真的可用
algoviz ai-check
```

### 4.1 大模型是否被调用？

每次任务都会在三个地方明确显示：

- **CLI**：生成结束打印 `大模型：✅ 已调用 DeepSeek（N 次）` 或 `未调用（未配置 Key / AI 关闭）`；
- **任务库**：`algoviz jobs` 的「AI 讲解」列、GUI 任务卡片上的 AI 徽标；
- **元数据**：`output/jobs/<id>/meta.json` 的 `ai_usage`（含状态、调用次数、成功/失败、耗时、错误）。

状态含义：

| 状态 | 含义 |
|---|---|
| `used` | 至少一次 DeepSeek 调用成功；讲解文案由模型生成 |
| `failed` | 尝试调用但失败，已自动回退本地模板 |
| `disabled` | 未配置 Key，或 `ALGOVIZ_AI_MODE=off` |
| `unused` | Key 可用但本次没有触发调用 |

如果「加了 Key 但视频没差异」，按顺序检查：

1. GUI 右上角 AI 徽标/横幅是否显示「未配置 Key」；
2. 打开「AI 设置」点「测试连接」，看是否 401/网络错误；
3. Key 是否写入了项目根目录 `.env`（GUI 会显示配置文件绝对路径）；
4. 设置是否保存后立即生效（GUI 会热更新运行中的服务，无需重启）；
5. 大模型只影响**讲解文案和参数提取**，动画/算法/画面结构保持一致；差异主要出现在字幕、旁白和总结页的「讲解：DeepSeek」标识。

## 5. 输出

```text
output/
├─ videos/<标题>_<job_id>.mp4        # 最终成品
├─ jobs/<job_id>/
│  ├─ events.json                    # 可重放事件流
│  ├─ script.json                    # 六段式脚本
│  ├─ plan.json                      # 场景计划 + 时间轴
│  ├─ scene.py                       # 生成的 Manim 入口
│  ├─ audio/                         # 分段 TTS
│  ├─ narration.wav                  # 拼接旁白
│  ├─ subtitles.srt                  # 中文字幕
│  ├─ video_silent.mp4               # Manim 原始渲染
│  ├─ final.mp4                      # 音视频合成
│  ├─ qc.json                        # 质量报告
│  ├─ manim.log                      # 渲染日志
│  ├─ pipeline.log                   # 阶段日志
│  └─ meta.json                      # 任务元数据
└─ tasks.sqlite3                     # 任务状态机
```

## 6. 算法与事件覆盖

| 类别 | 算法 | 关键事件 |
|---|---|---|
| 排序 | 冒泡、选择、插入、快速、归并 | compare / swap / update / mark / complete |
| 查找 | 二分、线性 | compare / visit / found / shrink |
| 树 | BST 构建、BST 查找、前/中/后/层序遍历 | create / compare / visit / enqueue / dequeue |
| 图 | BFS、DFS、Dijkstra | enqueue / dequeue / push / pop / relax / backtrack |
| DP | 0-1 背包、LCS | init / update(fill) / backtrack |

所有事件共用一套 `StepType`，并携带：

```json
{
  "step_id": 3,
  "type": "compare",
  "targets": [0, 1],
  "description": "比较 a[0]=5 与 a[1]=3",
  "code_line": 7,
  "visual_action": "compare",
  "state_before": {"kind": "array", "array": {"values": [5, 3, 8, 1]}},
  "state_after":  {"kind": "array", "array": {"values": [5, 3, 8, 1]}},
  "meta": {"values": [5, 3]}
}
```

`algoviz/protocol/events.py` 中的 Pydantic 模型会校验：

- `step_id` 从 0 连续递增；
- `state_before/state_after.kind` 与 `metadata.visual_kind` 一致；
- 所有字段 `extra="forbid"`，防止协议漂移。

## 7. 时间轴与同步

1. 脚本固定六段：问题引入 → 核心思想 → 执行过程（多段）→ 代码对应 → 复杂度 → 总结；
2. 执行过程按每段 3~5 步分组（可配置 `steps_per_segment`），最多约 14 段，控制视频长度；
3. 每段单独 TTS，并用 `ffprobe` 测量真实时长；
4. 场景在每个段落边界 `pad_to(start + duration)`，避免 Manim 帧取整导致的累计漂移；
5. 每段音频补齐/裁切到段落时长后顺序拼接，保证音画同步；
6. 字幕以段落为单位内嵌在画面底部，并导出 SRT。

## 8. 批量与任务状态

`jobs/db.py` 使用 SQLite，状态严格对应 `readme.md` 8.2：

```text
pending → parsing → executing → rendering → synthesizing → validating → completed
                                                              ↘ failed
```

- 单个任务失败只重试该任务（`ALGOVIZ_RETRIES`，默认 1 次）；
- 进程重启时，处于中间状态的任务会恢复为 `pending`；
- `algoviz jobs` 可查看进度、时长、是否已产出视频。

## 9. 配置

见 `.env.example`，常用项：

| 变量 | 默认 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 空 | 为空时使用本地讲解模板 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 模型 |
| `ALGOVIZ_AI_MODE` | `auto` | auto / off / on |
| `ALGOVIZ_TTS_PROVIDER` | `edge` | edge / sapi / silent |
| `ALGOVIZ_VOICE` | `zh-CN-XiaoxiaoNeural` | 音色 |
| `ALGOVIZ_THEME` | `dark` | dark / light |
| `ALGOVIZ_RESOLUTION` | `1920x1080` | 分辨率 |
| `ALGOVIZ_FPS` | `30` | 帧率 |
| `ALGOVIZ_WORKERS` | `2` | 并发数 |
| `ALGOVIZ_RETRIES` | `1` | 重试次数 |
| `ALGOVIZ_RENDER_QUALITY` | `high` | high / medium / low |

## 10. 质量检查

`qc.py` 在任务完成前检查：

- 文件大小、媒体可解析；
- 时长 > 5s 且与计划时长偏差 ≤ 1.5s；
- 有视频流，分辨率/帧率/编码符合预期（软警告）；
- 有音轨（开启配音时）；
- 算法独立校验通过；
- 抽 3 帧检查非空白。

`qc.ok=false` 会阻止任务标记为完成，错误写入 `meta.json` 与 `pipeline.log`。

## 10.5 Web GUI

`algoviz serve` 会同时启动 API 与内置 GUI（`algoviz/api/static/`，原生 HTML/CSS/JS，无需 Node 构建）：

- **新建任务**：自然语言 / 参数化两种模式；参数表单按算法默认值自动生成，数组用逗号分隔、图边用 JSON；
- **选项**：1080p/720p/480p、语音、主题、每段步骤数；
- **任务列表**：1.6s 轮询实时进度、状态、时长、算法校验、AI 徽标；完成后可直接预览视频、下载 SRT/事件 JSON；失败任务一键重试；
- **AI 设置**：查看 Key 是否配置（只显示掩码）、模型、Base URL、模式；测试连接；保存后立即热更新，无需重启；
- **批量任务**：粘贴/导入 JSON，前端自动合并 `defaults` 后提交；
- 大模型不可用时页面顶部显示黄色横幅，明确说明「当前使用本地模板」。

API 仍完整可用：`/docs` Swagger、`/api/v1/*`，静态页面只通过 `/static` 挂载。

界面截图：`output/gui_final.png`（任务列表与大模型状态）、`output/gui_ai.png`（AI 设置与连通性测试）。

## 11. 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
# 43 passed（含 GUI 静态页、AI 设置保存/掩码、调用用量统计）
```

覆盖 18 个算法的执行与校验、状态连续重放、JSON 往返、自然语言/伪代码解析、时间轴覆盖、字幕换行、批量文件、FastAPI 健康检查、TTS 文本规范化。

## 12. 与 `readme.md` 阶段计划的对照

| 阶段 | 状态 | 说明 |
|---|---|---|
| 一：MVP（排序/二分，自然语言→MP4） | ✅ | 5 种排序 + 2 种查找；完整音视频链路；参考实现校验 |
| 二：树/图/DP 与统一协议 | ✅ | 6 个树算法、3 个图算法、2 个 DP；四套可视化组件 |
| 三：批量、重试、API | ✅ | SQLite + 线程池 + FastAPI + 断点恢复 |
| 三：Python/Java/C++ 源码 AST 追踪与隔离 | ⏳ | 未实现；伪代码输入目前映射到标准算法 |
| Celery/Redis、MinIO、多语言 | ⏳ | 单机批量已由 SQLite + 线程池覆盖 |

## 13. 已知限制

- 无 LaTeX 依赖，因此不渲染数学公式，复杂度为纯文本；
- 演示规模有限制：数组 ≤16、图 ≤10 节点、背包容量 ≤12、字符串长度 ≤8；
- 图布局为圆形/自定义坐标，无条件导向自动布局；
- 未实现真正的通用伪代码解释器与不可信代码沙箱；
- 大模型讲解文本建议人工抽检；没有 Key 时讲解为本地模板，质量稳定但不够「个性化」。

## 15. 验收结果

`tasks/demo.json` 连续提交 10 个任务（覆盖 5 类算法），经失败重试与最终布局修复后全部通过：

| # | 视频 | 算法 | 时长 | 校验 |
|---|---|---|---|---|
| 1 | 冒泡排序：相邻交换 | bubble_sort | 126.5s | ✅ |
| 2 | 快速排序（自然语言解析） | quick_sort | 128.5s | ✅ |
| 3 | 归并排序：分治与合并 | merge_sort | 172.9s | ✅ |
| 4 | 二分查找：每次排除一半 | binary_search | 73.5s | ✅ |
| 5 | 二叉搜索树的中序遍历 | tree_inorder | 78.9s | ✅ |
| 6 | 二叉搜索树构建 | bst_build | 125.0s | ✅ |
| 7 | BFS 广度优先搜索 | bfs | 108.6s | ✅ |
| 8 | Dijkstra 最短路径 | dijkstra | 126.4s | ✅ |
| 9 | 0-1 背包：二维动态规划 | knapsack_01 | 136.0s | ✅ |
| 10 | 最长公共子序列 LCS | lcs | 146.6s | ✅ |

合计约 20.4 分钟成片，全部 1920×1080 / 30 FPS / H.264 + AAC，含中文配音与内嵌字幕。
清单见 `output/videos/MANIFEST.md`，每个任务的 `meta.json` / `qc.json` / `events.json` 位于 `output/jobs/<job_id>/`。

另外生成了一条 AI 模式验证视频 `output/videos/二分查找：有序数组中的对数级查找_f84672887a8a.mp4`：
`meta.ai_usage` 记录 `status=used`、`calls=2`（parse + narration）、`successes=2`，总结页显示
「AlgoViz · 讲解：DeepSeek deepseek-flash · binary_search」。GUI 任务卡片会显示「DeepSeek 已调用 · 2 次」。

验收过程中发现并修复的问题：

1. 自然语言任务进入批处理时 `Pipeline` 未触发解析（只接受显式算法）→ 已修复并用自然语言任务验证；
2. Dijkstra 距离面板调用不存在的 `scene.fmt` → 已补充；
3. Manim 中对 VGroup 与其子对象同时做动画导致文字漂移 → 改为只移动整组；
4. 字幕栏高度不足、合并缓冲区标签越界 → 调整布局并重渲染演示视频；
5. 测试使用生产任务库触发 `recover_interrupted()`，误伤运行中的任务 → 测试改用独立临时目录。

## 16. 参考项目

详见 `research/NOTES.md`。四个参考项目均克隆在 `research/vendor/`，仅用于设计研究，未复制其代码；运行依赖为 Manim CE 与 FFmpeg。
