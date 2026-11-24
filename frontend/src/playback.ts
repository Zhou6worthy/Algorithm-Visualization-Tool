import { computed, onBeforeUnmount, ref, watch, type Ref } from "vue";
import type { AnimationStep, ClassroomCase, ClassroomDeck, StepHint } from "./types";

export type PlaybackMode = "teacher" | "auto";

export function usePlayback(deck: Ref<ClassroomDeck | null>) {
  const activeCaseId = ref<string | null>(null);
  const stepIndex = ref(0);
  const speed = ref(1);
  const mode = ref<PlaybackMode>("teacher");
  const playing = ref(false);
  let timer: number | null = null;
  let timerToken = 0;

  const currentCase = computed<ClassroomCase | null>(() => {
    if (!deck.value) return null;
    return deck.value.cases.find((item) => item.case_id === activeCaseId.value) ?? null;
  });
  const steps = computed<AnimationStep[]>(() => currentCase.value?.trace?.steps ?? []);
  const currentStep = computed<AnimationStep | null>(() => steps.value[stepIndex.value] ?? null);
  const stepCount = computed(() => steps.value.length);
  const atEnd = computed(() => stepCount.value > 0 && stepIndex.value >= stepCount.value - 1);
  const currentStepView = computed(() => {
    const step = currentStep.value;
    if (!step || !currentCase.value) return null;
    return currentCase.value.step_views.find((item) => item.step_id === step.step_id) ?? null;
  });
  const currentHint = computed<StepHint | null>(() => {
    const step = currentStep.value;
    if (!step || !currentCase.value) return null;
    return currentCase.value.hints.find((item) => item.related_step_id === step.step_id) ?? null;
  });

  function clampIndex(value: number): number {
    if (!stepCount.value) return 0;
    return Math.max(0, Math.min(stepCount.value - 1, Math.floor(Number(value) || 0)));
  }

  function durationAt(index: number): number {
    const step = steps.value[index];
    const duration = Number(step?.duration);
    if (Number.isFinite(duration) && duration > 0) return duration;
    return Math.max(0.2, Number(deck.value?.default_step_duration) || 1.2);
  }

  const totalSeconds = computed(() => {
    let total = 0;
    for (let index = 0; index < steps.value.length; index += 1) total += durationAt(index);
    return total;
  });
  const elapsedSeconds = computed(() => {
    let total = 0;
    for (let index = 0; index < stepIndex.value; index += 1) total += durationAt(index);
    return total;
  });
  const progress = computed(() => {
    if (!stepCount.value) return 0;
    return stepCount.value === 1 ? 100 : (stepIndex.value / (stepCount.value - 1)) * 100;
  });

  function cancelTimer(): void {
    timerToken += 1;
    if (timer !== null) {
      window.clearTimeout(timer);
      timer = null;
    }
  }

  function scheduleNext(): void {
    if (!playing.value || !stepCount.value) return;
    cancelTimer();
    const token = timerToken;
    const delay = Math.max(120, (durationAt(stepIndex.value) / speed.value) * 1000);
    timer = window.setTimeout(() => onTimer(token), delay);
  }

  function onTimer(token: number): void {
    if (token !== timerToken || !playing.value) return;
    timer = null;
    if (!stepCount.value || atEnd.value) {
      playing.value = false;
      mode.value = "teacher";
      return;
    }
    stepIndex.value += 1;
    mode.value = "auto";
    scheduleNext();
  }

  function applyIndex(value: number): void {
    stepIndex.value = clampIndex(value);
  }

  function manual(value: number): void {
    cancelTimer();
    playing.value = false;
    mode.value = "teacher";
    applyIndex(value);
  }

  function loadCase(caseId: string): void {
    cancelTimer();
    playing.value = false;
    mode.value = "teacher";
    activeCaseId.value = caseId;
    stepIndex.value = 0;
  }

  function next(): void {
    manual(stepIndex.value + 1);
  }
  function previous(): void {
    manual(stepIndex.value - 1);
  }
  function seek(value: number): void {
    manual(value);
  }
  function reset(): void {
    manual(0);
  }
  function play(): void {
    if (!stepCount.value) return;
    cancelTimer();
    if (atEnd.value) applyIndex(0);
    mode.value = "auto";
    playing.value = true;
    scheduleNext();
  }
  function autoPlay(): void {
    if (!stepCount.value) return;
    cancelTimer();
    applyIndex(0);
    mode.value = "auto";
    playing.value = true;
    scheduleNext();
  }
  function pause(): void {
    if (!playing.value) return;
    cancelTimer();
    playing.value = false;
    mode.value = "teacher";
  }
  function resume(): void {
    if (!stepCount.value || playing.value) return;
    cancelTimer();
    if (atEnd.value) applyIndex(0);
    mode.value = "auto";
    playing.value = true;
    scheduleNext();
  }
  function setSpeed(value: number): void {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) return;
    speed.value = Math.max(0.25, Math.min(4, parsed));
    if (playing.value) scheduleNext();
  }

  watch(
    deck,
    (nextDeck) => {
      if (!nextDeck) {
        cancelTimer();
        activeCaseId.value = null;
        stepIndex.value = 0;
        playing.value = false;
        mode.value = "teacher";
        return;
      }
      const preferred = nextDeck.cases.find((item) => item.case_id === nextDeck.active_case_id);
      loadCase(preferred?.case_id ?? nextDeck.cases[0]?.case_id ?? "");
    },
    { immediate: true },
  );

  onBeforeUnmount(() => cancelTimer());

  return {
    activeCaseId,
    stepIndex,
    speed,
    mode,
    playing,
    currentCase,
    steps,
    currentStep,
    currentStepView,
    currentHint,
    stepCount,
    atEnd,
    totalSeconds,
    elapsedSeconds,
    progress,
    loadCase,
    next,
    previous,
    seek,
    reset,
    play,
    autoPlay,
    pause,
    resume,
    setSpeed,
  };
}

export function stepTypeLabel(type: string | undefined): string {
  const labels: Record<string, string> = {
    init: "初始化",
    visit: "访问",
    compare: "查询",
    update: "写入",
    found: "完成返回",
    complete: "执行完成",
    swap: "交换",
    mark: "标记",
    note: "说明",
  };
  return type ? labels[type] ?? type : "步骤";
}

export function formatSeconds(value: number): string {
  const total = Math.max(0, Number(value) || 0);
  return `${total.toFixed(1)}s`;
}
