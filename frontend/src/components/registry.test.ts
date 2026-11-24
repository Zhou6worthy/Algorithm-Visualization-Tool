import { describe, expect, it } from "vitest";
import {
  resolveVisualComponent,
  visualComponentKinds,
  visualComponentRegistry,
} from "./registry";

describe("VisualPlan component registry", () => {
  it("registers the component kinds used by both algorithms", () => {
    expect(visualComponentKinds()).toEqual(
      expect.arrayContaining(["array", "hash_map", "variables", "code", "search_range"]),
    );
    expect(resolveVisualComponent("array")).not.toBeNull();
    expect(resolveVisualComponent("hash_map")).not.toBeNull();
    expect(resolveVisualComponent("search_range")).not.toBeNull();
  });

  it("returns null for an unknown component kind so the UI can show an explicit error", () => {
    expect(resolveVisualComponent("not_a_real_component")).toBeNull();
    expect(Object.keys(visualComponentRegistry)).not.toContain("not_a_real_component");
  });
});
