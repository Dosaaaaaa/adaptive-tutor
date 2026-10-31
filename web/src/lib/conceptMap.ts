// Lays a concept graph out from left to right: prerequisites on the left, what they unlock on the right.
// No graph library: the graphs are small (about 5 to 15 concepts), so a layered layout with a few ordering passes is enough.

export interface MapNode {
  id: string;
}
export type MapEdge = [parent: string, child: string];

export interface PlacedNode {
  id: string;
  layer: number;
  row: number;
  x: number;
  y: number;
}

export interface PlacedEdge {
  from: string;
  to: string;
  d: string;
}

export interface MapLayout {
  nodes: PlacedNode[];
  edges: PlacedEdge[];
  width: number;
  height: number;
}

export const NODE_W = 208;
export const NODE_H = 80;
export const GAP_X = 76;
export const GAP_Y = 22;
export const PAD = 14;

/** Longest path from any concept with no prerequisite. Concepts caught in a cycle (which a valid quiz never has) are put last. */
export function assignLayers(ids: string[], edges: MapEdge[]): Map<string, number> {
  const known = new Set(ids);
  const parents = new Map<string, string[]>(ids.map((id) => [id, []]));
  const children = new Map<string, string[]>(ids.map((id) => [id, []]));
  for (const [p, c] of edges) {
    if (p === c || !known.has(p) || !known.has(c)) continue;
    if (parents.get(c)!.includes(p)) continue;
    parents.get(c)!.push(p);
    children.get(p)!.push(c);
  }
  const layer = new Map<string, number>();
  const waiting = new Map(ids.map((id) => [id, parents.get(id)!.length]));
  const queue = ids.filter((id) => waiting.get(id) === 0);
  queue.forEach((id) => layer.set(id, 0));
  for (let i = 0; i < queue.length; i++) {
    const id = queue[i]!;
    for (const child of children.get(id)!) {
      layer.set(child, Math.max(layer.get(child) ?? 0, layer.get(id)! + 1));
      waiting.set(child, waiting.get(child)! - 1);
      if (waiting.get(child) === 0) queue.push(child);
    }
  }
  const deepest = Math.max(-1, ...layer.values());
  for (const id of ids) if (!layer.has(id)) layer.set(id, deepest + 1);
  return layer;
}

function average(values: number[], fallback: number): number {
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : fallback;
}

export function layoutMap(nodes: MapNode[], edges: MapEdge[]): MapLayout {
  const ids = nodes.map((n) => n.id);
  const known = new Set(ids);
  const layerOf = assignLayers(ids, edges);
  const layerCount = ids.length ? Math.max(...layerOf.values()) + 1 : 0;

  const columns: string[][] = Array.from({ length: layerCount }, () => []);
  for (const id of ids) columns[layerOf.get(id)!]!.push(id);

  const parentsOf = (id: string) => edges.filter(([p, c]) => c === id && known.has(p)).map(([p]) => p);
  const childrenOf = (id: string) => edges.filter(([p, c]) => p === id && known.has(c)).map(([, c]) => c);
  const positionIn = (column: string[]) => new Map(column.map((id, i) => [id, i]));

  // Reduce crossings: sort each column by the average row of its neighbours, forwards then backwards, a few times.
  for (let pass = 0; pass < 4; pass++) {
    const forward = pass % 2 === 0;
    const order = forward ? columns.keys() : [...columns.keys()].reverse();
    for (const index of order) {
      const reference = columns[forward ? index - 1 : index + 1];
      if (!reference) continue;
      const rows = positionIn(reference);
      const current = positionIn(columns[index]!);
      const score = (id: string) =>
        average((forward ? parentsOf(id) : childrenOf(id)).map((n) => rows.get(n)).filter((v): v is number => v !== undefined), current.get(id)!);
      columns[index] = [...columns[index]!].sort((a, b) => score(a) - score(b) || current.get(a)! - current.get(b)!);
    }
  }

  const tallest = Math.max(1, ...columns.map((c) => c.length));
  const innerHeight = tallest * NODE_H + (tallest - 1) * GAP_Y;
  const placed: PlacedNode[] = [];
  columns.forEach((column, layer) => {
    const used = column.length * NODE_H + (column.length - 1) * GAP_Y;
    const top = PAD + (innerHeight - used) / 2;
    column.forEach((id, row) => {
      placed.push({ id, layer, row, x: PAD + layer * (NODE_W + GAP_X), y: top + row * (NODE_H + GAP_Y) });
    });
  });

  const at = new Map(placed.map((n) => [n.id, n]));
  const drawn: PlacedEdge[] = [];
  const seen = new Set<string>();
  for (const [from, to] of edges) {
    const a = at.get(from);
    const b = at.get(to);
    const key = `${from}>${to}`;
    if (!a || !b || from === to || seen.has(key)) continue;
    seen.add(key);
    const x1 = a.x + NODE_W;
    const y1 = a.y + NODE_H / 2;
    const x2 = b.x;
    const y2 = b.y + NODE_H / 2;
    const mid = (x1 + x2) / 2;
    drawn.push({ from, to, d: `M${x1} ${y1} C${mid} ${y1} ${mid} ${y2} ${x2} ${y2}` });
  }

  return {
    nodes: placed,
    edges: drawn,
    width: layerCount ? PAD * 2 + layerCount * NODE_W + (layerCount - 1) * GAP_X : 0,
    height: ids.length ? PAD * 2 + innerHeight : 0,
  };
}
