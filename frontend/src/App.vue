<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { api, waitForRun } from "./api";
import { stepTypeLabel, usePlayback } from "./playback";
import type {
  CaseRunRecord,
  ClassroomDeck,
  Problem,
  Project,
  ProjectPayload,
  ProjectSummary,
  RunRecord,
  TestCase,
} from "./types";
import CodeEditor from "./components/CodeEditor.vue";
import PlaybackControls from "./components/PlaybackControls.vue";
import TeachingHintPanel from "./components/TeachingHintPanel.vue";
import TestCaseEditor from "./components/TestCaseEditor.vue";
import VisualHost from "./components/VisualHost.vue";

const SAMPLE_SOURCE = `def two_sum(nums, target):
    seen = {}
    for i, x in enumerate(nums):
        need = target - x
        if need in seen:
            return [seen[need], i]
        seen[x] = i
    return []
`;

const SAMPLE_PROBLEM: Problem = {
  title: "Two Sum · 哈希表",
  description:
    "给定一个整数数组 nums 和一个目标值 target，请找出数组中和为 target 的两个整数，并返回它们的下标。",
  idea:
    "遍历数组，用哈希表 seen 记录已经出现过的数字和下标。对当前数字 x，查找 target - x 是否已经出现；若命中，直接返回两个下标。",
  source: SAMPLE_SOURCE,
  language: "python",
  algorithm: "two_sum",
  source_style: "function",
};

function sampleCases(): TestCase[] {
  return [
    {
      case_id: "case_normal",
      name: "正常查找",
      input_data: { nums: [2, 7, 11, 15], target: 9 },
      expected_output: [0, 1],
      source: "user",
      description: "第二轮命中",
    },
    {
      case_id: "case_first",
      name: "第二个元素命中",
      input_data: { nums: [3, 2, 4], target: 5 },
      expected_output: [0, 1],
      source: "user",
      description: "",
    },
    {
      case_id: "case_none",
      name: "找不到答案",
      input_data: { nums: [1, 2, 3], target: 100 },
      expected_output: [],
      source: "user",
      description: "",
    },
    {
      case_id: "case_mismatch",
      name: "预期不一致",
      input_data: { nums: [1, 2, 3], target: 4 },
      expected_output: [1, 2],
      source: "user",
      description: "真实执行返回 [0, 2]",
    },
    {
      case_id: "case_ai_extra",
      name: "AI 补充边界用例",
      input_data: { nums: [1, 2], target: 3 },
      expected_output: [0, 1],
      source: "ai_generated",
      description: "边界补充",
    },
    {
      case_id: "case_invalid",
      name: "缺少 target",
      input_data: { nums: [1] },
      expected_output: null,
      source: "user",
      description: "输入校验失败，不生成假轨迹",
    },
  ];
}

const SAMPLE_BINARY_SOURCE = `def binary_search(nums, target):
    left, right = 0, len(nums) - 1
    while left <= right:
        mid = (left + right) // 2
        if nums[mid] == target:
            return mid
        if nums[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1
`;

const SAMPLE_BINARY_PROBLEM: Problem = {
  title: "Binary Search · 二分查找",
  description:
    "给定一个升序整数数组 nums 和一个目标值 target，返回 target 在数组中的下标；如果不存在，返回 -1。",
  idea:
    "维护闭区间 [left, right]。每轮取中点 mid，将 nums[mid] 与 target 比较：相等则命中；中间值偏小则排除左半区，偏大则排除右半区。",
  source: SAMPLE_BINARY_SOURCE,
  language: "python",
  algorithm: "binary_search",
  source_style: "function",
};

function binarySampleCases(): TestCase[] {
  return [
    {
      case_id: "bs_middle",
      name: "中间命中",
      input_data: { nums: [1, 3, 5, 7, 9, 11], target: 7 },
      expected_output: 3,
      source: "user",
      description: "目标位于中间位置",
    },
    {
      case_id: "bs_left",
      name: "左端命中",
      input_data: { nums: [1, 3, 5, 7, 9, 11], target: 1 },
      expected_output: 0,
      source: "user",
      description: "",
    },
    {
      case_id: "bs_right",
      name: "右端命中",
      input_data: { nums: [1, 3, 5, 7, 9, 11], target: 11 },
      expected_output: 5,
      source: "user",
      description: "",
    },
    {
      case_id: "bs_none",
      name: "目标不存在",
      input_data: { nums: [1, 3, 5, 7, 9, 11], target: 8 },
      expected_output: -1,
      source: "user",
      description: "区间最终为空",
    },
    {
      case_id: "bs_empty",
      name: "空数组",
      input_data: { nums: [], target: 5 },
      expected_output: -1,
      source: "user",
      description: "",
    },
    {
      case_id: "bs_ai_extra",
      name: "AI 补充目标小于所有元素",
      input_data: { nums: [2, 4, 6, 8], target: 1 },
      expected_output: -1,
      source: "ai_generated",
      description: "边界用例",
    },
  ];
}

const projects = ref<ProjectSummary[]>([]);
const project = ref<Project | null>(null);
const projectName = ref("新算法项目");
const problem = reactive<Problem>({ ...SAMPLE_PROBLEM, source: "" });
const cases = ref<TestCase[]>([]);
const run = ref<RunRecord | null>(null);
const runCases = ref<CaseRunRecord[]>([]);
const runHistory = ref<RunRecord[]>([]);
const deck = ref<ClassroomDeck | null>(null);
const loading = ref(false);
const saving = ref(false);
const running = ref(false);
const error = ref("");
const notice = ref("");
const savedSnapshot = ref("");

const playback = usePlayback(deck);
const {
  activeCaseId,
  stepIndex,
  speed,
  mode,
  playing,
  currentCase,
  currentStep,
  currentStepView,
  currentHint,
  stepCount,
  atEnd,
  totalSeconds,
  elapsedSeconds,
  progress,
} = playback;

const projectId = computed(() => project.value?.project_id ?? "");
const currentCaseStatus = computed(
  () => runCases.value.find((item) => item.case_id === currentCase.value?.case_id) ?? null,
);
const hasTrace = computed(() => stepCount.value > 0);
const activeLine = computed(() => currentStep.value?.code_line ?? null);
const currentCode = computed(() => deck.value?.code || problem.source);
const visualComponents = computed(() => deck.value?.visual_plan.components ?? []);
const algorithmEntry = computed(() => (problem.algorithm === "binary_search" ? "binary_search" : "two_sum"));
const payload = computed<ProjectPayload>(() => ({
  name: projectName.value.trim() || "未命名算法项目",
  problem: { ...problem },
  cases: cases.value.map((item) => ({ ...item, input_data: { ...item.input_data } })),
}));
const currentSnapshot = computed(() => JSON.stringify(payload.value));
const dirty = computed(() => Boolean(project.value) && currentSnapshot.value !== savedSnapshot.value);
const canRun = computed(() => Boolean(project.value) && Boolean(problem.source.trim()) && cases.value.length > 0);
const runStatusText = computed(() => {
  if (running.value) return "真实执行中";
  const status = run.value?.status;
  return status === "completed" ? "执行完成" : status === "failed" ? "执行失败" : status === "running" ? "执行中" : status === "queued" ? "排队中" : "尚未执行";
});
const runStatusClass = computed(() => {
  if (running.value) return "running";
  if (run.value?.status === "completed") return "ok";
  if (run.value?.status === "failed") return "bad";
  if (run.value?.status === "running" || run.value?.status === "queued") return "running";
  return "";
});

function cloneProblem(value: Problem): Problem {
  return { ...value };
}
function cloneCases(values: TestCase[]): TestCase[] {
  return values.map((item) => ({
    ...item,
    input_data: JSON.parse(JSON.stringify(item.input_data ?? {})) as Record<string, unknown>,
    expected_output: item.expected_output === undefined ? null : JSON.parse(JSON.stringify(item.expected_output)),
  }));
}

function applyProject(next: Project, options: { resetExecution?: boolean } = {}): void {
  project.value = next;
  projectName.value = next.name;
  Object.assign(problem, cloneProblem(next.problem));
  cases.value = cloneCases(next.cases);
  savedSnapshot.value = currentSnapshot.value;
  if (options.resetExecution !== false) {
    run.value = null;
    runCases.value = [];
    runHistory.value = [];
    deck.value = null;
  }
  activeLocalStorage(next.project_id);
}

function activeLocalStorage(id: string): void {
  try {
    localStorage.setItem("algoviz.workbench.project", id);
  } catch {
    // localStorage is optional; the server remains the source of truth.
  }
}

async function refreshProjects(): Promise<void> {
  try {
    projects.value = await api.listProjects();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

async function refreshRunHistory(): Promise<void> {
  if (!projectId.value) return;
  try {
    runHistory.value = await api.listRuns(projectId.value);
  } catch {
    runHistory.value = [];
  }
}

async function loadProject(projectIdValue: string): Promise<void> {
  if (!projectIdValue) return;
  loading.value = true;
  error.value = "";
  notice.value = "";
  try {
    const next = await api.getProject(projectIdValue);
    applyProject(next);
    await refreshRunHistory();
    if (next.last_run) {
      await loadRun(next.last_run.run_id, false);
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function loadProjects(): Promise<void> {
  await refreshProjects();
  let preferred = "";
  try {
    preferred = localStorage.getItem("algoviz.workbench.project") ?? "";
  } catch {
    preferred = "";
  }
  const selected = projects.value.find((item) => item.project_id === preferred) ?? projects.value[0];
  if (selected) await loadProject(selected.project_id);
}

async function createBlankProject(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const next = await api.createProject({
      name: "新算法项目",
      problem: {
        ...problem,
        source: "",
        title: problem.algorithm === "binary_search" ? "Binary Search · 二分查找" : "Two Sum",
      },
      cases: [],
    });
    applyProject(next);
    await refreshProjects();
    notice.value = "新项目已创建。填写题目、源码和测试用例后保存。";
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function createSampleProject(kind: "two_sum" | "binary_search" = "two_sum"): Promise<void> {
  loading.value = true;
  error.value = "";
  const binary = kind === "binary_search";
  try {
    const next = await api.createProject({
      name: binary ? "二分查找课堂示例" : "Two Sum 课堂示例",
      problem: { ...(binary ? SAMPLE_BINARY_PROBLEM : SAMPLE_PROBLEM) },
      cases: binary ? binarySampleCases() : sampleCases(),
    });
    applyProject(next);
    await refreshProjects();
    notice.value = binary
      ? "二分查找示例项目已创建，可直接点击执行。"
      : "Two Sum 示例项目已创建，可直接点击执行。";
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

function fillSample(kind: "two_sum" | "binary_search" = "two_sum"): void {
  const binary = kind === "binary_search";
  projectName.value = binary ? "二分查找课堂示例" : "Two Sum 课堂示例";
  Object.assign(problem, binary ? SAMPLE_BINARY_PROBLEM : SAMPLE_PROBLEM);
  cases.value = binary ? binarySampleCases() : sampleCases();
  notice.value = binary
    ? "二分查找示例已填入，点击保存项目后执行。"
    : "Two Sum 示例已填入，点击保存项目后执行。";
}

async function saveProject(): Promise<boolean> {
  if (!project.value) {
    try {
      const next = await api.createProject(payload.value);
      applyProject(next);
      await refreshProjects();
      return true;
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err);
      return false;
    }
  }
  saving.value = true;
  error.value = "";
  try {
    const executionStale = currentSnapshot.value !== savedSnapshot.value;
    const next = await api.updateProject(project.value.project_id, payload.value);
    applyProject(next, { resetExecution: executionStale });
    await refreshProjects();
    await refreshRunHistory();
    notice.value = "项目已保存。";
    return true;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
    return false;
  } finally {
    saving.value = false;
  }
}

async function executeRun(): Promise<void> {
  if (running.value) return;
  if (!project.value) {
    const created = await saveProject();
    if (!created) return;
  } else if (dirty.value) {
    const saved = await saveProject();
    if (!saved) return;
  }
  if (!project.value) return;
  if (!problem.source.trim()) {
    error.value = "请先输入 Python 源码。";
    return;
  }
  if (!cases.value.length) {
    error.value = "请至少添加一个测试用例。";
    return;
  }
  running.value = true;
  error.value = "";
  notice.value = "";
  try {
    const created = await api.createRun(project.value.project_id);
    run.value = created;
    const final = await waitForRun(created.run_id, {
      intervalMs: 500,
      onUpdate: (item) => {
        run.value = item;
      },
    });
    run.value = final;
    if (final.status === "failed") {
      throw new Error(final.error || "执行失败");
    }
    const [caseResults, envelope] = await Promise.all([
      api.getCases(final.run_id),
      api.getClassroom(final.run_id),
    ]);
    runCases.value = caseResults;
    deck.value = envelope.classroom;
    notice.value = "真实执行完成，已生成课堂演示数据。";
    await refreshProjects();
    await refreshRunHistory();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    running.value = false;
  }
}

async function loadRun(runId: string, showLoading = true): Promise<void> {
  if (showLoading) running.value = true;
  try {
    const record = await api.getRun(runId);
    run.value = record;
    if (record.status === "completed") {
      const [caseResults, envelope] = await Promise.all([api.getCases(runId), api.getClassroom(runId)]);
      runCases.value = caseResults;
      deck.value = envelope.classroom;
    } else {
      runCases.value = [];
      deck.value = null;
      if (record.status === "failed") error.value = record.error || "执行失败";
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    if (showLoading) running.value = false;
  }
}

function onProjectSelect(event: Event): void {
  const id = (event.target as HTMLSelectElement).value;
  if (id) void loadProject(id);
}

function onCaseUpdated(index: number, next: TestCase): void {
  cases.value[index] = next;
}
function addCase(): void {
  const suffix = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
  cases.value.push({
    case_id: `case_${suffix}`,
    name: `新用例 ${cases.value.length + 1}`,
    input_data: { nums: [2, 7, 11, 15], target: 9 },
    expected_output: [0, 1],
    source: "user",
    description: "",
  });
}
function removeCase(caseIdValue: string): void {
  cases.value = cases.value.filter((item) => item.case_id !== caseIdValue);
}
function caseStatus(caseIdValue: string): CaseRunRecord | null {
  return runCases.value.find((item) => item.case_id === caseIdValue) ?? null;
}
function selectCase(caseIdValue: string): void {
  if (!deck.value?.cases.some((item) => item.case_id === caseIdValue)) return;
  playback.loadCase(caseIdValue);
}
function caseStatusLabel(status: string | undefined): string {
  return status === "success"
    ? "执行成功"
    : status === "failed"
      ? "预期不一致"
      : status === "error"
        ? "执行错误"
        : status === "running"
          ? "执行中"
          : "未执行";
}
function caseStatusClass(status: string | undefined): string {
  return status === "success" ? "ok" : status === "failed" ? "warn" : status === "error" ? "bad" : "";
}
function fmt(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}
function shortTime(value: string | null | undefined): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return value;
  }
}
function isDeckCase(caseIdValue: string): boolean {
  return Boolean(deck.value?.cases.some((item) => item.case_id === caseIdValue));
}

function onKeydown(event: KeyboardEvent): void {
  const target = event.target as HTMLElement | null;
  if (target && (target.closest("input, textarea, select, .cm-editor") || target.isContentEditable)) return;
  if (event.code === "Space") {
    event.preventDefault();
    if (playing.value) playback.pause();
    else playback.play();
  } else if (event.code === "ArrowLeft") {
    event.preventDefault();
    playback.previous();
  } else if (event.code === "ArrowRight") {
    event.preventDefault();
    playback.next();
  } else if (event.code === "Home") {
    event.preventDefault();
    playback.reset();
  } else if (event.code === "End") {
    event.preventDefault();
    playback.seek(stepCount.value - 1);
  }
}

onMounted(() => {
  window.addEventListener("keydown", onKeydown);
  (window as unknown as Record<string, unknown>).__workbench = {
    getProjectId: () => project.value?.project_id ?? null,
    getRunId: () => run.value?.run_id ?? null,
    getStepIndex: () => stepIndex.value,
    getCaseId: () => activeCaseId.value,
    getPlaying: () => playing.value,
    getSpeed: () => speed.value,
    getDeck: () => deck.value,
    getRun: () => run.value,
    isDirty: () => dirty.value,
  };
  loadProjects();
});
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKeydown);
});
</script>

<template>
  <div class="app-shell">
    <header class="topbar panel">
      <div class="brand">
        <div class="brand-mark">AV</div>
        <div>
          <div class="brand-kicker">AI ALGORITHM VISUALIZER</div>
          <h1>AlgoViz Workbench</h1>
          <div class="brand-sub">算法备课 · 真实执行轨迹 · 课堂演示</div>
        </div>
      </div>
      <div class="project-switcher">
        <label class="small-label" for="project-select">当前项目</label>
        <select id="project-select" :value="projectId" data-testid="project-select" @change="onProjectSelect">
          <option value="">未选择项目</option>
          <option v-for="item in projects" :key="item.project_id" :value="item.project_id">
            {{ item.name }} · {{ item.title }}
          </option>
        </select>
        <span class="save-state" :class="{ dirty }">
          {{ dirty ? "有未保存修改" : project ? "已保存" : "" }}
        </span>
      </div>
      <div class="top-actions">
        <button class="ghost-button" type="button" data-testid="new-project-btn" @click="createBlankProject">
          ＋ 新建项目
        </button>
        <button class="ghost-button" type="button" :disabled="!project || saving" data-testid="save-project-btn" @click="saveProject">
          {{ saving ? "保存中…" : "保存项目" }}
        </button>
        <button
          class="primary-button top-run"
          type="button"
          :disabled="!canRun || running"
          data-testid="run-btn"
          @click="executeRun"
        >
          {{ running ? "真实执行中…" : "执行 / 生成演示" }}
        </button>
        <button class="ghost-button" type="button" disabled title="导出功能将在后续版本提供" data-testid="export-btn">
          导出 · 预留
        </button>
      </div>
    </header>

    <div v-if="error" class="toast error-toast" data-testid="error-toast">
      <span>{{ error }}</span>
      <button class="toast-close" type="button" @click="error = ''">×</button>
    </div>
    <div v-if="notice" class="toast notice-toast" data-testid="notice-toast">
      <span>{{ notice }}</span>
      <button class="toast-close" type="button" @click="notice = ''">×</button>
    </div>

    <section v-if="!project && !loading" class="welcome panel">
      <div class="welcome-kicker">AI Algorithm Teaching Assistant</div>
      <h2>从 AC 代码到可讲的算法课堂</h2>
      <p>
        输入 Python 解法与多个测试用例，系统会调用现有 M1～M3 引擎真实执行代码，
        生成独立的 ExecutionTrace、AnimationTrace、StepHint 和多用例课堂演示。
      </p>
      <div class="welcome-actions">
        <button class="primary-button" type="button" data-testid="welcome-new-btn" @click="createBlankProject">
          新建算法项目
        </button>
        <button class="ghost-button" type="button" data-testid="welcome-sample-btn" @click="createSampleProject('two_sum')">
          创建 Two Sum 示例项目
        </button>
        <button class="ghost-button" type="button" data-testid="welcome-binary-btn" @click="createSampleProject('binary_search')">
          创建二分查找示例项目
        </button>
      </div>
    </section>

    <main v-if="project" class="workspace" :class="{ 'is-loading': loading }">
      <aside class="left-column">
        <section class="panel input-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-eyebrow">01 · Problem</div>
              <h2>题目与算法输入</h2>
            </div>
            <div class="sample-links">
              <button class="link-button" type="button" data-testid="fill-sample-btn" @click="fillSample('two_sum')">
                Two Sum 示例
              </button>
              <button class="link-button" type="button" data-testid="fill-binary-btn" @click="fillSample('binary_search')">
                二分查找示例
              </button>
            </div>
          </div>
          <label class="field-label">
            项目名称
            <input v-model="projectName" class="text-input" data-testid="project-name" />
          </label>
          <label class="field-label">
            题目标题
            <input v-model="problem.title" class="text-input" data-testid="problem-title" />
          </label>
          <label class="field-label">
            题目描述
            <textarea v-model="problem.description" class="text-area" rows="3" data-testid="problem-description"></textarea>
          </label>
          <label class="field-label">
            解题思路
            <textarea v-model="problem.idea" class="text-area" rows="3" data-testid="problem-idea"></textarea>
          </label>
          <div class="form-grid">
            <label class="field-label">
              算法
              <select v-model="problem.algorithm" class="select-input" data-testid="problem-algorithm">
                <option value="two_sum">Two Sum · 哈希表</option>
                <option value="binary_search">Binary Search · 二分查找</option>
              </select>
            </label>
            <label class="field-label">
              语言
              <select v-model="problem.language" class="select-input" data-testid="problem-language">
                <option value="python">Python</option>
              </select>
            </label>
            <label class="field-label">
              代码形态
              <select v-model="problem.source_style" class="select-input" data-testid="problem-style">
                <option value="function">函数版 {{ algorithmEntry }}</option>
                <option value="leetcode_class">LeetCode 类版 Solution.{{ algorithmEntry }}</option>
              </select>
            </label>
          </div>
          <div class="code-heading">
            <span>算法源码</span>
            <span class="muted small">Python · 当前执行行会同步高亮</span>
          </div>
          <CodeEditor v-model="problem.source" :active-line="activeLine" data-testid="code-editor" />
        </section>

        <section class="panel cases-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-eyebrow">02 · Test Cases</div>
              <h2>测试用例 <span class="count-badge" data-testid="case-count">{{ cases.length }}</span></h2>
            </div>
            <button class="ghost-button compact" type="button" data-testid="add-case-btn" @click="addCase">
              ＋ 添加用例
            </button>
          </div>
          <div class="cases-scroll">
            <TestCaseEditor
              v-for="(item, index) in cases"
              :key="`${projectId}-${item.case_id}`"
              :model-value="item"
              :status="caseStatus(item.case_id)"
              :can-delete="cases.length > 1"
              @update:model-value="onCaseUpdated(index, $event)"
              @remove="removeCase"
            />
            <div v-if="!cases.length" class="empty-state">
              还没有测试用例。点击“添加用例”，输入 Two Sum 的 nums 与 target。
            </div>
          </div>
        </section>
      </aside>

      <section class="center-column">
        <div class="case-tabs" data-testid="case-tabs">
          <button
            v-for="item in cases"
            :key="item.case_id"
            class="case-tab"
            :class="{ active: activeCaseId === item.case_id, disabled: !isDeckCase(item.case_id) }"
            type="button"
            :disabled="!isDeckCase(item.case_id)"
            :data-case-id="item.case_id"
            @click="selectCase(item.case_id)"
          >
            <span>{{ item.name }}</span>
            <span
              class="status-badge"
              :class="caseStatusClass(caseStatus(item.case_id)?.status)"
            >
              {{ caseStatusLabel(caseStatus(item.case_id)?.status) }}
            </span>
          </button>
        </div>

        <section v-if="currentCase" class="case-summary panel">
          <div class="case-summary-main">
            <div class="panel-eyebrow">CURRENT CASE · 真实轨迹</div>
            <h2>{{ currentCase.name }}</h2>
            <div class="badge-row">
              <span class="badge blue">{{ currentCase.source === "ai_generated" ? "AI 补充" : "用户提供" }}</span>
              <span
                class="status-badge"
                :class="caseStatusClass(currentCase.status)"
              >{{ caseStatusLabel(currentCase.status) }}</span>
              <span class="badge" :class="currentCase.trace?.verified ? 'ok' : 'warn'">
                {{ currentCase.trace?.verified ? "轨迹已验证" : "轨迹未验证" }}
              </span>
            </div>
            <div class="case-summary-data">
              <span>input <code>{{ fmt(currentCase.input_data) }}</code></span>
              <span>expected <code>{{ fmt(currentCase.expected_output) }}</code></span>
              <span>actual <code>{{ fmt(currentCase.actual_output) }}</code></span>
            </div>
            <div v-if="currentCase.error" class="inline-error">{{ currentCase.error }}</div>
          </div>
          <div class="case-summary-side">
            <span class="metric-value">{{ stepCount }}</span>
            <span class="metric-label">真实步骤</span>
            <span class="muted small">{{ currentCase.run_id }}</span>
          </div>
        </section>

        <div v-if="currentCase && !hasTrace" class="panel no-trace-panel">
          <h2>该用例没有可播放轨迹</h2>
          <p>{{ currentCase.error || "执行输入或追踪失败，因此系统没有生成伪造的 AnimationTrace。" }}</p>
        </div>

        <div v-else-if="visualComponents.length" class="visual-grid" data-testid="visual-grid">
          <VisualHost
            v-for="spec in visualComponents"
            :key="spec.component_id"
            :spec="spec"
            :step="currentStep"
            :view="currentStepView"
            :code="currentCode"
          />
        </div>
        <div v-else class="panel visual-empty">
          <h2>还没有可视化计划</h2>
          <p>填写源码和测试用例后点击“执行 / 生成演示”，后端会通过算法 Profile 生成 VisualPlan。</p>
        </div>

        <section class="panel step-panel">
          <div class="step-panel-head">
            <div>
              <div class="panel-eyebrow">PLAYBACK POSITION</div>
              <h2 data-testid="step-title">
                {{ hasTrace ? `步骤 ${stepIndex + 1} / ${stepCount}` : "等待执行" }}
              </h2>
            </div>
            <span class="badge blue" data-testid="step-type">{{ stepTypeLabel(currentStep?.type) }}</span>
          </div>
          <p class="step-description" data-testid="step-description">
            {{ currentStep?.description || currentStep?.narration || "执行代码后，这里会显示真实执行步骤。" }}
          </p>
          <div class="step-meta">
            <span>code_line <b>{{ currentStep?.code_line ?? "—" }}</b></span>
            <span>step_id <b>{{ currentStep?.step_id ?? "—" }}</b></span>
            <span>trace <b>{{ currentCase?.trace?.metadata.execution_trace_id || "—" }}</b></span>
          </div>
        </section>
      </section>

      <aside class="right-column">
        <section class="panel run-panel">
          <div class="panel-heading compact">
            <div>
              <div class="panel-eyebrow">EXECUTION</div>
              <h2>执行状态</h2>
            </div>
            <span class="status-badge" :class="runStatusClass" data-testid="run-status">{{ runStatusText }}</span>
          </div>
          <div v-if="run" class="run-meta">
            <div><span class="muted">run_id</span><code>{{ run.run_id }}</code></div>
            <div><span class="muted">创建</span>{{ shortTime(run.created_at) }}</div>
            <div v-if="run.error" class="inline-error">{{ run.error }}</div>
            <div class="summary-chips" v-if="run.summary.case_count">
              <span class="summary-chip ok">{{ run.summary.success ?? 0 }} 成功</span>
              <span class="summary-chip warn">{{ run.summary.failed ?? 0 }} 不一致</span>
              <span class="summary-chip bad">{{ run.summary.error ?? 0 }} 错误</span>
              <span class="summary-chip">{{ run.summary.steps_total ?? 0 }} 步</span>
            </div>
          </div>
          <p v-else class="muted small">点击顶部“执行 / 生成演示”，后端会真实运行源码，并为每个用例生成独立轨迹。</p>
          <div v-if="running" class="loading-line"><span class="spinner"></span> 正在执行真实代码与生成课堂数据…</div>
          <div class="run-actions">
            <button class="ghost-button compact" type="button" :disabled="!canRun || running" data-testid="execute-panel-btn" @click="executeRun">
              {{ running ? "执行中…" : "执行当前项目" }}
            </button>
            <button class="ghost-button compact" type="button" :disabled="!project" @click="refreshRunHistory">
              刷新历史
            </button>
          </div>
          <div v-if="runHistory.length" class="run-history">
            <div class="run-history-title">最近执行</div>
            <button
              v-for="item in runHistory.slice(0, 5)"
              :key="item.run_id"
              class="run-history-row"
              type="button"
              @click="loadRun(item.run_id)"
            >
              <span class="status-dot" :class="item.status"></span>
              <span>{{ shortTime(item.created_at) }}</span>
              <span class="muted">{{ item.status }}</span>
            </button>
          </div>
        </section>

        <TeachingHintPanel :hint="currentHint" />
      </aside>
    </main>

    <div v-if="loading" class="loading-overlay"><span class="spinner"></span> 加载项目…</div>

    <PlaybackControls
      v-if="project"
      :step-index="stepIndex"
      :step-count="stepCount"
      :speed="speed"
      :playing="playing"
      :mode="mode"
      :elapsed="elapsedSeconds"
      :total="totalSeconds"
      :progress="progress"
      :has-trace="hasTrace"
      @previous="playback.previous"
      @next="playback.next"
      @play="playback.play"
      @auto-play="playback.autoPlay"
      @pause="playback.pause"
      @resume="playback.resume"
      @reset="playback.reset"
      @seek="playback.seek"
      @speed="playback.setSpeed"
    />
    <div v-if="project" class="shortcut-hint">快捷键：← / → 单步 · Space 播放/暂停 · Home 重置 · End 末尾</div>
  </div>
</template>
