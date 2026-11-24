<script setup lang="ts">
import { computed } from "vue";
import type { AnimationStep } from "../types";

const props = defineProps<{ step: AnimationStep | null }>();

const array = computed(() => props.step?.state_after.array ?? null);
const values = computed(() => array.value?.values ?? []);
const found = computed(() => new Set(array.value?.found_indices ?? []));
const pointers = computed(() => array.value?.pointers ?? {});
const activeRange = computed(() => array.value?.active_range ?? null);

function isInRange(index: number): boolean {
  const range = activeRange.value;
  if (!range || range.length !== 2) return true;
  return index >= range[0] && index <= range[1];
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

function pointerLabels(index: number): string[] {
  return Object.entries(pointers.value)
    .filter(([, value]) => Number(value) === index)
    .map(([name, value]) => `${name} = ${fmt(value)}`);
}
</script>

<template>
  <div class="array-wrap">
    <div v-if="values.length" class="array-cells">
      <div
        v-for="(value, index) in values"
        :key="index"
        class="array-cell"
        :class="{
          active: pointerLabels(index).length,
          found: found.has(index),
          'in-range': activeRange && isInRange(index),
          'outside-range': activeRange && !isInRange(index),
        }"
      >
        <span v-if="pointerLabels(index).length" class="array-pointer">
          {{ pointerLabels(index).join(" · ") }}
        </span>
        <span class="array-value">{{ fmt(value) }}</span>
        <span class="array-index">{{ index }}</span>
      </div>
    </div>
    <div v-else class="empty-state">空数组</div>
    <div v-if="array?.target !== null && array?.target !== undefined" class="array-target">
      target = {{ fmt(array.target) }}
    </div>
  </div>
</template>
