import type { MedicationBatchActionOutcome } from '@/services/api/writeIntents';
import { readMedicationBatchIntentId } from '@/services/api/writeIntents';

import type { ChatCardActionDescriptor, ServerCardDescriptor } from './types';

export function medicationBatchIntentIdForAction(
  action: ChatCardActionDescriptor,
): number | null {
  if (action.action !== 'write_intent.confirm' && action.action !== 'write_intent.dismiss') {
    return null;
  }
  return readMedicationBatchIntentId(action.payload?.write_intent_id);
}

export function medicationBatchItemCount(
  descriptor: ServerCardDescriptor,
  intentId: number,
): number | null {
  if (descriptor.type === 'cards_group' && Array.isArray(descriptor.data?.cards)) {
    for (const child of descriptor.data.cards as ServerCardDescriptor[]) {
      const count = medicationBatchItemCount(child, intentId);
      if (count != null) return count;
    }
    return null;
  }
  if (!cardTargetsMedicationIntent(descriptor, intentId)) return null;
  return Array.isArray(descriptor.data?.items) ? descriptor.data.items.length : null;
}

export function projectMedicationBatchPending(
  descriptor: ServerCardDescriptor,
  intentId: number,
  pending: boolean,
): ServerCardDescriptor {
  return mapMedicationDescriptor(descriptor, intentId, (card) => ({
    ...card,
    data: { ...(card.data || {}), action_pending: pending },
  }));
}

export function projectMedicationBatchTerminal(
  descriptor: ServerCardDescriptor,
  intentId: number,
  outcome: MedicationBatchActionOutcome,
): ServerCardDescriptor {
  return mapMedicationDescriptor(descriptor, intentId, (card) => ({
    type: card.type,
    data: {
      ...(card.data || {}),
      action_pending: false,
      decision_status: outcome.decisionStatus,
      write_receipts: outcome.decisionStatus === 'executed' ? outcome.writeReceipts : [],
      safety_alerts: outcome.decisionStatus === 'executed' ? outcome.safetyAlerts : [],
    },
    actions: [],
  }));
}

function mapMedicationDescriptor(
  descriptor: ServerCardDescriptor,
  intentId: number,
  transform: (card: ServerCardDescriptor) => ServerCardDescriptor,
): ServerCardDescriptor {
  if (descriptor.type === 'cards_group' && Array.isArray(descriptor.data?.cards)) {
    return {
      ...descriptor,
      data: {
        ...descriptor.data,
        cards: (descriptor.data.cards as ServerCardDescriptor[]).map(card => (
          mapMedicationDescriptor(card, intentId, transform)
        )),
      },
    };
  }
  return cardTargetsMedicationIntent(descriptor, intentId)
    ? transform(descriptor)
    : descriptor;
}

function cardTargetsMedicationIntent(
  descriptor: ServerCardDescriptor,
  intentId: number,
): boolean {
  return descriptor.type === 'medication_draft'
    && Array.isArray(descriptor.actions)
    && descriptor.actions.some(action => (
      medicationBatchIntentIdForAction(action) === intentId
    ));
}
