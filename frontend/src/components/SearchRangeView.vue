<script setup lang="ts">
import { computed } from "vue";
import type { AnimationStep } from "../types";

const props = defineProps<{ step: AnimationStep | null }>();

const array = computed(() => props.step?.state_after.array ?? null);
const pointers = computed(() => array.value?.pointers ?? {});
const activeRange = computed(() => array.value?.active_range ?? null);
const hasRange = computed(() => Array.isArray(activeRange.value) && activeRange.value.length === 2 && activeRange.value[0] <= activeRange.value[1]);
const rangeLabel = computed(() => {
  if (!hasRange.value || !activeRange.value) return "空区间";
  return `[${activeRange.value[0]}, ${activeRange.value[1]}]`;
});
const rangeSize = computed(() => (hasRange.value && activeRange.value ? activeRange.value[1] - activeRange.value[0] + 1 : 0));
const left = computed(() => pointers.value.left ?? "—");
const right = computed(() => pointers.value.right ?? "—");
const mid = computed(() => pointers.value.mid ?? "—");
const midValue = computed(() => {
  const index = pointers.value.mid;
  const values = array.value?.values ?? [];
  return index !== undefined && index >= 0 && index < values.length ? values[index] : "—";
});
</script>

<template>
  <div class="search-range">
    <div class="range-headline" data-testid="search-range-label">
      <span class="range-kicker">active range</span>
      <strong>{{ rangeLabel }}</strong>
      <span class="range-size">{{ rangeSize }} 个候选</span>
    </div>
    <div class="range-track">
      <div
        v-if="hasRange"
        class="range-fill"
        :style="{
          left: `${(activeRange![0] / Math.max(1, (array?.values.length ?? 1) - 1)) * 100}%`,
          width: `${(Math.max(1, rangeSize) / Math.max(1, array?.values.length ?? 1)) * 100}%`,
        }"
      ></div>
    </div>
    <div class="range-pointers">
      <div class="range-pointer left"><span>left</span><b>{{ left }}</b></div>
      <div class="range-pointer mid"><span>mid</span><b>{{ mid }}</b><small>nums[mid] = {{ midValue }}</small></div>
      <div class="range-pointer right"><span>right</span><b>{{ right }}</b></div>
    </div>
    <div class="range-note">
      每轮只保留可能包含 target 的闭区间；`left > right` 表示搜索结束。
    </div>
  </div>
</template>
