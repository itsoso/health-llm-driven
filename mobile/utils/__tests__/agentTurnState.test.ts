import {
  agentTurnPhaseFromStatus,
  createIdleAgentTurn,
  isAgentTurnTerminal,
  reduceAgentTurn,
} from '../agentTurnState';

describe('agentTurnState', () => {
  it('starts a fresh submitted turn with a stable client id', () => {
    const state = reduceAgentTurn(createIdleAgentTurn(), {
      type: 'submit',
      turnId: 'turn-1',
      at: 100,
      requestFingerprint: 'request-abc',
    });

    expect(state).toMatchObject({
      phase: 'submitted',
      turnId: 'turn-1',
      requestFingerprint: 'request-abc',
      startedAt: 100,
      updatedAt: 100,
      recoverable: true,
    });
  });

  it.each([
    ['accepted', 'running'],
    ['thinking', 'running'],
    ['vision', 'running'],
    ['tool', 'running'],
    ['synthesis', 'running'],
    ['unknown', 'running'],
  ] as const)('maps backend status %s to %s', (stage, expected) => {
    expect(agentTurnPhaseFromStatus(stage)).toBe(expected);
  });

  it('keeps the contextual acknowledgement when a generic thinking heartbeat arrives', () => {
    const submitted = reduceAgentTurn(createIdleAgentTurn(), {
      type: 'submit', turnId: 'turn-contextual-status', at: 10, label: '正在提交…',
    });
    const accepted = reduceAgentTurn(submitted, {
      type: 'accepted', at: 20, label: '正在读取昨晚睡眠并评估今日训练…',
    });
    const thinking = reduceAgentTurn(accepted, {
      type: 'status', at: 30, stage: 'thinking', label: '正在思考…',
    });
    const synthesis = reduceAgentTurn(thinking, {
      type: 'status', at: 40, stage: 'synthesis', label: '正在整理回答…',
    });

    expect(thinking.label).toBe('正在读取昨晚睡眠并评估今日训练…');
    expect(synthesis.label).toBe('正在整理回答…');
  });

  it('moves a write tool through writing and verification', () => {
    const submitted = reduceAgentTurn(createIdleAgentTurn(), {
      type: 'submit', turnId: 'turn-write', at: 10,
    });
    const writing = reduceAgentTurn(submitted, {
      type: 'tool_started', toolName: 'health_record', writes: true, at: 20,
    });
    const verifying = reduceAgentTurn(writing, {
      type: 'tool_finished', toolName: 'health_record', writes: true, success: true, receiptVerified: true, at: 30,
    });

    expect(writing).toMatchObject({ phase: 'writing', hadWrite: true });
    expect(verifying).toMatchObject({
      phase: 'verifying',
      hadWrite: true,
      writeVerified: true,
    });
  });

  it('waits for the authoritative done event when a write lacks a receipt', () => {
    const submitted = reduceAgentTurn(createIdleAgentTurn(), {
      type: 'submit', turnId: 'turn-unverified', at: 10,
    });
    const verifying = reduceAgentTurn(submitted, {
      type: 'tool_finished',
      toolName: 'health_record',
      writes: true,
      success: true,
      receiptVerified: false,
      at: 30,
    });

    expect(verifying).toMatchObject({
      phase: 'verifying',
      errorCode: 'write_receipt_missing_identity',
      recoverable: false,
      writeVerified: false,
    });
  });

  it('keeps the turn running when a read-only tool fails so a later answer can recover', () => {
    const submitted = reduceAgentTurn(createIdleAgentTurn(), {
      type: 'submit', turnId: 'turn-read-failure', at: 10,
    });
    const afterReadFailure = reduceAgentTurn(submitted, {
      type: 'tool_finished',
      toolName: 'weather_context',
      writes: false,
      success: false,
      errorCode: 'tool_failed',
      at: 20,
    });
    const completed = reduceAgentTurn(afterReadFailure, {
      type: 'done', completionStatus: 'complete', messageId: 8, at: 30,
    });

    expect(afterReadFailure).toMatchObject({
      phase: 'running',
      hadWrite: false,
      recoverable: true,
    });
    expect(completed).toMatchObject({ phase: 'completed', messageId: 8 });
  });

  it('does not allow done to certify a write that never produced a verified receipt', () => {
    const submitted = reduceAgentTurn(createIdleAgentTurn(), {
      type: 'submit', turnId: 'turn-missing-receipt', at: 10,
    });
    const writing = reduceAgentTurn(submitted, {
      type: 'tool_started', toolName: 'health_record', writes: true, at: 20,
    });
    const failed = reduceAgentTurn(writing, {
      type: 'done', completionStatus: 'complete', messageId: 9, at: 30,
    });

    expect(failed).toMatchObject({
      phase: 'failed',
      messageId: 9,
      hadWrite: true,
      errorCode: 'write_receipt_missing_identity',
      recoverable: false,
    });
  });

  it('keeps an uncertain write nonterminal and applies a nonretryable final verdict', () => {
    const submitted = reduceAgentTurn(createIdleAgentTurn(), {
      type: 'submit', turnId: 'turn-uncertain', at: 10,
    });
    const verifying = reduceAgentTurn(submitted, {
      type: 'tool_finished',
      toolName: 'health_record',
      writes: true,
      success: false,
      receiptVerified: false,
      errorCode: 'missing_receipt',
      at: 20,
    });
    const failed = reduceAgentTurn(verifying, {
      type: 'done',
      completionStatus: 'error',
      retryable: false,
      errorCode: 'missing_receipt',
      messageId: 10,
      at: 30,
    });

    expect(verifying).toMatchObject({
      phase: 'verifying',
      recoverable: false,
      errorCode: 'missing_receipt',
    });
    expect(failed).toMatchObject({
      phase: 'failed',
      recoverable: false,
      errorCode: 'missing_receipt',
      messageId: 10,
    });
  });

  it('exposes retry_source only when the authoritative done event allows it', () => {
    const submitted = reduceAgentTurn(createIdleAgentTurn(), {
      type: 'submit', turnId: 'turn-safe-retry', at: 10,
    });
    const failed = reduceAgentTurn(submitted, {
      type: 'done',
      completionStatus: 'error',
      retryable: true,
      retryMode: 'retry_source',
      errorCode: 'write_without_tool',
      at: 20,
    });

    expect(failed).toMatchObject({
      phase: 'failed',
      recoverable: true,
      retryMode: 'retry_source',
      errorCode: 'write_without_tool',
    });
  });

  it.each([
    ['waiting_for_user', 'waiting_for_user'],
    ['blocked', 'blocked'],
    ['failed', 'failed'],
    ['refused', 'refused'],
    ['reconciliation_required', 'reconciliation_required'],
  ] as const)('uses authoritative %s terminal status instead of legacy complete', (terminalStatus, phase) => {
    const submitted = reduceAgentTurn(createIdleAgentTurn(), {
      type: 'submit', turnId: `turn-${terminalStatus}`, at: 10,
    });
    const terminal = reduceAgentTurn(submitted, {
      type: 'done',
      completionStatus: 'complete',
      terminalStatus,
      retryable: false,
      errorCode: terminalStatus,
      at: 20,
    });

    expect(terminal).toMatchObject({ phase, recoverable: false });
    expect(terminal.phase).not.toBe('completed');
  });

  it('keeps an interrupted turn recoverable and resolves it from server state', () => {
    const submitted = reduceAgentTurn(createIdleAgentTurn(), {
      type: 'submit', turnId: 'turn-resume', at: 10,
    });
    const interrupted = reduceAgentTurn(submitted, {
      type: 'interrupt', at: 20, errorCode: 'app_backgrounded',
    });
    const recovered = reduceAgentTurn(interrupted, {
      type: 'recover',
      serverStatus: 'completed',
      conversationId: 8,
      messageId: 19,
      at: 30,
    });

    expect(interrupted).toMatchObject({ phase: 'interrupted', recoverable: true });
    expect(recovered).toMatchObject({
      phase: 'completed',
      conversationId: 8,
      messageId: 19,
      recoverable: false,
    });
  });

  it('keeps accepted transport recovery without granting a resubmit action', () => {
    const submitted = reduceAgentTurn(createIdleAgentTurn(), {
      type: 'submit', turnId: 'turn-accepted-loss', at: 10,
    });
    const accepted = reduceAgentTurn(submitted, {
      type: 'accepted', conversationId: 8, at: 15,
    });
    const interrupted = reduceAgentTurn(accepted, {
      type: 'interrupt',
      at: 20,
      errorCode: 'stream_transport_interrupted',
      recoverable: true,
    });

    expect(interrupted).toMatchObject({
      phase: 'interrupted',
      recoverable: true,
      conversationId: 8,
    });
    expect(interrupted.retryMode).toBeUndefined();
  });

  it('hydrates verified write state from authoritative recovery metadata', () => {
    const interrupted = {
      ...reduceAgentTurn(createIdleAgentTurn(), {
        type: 'submit', turnId: 'turn-write-recovery', at: 10,
      }),
      phase: 'interrupted' as const,
      hadWrite: true,
    };
    const recovered = reduceAgentTurn(interrupted, {
      type: 'recover',
      serverStatus: 'completed',
      conversationId: 8,
      messageId: 20,
      hadWrite: true,
      writeVerified: true,
      at: 30,
    });

    expect(recovered).toMatchObject({
      phase: 'completed',
      hadWrite: true,
      writeVerified: true,
      recoverable: false,
    });
  });

  it('does not make a recovered server failure retryable without an explicit action', () => {
    const interrupted = reduceAgentTurn(
      reduceAgentTurn(createIdleAgentTurn(), {
        type: 'submit', turnId: 'turn-recovered-failure', at: 10,
      }),
      { type: 'interrupt', at: 20 },
    );
    const failed = reduceAgentTurn(interrupted, {
      type: 'recover',
      serverStatus: 'failed',
      errorCode: 'missing_receipt',
      at: 30,
    });

    expect(failed).toMatchObject({
      phase: 'failed',
      recoverable: false,
      errorCode: 'missing_receipt',
    });
  });

  it('hydrates a serializable non-idle snapshot', () => {
    const snapshot = {
      version: 1 as const,
      phase: 'interrupted' as const,
      turnId: 'turn-hydrated',
      conversationId: 42,
      startedAt: 100,
      updatedAt: 200,
      errorCode: 'app_backgrounded',
      recoverable: true,
      hadWrite: false,
    };

    expect(reduceAgentTurn(createIdleAgentTurn(), {
      type: 'hydrate',
      snapshot,
    })).toEqual(snapshot);
  });

  it('does not let late stream events overwrite a terminal turn', () => {
    const submitted = reduceAgentTurn(createIdleAgentTurn(), {
      type: 'submit', turnId: 'turn-terminal', at: 10,
    });
    const completed = reduceAgentTurn(submitted, {
      type: 'done', completionStatus: 'complete', messageId: 7, at: 20,
    });
    const lateStatus = reduceAgentTurn(completed, {
      type: 'status', stage: 'tool', label: '迟到的状态', at: 30,
    });

    expect(lateStatus).toEqual(completed);
    expect(isAgentTurnTerminal(lateStatus)).toBe(true);
  });

  it('maps an interrupted done event to a nonretryable terminal state by default', () => {
    const submitted = reduceAgentTurn(createIdleAgentTurn(), {
      type: 'submit', turnId: 'turn-cutoff', at: 10,
    });
    const interrupted = reduceAgentTurn(submitted, {
      type: 'done', completionStatus: 'interrupted', messageId: 11, at: 20,
    });

    expect(interrupted).toMatchObject({
      phase: 'interrupted',
      messageId: 11,
      errorCode: 'stream_interrupted',
      recoverable: false,
    });
    expect(isAgentTurnTerminal(interrupted)).toBe(true);
  });
});
