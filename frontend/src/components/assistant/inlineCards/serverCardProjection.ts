import { renderServerCards } from './registry';
import type { ServerCardDescriptor } from './types';
import type { MedicationBatchActionOutcome } from '@/services/api/writeIntents';

export interface MedicationBatchTerminalProjection {
  intentId: number;
  outcome: MedicationBatchActionOutcome;
}

/**
 * Keep every valid server-issued card attached to the same assistant message.
 * A reply can legitimately contain both a media result and a recoverable diet
 * action; selecting the first descriptor makes the later action undiscoverable.
 */
export function projectServerCards(
  value: unknown,
  assistantMeta?: unknown,
): ServerCardDescriptor | null {
  const cards = restoreMedicationTerminalFromMeta(
    renderServerCards(value as ServerCardDescriptor[] | null | undefined),
    assistantMeta,
  );
  if (cards.length === 0) return null;
  if (cards.length === 1) return cards[0];
  return { type: 'cards_group', data: { cards } };
}

function restoreMedicationTerminalFromMeta(
  cards: ServerCardDescriptor[],
  assistantMeta: unknown,
): ServerCardDescriptor[] {
  const terminal = medicationBatchTerminalFromMeta(assistantMeta);
  if (!terminal) return cards;
  const { intentId, outcome } = terminal;
  const medicationCards = cards.filter(card => card.type === 'medication_draft');
  return cards.map((card) => {
    if (card.type !== 'medication_draft') return card;
    const targetsIntent = card.actions?.some(action => (
      readIntentId(action.payload?.write_intent_id) === intentId
    ));
    if (!targetsIntent && medicationCards.length !== 1) return card;
    return {
      type: card.type,
      data: {
        ...(card.data || {}),
        decision_status: outcome.decisionStatus,
        write_receipts: outcome.decisionStatus === 'executed' ? outcome.writeReceipts : [],
        safety_alerts: outcome.decisionStatus === 'executed' ? outcome.safetyAlerts : [],
      },
    };
  });
}

/**
 * Decode one authoritative medication terminal from an SSE done payload or
 * persisted assistant meta. New servers keep exact batch evidence inside the
 * decision namespace because the top-level arrays may also contain unrelated
 * writes from the same turn. Top-level arrays are legacy fallback only.
 */
export function medicationBatchTerminalFromMeta(
  assistantMeta: unknown,
): MedicationBatchTerminalProjection | null {
  if (!assistantMeta || typeof assistantMeta !== 'object' || Array.isArray(assistantMeta)) {
    return null;
  }
  const meta = assistantMeta as Record<string, unknown>;
  const rawDecision = meta.medication_batch_decision;
  if (!rawDecision || typeof rawDecision !== 'object' || Array.isArray(rawDecision)) return null;
  const decision = rawDecision as Record<string, unknown>;
  const intentId = readIntentId(decision.intent_id);
  const status = decision.status;
  if (intentId == null || (status !== 'executed' && status !== 'dismissed' && status !== 'expired')) {
    return null;
  }
  const writeReceipts = status === 'executed'
    ? (Array.isArray(decision.write_receipts)
      ? decision.write_receipts
      : Array.isArray(meta.write_receipts) ? meta.write_receipts : [])
    : [];
  const safetyAlerts = status === 'executed'
    ? (Array.isArray(decision.safety_alerts)
      ? decision.safety_alerts
      : Array.isArray(meta.safety_alerts) ? meta.safety_alerts : [])
    : [];
  return {
    intentId,
    outcome: {
      decisionStatus: status,
      writeReceipts: writeReceipts as MedicationBatchActionOutcome['writeReceipts'],
      safetyAlerts: safetyAlerts as MedicationBatchActionOutcome['safetyAlerts'],
      reconciliationRequired: status === 'executed' && writeReceipts.length === 0,
    },
  };
}

function readIntentId(value: unknown): number | null {
  const normalized = typeof value === 'number'
    ? value
    : typeof value === 'string' && value.trim()
      ? Number(value)
      : NaN;
  return Number.isInteger(normalized) && normalized > 0 ? normalized : null;
}
