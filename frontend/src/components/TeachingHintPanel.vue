<script setup lang="ts">
import { ref, watch } from "vue";
import type { StepHint } from "../types";

const props = defineProps<{ hint: StepHint | null }>();
const answerOpen = ref(false);

watch(
  () => props.hint,
  () => {
    answerOpen.value = false;
  },
);
</script>

<template>
  <section class="panel hint-panel" data-testid="hint-panel">
    <div class="panel-eyebrow">教学提示</div>
    <template v-if="hint">
      <h2 class="hint-title" data-testid="hint-title">{{ hint.title }}</h2>
      <p class="hint-explanation" data-testid="hint-explanation">{{ hint.explanation }}</p>
      <div class="hint-block">
        <span class="hint-label">常见错误</span>
        <p>{{ hint.common_mistake || "—" }}</p>
      </div>
      <div class="hint-block question">
        <span class="hint-label">课堂提问</span>
        <p data-testid="hint-question">{{ hint.question || "—" }}</p>
      </div>
      <button
        v-if="hint.answer"
        class="ghost-button hint-toggle"
        type="button"
        data-testid="hint-toggle"
        @click="answerOpen = !answerOpen"
      >
        {{ answerOpen ? "收起参考答案" : "显示参考答案" }}
      </button>
      <div v-if="hint.answer && answerOpen" class="hint-answer" data-testid="hint-answer">
        {{ hint.answer }}
      </div>
    </template>
    <template v-else>
      <h2 class="hint-title muted">本步骤暂无教学提示</h2>
      <p class="hint-explanation">当前执行步骤没有附带教学素材。继续播放或选择有提示的步骤。</p>
    </template>
  </section>
</template>
