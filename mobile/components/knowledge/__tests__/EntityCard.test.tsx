import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import { EntityCard } from '../EntityCard';
import type { KnowledgeDocument } from '../../../services/systemKnowledge';

function makeEntity(overrides: Partial<KnowledgeDocument> = {}): KnowledgeDocument {
  return {
    doc_id: 'entity:gene/MTHFR',
    doc_type: 'entity',
    entity_type: 'gene',
    entity_id: 'MTHFR',
    title: 'MTHFR 亚甲基四氢叶酸还原酶',
    summary: '影响叶酸代谢与同型半胱氨酸水平',
    evidence_level: 'A',
    ...overrides,
  };
}

describe('EntityCard', () => {
  it('renders gene entity with title, summary, evidence level', () => {
    const screen = render(<EntityCard entity={makeEntity()} />);
    expect(screen.getByText('基因')).toBeTruthy();
    expect(screen.getByText('MTHFR 亚甲基四氢叶酸还原酶')).toBeTruthy();
    expect(screen.getByText(/影响叶酸代谢/)).toBeTruthy();
    expect(screen.getByText('A级')).toBeTruthy();
  });

  it('falls back to entity_id when title missing', () => {
    const screen = render(
      <EntityCard
        entity={makeEntity({ title: null, summary: null, evidence_level: null })}
      />,
    );
    expect(screen.getByText('MTHFR')).toBeTruthy();
    expect(screen.queryByText(/级$/)).toBeNull();
  });

  it('renders nutrient and supplement types with localized labels', () => {
    const nut = render(
      <EntityCard
        entity={makeEntity({
          entity_type: 'nutrient',
          entity_id: 'folate',
          title: '叶酸',
        })}
      />,
    );
    expect(nut.getByText('营养素')).toBeTruthy();

    const sup = render(
      <EntityCard
        entity={makeEntity({
          entity_type: 'supplement',
          entity_id: '5-mthf',
          title: '5-MTHF',
        })}
      />,
    );
    expect(sup.getByText('补剂')).toBeTruthy();
  });

  it('can act as a deep-link entry when onPress is provided', () => {
    const onPress = jest.fn();
    const screen = render(<EntityCard entity={makeEntity()} onPress={onPress} />);

    fireEvent.press(screen.getByTestId('knowledge-entity-card-entity:gene/MTHFR'));

    expect(onPress).toHaveBeenCalledTimes(1);
  });
});
