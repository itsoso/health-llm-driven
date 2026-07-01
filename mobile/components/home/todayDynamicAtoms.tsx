import React from 'react';
import { View } from 'react-native';

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

export interface TodayDynamicAtomRenderArgs {
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
}

interface TodayDynamicAtomSpec {
  atom: string;
  render: (args: TodayDynamicAtomRenderArgs) => React.ReactElement | null;
}

export const TODAY_DYNAMIC_ATOMS: Record<string, TodayDynamicAtomSpec> = {
  daily_artifact: {
    atom: 'daily_artifact',
    render: renderDailyArtifactAtom,
  },
};

export function resolveTodayDynamicAtom(card: TodayDynamicCard): string {
  const atom = card.render?.atom;
  return typeof atom === 'string' && atom.trim() ? atom.trim() : card.type;
}

export function collectTodayDynamicPromotedTitleKeys(view: TodayDynamicView | null | undefined): Set<string> {
  const keys = new Set<string>();
  for (const section of view?.sections ?? []) {
    for (const card of section.cards) {
      if (resolveTodayDynamicAtom(card) !== 'daily_artifact') continue;
      const artifact = card.data as Partial<DailyArtifact>;
      if (artifact.top_action?.title) keys.add(artifact.top_action.title);
    }
  }
  return keys;
}

export function shouldRenderTodayDynamicCard(
  card: TodayDynamicCard,
  promotedTitleKeys: Set<string>,
): boolean {
  if (promotedTitleKeys.size === 0) return true;
  const atom = resolveTodayDynamicAtom(card);
  if (atom === 'runtime_agenda') return false;
  if (!isLowSignalDuplicateCandidate(atom)) return true;
  const key = titleKey(dynamicCardTitle(card));
  return !key || !hasTitleKey(promotedTitleKeys, key);
}

export function renderTodayDynamicAtom(args: TodayDynamicAtomRenderArgs): React.ReactElement | null {
  const atom = resolveTodayDynamicAtom(args.card);
  const spec = TODAY_DYNAMIC_ATOMS[atom];
  if (spec) return spec.render(args);
  if (!CARD_MAP[atom]) return null;

  const descriptor: ServerCardDescriptor = {
    type: atom,
    data: args.card.data,
    actions: args.card.actions,
  };
  const rendered = renderCard(
    descriptor,
    args.onCardAction ? { onAction: args.onCardAction } : {},
  );
  return rendered ? <View key={args.key}>{rendered}</View> : null;
}

function renderDailyArtifactAtom({
  card,
  key,
  completing,
  skipping,
  onDailyArtifactComplete,
  onDailyArtifactSkip,
  onDailyArtifactAsk,
  onDailyArtifactExplainBasis,
  onDailyArtifactPressAction,
}: TodayDynamicAtomRenderArgs): React.ReactElement {
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

function isLowSignalDuplicateCandidate(atom: string): boolean {
  return [
    'discovery',
    'operating_review',
    'metric_chart',
    'metric_line_chart',
    'line_chart',
    'metric_empty_state',
  ].includes(atom);
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

function hasTitleKey(values: Set<string>, key: string): boolean {
  for (const value of values) {
    if (titleKey(value) === key) return true;
  }
  return false;
}

function titleKey(value: unknown): string {
  return String(value ?? '')
    .replace(/[：:]/gu, '')
    .replace(/[，,。.;；\s]+/gu, '')
    .trim()
    .toLowerCase();
}
