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
  const dailyArtifactTitles = collectDailyArtifactTitleKeys(view);
  const sections = [...(view?.sections ?? [])]
    .map((section) => ({
      ...section,
      cards: section.cards.filter((card) => shouldRenderDynamicCard(card, dailyArtifactTitles)),
    }))
    .filter((section) => section.cards.length > 0)
    .sort((a, b) => b.priority - a.priority);
  if (sections.length === 0) return null;

  return (
    <View style={styles.container} testID="dynamic-today-view">
      {sections.map((section) => {
        const renderedCards = section.cards
          .map((card, index) => {
            const atom = cardAtom(card);
            return renderDynamicCard({
              card,
              atom,
              key: `${section.slot}:${card.id ?? atom}:${index}`,
              completing,
              skipping,
              onDailyArtifactComplete,
              onDailyArtifactSkip,
              onDailyArtifactAsk,
              onDailyArtifactExplainBasis,
              onDailyArtifactPressAction,
              onCardAction,
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

function collectDailyArtifactTitleKeys(view: TodayDynamicView | null | undefined): Set<string> {
  const keys = new Set<string>();
  for (const section of view?.sections ?? []) {
    for (const card of section.cards) {
      if (cardAtom(card) !== 'daily_artifact') continue;
      const artifact = card.data as Partial<DailyArtifact>;
      const key = titleKey(artifact.top_action?.title);
      if (key) keys.add(key);
    }
  }
  return keys;
}

function shouldRenderDynamicCard(card: TodayDynamicCard, dailyArtifactTitleKeys: Set<string>): boolean {
  if (dailyArtifactTitleKeys.size === 0) return true;
  const atom = cardAtom(card);
  if (atom === 'runtime_agenda') return false;
  if (!isLowSignalDuplicateCandidate(atom)) return true;
  const key = titleKey(dynamicCardTitle(card));
  return !key || !dailyArtifactTitleKeys.has(key);
}

function isLowSignalDuplicateCandidate(type: string): boolean {
  return [
    'discovery',
    'operating_review',
    'metric_chart',
    'metric_line_chart',
    'line_chart',
    'metric_empty_state',
  ].includes(type);
}

function dynamicCardTitle(card: TodayDynamicCard): string | null {
  const data = card.data as Record<string, unknown>;
  const direct = data.title;
  if (typeof direct === 'string') return direct;
  const nextAction = data.next_action;
  if (nextAction && typeof nextAction === 'object') {
    const title = (nextAction as Record<string, unknown>).title;
    if (typeof title === 'string') return title;
  }
  const actionTitle = data.action_title;
  return typeof actionTitle === 'string' ? actionTitle : null;
}

function titleKey(value: unknown): string {
  return String(value ?? '')
    .replace(/[：:]/gu, '')
    .replace(/[，,。.;；\s]+/gu, '')
    .trim()
    .toLowerCase();
}

function renderDynamicCard({
  card,
  atom,
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
  atom: string;
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
  if (atom === 'daily_artifact') {
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

  if (!CARD_MAP[atom]) return null;

  const descriptor: ServerCardDescriptor = {
    type: atom,
    data: card.data,
    actions: card.actions,
  };
  const rendered = renderCard(descriptor, onCardAction ? { onAction: onCardAction } : {});
  return rendered ? <View key={key}>{rendered}</View> : null;
}

function cardAtom(card: TodayDynamicCard): string {
  const atom = card.render?.atom;
  return typeof atom === 'string' && atom.trim() ? atom.trim() : card.type;
}

const styles = StyleSheet.create({
  container: {
    gap: 12,
  },
  section: {
    gap: 10,
  },
});
