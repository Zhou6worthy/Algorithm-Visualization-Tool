<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  stepIndex: number;
  stepCount: number;
  speed: number;
  playing: boolean;
  mode: "teacher" | "auto";
  elapsed: number;
  total: number;
  progress: number;
  hasTrace: boolean;
}>();
const emit = defineEmits<{
  previous: [];
  next: [];
  play: [];
  autoPlay: [];
  pause: [];
  resume: [];
  reset: [];
  seek: [value: number];
  speed: [value: number];
}>();

const maxStep = computed(() => Math.max(0, props.stepCount - 1));
const currentLabel = computed(() =>
  props.hasTrace ? `步骤 ${props.stepIndex + 1} / ${props.stepCount}` : "步骤 0 / 0",
);
</script>

<template>
  <footer class="playback-bar" data-testid="playback-controls">
    <div class="playback-buttons">
      <button type="button" :disabled="!hasTrace || stepIndex <= 0" data-testid="prev-btn" @click="emit('previous')">
        ◀ 上一步
      </button>
      <button type="button" :disabled="!hasTrace || stepIndex >= stepCount - 1" data-testid="next-btn" @click="emit('next')">
        下一步 ▶
      </button>
      <button
        class="primary-button"
        type="button"
        :disabled="!hasTrace || playing"
        data-testid="play-btn"
        @click="emit('play')"
      >
        ▶ 播放
      </button>
      <button type="button" :disabled="!hasTrace || !playing" data-testid="pause-btn" @click="emit('pause')">
        ⏸ 暂停
      </button>
      <button type="button" :disabled="!hasTrace || playing" data-testid="resume-btn" @click="emit('resume')">
        ⏵ 继续
      </button>
      <button type="button" :disabled="!hasTrace" data-testid="auto-btn" @click="emit('autoPlay')">
        ⟲ 从头演示
      </button>
      <button type="button" :disabled="!hasTrace" data-testid="reset-btn" @click="emit('reset')">
        重置
      </button>
    </div>
    <div class="timeline">
      <input
        type="range"
        min="0"
        :max="maxStep"
        step="1"
        :value="stepIndex"
        :disabled="!hasTrace"
        data-testid="timeline"
        aria-label="步骤时间轴"
        @input="emit('seek', Number(($event.target as HTMLInputElement).value))"
      />
      <span class="timeline-label" data-testid="step-progress">{{ currentLabel }}</span>
      <span class="timeline-label muted" data-testid="time-progress">
        {{ hasTrace ? `${elapsed.toFixed(1)}s / ${total.toFixed(1)}s` : "—" }}
      </span>
    </div>
    <label class="speed-control">
      速度
      <select
        :value="String(speed)"
        :disabled="!hasTrace"
        data-testid="speed-select"
        @change="emit('speed', Number(($event.target as HTMLSelectElement).value))"
      >
        <option value="0.5">0.5×</option>
        <option value="1">1×</option>
        <option value="1.5">1.5×</option>
        <option value="2">2×</option>
      </select>
    </label>
    <span class="mode-badge" :class="mode">{{ mode === "auto" ? "自动播放" : "教师控制" }}</span>
  </footer>
</template>
