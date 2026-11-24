<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { basicSetup } from "codemirror";
import { python } from "@codemirror/lang-python";
import { oneDark } from "@codemirror/theme-one-dark";
import { EditorState, StateEffect, StateField } from "@codemirror/state";
import { Decoration, EditorView, type DecorationSet } from "@codemirror/view";

const props = withDefaults(
  defineProps<{
    modelValue: string;
    activeLine?: number | null;
    readonly?: boolean;
  }>(),
  { activeLine: null, readonly: false },
);
const emit = defineEmits<{ "update:modelValue": [value: string] }>();

const host = ref<HTMLDivElement | null>(null);
let view: EditorView | null = null;
let syncingExternal = false;

const setActiveLine = StateEffect.define<number | null>();
const activeLineField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(decorations, transaction) {
    decorations = decorations.map(transaction.changes);
    for (const effect of transaction.effects) {
      if (!effect.is(setActiveLine)) continue;
      if (effect.value == null || effect.value < 1) return Decoration.none;
      const lineNumber = Math.min(effect.value, transaction.state.doc.lines);
      const line = transaction.state.doc.line(lineNumber);
      return Decoration.set([
        Decoration.line({ class: "cm-execution-line" }).range(line.from),
      ]);
    }
    return decorations;
  },
  provide: (field) => EditorView.decorations.from(field),
});

function applyActiveLine(line: number | null | undefined): void {
  if (!view) return;
  const value = line && line > 0 ? line : null;
  const effects: StateEffect<unknown>[] = [setActiveLine.of(value)];
  if (value != null) {
    const line = view.state.doc.line(Math.min(value, view.state.doc.lines));
    effects.push(EditorView.scrollIntoView(line.from, { y: "nearest" }));
  }
  view.dispatch({ effects });
}

onMounted(() => {
  if (!host.value) return;
  view = new EditorView({
    parent: host.value,
    state: EditorState.create({
      doc: props.modelValue,
      extensions: [
        basicSetup,
        python(),
        oneDark,
        EditorView.lineWrapping,
        EditorView.theme({
          "&": { height: "350px" },
          ".cm-scroller": { overflow: "auto" },
          ".cm-content": { fontFamily: '"Cascadia Mono", Consolas, monospace', fontSize: "12.5px" },
        }),
        activeLineField,
        EditorView.editable.of(!props.readonly),
        EditorView.updateListener.of((update) => {
          if (!update.docChanged || syncingExternal) return;
          emit("update:modelValue", update.state.doc.toString());
        }),
      ],
    }),
  });
  (window as unknown as Record<string, unknown>).__codeEditor = view;
  applyActiveLine(props.activeLine);
});

watch(
  () => props.modelValue,
  (value) => {
    if (!view) return;
    const current = view.state.doc.toString();
    if (current === value) return;
    syncingExternal = true;
    try {
      view.dispatch({
        changes: { from: 0, to: current.length, insert: value },
      });
    } finally {
      syncingExternal = false;
    }
  },
);

watch(
  () => props.activeLine,
  (line) => applyActiveLine(line),
);

onBeforeUnmount(() => {
  view?.destroy();
  view = null;
  (window as unknown as Record<string, unknown>).__codeEditor = null;
});
</script>

<template>
  <div ref="host" class="code-editor" aria-label="Python 源码编辑器"></div>
</template>

<style>
.code-editor {
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  background: #0a1424;
}
.code-editor .cm-editor {
  background: #0a1424;
}
.code-editor .cm-execution-line {
  background: rgba(251, 191, 36, 0.14);
  box-shadow: inset 3px 0 0 var(--accent);
}
.code-editor .cm-gutters {
  border-right: 1px solid rgba(42, 65, 95, 0.7);
  background: #0a1424;
}
</style>
