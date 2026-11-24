<script setup lang="ts">
import { computed } from "vue";
import type { AnimationStep } from "../types";

const props = defineProps<{ step: AnimationStep | null }>();

const dict = computed(() => props.step?.state_after.dict_state ?? null);
const entries = computed(() => dict.value?.entries ?? []);
const lookupKey = computed(() => dict.value?.lookup_key ?? null);
const lookupStatus = computed(() => dict.value?.lookup_status ?? null);
const freshKey = computed(() => {
  const step = props.step;
  if (!step || step.type !== "update") return "";
  return String(step.meta?.key ?? "");
});

function fmt(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function isHit(entry: { key: string; highlighted?: boolean }): boolean {
  return Boolean(entry.highlighted) || (lookupStatus.value === "hit" && String(lookupKey.value) === String(entry.key));
}
</script>

<template>
  <div class="hash-body">
    <div v-if="!entries.length" class="empty-state">{ } 空哈希表</div>
    <div v-else class="table-scroll">
      <table class="data-table">
        <thead>
          <tr><th>key</th><th>value</th></tr>
        </thead>
        <tbody>
          <tr
            v-for="entry in entries"
            :key="entry.key"
            :class="{ hit: isHit(entry), fresh: String(freshKey) === String(entry.key) }"
          >
            <td>{{ entry.key }}</td>
            <td>{{ fmt(entry.value) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="lookup-row">
      <template v-if="lookupKey !== null">
        <span>查找 <b>{{ lookupKey }}</b> →</span>
        <span class="pill" :class="lookupStatus === 'hit' ? 'hit' : lookupStatus === 'miss' ? 'miss' : 'none'">
          {{ lookupStatus === "hit" ? "HIT" : lookupStatus === "miss" ? "MISS" : "—" }}
        </span>
      </template>
      <span v-else class="pill none">等待下一次查找</span>
    </div>
  </div>
</template>
