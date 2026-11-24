# AlgoViz Workbench

**AI 算法课堂备课与演示辅助工具。**  
教师输入题目、解题思路、Python 源码和多个测试用例，系统真实执行代码，生成执行轨迹与课堂可视化，教师可以在课堂上手动控制或自动播放。

> 这不是“安全执行任意陌生人代码”的在线判题平台。当前只面向本机、可信代码的个人备课场景，LocalSandbox 不是生产级安全沙箱。

## 快速启动

```powershell
cd D:\work\算法可视化工具
.\.venv\Scripts\python.exe -m uvicorn algoviz.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000/
```

旧版视频工厂保留在 `http://127.0.0.1:8000/legacy`。

## 当前能力

- Two Sum：真实执行、ExecutionTrace、AnimationTrace、多用例、课堂播放、教学提示。
- 第二算法（二分查找）：真实执行、独立语义适配、AlgorithmProfile、VisualPlan 动态组件、课堂提示。
- Vue 3 + TypeScript 工作台：CodeMirror 源码编辑、测试用例管理、SQLite 项目持久化、刷新恢复。
- 后端 FastAPI：项目/运行/课堂数据 API。
- 前端播放器：上一步/下一步/时间轴/自动播放/暂停/继续/速度/切换用例。
- 原有 M1/M2/M3 视频生成与 M3-8 课堂 HTML 保留。

## 目录

```text
algoviz/                 Python 后端（M1/M2/M3/M4/M5）
  algorithms/            算法 Profile 注册
  execution/             执行、追踪、语义适配
  protocol/              统一数据协议
  teaching/              教学计划、提示、课堂数据
  workbench/             M4/M5 工作台 API 与 SQLite
  api/                   FastAPI 应用与前端静态资源
frontend/                Vue 3 + TypeScript + Vite 前端
tests/                   pytest 测试
scripts/                 演示、回归与浏览器 E2E 脚本
docs/                    需求、架构文档、历史报告、M5 报告
output/                  生成产物与回归证据（不参与源码发布）
```

## 文档

- [文档索引](docs/README.md)
- [M5 需求](docs/requirements/M5.md)
- [M5 实施报告](docs/reports/M5_IMPLEMENTATION_REPORT.md)
- [M5 架构审查](docs/architecture/M5_ARCHITECTURE_REVIEW.md)
- [M4 实施报告](docs/reports/M4_IMPLEMENTATION_REPORT.md)
- [M3-6～M3-8 实施报告](docs/reports/M3_6_TO_M3_8_IMPLEMENTATION_REPORT.md)

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
# M5: 119 passed
```

前端 unit / typecheck：

```powershell
cd frontend
npm run test:unit
npm run typecheck
```

真实浏览器 E2E：

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe scripts\m5_browser_check.py
```

## 前端开发

需要 Node.js 20+（本机可用 `D:\Program_Files_\nvm\v24.19.0`）：

```powershell
cd frontend
npm install
npm run dev
```

Vite 地址：`http://127.0.0.1:5173/static/workbench/`

生产构建：

```powershell
npm run typecheck
npm run build
```

构建产物写入 `algoviz/api/static/workbench/`，由 FastAPI 在 `/` 提供。

## 安全边界

- 默认只监听 `127.0.0.1`。
- 当前 `LocalSandbox` 通过子进程和资源限制运行本机可信代码，**不构成对陌生代码、学生提交或网络上传代码的安全隔离**。
- 如果要开放给其他用户，必须先设计 Docker/系统级隔离、资源配额、网络禁用和安全审计，不能直接暴露现有执行接口。
