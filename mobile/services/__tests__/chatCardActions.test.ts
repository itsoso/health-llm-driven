jest.mock('../agenda', () => ({
  completeAgendaItem: jest.fn(),
}));

jest.mock('../writeIntents', () => ({
  confirmWriteIntent: jest.fn(),
  dismissWriteIntent: jest.fn(),
}));

import { completeAgendaItem } from '../agenda';
import { confirmWriteIntent, dismissWriteIntent } from '../writeIntents';
import { executeChatCardAction } from '../chatCardActions';

const completeAgenda = completeAgendaItem as jest.MockedFunction<typeof completeAgendaItem>;
const confirmIntent = confirmWriteIntent as jest.MockedFunction<typeof confirmWriteIntent>;
const dismissIntent = dismissWriteIntent as jest.MockedFunction<typeof dismissWriteIntent>;

function queryClient() {
  return {
    invalidateQueries: jest.fn().mockResolvedValue(undefined),
  };
}

describe('executeChatCardAction', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    completeAgenda.mockResolvedValue({ ok: true });
    confirmIntent.mockResolvedValue({ status: 'executed' });
    dismissIntent.mockResolvedValue({ status: 'dismissed' });
  });

  it('executes allowlisted agenda completion and refreshes runtime queries', async () => {
    const qc = queryClient();

    const result = await executeChatCardAction(
      {
        action: 'complete_agenda',
        endpoint: '/agenda/complete',
        label: '完成',
        payload: { source: { object_type: 'health_protocol', object_id: 12 } },
      },
      { queryClient: qc },
    );

    expect(result).toEqual({ status: 'executed', action: 'complete_agenda' });
    expect(completeAgenda).toHaveBeenCalledWith(
      { object_type: 'health_protocol', object_id: 12 },
      'protocol',
      undefined,
      { status: 'done' },
    );
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['timeline', 'today'] });
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['agenda', 'today'] });
  });

  it('executes allowlisted agenda skip with a reason', async () => {
    const qc = queryClient();

    await executeChatCardAction(
      {
        action: 'skip_agenda',
        label: '跳过',
        payload: {
          source: { object_type: 'health_protocol', object_id: 12 },
          skip_reason: 'too_tired',
        },
      },
      { queryClient: qc },
    );

    expect(completeAgenda).toHaveBeenCalledWith(
      { object_type: 'health_protocol', object_id: 12 },
      'protocol',
      undefined,
      { status: 'skipped', skipReason: 'too_tired' },
    );
  });

  it('confirms and dismisses write-intent actions through the manual-confirm ledger', async () => {
    const qc = queryClient();

    await executeChatCardAction(
      { action: 'confirm_write_intent', label: '确认', payload: { id: 7 } },
      { queryClient: qc },
    );
    await executeChatCardAction(
      { action: 'dismiss_write_intent', label: '忽略', payload: { write_intent_id: 8 } },
      { queryClient: qc },
    );

    expect(confirmIntent).toHaveBeenCalledWith(7);
    expect(dismissIntent).toHaveBeenCalledWith(8);
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['write-intents'] });
  });

  it('returns invalid for malformed known actions without calling write APIs', async () => {
    const result = await executeChatCardAction(
      { action: 'complete_agenda', label: '完成', payload: { source: { object_type: 'health_protocol' } } },
      { queryClient: queryClient() },
    );

    expect(result.status).toBe('invalid');
    expect(completeAgenda).not.toHaveBeenCalled();
    expect(confirmIntent).not.toHaveBeenCalled();
    expect(dismissIntent).not.toHaveBeenCalled();
  });

  it('treats unknown card actions as no-op instead of posting arbitrary endpoints', async () => {
    const result = await executeChatCardAction(
      { action: 'post_anything', endpoint: '/admin/log-level', label: '危险动作', payload: { level: 'DEBUG' } },
      { queryClient: queryClient() },
    );

    expect(result).toEqual({ status: 'unsupported', action: 'post_anything' });
    expect(completeAgenda).not.toHaveBeenCalled();
    expect(confirmIntent).not.toHaveBeenCalled();
    expect(dismissIntent).not.toHaveBeenCalled();
  });
});
