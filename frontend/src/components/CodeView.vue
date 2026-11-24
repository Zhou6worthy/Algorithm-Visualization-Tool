<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ code: string; activeLine?: number | null }>();
const lines = computed(() => (props.code ? props.code.replace(/\r\n/g, "\n").split("\n") : []));
</script>

<template>
  <div class="code-view">
    <div v-if="!lines.length" class="empty-state">暂无源码</div>
    <template v-else>
      <div
        v-for="(line, index) in lines"
        :key="index"
        class="code-view-line"
        :class="{ active: props.activeLine === index + 1 }"
      >
        <span class="code-view-no">{{ index + 1 }}</span>
        <span class="code-view-text">{{ line || " " }}</span>
      </div>
    </template>
  </div>
</template>
