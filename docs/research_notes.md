# 开源项目调研记录

调研时间：2026-11-15  
目的：验证 `readme.md` 的技术路线，决定哪些项目可直接研究、哪些只借鉴思路。

四个参考仓库已浅克隆到 `research/vendor/`（不参与运行）：

```powershell
git clone --depth 1 https://github.com/jerrybuks/algo-visuals research/vendor/algo-visuals
git clone --depth 1 https://github.com/browser-use/video-use research/vendor/video-use
git clone --depth 1 https://github.com/HoltzTomas/claiss research/vendor/claiss
git clone --depth 1 https://github.com/theabbie/ManimFlow research/vendor/ManimFlow
```

> 注意：以下仅为研究结论，本项目没有复制这些仓库的代码；运行依赖是 Manim CE 与 FFmpeg。

## 1. Algo LightsOn / algo-visuals

- 仓库：https://github.com/jerrybuks/algo-visuals
- 栈：FastAPI + Manim CE + Edge TTS（可切换 MiniMax/OpenAI/ElevenLabs）+ FFmpeg + OpenRouter LLM
- 链路：LLM 写旁白和算法元数据 → 逐句 TTS → 测时长 → LLM 生成 Manim 场景代码 → 渲染 → FFmpeg 混音 → Cloudinary
- 亮点：
  - 任务状态机与 SSE 进度；
  - 8 种 visual_type（数组、递归拆分合并、树、图、矩阵等）作为风格指南；
  - 对生成代码做确定性修补与静态检查，渲染失败回喂错误重试；
  - TTS 失败静音降级，不阻塞视频。
- 局限：
  - 动画代码由 LLM 自由生成，正确性和稳定性依赖重试与提示词；
  - **仓库没有 LICENSE 文件**（默认版权保留），因此本项目只阅读其架构与接口设计，不复制代码；
  - 依赖 Cloudinary/Supabase 才能完整运行。
- 本项目的取舍：借鉴「段落时长驱动动画」「TTS 降级」「状态机」；把 LLM 生成 Manim 代码替换成**确定性事件 + 固定模板**，并增加独立算法校验。

## 2. Manim Video Skill（video-use）

- 仓库：https://github.com/browser-use/video-use（`skills/manim-video`）
- 许可证：MIT
- 内容：面向 Agent 的 Manim 生产规范，包含场景规划、mobjects、动画、排版、渲染、排查等 15 份参考文档。
- 借鉴：
  - 分层透明度（主元素 1.0、上下文 0.4、结构 0.15）；
  - 呼吸感与留白、统一字体与配色；
  - 「先叙事后代码」的场景规划顺序。
- 未采用：Agent 生成—渲染—纠错循环（本项目模板固定，不需要生成代码）。

## 3. Claiss

- 仓库：https://github.com/HoltzTomas/claiss
- 许可证：MIT
- 栈：Next.js + Manim 0.18 + Modal 无服务器编译 + Vercel Blob
- 定位：AI 辅助 Manim 动画工具，支持场景预览、编辑、排序、合并。
- 借鉴：后续做「人工审核 / 场景重排 / 批量归档」的产品形态。
- 未采用：前端与 Modal 编译（本地批量渲染更简单）。

## 4. ManimFlow

- 仓库：https://github.com/theabbie/ManimFlow
- 许可证：MIT
- 栈：Streamlit + Pi Agent + Manim + FFmpeg + AbbieSpeak 语音
- 亮点：
  - Agent 在隔离工作区生成、渲染、根据错误自动修复；
  - 布局审计（重叠、越界、拥挤）并回喂给 Agent；
  - 失败时保留上一个有效视频。
- 借鉴：布局审计思路（本项目通过固定模板避免大部分布局问题）；失败任务保留中间产物的做法。
- 未采用：Agent 自动修复（会引入不可控的代码执行风险）。

## 5. Manim CE / Motion Canvas

- Manim CE：MIT，Python，算法/数学动画生态成熟，本项目的实际渲染引擎。
- Motion Canvas：MIT，TypeScript，实时预览体验好，但跨语言集成成本高。
- 结论：选择 Manim CE；Windows 上 `pycairo`、`manimpango` 均有 cp312 预编译 wheel，安装无需系统 Cairo/Pango。

## 6. 最终决定

| 维度 | 决定 |
|---|---|
| 动画 | Manim CE + 自研事件驱动模板（不生成动画代码） |
| 算法执行 | 自研五类追踪器 + 独立参考实现校验 |
| 协议 | Pydantic v2，严格字段与状态连续性校验 |
| 大模型 | DeepSeek（OpenAI 兼容），失败自动回退本地模板 |
| TTS | Edge TTS（在线）→ Windows SAPI（离线）→ 静音 |
| 合成 | FFmpeg（H.264 + AAC，MP4 faststart） |
| 批量 | SQLite + 线程池（单机足够；Celery/Redis 留作规模化扩展） |
| 参考项目 | 只研究思路，不复制代码；运行依赖许可证均为 MIT（Manim CE、FFmpeg） |
