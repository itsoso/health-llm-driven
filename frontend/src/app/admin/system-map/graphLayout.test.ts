import { describe, expect, it } from 'vitest';

import { layoutSystemMap } from './graphLayout';


const entities = [
  {
    id: 'component.backend',
    kind: 'component',
    name: 'Backend',
    coverage: 'declaration',
    source: { type: 'declaration', path: 'fixture.json' },
  },
  {
    id: 'resource.postgresql',
    kind: 'resource',
    name: 'PostgreSQL',
    coverage: 'declaration',
    source: { type: 'declaration', path: 'fixture.json' },
  },
  {
    id: 'surface.web.admin',
    kind: 'surface',
    name: 'Admin',
    coverage: 'complete',
    source: { type: 'code', path: 'frontend/src/app/admin/page.tsx' },
  },
] as const;

const relations = [
  {
    from: 'component.backend',
    type: 'writesTo',
    to: 'resource.postgresql',
    coverage: 'declaration',
    source: { type: 'declaration', path: 'fixture.json' },
  },
] as const;


describe('layoutSystemMap', () => {
  it('produces deterministic fixed-column coordinates', () => {
    const first = layoutSystemMap([...entities], [...relations]);
    const second = layoutSystemMap([...entities].reverse(), [...relations]);

    expect(second).toEqual(first);
    expect(first.nodes.find((node) => node.id === 'component.backend')?.x)
      .toBeLessThan(first.nodes.find((node) => node.id === 'resource.postgresql')?.x ?? 0);
  });

  it('removes relations incident to filtered-out entities', () => {
    const visible = entities.filter((entity) => entity.id !== 'resource.postgresql');

    const result = layoutSystemMap(visible, [...relations]);

    expect(result.relations).toEqual([]);
  });

  it('ignores unknown relation endpoints without throwing', () => {
    const unresolved = {
      ...relations[0],
      to: 'resource.missing',
    };

    expect(() => layoutSystemMap([...entities], [unresolved])).not.toThrow();
    expect(layoutSystemMap([...entities], [unresolved]).relations).toEqual([]);
  });
});
