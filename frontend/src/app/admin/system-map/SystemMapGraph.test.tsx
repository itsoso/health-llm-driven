import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SystemMapGraph } from './SystemMapGraph';
import type { SystemMapEntity, SystemMapRelation } from './types';


const entities: SystemMapEntity[] = [
  {
    id: 'component.backend',
    kind: 'component',
    name: 'Backend Service With A Deliberately Long Name',
    coverage: 'declaration',
    source: { type: 'declaration', path: 'fixture.json' },
  },
  {
    id: 'resource.postgresql',
    kind: 'resource',
    name: 'PostgreSQL',
    coverage: 'partial',
    source: { type: 'declaration', path: 'fixture.json' },
  },
];

const relations: SystemMapRelation[] = [
  {
    from: 'component.backend',
    type: 'writesTo',
    to: 'resource.postgresql',
    coverage: 'declaration',
    source: { type: 'declaration', path: 'fixture.json' },
  },
];


describe('SystemMapGraph', () => {
  it('renders accessible nodes, relations and coverage badges', () => {
    render(<SystemMapGraph entities={entities} relations={relations} />);

    expect(screen.getByRole('img', { name: '系统实体关系图' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Backend Service With A Deliberately Long Name/ }))
      .toBeInTheDocument();
    expect(screen.getByLabelText('component.backend writesTo resource.postgresql'))
      .toBeInTheDocument();
    expect(screen.getByText('声明')).toBeInTheDocument();
    expect(screen.getByText('部分')).toBeInTheDocument();
    expect(screen.getByText('Backend Service With A Deliberately Long Name', { selector: 'title' }))
      .toBeInTheDocument();
  });

  it('reports the selected entity', () => {
    const onSelect = vi.fn();
    render(<SystemMapGraph entities={entities} relations={relations} onSelect={onSelect} />);

    fireEvent.click(screen.getByRole('button', { name: /PostgreSQL/ }));

    expect(onSelect).toHaveBeenCalledWith(entities[1]);
  });

  it('shows an explicit empty state', () => {
    render(<SystemMapGraph entities={[]} relations={[]} />);

    expect(screen.getByText('当前筛选条件下没有系统实体。')).toBeInTheDocument();
  });
});
