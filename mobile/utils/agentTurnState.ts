export type AgentTurnPhase =
  | 'idle'
  | 'submitted'
  | 'running'
  | 'writing'
  | 'verifying'
  | 'completed'
  | 'failed'
  | 'interrupted';

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
      writeOutcome?: 'verified' | 'rejected' | 'failed' | 'uncertain';
      errorCode?: string;
      label?: string;
    }
  | {
      type: 'done';
      at: number;
      completionStatus?: 'complete' | 'interrupted' | 'error' | 'unknown';
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
      at: number;
      serverStatus: 'running' | 'completed' | 'failed' | 'interrupted';
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
  return state.phase === 'completed' || state.phase === 'failed' || state.phase === 'interrupted';
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

export function reduceAgentTurn(state: AgentTurnState, event: AgentTurnEvent): AgentTurnState {
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
      if (event.completionStatus === 'interrupted') {
        return {
          ...state,
          phase: 'interrupted',
          conversationId: event.conversationId ?? state.conversationId,
          messageId: event.messageId ?? state.messageId,
          updatedAt: event.at,
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
        phase: event.serverStatus === 'completed'
          ? 'completed'
          : event.serverStatus === 'failed'
            ? 'failed'
            : event.serverStatus === 'interrupted'
              ? 'interrupted'
              : 'running',
        conversationId: event.conversationId ?? state.conversationId,
        messageId: event.messageId ?? state.messageId,
        updatedAt: event.at,
        label: event.label,
        errorCode: event.serverStatus === 'failed'
          ? (event.errorCode ?? 'recovery_failed')
          : event.serverStatus === 'interrupted'
            ? (event.errorCode ?? 'stream_interrupted')
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
