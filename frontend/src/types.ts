export type CaseSource = "user" | "ai_generated";
export type RunStatus = "queued" | "running" | "completed" | "failed";

export interface Problem {
  title: string;
  description: string;
  idea: string;
  source: string;
  language: "python";
  algorithm: string;
  source_style: "function" | "leetcode_class";
}

export interface TestCase {
  case_id: string;
  name: string;
  input_data: Record<string, unknown>;
  expected_output: unknown;
  source: CaseSource;
  description: string;
}

export interface ProjectPayload {
  name: string;
  problem: Problem;
  cases: TestCase[];
}

export interface LastRun {
  run_id: string;
  status: RunStatus;
  created_at: string;
  finished_at?: string | null;
}

export interface Project extends ProjectPayload {
  project_id: string;
  created_at: string;
  updated_at: string;
  last_run: LastRun | null;
}

export interface ProjectSummary {
  project_id: string;
  name: string;
  title: string;
  algorithm: string;
  updated_at: string;
  case_count: number;
  last_run_status: RunStatus | null;
}

export interface RunSummary {
  case_count?: number;
  success?: number;
  failed?: number;
  error?: number;
  trace_count?: number;
  steps_total?: number;
}

export interface RunRecord {
  run_id: string;
  project_id: string;
  status: RunStatus;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
  summary: RunSummary;
  project_name: string;
  problem_title: string;
}

export type CaseRunStatus = "pending" | "running" | "success" | "failed" | "error";

export interface CaseRunRecord {
  case_id: string;
  name: string;
  source: CaseSource;
  status: CaseRunStatus;
  expected_output: unknown;
  actual_output: unknown;
  error?: string | null;
  step_count: number;
  execution_trace_id?: string | null;
  animation_trace_id?: string | null;
}

// AnimationTrace / VisualState, intentionally mirrors algoviz.protocol.events.
export interface ArrayState {
  values: Array<string | number>;
  sorted_indices?: number[];
  active_range?: number[] | null;
  pointers?: Record<string, number>;
  target?: unknown;
  found_index?: number | null;
  aux?: unknown[] | null;
  found_indices?: number[];
}

export interface DictEntryView {
  key: string;
  value: unknown;
  highlighted?: boolean;
}

export interface DictState {
  title?: string;
  entries: DictEntryView[];
  lookup_key?: string | null;
  lookup_status?: "hit" | "miss" | null;
  highlighted_keys?: string[];
}

export interface VariableView {
  name: string;
  type?: string;
  value: string;
  changed?: boolean;
  truncated?: boolean;
}

export interface VisualState {
  kind: string;
  array?: ArrayState | null;
  dict_state?: DictState | null;
  variables?: VariableView[];
  note?: string | null;
}

export interface AnimationStep {
  step_id: number;
  type: string;
  targets: Array<string | number>;
  description: string;
  narration?: string;
  code_line?: number | null;
  duration?: number | null;
  visual_action?: string;
  state_before: VisualState;
  state_after: VisualState;
  meta?: Record<string, unknown>;
}

export interface TraceMetadata {
  algorithm: string;
  title: string;
  category: string;
  visual_kind: string;
  execution_trace_id?: string | null;
  code?: string;
}

export interface AnimationTrace {
  schema_version: string;
  metadata: TraceMetadata;
  steps: AnimationStep[];
  result: Record<string, unknown>;
  verified: boolean;
  verification_notes: string[];
}

export interface StepHint {
  hint_id: string;
  related_step_id: number;
  kind: string;
  title: string;
  explanation: string;
  common_mistake: string;
  question: string;
  answer: string;
  concepts: string[];
}

export interface ClassroomVariable {
  label: string;
  value: string;
  changed: boolean;
}

export interface ClassroomStepView {
  step_id: number;
  variables: ClassroomVariable[];
}

export interface ClassroomCase {
  case_id: string;
  run_id: string;
  name: string;
  source: CaseSource;
  status: CaseRunStatus;
  input_data: Record<string, unknown>;
  expected_output: unknown;
  actual_output: unknown;
  error?: string | null;
  trace: AnimationTrace | null;
  hints: StepHint[];
  step_views: ClassroomStepView[];
}

export interface ComponentSpec {
  component_id: string;
  kind: string;
  slot: string;
  title: string;
  options: Record<string, unknown>;
}

export interface LayoutBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface VisualPlan {
  schema_version: string;
  components: ComponentSpec[];
  slots: Record<string, LayoutBox>;
  theme: string;
}

export interface ClassroomDeck {
  schema_version: string;
  title: string;
  algorithm: string;
  code: string;
  code_language: string;
  visual_plan: VisualPlan;
  cases: ClassroomCase[];
  active_case_id: string;
  default_step_duration: number;
}

export interface ClassroomEnvelope {
  run: RunRecord;
  cases: CaseRunRecord[];
  classroom: ClassroomDeck;
}

export interface ApiError {
  detail?: string;
  message?: string;
}
