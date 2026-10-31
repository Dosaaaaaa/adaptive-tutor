import { describe, expect, it } from "vitest";
import { assignLayers, layoutMap, NODE_H, NODE_W, type MapEdge } from "./conceptMap";

const ids = (...names: string[]) => names.map((id) => ({ id }));

describe("assignLayers", () => {
  it("puts a chain in consecutive layers", () => {
    const layers = assignLayers(["A", "B", "C"], [["A", "B"], ["B", "C"]]);
    expect([layers.get("A"), layers.get("B"), layers.get("C")]).toEqual([0, 1, 2]);
  });

  it("uses the longest path, so a concept sits after all of its prerequisites", () => {
    const layers = assignLayers(["A", "B", "C", "D"], [["A", "B"], ["B", "D"], ["A", "C"], ["C", "D"], ["A", "D"]]);
    expect(layers.get("D")).toBe(2);
  });

  it("keeps unconnected concepts in the first layer", () => {
    const layers = assignLayers(["A", "B", "Z"], [["A", "B"]]);
    expect(layers.get("Z")).toBe(0);
  });

  it("does not hang or crash on a cycle", () => {
    const layers = assignLayers(["A", "B", "C"], [["A", "B"], ["B", "C"], ["C", "B"]]);
    expect(layers.size).toBe(3);
  });

  it("ignores edges that point at concepts that do not exist, and self-loops", () => {
    const layers = assignLayers(["A", "B"], [["A", "X"], ["B", "B"], ["A", "B"]]);
    expect(layers.get("B")).toBe(1);
  });
});

describe("layoutMap", () => {
  const edges: MapEdge[] = [["C1", "C2"], ["C1", "C3"], ["C2", "C4"], ["C3", "C4"], ["C4", "C5"]];
  const layout = layoutMap(ids("C1", "C2", "C3", "C4", "C5"), edges);

  it("places every concept once", () => {
    expect(layout.nodes.map((n) => n.id).sort()).toEqual(["C1", "C2", "C3", "C4", "C5"]);
  });

  it("runs left to right: a concept is always to the right of its prerequisites", () => {
    const x = new Map(layout.nodes.map((n) => [n.id, n.x]));
    for (const [parent, child] of edges) expect(x.get(parent)!).toBeLessThan(x.get(child)!);
  });

  it("never overlaps two concepts", () => {
    for (const a of layout.nodes) {
      for (const b of layout.nodes) {
        if (a.id >= b.id) continue;
        const apart = a.x + NODE_W <= b.x || b.x + NODE_W <= a.x || a.y + NODE_H <= b.y || b.y + NODE_H <= a.y;
        expect(apart).toBe(true);
      }
    }
  });

  it("draws one line for each prerequisite, from the right edge of one box to the left edge of the next", () => {
    expect(layout.edges).toHaveLength(edges.length);
    const first = layout.nodes.find((n) => n.id === "C1")!;
    const line = layout.edges.find((e) => e.from === "C1" && e.to === "C2")!;
    expect(line.d.startsWith(`M${first.x + NODE_W} ${first.y + NODE_H / 2}`)).toBe(true);
  });

  it("fits everything inside the width and height it reports", () => {
    for (const n of layout.nodes) {
      expect(n.x + NODE_W).toBeLessThanOrEqual(layout.width);
      expect(n.y + NODE_H).toBeLessThanOrEqual(layout.height);
    }
  });

  it("gives the same picture for the same input", () => {
    expect(layoutMap(ids("C1", "C2", "C3", "C4", "C5"), edges)).toEqual(layout);
  });

  it("handles an empty graph", () => {
    expect(layoutMap([], [])).toEqual({ nodes: [], edges: [], width: 0, height: 0 });
  });

  it("keeps duplicate edges from being drawn twice", () => {
    expect(layoutMap(ids("A", "B"), [["A", "B"], ["A", "B"]]).edges).toHaveLength(1);
  });
});
