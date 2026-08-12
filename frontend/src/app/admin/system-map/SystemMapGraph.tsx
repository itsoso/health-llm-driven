'use client';

import { useMemo } from 'react';

import { layoutSystemMap } from './graphLayout';
import type {
  SystemMapCoverage,
  SystemMapEntity,
  SystemMapEntityKind,
  SystemMapRelation,
} from './types';


interface SystemMapGraphProps {
  entities: SystemMapEntity[];
  relations: SystemMapRelation[];
  onSelect?: (entity: SystemMapEntity) => void;
}

const KIND_COLORS: Record<SystemMapEntityKind, { fill: string; stroke: string }> = {
  component: { fill: '#102a43', stroke: '#38bdf8' },
  surface: { fill: '#132f2d', stroke: '#34d399' },
  api: { fill: '#33240f', stroke: '#fbbf24' },
  job: { fill: '#2f1b3d', stroke: '#c084fc' },
  resource: { fill: '#352020', stroke: '#fb7185' },
};

const COVERAGE_LABELS: Record<SystemMapCoverage, string> = {
  complete: '完整',
  partial: '部分',
  declaration: '声明',
};

const NODE_WIDTH = 176;
const NODE_HEIGHT = 48;


function truncateLabel(value: string): string {
  return value.length > 22 ? `${value.slice(0, 21)}…` : value;
}

export function SystemMapGraph({ entities, relations, onSelect }: SystemMapGraphProps) {
  const entitiesById = useMemo(
    () => new Map(entities.map((entity) => [entity.id, entity])),
    [entities],
  );
  const layout = useMemo(
    () => layoutSystemMap(entities, relations),
    [entities, relations],
  );

  if (layout.nodes.length === 0) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-950/60 px-6 py-16 text-center text-sm text-slate-400">
        当前筛选条件下没有系统实体。
      </div>
    );
  }

  return (
    <div className="overflow-auto rounded-xl border border-slate-800 bg-[#071019] shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
      <svg
        role="img"
        aria-label="系统实体关系图"
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        width={layout.width}
        height={layout.height}
        className="min-w-full"
      >
        <defs>
          <pattern id="system-map-grid" width="24" height="24" patternUnits="userSpaceOnUse">
            <path d="M 24 0 L 0 0 0 24" fill="none" stroke="#162231" strokeWidth="0.6" />
          </pattern>
          <marker id="system-map-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 8 4 L 0 8 z" fill="#40556d" />
          </marker>
        </defs>
        <rect width="100%" height="100%" fill="url(#system-map-grid)" />

        <g aria-label="系统关系">
          {layout.relations.map((relation) => (
            <line
              key={`${relation.from}:${relation.type}:${relation.to}`}
              aria-label={`${relation.from} ${relation.type} ${relation.to}`}
              x1={relation.fromNode.x + NODE_WIDTH / 2}
              y1={relation.fromNode.y}
              x2={relation.toNode.x - NODE_WIDTH / 2}
              y2={relation.toNode.y}
              stroke="#40556d"
              strokeWidth="1.25"
              strokeOpacity="0.72"
              markerEnd="url(#system-map-arrow)"
            >
              <title>{`${relation.from} ${relation.type} ${relation.to}`}</title>
            </line>
          ))}
        </g>

        <g aria-label="系统实体">
          {layout.nodes.map((node) => {
            const color = KIND_COLORS[node.kind];
            const label = `${node.name}，${node.kind}，覆盖度${COVERAGE_LABELS[node.coverage]}`;
            const select = () => {
              const entity = entitiesById.get(node.id);
              if (entity) onSelect?.(entity);
            };
            return (
              <g
                key={node.id}
                role="button"
                tabIndex={0}
                aria-label={label}
                transform={`translate(${node.x},${node.y})`}
                className="cursor-pointer outline-none focus:[&_rect:first-of-type]:stroke-white"
                onClick={select}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    select();
                  }
                }}
              >
                <title>{node.name}</title>
                <rect
                  x={-NODE_WIDTH / 2}
                  y={-NODE_HEIGHT / 2}
                  width={NODE_WIDTH}
                  height={NODE_HEIGHT}
                  rx="10"
                  fill={color.fill}
                  stroke={color.stroke}
                  strokeWidth="1.4"
                />
                <text x={-NODE_WIDTH / 2 + 12} y="-4" fill="#e6edf5" fontSize="11" fontWeight="600">
                  {truncateLabel(node.name)}
                </text>
                <text x={-NODE_WIDTH / 2 + 12} y="13" fill="#91a4b8" fontSize="8.5">
                  {node.kind} · {node.id.slice(0, 25)}
                </text>
                <g transform={`translate(${NODE_WIDTH / 2 - 38},${NODE_HEIGHT / 2 - 13})`}>
                  <rect width="30" height="13" rx="6.5" fill={color.stroke} fillOpacity="0.16" />
                  <text x="15" y="9.2" textAnchor="middle" fill={color.stroke} fontSize="7.5" fontWeight="700">
                    {COVERAGE_LABELS[node.coverage]}
                  </text>
                </g>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
