<script setup lang="ts">
import { computed } from "vue";
import type { ClassroomStepView } from "../types";

const props = defineProps<{ view: ClassroomStepView | null }>();
const variables = computed(() => props.view?.variables ?? []);
</script>

<template>
  <div v-if="variables.length" class="variable-grid">
    <div
      v-for="item in variables"
      :key="item.label"
      class="variable-row"
      :class="{ changed: item.changed }"
    >
      <span class="variable-label">{{ item.label }}</span>
      <span class="variable-value">{{ item.value }}</span>
    </div>
  </div>
  <div v-else class="empty-state">暂无变量</div>
</template>
