import type { Component } from "vue";
import type { AnimationStep, ClassroomStepView, ComponentSpec } from "../types";
import ArrayView from "./ArrayView.vue";
import CodeView from "./CodeView.vue";
import HashMapView from "./HashMapView.vue";
import SearchRangeView from "./SearchRangeView.vue";
import VariableView from "./VariableView.vue";

export interface VisualContext {
  spec: ComponentSpec;
  step: AnimationStep | null;
  view: ClassroomStepView | null;
  code: string;
}

export interface VisualRegistryEntry {
  component: Component;
  props: (context: VisualContext) => Record<string, unknown>;
}

export const visualComponentRegistry: Record<string, VisualRegistryEntry> = {
  array: {
    component: ArrayView,
    props: ({ step }) => ({ step }),
  },
  hash_map: {
    component: HashMapView,
    props: ({ step }) => ({ step }),
  },
  variables: {
    component: VariableView,
    props: ({ view }) => ({ view }),
  },
  code: {
    component: CodeView,
    props: ({ step, code }) => ({ code, activeLine: step?.code_line ?? null }),
  },
  search_range: {
    component: SearchRangeView,
    props: ({ step }) => ({ step }),
  },
};

export function resolveVisualComponent(kind: string): VisualRegistryEntry | null {
  return visualComponentRegistry[kind] ?? null;
}

export function visualComponentKinds(): string[] {
  return Object.keys(visualComponentRegistry);
}
