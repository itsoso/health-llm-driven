/* eslint-disable @typescript-eslint/no-require-imports, import/first */

const mockApiPost = jest.fn();
const mockConfirmWriteIntent = jest.fn();
const mockDismissWriteIntent = jest.fn();

jest.mock('../api', () => ({
  __esModule: true,
  default: { post: (...args: any[]) => mockApiPost(...args) },
}));

jest.mock('../writeIntents', () => ({
  confirmWriteIntent: (...args: any[]) => mockConfirmWriteIntent(...args),
  dismissWriteIntent: (...args: any[]) => mockDismissWriteIntent(...args),
}));

import { dispatchChatCardAction } from '../chatCardActions';

describe('dispatchChatCardAction', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockApiPost.mockResolvedValue({ data: { ok: true } });
    mockConfirmWriteIntent.mockResolvedValue({ status: 'executed' });
    mockDismissWriteIntent.mockResolvedValue({ status: 'dismissed' });
  });

  it('completes agenda actions only through the allowed manual-confirm endpoint', async () => {
    await dispatchChatCardAction({
      label: '完成',
      action: 'agenda.complete',
      endpoint: '/agenda/complete',
      requires_manual_confirm: true,
      payload: {
        source: { object_type: 'health_protocol', object_id: 7 },
      },
    });

    expect(mockApiPost).toHaveBeenCalledWith('/agenda/complete', {
      object_type: 'health_protocol',
      object_id: 7,
      status: 'done',
      track: 'protocol',
      value: null,
    });
  });

  it('rejects write actions that are not explicitly manual-confirmed', async () => {
    await expect(dispatchChatCardAction({
      label: '完成',
      action: 'agenda.complete',
      endpoint: '/agenda/complete',
      payload: {
        source: { object_type: 'health_protocol', object_id: 7 },
      },
    })).rejects.toThrow('manual_confirm_required');

    expect(mockApiPost).not.toHaveBeenCalled();
  });

  it('rejects arbitrary endpoints instead of forwarding model-chosen writes', async () => {
    await expect(dispatchChatCardAction({
      label: '危险写入',
      action: 'agenda.complete',
      endpoint: '/medications/7/dose',
      requires_manual_confirm: true,
      payload: {
        source: { object_type: 'health_protocol', object_id: 7 },
      },
    })).rejects.toThrow('unsupported_card_action_endpoint');

    expect(mockApiPost).not.toHaveBeenCalled();
  });

  it('confirms write-intent actions by id', async () => {
    await dispatchChatCardAction({
      label: '确认写入',
      action: 'write_intent.confirm',
      endpoint: '/write-intents/42/confirm',
      requires_manual_confirm: true,
      payload: { write_intent_id: 42 },
    });

    expect(mockConfirmWriteIntent).toHaveBeenCalledWith(42);
  });

  it('opens only app-local route actions', async () => {
    await expect(dispatchChatCardAction({
      label: '打开阿衡',
      action: 'route.open',
      payload: { route: '/(tabs)/chat?prompt=hrv' },
    })).resolves.toEqual({
      status: 'opened',
      route: '/(tabs)/chat?prompt=hrv',
    });
  });

  it('rejects scheme-relative and control-character route actions', async () => {
    await expect(dispatchChatCardAction({
      label: '打开外部站点',
      action: 'route.open',
      payload: { route: '//example.test/path' },
    })).rejects.toThrow('invalid_route_action');

    await expect(dispatchChatCardAction({
      label: '打开异常路径',
      action: 'route.open',
      payload: { route: '/(tabs)/chat\ninject' },
    })).rejects.toThrow('invalid_route_action');
  });
});
