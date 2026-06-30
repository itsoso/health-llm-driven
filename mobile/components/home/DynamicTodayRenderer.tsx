import React from 'react';
import { StyleSheet, View } from 'react-native';

import type {
  ChatCardActionDescriptor,
  ServerCardDescriptor,
} from '../chat/cards/types';
import { CARD_MAP, renderCard } from '../chat/cards';
import type { AgendaSkipReason } from '../../services/agenda';
import type {
  DailyArtifact,
  DailyArtifactTopAction,
} from '../../services/dailyArtifact';
import type {
  TodayDynamicCard,
  TodayDynamicView,
} from '../../services/todayDynamicView';
import DailyArtifactCard from './DailyArtifactCard';

export default function DynamicTodayRenderer({
  view,
  completing = false,
  skipping = false,
  onDailyArtifactComplete,
  onDailyArtifactSkip,
  onDailyArtifactAsk,
  onDailyArtifactExplainBasis,
  onDailyArtifactPressAction,
  onCardAction,
}: {
  view?: TodayDynamicView | null;
  completing?: boolean;
  skipping?: boolean;
  onDailyArtifactComplete?: (artifact: DailyArtifact, action: DailyArtifactTopAction) => void;
  onDailyArtifactSkip?: (
    artifact: DailyArtifact,
    reason: AgendaSkipReason,
    action: DailyArtifactTopAction | null,
  ) => void;
  onDailyArtifactAsk?: (artifact: DailyArtifact) => void;
  onDailyArtifactExplainBasis?: (artifact: DailyArtifact) => void;
  onDailyArtifactPressAction?: (artifact: DailyArtifact, action: DailyArtifactTopAction) => void;
  onCardAction?: (action: ChatCardActionDescriptor, descriptor: ServerCardDescriptor) => void;
}) {
  const sections = [...(view?.sections ?? [])]
    .filter((section) => section.cards.length > 0)
    .sort((a, b) => b.priority - a.priority);
  if (sections.length === 0) return null;

  return (
    <View style={styles.container} testID="dynamic-today-view">
      {sections.map((section) => {
        const renderedCards = section.cards
          .map((card, index) => renderDynamicCard({
            card,
            key: `${section.slot}:${card.type}:${index}`,
            completing,
            skipping,
            onDailyArtifactComplete,
            onDailyArtifactSkip,
            onDailyArtifactAsk,
            onDailyArtifactExplainBasis,
            onDailyArtifactPressAction,
            onCardAction,
          }))
          .filter(Boolean);
        if (renderedCards.length === 0) return null;
        return (
          <View key={section.slot} style={styles.section}>
            {renderedCards}
          </View>
        );
      })}
    </View>
  );
}

function renderDynamicCard({
  card,
  key,
  completing,
  skipping,
  onDailyArtifactComplete,
  onDailyArtifactSkip,
  onDailyArtifactAsk,
  onDailyArtifactExplainBasis,
  onDailyArtifactPressAction,
  onCardAction,
}: {
  card: TodayDynamicCard;
  key: string;
  completing: boolean;
  skipping: boolean;
  onDailyArtifactComplete?: (artifact: DailyArtifact, action: DailyArtifactTopAction) => void;
  onDailyArtifactSkip?: (
    artifact: DailyArtifact,
    reason: AgendaSkipReason,
    action: DailyArtifactTopAction | null,
  ) => void;
  onDailyArtifactAsk?: (artifact: DailyArtifact) => void;
  onDailyArtifactExplainBasis?: (artifact: DailyArtifact) => void;
  onDailyArtifactPressAction?: (artifact: DailyArtifact, action: DailyArtifactTopAction) => void;
  onCardAction?: (action: ChatCardActionDescriptor, descriptor: ServerCardDescriptor) => void;
}): React.ReactElement | null {
  if (card.type === 'daily_artifact') {
    const artifact = card.data as DailyArtifact;
    return (
      <DailyArtifactCard
        key={key}
        artifact={artifact}
        completing={completing}
        skipping={skipping}
        onComplete={(action) => onDailyArtifactComplete?.(artifact, action)}
        onSkip={(reason, action) => onDailyArtifactSkip?.(artifact, reason, action)}
        onAskReva={(value) => onDailyArtifactAsk?.(value)}
        onExplainBasis={(value) => onDailyArtifactExplainBasis?.(value)}
        onPressAction={(action) => onDailyArtifactPressAction?.(artifact, action)}
      />
    );
  }

  if (!CARD_MAP[card.type]) return null;

  const descriptor: ServerCardDescriptor = {
    type: card.type,
    data: card.data,
    actions: card.actions,
  };
  const rendered = renderCard(descriptor, onCardAction ? { onAction: onCardAction } : {});
  return rendered ? <View key={key}>{rendered}</View> : null;
}

const styles = StyleSheet.create({
  container: {
    gap: 12,
  },
  section: {
    gap: 10,
  },
});
