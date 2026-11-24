# M1 交付报告：真实执行闭环（Two Sum）

> 范围：只做 M1，不包含 HTML 播放器、GUI、MP4 渲染、其他语义追踪器。  
> 旧 18 个算法路径未修改；旧 `Trace/AnimationStep/VisualState` 字段语义未改变，仅新增可选字段。

## 1. 状态

M1 已完成两个验收形态：

| 形态 | 入口 | 输出 | 真实事件 | 语义步骤 | 校验 |
|---|---|---|---|---|---|
| 普通函数 | `two_sum` | `[0, 1]` | 11 | 8 | 全部通过 |
| LeetCode 类 | `Solution.two_sum` | `[0, 1]` | 11 | 8 | 全部通过 |

产物：

- `output/m1/two_sum_function/execution.json`
- `output/m1/two_sum_function/animation_events.json`
- `output/m1/two_sum_class/execution.json`
- `output/m1/two_sum_class/animation_events.json`
- `output/m1/summary.json`

## 2. 新增与修改文件

### 新增

| 文件 | 作用 |
|---|---|
| `algoviz/protocol/execution.py` | ExecutionTrace / ExecutionEvent / BranchArc / SemanticOperation / StaticFacts |
| `algoviz/execution/__init__.py` | 执行层包 |
| `algoviz/execution/safe_serializer.py` | 无副作用 SafeSerializer |
| `algoviz/execution/python_adapter.py` | user_solution.py + harness.py 适配、行号映射 |
| `algoviz/execution/harness.py` | 独立调用入口、受控 frames/result 输出 |
| `algoviz/execution/collector.py` | Python `sys.settrace` 真实时序采集 |
| `algoviz/execution/static_analyzer.py` | AST 结构与 branch arc 标注 |
| `algoviz/execution/semantic.py` | Two Sum Semantic Tracer + GENERIC_LINE 降级 |
| `algoviz/execution/trace_adapter.py` | ExecutionTrace → 现有 Animation Trace |
| `algoviz/execution/validator.py` | 输出/帧/证据/哈希/终态校验 |
| `algoviz/execution/orchestrator.py` | M1 全链路编排 |
| `algoviz/execution/sandbox.py` | LocalSandbox + DockerSandbox 生命周期骨架 |
| `scripts/m1_two_sum.py` | M1 验收脚本 |
| `tests/test_m1_execution.py` | M1 测试（9 个用例） |
| `M1_REPORT.md` | 本报告 |

### 修改

| 文件 | 改动 |
|---|---|
| `algoviz/protocol/events.py` | 新增可选 `dict_state`、`variables`、`found_indices`、`source_kind`、`execution_trace_id`；`category` 增加 `custom` |
| `algoviz/protocol/teaching.py` | 未改动 |
| `tests/` | 新增 M1 测试；旧测试未改动 |

未改动：18 个 tracer、`verify.py`、TTS/FFmpeg、Manim 场景、SQLite、GUI。

## 3. 模块接口

### GenericTracer

```python
class GenericTracer(Protocol):
    def instrument(self, program: PreparedProgram, limits: TraceLimits) -> PreparedProgram: ...
    def collect(self, program: PreparedProgram, sandbox_result: SandboxResult,
                limits: TraceLimits) -> GenericTrace: ...
```

本实现：

- `algoviz/execution/collector.py` 的 `PythonTraceCollector`；
- 只在真正调用用户入口前安装 `sys.settrace`；
- line 事件记录 `locals_before`，由同一 frame 下一事件确认 `locals_after`；
- call/return/exception 单独记录；
- 不生成语义事件。

### PythonExecutionAdapter

```python
class PythonExecutionAdapter:
    def prepare(self, source: str, *, style: ExecutionStyle | str = "function",
                entry_point: str = "two_sum", args: list[Any] | None = None,
                kwargs: dict[str, Any] | None = None) -> PreparedProgram: ...
```

- `user_solution.py` 原样 bytes 写入；
- `harness.py` 独立文件，只负责加载/调用/输出；
- 追踪过滤 `filename == user_solution.py`，harness 不进入 trace；
- `source_map` 当前为恒等映射；用户行号 = trace 行号；
- 支持 function / leetcode_class；stdin 明确抛 `ExecutionAdapterError`（M1 不做）。

### SandboxRunner

```python
class SandboxRunner(Protocol):
    def run(self, prepared: PreparedProgram, work_dir: Path,
            limits: TraceLimits | None = None) -> SandboxResult: ...
```

- `LocalSandbox`：可信代码、独立 Python 进程、超时、stdout/stderr 上限；
- `DockerSandbox`：`create`（无 `--rm`）→ `start` → `wait` → `docker cp` 白名单 →
  `finally docker rm -f`；M1 仅生命周期骨架，不默认启用。

### SemanticTracer

```python
class TwoSumSemanticTracer:
    def analyze(self, generic: GenericTrace, static: StaticFacts,
                context: SemanticContext) -> SemanticResult: ...
```

- AST 提供结构：`for`、`if need in seen`、`seen[x] = i`、`return`；
- 运行时提供证据：执行过该行、`seen` 前后快照、分支 arc 的 `if_true/if_false`；
- 每个 `SemanticOperation.evidence_event_ids` 非空；
- 无法匹配时返回 `GENERIC_LINE`，不伪造 hash 操作。

### TraceAdapter

```python
class TwoSumTraceAdapter:
    def adapt(self, execution: ExecutionTrace) -> Trace: ...
```

- 只消费 `ExecutionTrace`，不重新执行；
- 代码行直接使用用户源码行号；
- 输出与现有 Manim 渲染器兼容的 `Trace`。

### SafeSerializer

```python
class SafeSerializer:
    def serialize(self, value: Any) -> SerializedValue: ...
    def serialize_locals(self, mapping: dict[str, Any]) -> dict[str, Any]: ...
```

规则：

- 精确内置类型优先；
- 不调用 `repr/str/property/__iter__/__len__`；
- TreeNode/ListNode 专用字段读取；
- dataclass 只读字段；
- 其他自定义对象返回 `unsupported`；
- 循环引用返回 `cycle`，大对象/超预算返回 `truncated`。

## 4. P0/P1 修正验证

### 4.1 `sys.settrace` 时序

真实事件（函数版）：

```text
1 CALL line1  nums,target
2 LINE line2  before nums,target          after seen={}
3 LINE line3  before seen={}              after i=0,x=2
4 LINE line4  before i=0,x=2              after need=7
5 LINE line5  before seen={} need=7       after same; arc 5→7 if_false
6 LINE line7  before seen={}              after seen={2:0}; arc 7→3 loop_back
7 LINE line3  before seen={2:0},i=0,x=2,need=7   after i=1,x=7
8 LINE line4  before i=1,x=7,need=7       after need=2
9 LINE line5  before seen={2:0},need=2    after same; arc 5→6 if_true
10 LINE line6 before need=2               after same
11 RETURN line6 return [0,1]
```

`execution.json` 中 `line2.locals_before` 不含 `seen`，`line2.locals_after` 才含 `seen={}`；`line7.locals_after` 才含 `seen={2:0}`。

### 4.2 TRACE_INCOMPLETE

测试代码：

```python
import sys
def two_sum(nums, target):
    sys.settrace(None)
    return [0, 1]
```

结果：

- `status = trace_incomplete`
- `trace_complete = false`
- `validation.trace_verified = false`
- 事件只有 call + line，缺少 return 终态

同进程追踪局限（LocalSandbox 只用于可信代码）：

- 用户代码可调用 `sys.settrace(None)` 或安装自己的 tracer；
- 可读 `sys.argv`、尝试关闭事件文件；
- 因此 LocalSandbox **不能抵御恶意代码**；生产必须用 Docker。

### 4.3 SafeSerializer

测试覆盖：

- `Evil.__repr__` 抛异常、property 抛异常 → 返回 `unsupported`，没有调用用户方法；
- `Hostile.__getattribute__` 抛异常 → 返回 `unsupported`；
- TreeNode / ListNode → 专用字段展开；
- 自引用 list → `$cycle`；
- dataclass → 字段展开。

### 4.4 哈希查找状态

- 第 1 次 lookup：`state_before.dict_state.lookup_status = null` → `state_after = miss`
- 第 2 次 lookup：`state_before = null` → `state_after = hit`
- 第 1 次 miss 后执行 insert：`seen={2:0}`
- 第 2 次 hit 后立即 return：**没有第二次 insert，`seen` 仍只有 `{2:0}`**

### 4.5 Docker 生命周期

`DockerSandbox` 测试（fake docker command）：

- create 命令不含 `--rm`；
- 顺序为 `create → start → wait → cp → rm -f`；
- cp 失败/超时仍执行 `rm -f`；
- 容器名一致；
- 只 cp `frames.jsonl`、`result.json` 两个白名单文件。

M1 未连接真实 Docker daemon；真实 Docker 集成属于 M3。

## 5. 测试结果

```text
pytest -q
52 passed
```

包含：

- 旧 43 个测试全部通过；
- M1 新增 9 个测试：

```text
test_safe_serializer_no_side_effects_and_cycles
test_safe_serializer_nodes_and_hostile_objects
test_adapter_keeps_user_source_exact
test_two_sum_function_real_trace
test_two_sum_leetcode_class
test_trace_incomplete_when_user_disables_settrace
test_output_mismatch_rejected
test_docker_lifecycle_copies_then_removes
test_docker_cleanup_on_copy_failure
```

## 6. 已知限制 / 未解决问题

1. **LocalSandbox 不是安全边界**：同进程追踪，用户可关闭/替换 tracer、读写 argv；只能用于可信代码。生产 Docker 后端在 M3 完成并验收。
2. **Docker 未真实运行**：M1 只验证命令生命周期与清理；需 M3 在 Docker Desktop/daemon 上测试网络、内存、CPU、OOM、输出限制。
3. **只支持 Two Sum 语义**：其他算法只有 `GENERIC_LINE` 降级；M1 按要求不开发新语义追踪器。
4. **不支持 stdin / Java / C++**：适配器预留接口，当前显式拒绝。
5. **行号映射是恒等映射**：user_solution.py 保持原样，因此当前不需要偏移；Java/C++/需要前置 prelude 的语言必须实现 source map。
6. **异常/栈展开的边界情况**：`exception` 后 `return` 的 unwind 标记已实现，但复杂异常链未覆盖测试。
7. **SafeSerializer 通用自定义对象**：默认 `unsupported`（符合安全要求），不会展示任意字段；如未来要展示，需要显式白名单 serializer。
8. **LocalSandbox 输出上限**是执行后检查，不是实时 kill；M3 Docker 使用 tmpfs/输出白名单和宿主 supervisor。
9. **复杂度讲解**未在 M1 实现；M2 再做 theory/user-code/observed 三分解。
10. **HTML/MP4/GUI**不在 M1；当前只输出 `execution.json` 与 `animation_events.json`。

## 7. 复现命令

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\m1_two_sum.py
```
