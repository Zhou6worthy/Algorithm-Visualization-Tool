<script setup lang="ts">
import { computed } from "vue";
import type { AnimationStep, ClassroomStepView, ComponentSpec } from "../types";
import UnknownView from "./UnknownView.vue";
import { resolveVisualComponent } from "./registry";

const props = defineProps<{
  spec: ComponentSpec;
  step: AnimationStep | null;
  view: ClassroomStepView | null;
  code: string;
}>();

const resolved = computed(() => resolveVisualComponent(props.spec.kind));
const title = computed(() => String(props.spec.options?.title ?? props.spec.title ?? props.spec.kind));
const dynamicProps = computed(() => {
  if (!resolved.value) return {};
  return resolved.value.props({
    spec: props.spec,
    step: props.step,
    view: props.view,
    code: props.code,
  });
});
</script>

<template>
  <section
    class="panel visual-panel visual-component"
    :data-kind="spec.kind"
    :data-slot="spec.slot"
    :data-component-id="spec.component_id"
  >
    <div class="panel-heading compact">
      <div>
        <div class="panel-eyebrow">{{ spec.kind.toUpperCase() }}</div>
        <h2>{{ title }}</h2>
      </div>
    </div>
    <component v-if="resolved" :is="resolved.component" v-bind="dynamicProps" />
    <UnknownView v-else :kind="spec.kind" />
  </section>
</template>
