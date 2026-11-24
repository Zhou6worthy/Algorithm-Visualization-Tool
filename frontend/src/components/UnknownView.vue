<script setup lang="ts">
defineProps<{ kind: string }>();
</script>

<template>
  <div class="unknown-visual" data-testid="unknown-component">
    <strong>未知视觉组件</strong>
    <p>
      后端 VisualPlan 请求了未注册的组件类型 <code>{{ kind }}</code>。
      请检查前端 Component Registry 或后端 ComponentKind。
    </p>
  </div>
</template>
