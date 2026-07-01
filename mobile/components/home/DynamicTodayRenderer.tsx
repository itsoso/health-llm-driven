import React from 'react';
import { StyleSheet, View } from 'react-native';

import type {
  ChatCardActionDescriptor,
  ChatCardActionRuntimeState,
  ServerCardDescriptor,
} from '../chat/cards/types';
import { getCardActionRuntimeKey } from '../chat/cards';
import type { AgendaSkipReason } from '../../services/agenda';
import type {
  DailyArtifact,
  DailyArtifactTopAction,
} from '../../services/dailyArtifact';
import type {
  TodayDynamicView,
} from '../../services/todayDynamicView';
import {
  collectTodayDynamicPromotedTitleKeys,
  renderTodayDynamicAtom,
  resolveTodayDynamicAtom,
  shouldRenderTodayDynamicCard,
} from './todayDynamicAtoms';

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
  onCardAction?: (action: ChatCardActionDescriptor, descriptor: ServerCardDescriptor) => Promise<void> | void;
}) {
  const [actionStateByKey, setActionStateByKey] = React.useState<Record<string, ChatCardActionRuntimeState>>({});
  const handleCardAction = React.useCallback(async (
    action: ChatCardActionDescriptor,
    descriptor: ServerCardDescriptor,
  ) => {
    if (!onCardAction) return;
    const actionKey = getCardActionRuntimeKey(action, descriptor);
    const state = actionStateByKey[actionKey];
    if (state === 'running' || state === 'done') return;
    setActionStateByKey(prev => ({ ...prev, [actionKey]: 'running' }));
    try {
      await onCardAction(action, descriptor);
      setActionStateByKey(prev => ({ ...prev, [actionKey]: 'done' }));
    } catch {
      setActionStateByKey(prev => ({ ...prev, [actionKey]: 'error' }));
    }
  }, [actionStateByKey, onCardAction]);
  const promotedTitleKeys = collectTodayDynamicPromotedTitleKeys(view);
  const sections = [...(view?.sections ?? [])]
    .map((section) => ({
      ...section,
      cards: section.cards.filter((card) => shouldRenderTodayDynamicCard(card, promotedTitleKeys)),
    }))
    .filter((section) => section.cards.length > 0)
    .sort((a, b) => b.priority - a.priority);
  if (sections.length === 0) return null;

  return (
    <View style={styles.container} testID="dynamic-today-view">
      {sections.map((section) => {
        const renderedCards = section.cards
          .map((card, index) => {
            const atom = resolveTodayDynamicAtom(card);
            return renderTodayDynamicAtom({
              card,
              key: `${section.slot}:${card.id ?? atom}:${index}`,
              completing,
              skipping,
              onDailyArtifactComplete,
              onDailyArtifactSkip,
              onDailyArtifactAsk,
              onDailyArtifactExplainBasis,
              onDailyArtifactPressAction,
              onCardAction: onCardAction ? handleCardAction : undefined,
              actionStateByKey,
            });
          })
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

const styles = StyleSheet.create({
  container: {
    gap: 12,
  },
  section: {
    gap: 10,
  },
});
