import { useId, useMemo } from "react";
import { CLASS_STATE, STATE_LABEL } from "../format";
import { layoutMap, NODE_H, NODE_W } from "../lib/conceptMap";
import type { ClassStatus } from "../types";
import { Icon } from "./Icon";
import { StateGlyph } from "./Status";

export interface MapConcept {
  id: string;
  name: string;
  status: ClassStatus;
  understood: number;
  n: number;
}

interface Props {
  nodes: MapConcept[];
  edges: [string, string][];
  startHere: ReadonlySet<string>;
  selected: string | null;
  onSelect: (id: string | null) => void;
}

/**
 * The class's concept map: what must be learned first on the left, what it unlocks on the right.
 * Each box is a real button (so it works with a keyboard and a screen reader) laid over an SVG that draws only the lines.
 * A box shows the concept, how many students understood it and a shape for its status (check, half, cross).
 */
export function ConceptMap({ nodes, edges, startHere, selected, onSelect }: Props) {
  const markerId = useId();
  const layout = useMemo(() => layoutMap(nodes, edges), [nodes, edges]);
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  return (
    <div className="map">
      <div className="map__scroll">
        <div className="map__canvas" role="group" aria-label="Concept map. Concepts on the left come first." style={{ width: layout.width, height: layout.height }}>
          <svg className="map__svg" viewBox={`0 0 ${layout.width} ${layout.height}`} width={layout.width} height={layout.height} aria-hidden="true" focusable="false">
            <defs>
              <marker id={markerId} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
                <path className="map__arrow" d="M0 1L9 5L0 9z" />
              </marker>
            </defs>
            {layout.edges.map((e) => (
              <path
                key={`${e.from}-${e.to}`}
                className="map__edge"
                d={e.d}
                markerEnd={`url(#${markerId})`}
                data-lit={selected === e.from || selected === e.to ? "true" : undefined}
              />
            ))}
          </svg>
          {layout.nodes.map((p) => {
            const c = byId.get(p.id);
            if (!c) return null;
            const state = CLASS_STATE[c.status];
            return (
              <button
                key={c.id}
                type="button"
                className="map__node"
                data-status={c.status}
                aria-pressed={selected === c.id}
                style={{ left: p.x, top: p.y, width: NODE_W, height: NODE_H }}
                onClick={() => onSelect(selected === c.id ? null : c.id)}
              >
                <StateGlyph state={state} size={16} />
                <span className="map__name">{c.name}</span>
                <span className="map__count"><span className="figure">{c.understood}</span> of <span className="figure">{c.n}</span> understood</span>
                {startHere.has(c.id) ? <span className="map__tag">Start here</span> : null}
                <span className="visually-hidden">Status: {STATE_LABEL[state]}.</span>
              </button>
            );
          })}
        </div>
      </div>
      <p className="map__hint">Swipe sideways to see the whole map.</p>
      <ul className="legend" aria-label="What the shapes mean">
        <li><StateGlyph state="understood" /> Class has it: 75% or more understood</li>
        <li><StateGlyph state="shaky" /> Shaky: 50% to 75%</li>
        <li><StateGlyph state="missing" /> Missing: under 50%</li>
        <li><Icon name="flag" /> Start here: where most students first get stuck</li>
      </ul>
    </div>
  );
}
