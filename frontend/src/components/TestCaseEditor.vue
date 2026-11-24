<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { CaseRunRecord, TestCase } from "../types";

const props = defineProps<{
  modelValue: TestCase;
  status?: CaseRunRecord | null;
  canDelete?: boolean;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: TestCase];
  remove: [caseId: string];
}>();

const inputText = ref("");
const expectedText = ref("");
const inputError = ref("");
const expectedError = ref("");
const source = computed({
  get: () => props.modelValue.source,
  set: (value: "user" | "ai_generated") => patch({ source: value }),
});

function formatInput(value: Record<string, unknown>): string {
  return JSON.stringify(value ?? {}, null, 2);
}
function formatExpected(value: unknown): string {
  if (value === null || value === undefined) return "";
  return JSON.stringify(value, null, 2);
}
function syncText(): void {
  inputText.value = formatInput(props.modelValue.input_data);
  expectedText.value = formatExpected(props.modelValue.expected_output);
  inputError.value = "";
  expectedError.value = "";
}
watch(() => props.modelValue.case_id, syncText, { immediate: true });

function patch(update: Partial<TestCase>): void {
  emit("update:modelValue", { ...props.modelValue, ...update });
}

function onName(event: Event): void {
  patch({ name: (event.target as HTMLInputElement).value });
}
function onInputJson(event: Event): void {
  const text = (event.target as HTMLTextAreaElement).value;
  inputText.value = text;
  try {
    const parsed = JSON.parse(text);
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("input_data 必须是 JSON 对象");
    }
    inputError.value = "";
    patch({ input_data: parsed as Record<string, unknown> });
  } catch (error) {
    inputError.value = error instanceof Error ? error.message : "JSON 格式错误";
  }
}
function onExpectedJson(event: Event): void {
  const text = (event.target as HTMLTextAreaElement).value;
  expectedText.value = text;
  if (!text.trim()) {
    expectedError.value = "";
    patch({ expected_output: null });
    return;
  }
  try {
    const parsed = JSON.parse(text);
    expectedError.value = "";
    patch({ expected_output: parsed });
  } catch (error) {
    expectedError.value = error instanceof Error ? error.message : "JSON 格式错误";
  }
}

const statusLabel = computed(() => {
  const status = props.status?.status;
  return status === "success"
    ? "执行成功"
    : status === "failed"
      ? "预期不一致"
      : status === "error"
        ? "执行错误"
        : status === "running"
          ? "执行中"
          : "未执行";
});
const statusClass = computed(() => {
  const status = props.status?.status;
  return status === "success" ? "ok" : status === "failed" ? "warn" : status === "error" ? "bad" : "";
});
</script>

<template>
  <article class="case-card" :data-case-id="modelValue.case_id" data-testid="case-card">
    <div class="case-card-head">
      <input
        class="case-name-input"
        :value="modelValue.name"
        data-testid="case-name"
        aria-label="用例名称"
        @input="onName"
      />
      <span class="status-badge" :class="statusClass" data-testid="case-status">{{ statusLabel }}</span>
    </div>
    <div class="case-meta-row">
      <label class="small-label">
        来源
        <select v-model="source" data-testid="case-source">
          <option value="user">用户提供</option>
          <option value="ai_generated">AI 补充</option>
        </select>
      </label>
      <span class="case-id">{{ modelValue.case_id }}</span>
      <button
        class="ghost-button danger-text"
        type="button"
        :disabled="!canDelete"
        data-testid="delete-case-btn"
        @click="emit('remove', modelValue.case_id)"
      >
        删除
      </button>
    </div>
    <label class="small-label">
      input_data
      <textarea
        v-model="inputText"
        class="json-input"
        rows="4"
        spellcheck="false"
        data-testid="case-input"
        @input="onInputJson"
      ></textarea>
      <span v-if="inputError" class="field-error">{{ inputError }}</span>
    </label>
    <label class="small-label">
      expected_output
      <textarea
        v-model="expectedText"
        class="json-input"
        rows="2"
        spellcheck="false"
        placeholder="留空表示不做输出校验"
        data-testid="case-expected"
        @input="onExpectedJson"
      ></textarea>
      <span v-if="expectedError" class="field-error">{{ expectedError }}</span>
    </label>
    <div v-if="status" class="case-result">
      <span>actual：<code>{{ status.actual_output === null || status.actual_output === undefined ? "—" : JSON.stringify(status.actual_output) }}</code></span>
      <span v-if="status.error" class="case-error">{{ status.error }}</span>
    </div>
  </article>
</template>
