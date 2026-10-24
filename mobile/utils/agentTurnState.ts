import { normalizeWriteReceipt } from '../services/writeReceipt';

export type AgentTerminalStatus =
  | 'complete'
  | 'partial'
  | 'waiting_for_user'
  | 'blocked'
  | 'failed'
  | 'refused'
  | 'reconciliation_required';

export function normalizeAgentTerminalStatus(value: unknown): AgentTerminalStatus | undefined {
  return value === 'complete'
    || value === 'partial'
    || value === 'waiting_for_user'
    || value === 'blocked'
    || value === 'failed'
    || value === 'refused'
    || value === 'reconciliation_required'
    ? value
    : undefined;
}

export type AgentTurnPhase =
  | 'idle'
  | 'submitted'
  | 'running'
  | 'writing'
  | 'verifying'
  | 'waiting_for_user'
  | 'blocked'
  | 'refused'
  | 'reconciliation_required'
  | 'partial'
  | 'completed'
  | 'failed'
  | 'interrupted';

export type AgentRecoveredPhase = 'partial' | 'completed' | 'failed' | 'interrupted'
  | 'waiting_for_user' | 'blocked' | 'refused' | 'reconciliation_required';

export function recoveredAgentPhase(
  completionStatus: unknown, terminalStatus: unknown, missingWriteReceipt: boolean,
): AgentRecoveredPhase {
  if (missingWriteReceipt) return 'failed';
  if (terminalStatus === 'partial' || terminalStatus === 'waiting_for_user' || terminalStatus === 'blocked'
      || terminalStatus === 'failed' || terminalStatus === 'refused'
      || terminalStatus === 'reconciliation_required') return terminalStatus;
  if (completionStatus === 'interrupted') return 'interrupted';
  return completionStatus === 'error' ? 'failed' : 'completed';
}

export type AgentRetryMode = 'resubmit' | 'retry_source';

export interface AgentTurnState {
  version: 1;
  phase: AgentTurnPhase;
  turnId: string | null;
  requestFingerprint?: string;
  conversationId?: number;
  messageId?: number;
  startedAt?: number;
  updatedAt?: number;
  label?: string;
  errorCode?: string;
  retryMode?: AgentRetryMode;
  recoverable: boolean;
  hadWrite: boolean;
  writeVerified?: boolean;
  verifiedWriteOperationIds?: string[];
  writeUncertain?: boolean;
  resultLabel?: string;
}

export type AgentTurnEvent =
  | { type: 'hydrate'; snapshot: AgentTurnState }
  | { type: 'submit'; turnId: string; at: number; requestFingerprint?: string; label?: string }
  | { type: 'accepted'; at: number; conversationId?: number; label?: string }
  | { type: 'status'; at: number; stage?: string; label?: string }
  | { type: 'tool_started'; at: number; toolName?: string; writes?: boolean; label?: string }
  | {
      type: 'tool_finished';
      at: number;
      toolName?: string;
      writes?: boolean;
      success: boolean;
      receiptVerified?: boolean;
      writeReceipts?: readonly unknown[];
      writeOutcome?: 'verified' | 'rejected' | 'failed' | 'uncertain';
      errorCode?: string;
      label?: string;
    }
  | {
      type: 'done';
      at: number;
      writeReceipts?: readonly unknown[];
      actionOutcomes?: readonly { status?: unknown }[];
      completionStatus?: 'complete' | 'interrupted' | 'error' | 'unknown';
      terminalStatus?: 'complete' | 'partial' | 'waiting_for_user' | 'blocked' | 'failed' | 'refused' | 'reconciliation_required';
      conversationId?: number;
      messageId?: number;
      retryable?: boolean;
      retryMode?: AgentRetryMode;
      errorCode?: string;
    }
  | { type: 'fail'; at: number; errorCode: string; label?: string; recoverable?: boolean }
  | { type: 'interrupt'; at: number; errorCode?: string; label?: string; recoverable?: boolean }
  | {
      type: 'recover';
      turnId?: string;
      at: number;
      writeReceipts?: readonly unknown[];
      actionOutcomes?: readonly { status?: unknown }[];
      serverStatus: 'running' | AgentRecoveredPhase;
      conversationId?: number;
      messageId?: number;
      errorCode?: string;
      label?: string;
      hadWrite?: boolean;
      writeVerified?: boolean;
      recoverable?: boolean;
      retryMode?: AgentRetryMode;
    }
  | { type: 'reset' };

export function createIdleAgentTurn(): AgentTurnState {
  return {
    version: 1,
    phase: 'idle',
    turnId: null,
    recoverable: false,
    hadWrite: false,
  };
}

export function isAgentTurnTerminal(state: AgentTurnState): boolean {
  return state.phase === 'completed'
    || state.phase === 'partial'
    || state.phase === 'waiting_for_user'
    || state.phase === 'blocked'
    || state.phase === 'failed'
    || state.phase === 'refused'
    || state.phase === 'reconciliation_required'
    || state.phase === 'interrupted';
}

export function agentTurnPhaseFromStatus(_stage?: string): AgentTurnPhase {
  return 'running';
}

export function resolveAgentTurnStatusLabel(
  currentLabel: string | undefined,
  nextStage: string | undefined,
  nextLabel: string | undefined,
): string | undefined {
  // `thinking` is a generic heartbeat. Once the server has acknowledged the
  // concrete request, replacing that acknowledgement with a less informative
  // label makes the UI appear to regress. Specific progress stages are still
  // allowed to replace the current label.
  if (nextStage === 'thinking' && currentLabel?.trim()) return currentLabel;
  return nextLabel?.trim() ? nextLabel : currentLabel;
}

function reduceAgentTurnBase(state: AgentTurnState, event: AgentTurnEvent): AgentTurnState {
  if (event.type === 'reset') return createIdleAgentTurn();
  if (event.type === 'hydrate') return event.snapshot;
  if (event.type === 'submit') {
    return {
      version: 1,
      phase: 'submitted',
      turnId: event.turnId,
      requestFingerprint: event.requestFingerprint,
      startedAt: event.at,
      updatedAt: event.at,
      label: event.label,
      recoverable: true,
      retryMode: 'resubmit',
      hadWrite: false,
    };
  }
  if (isAgentTurnTerminal(state) && event.type !== 'recover') return state;

  switch (event.type) {
    case 'accepted':
      return {
        ...state,
        phase: 'running',
        conversationId: event.conversationId ?? state.conversationId,
        updatedAt: event.at,
        label: event.label ?? state.label,
        errorCode: undefined,
        recoverable: true,
        retryMode: undefined,
      };
    case 'status':
      return {
        ...state,
        phase: agentTurnPhaseFromStatus(event.stage),
        updatedAt: event.at,
        label: resolveAgentTurnStatusLabel(state.label, event.stage, event.label),
        recoverable: true,
      };
    case 'tool_started':
      return {
        ...state,
        phase: event.writes ? 'writing' : 'running',
        updatedAt: event.at,
        label: event.label ?? state.label,
        hadWrite: state.hadWrite || event.writes === true,
        recoverable: true,
      };
    case 'tool_finished': {
      const hadWrite = state.hadWrite || event.writes === true;
      if (!event.success && event.writes) {
        return {
          ...state,
          phase: 'verifying',
          updatedAt: event.at,
          label: event.label,
          errorCode: event.errorCode ?? 'tool_failed',
          recoverable: false,
          retryMode: undefined,
          hadWrite,
          writeVerified: event.writes ? false : state.writeVerified,
        };
      }
      if (!event.success) {
        return {
          ...state,
          phase: 'running',
          updatedAt: event.at,
          label: event.label ?? state.label,
          errorCode: undefined,
          recoverable: true,
          hadWrite,
        };
      }
      if (event.writes && event.receiptVerified === false) {
        return {
          ...state,
          phase: 'verifying',
          updatedAt: event.at,
          label: event.label,
          errorCode: event.errorCode ?? 'write_receipt_missing_identity',
          recoverable: false,
          retryMode: undefined,
          hadWrite: true,
          writeVerified: false,
        };
      }
      return {
        ...state,
        phase: event.writes ? 'verifying' : 'running',
        updatedAt: event.at,
        label: event.label ?? state.label,
        errorCode: undefined,
        recoverable: event.writes ? false : true,
        retryMode: event.writes ? undefined : state.retryMode,
        hadWrite,
        writeVerified: event.writes && event.receiptVerified === true ? true : state.writeVerified,
      };
    }
    case 'done':
      if (event.terminalStatus && event.terminalStatus !== 'complete') {
        const phase = event.terminalStatus;
        return {
          ...state,
          phase,
          conversationId: event.conversationId ?? state.conversationId,
          messageId: event.messageId ?? state.messageId,
          updatedAt: event.at,
          label: undefined,
          errorCode: event.errorCode ?? state.errorCode,
          recoverable: event.retryable === true,
          retryMode: event.retryable === true ? event.retryMode : undefined,
          ...(phase === 'reconciliation_required' ? { writeVerified: false } : {}),
        };
      }
      if (event.completionStatus === 'interrupted') {
        return {
          ...state,
          phase: 'interrupted',
          conversationId: event.conversationId ?? state.conversationId,
          messageId: event.messageId ?? state.messageId,
          updatedAt: event.at,
          label: undefined,
          errorCode: event.errorCode ?? state.errorCode ?? 'stream_interrupted',
          recoverable: event.retryable === true,
          retryMode: event.retryable === true ? event.retryMode : undefined,
        };
      }
      if (event.completionStatus === 'error') {
        return {
          ...state,
          phase: 'failed',
          conversationId: event.conversationId ?? state.conversationId,
          messageId: event.messageId ?? state.messageId,
          updatedAt: event.at,
          label: undefined,
          errorCode: event.errorCode ?? state.errorCode ?? 'stream_error',
          recoverable: event.retryable === true,
          retryMode: event.retryable === true ? event.retryMode : undefined,
        };
      }
      if (state.hadWrite && state.writeVerified !== true) {
        return {
          ...state,
          phase: 'failed',
          conversationId: event.conversationId ?? state.conversationId,
          messageId: event.messageId ?? state.messageId,
          updatedAt: event.at,
          label: undefined,
          errorCode: state.errorCode ?? 'write_receipt_missing_identity',
          recoverable: false,
          retryMode: undefined,
          writeVerified: false,
        };
      }
      return {
        ...state,
        phase: 'completed',
        conversationId: event.conversationId ?? state.conversationId,
        messageId: event.messageId ?? state.messageId,
        updatedAt: event.at,
        label: undefined,
        errorCode: undefined,
        recoverable: false,
        retryMode: undefined,
      };
    case 'fail':
      return {
        ...state,
        phase: 'failed',
        updatedAt: event.at,
        label: event.label,
        errorCode: event.errorCode,
        recoverable: event.recoverable ?? true,
        retryMode: (event.recoverable ?? true)
          ? (state.retryMode ?? 'resubmit')
          : undefined,
      };
    case 'interrupt':
      return {
        ...state,
        phase: 'interrupted',
        updatedAt: event.at,
        label: event.label,
        errorCode: event.errorCode ?? 'stream_interrupted',
        recoverable: event.recoverable ?? true,
        retryMode: (event.recoverable ?? true) ? state.retryMode : undefined,
      };
    case 'recover': {
      const recoveredIsRunning = event.serverStatus === 'running';
      const recoveredIsCompleted = event.serverStatus === 'completed';
      const recoveredIsRetryable = event.recoverable === true;
      return {
        ...state,
        phase: event.serverStatus,
        conversationId: event.conversationId ?? state.conversationId,
        messageId: event.messageId ?? state.messageId,
        updatedAt: event.at,
        label: event.label,
        errorCode: event.serverStatus === 'failed'
          ? (event.errorCode ?? 'recovery_failed')
          : event.serverStatus === 'interrupted'
            ? (event.errorCode ?? 'stream_interrupted')
            : event.serverStatus !== 'completed' && event.serverStatus !== 'running'
              ? event.errorCode
              : undefined,
        recoverable: recoveredIsRunning
          ? true
          : recoveredIsCompleted
            ? false
            : recoveredIsRetryable,
        retryMode: recoveredIsRetryable ? event.retryMode : undefined,
        hadWrite: event.hadWrite ?? state.hadWrite,
        writeVerified: event.writeVerified ?? state.writeVerified,
      };
    }
  }
}

/** A partial retry is authorized only for the server-bound pending intake items. */
export function hasActiveRetrySource(outcome: any, action: any): boolean {
  if (action?.type !== 'retry_source_turn' || action?.status !== 'active') return false;
  if (outcome?.status === 'reconciliation_required'
    || (Array.isArray(outcome?.actions) && outcome.actions.some((item: any) => item?.status === 'uncertain' || item?.status === 'reconciliation_required'))) return false;
  if (outcome?.status === 'partial') {
    return action.version === 1 && action.scope === 'intake_pending_items';
  }
  return outcome?.retryable === true;
}

/** Keep per-write evidence separate from the authoritative whole-turn verdict. */
export function reduceAgentTurn(state: AgentTurnState, event: AgentTurnEvent): AgentTurnState {
  const sameRecoveredMessage = event.type !== 'recover' || (
    typeof event.conversationId === 'number' && event.conversationId === state.conversationId
    && (event.turnId == null || event.turnId === state.turnId)
    && ((typeof event.messageId === 'number' && event.messageId === state.messageId)
      || ((event.messageId == null || state.messageId == null)
        && typeof event.turnId === 'string' && event.turnId.length > 0 && event.turnId === state.turnId))
  );
  const evidenceState = sameRecoveredMessage ? state : {
    ...state, hadWrite: false, writeVerified: undefined,
    verifiedWriteOperationIds: [], writeUncertain: false, resultLabel: undefined,
  };
  const next = reduceAgentTurnBase(evidenceState, event);
  if (event.type === 'reset' || event.type === 'submit' || event.type === 'hydrate') return next;
  if (isAgentTurnTerminal(state) && event.type !== 'recover') return next;
  const receipts = 'writeReceipts' in event ? event.writeReceipts : undefined;
  const ids = [...new Set([
    ...(evidenceState.verifiedWriteOperationIds || []),
    ...(receipts || []).flatMap(raw => {
      const receipt = normalizeWriteReceipt(raw);
      return receipt?.status === 'verified' ? [receipt.operationId] : [];
    }),
  ])];
  const actions = 'actionOutcomes' in event ? event.actionOutcomes : undefined;
  const uncertainAction = actions?.some(action => (
    action?.status === 'reconciliation_required' || action?.status === 'uncertain'
  ));
  const writeUncertain = evidenceState.writeUncertain === true || uncertainAction === true
    || next.phase === 'reconciliation_required'
    || (event.type === 'tool_finished' && event.writes === true
      && (event.writeOutcome === 'uncertain' || (event.success && event.receiptVerified === false)));
  const terminal = isAgentTurnTerminal(next);
  const hasVerified = ids.length > 0;
  const unsafeRetry = writeUncertain || (hasVerified && next.retryMode === 'resubmit');
  return {
    ...next,
    verifiedWriteOperationIds: ids,
    writeUncertain,
    ...(terminal && writeUncertain && next.phase === 'completed'
      ? { phase: 'reconciliation_required' as const } : {}),
    resultLabel: terminal && hasVerified && (next.phase !== 'completed' || writeUncertain)
      ? writeUncertain ? '部分已保存，其余记录状态待核对' : '部分已保存，请查看未完成事项'
      : undefined,
    ...(unsafeRetry ? { recoverable: false, retryMode: undefined } : {}),
  };
}
