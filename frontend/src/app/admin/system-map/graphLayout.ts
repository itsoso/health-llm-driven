import type { SystemMapEntity, SystemMapEntityKind, SystemMapRelation } from './types';


export interface PositionedEntity extends SystemMapEntity {
  x: number;
  y: number;
}

export interface PositionedRelation extends SystemMapRelation {
  fromNode: PositionedEntity;
  toNode: PositionedEntity;
}

export interface SystemMapLayout {
  nodes: PositionedEntity[];
  relations: PositionedRelation[];
  width: number;
  height: number;
}

const KIND_ORDER: SystemMapEntityKind[] = ['component', 'surface', 'api', 'job', 'resource'];
const LEFT = 110;
const TOP = 80;
const COLUMN_GAP = 220;
const ROW_GAP = 74;


export function layoutSystemMap(
  entities: SystemMapEntity[],
  relations: SystemMapRelation[],
): SystemMapLayout {
  const grouped = new Map<SystemMapEntityKind, SystemMapEntity[]>(
    KIND_ORDER.map((kind) => [kind, []]),
  );
  for (const entity of entities) {
    grouped.get(entity.kind)?.push(entity);
  }

  const nodes: PositionedEntity[] = [];
  for (const [column, kind] of KIND_ORDER.entries()) {
    const ordered = grouped.get(kind)?.sort((a, b) => a.id.localeCompare(b.id)) ?? [];
    for (const [row, entity] of ordered.entries()) {
      nodes.push({
        ...entity,
        x: LEFT + column * COLUMN_GAP,
        y: TOP + row * ROW_GAP,
      });
    }
  }

  const nodesById = new Map(nodes.map((node) => [node.id, node]));
  const positionedRelations: PositionedRelation[] = [];
  for (const relation of [...relations].sort((a, b) =>
    `${a.from}\0${a.type}\0${a.to}`.localeCompare(`${b.from}\0${b.type}\0${b.to}`)
  )) {
    const fromNode = nodesById.get(relation.from);
    const toNode = nodesById.get(relation.to);
    if (!fromNode || !toNode) continue;
    positionedRelations.push({ ...relation, fromNode, toNode });
  }

  const largestColumn = Math.max(1, ...KIND_ORDER.map((kind) => grouped.get(kind)?.length ?? 0));
  return {
    nodes,
    relations: positionedRelations,
    width: LEFT * 2 + COLUMN_GAP * (KIND_ORDER.length - 1),
    height: TOP * 2 + ROW_GAP * (largestColumn - 1),
  };
}
