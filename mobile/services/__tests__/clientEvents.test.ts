import api from '../api';
import {
  durationBucket,
  emitClientEvent,
  sanitizeClientEventMeta,
} from '../clientEvents';

jest.mock('../api', () => ({
  __esModule: true,
  default: { post: jest.fn().mockResolvedValue({ data: { ok: true } }) },
}));

const mockPost = api.post as jest.Mock;

describe('client reliability events', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it.each([
    [0, 'lt_1s'],
    [999, 'lt_1s'],
    [1_000, '1_3s'],
    [2_999, '1_3s'],
    [3_000, '3_10s'],
    [9_999, '3_10s'],
    [10_000, '10_30s'],
    [29_999, '10_30s'],
    [30_000, 'gte_30s'],
  ])('buckets a %d ms operation as %s', (elapsedMs, expected) => {
    expect(durationBucket(10_000, 10_000 + (elapsedMs as number))).toBe(expected);
  });

  it('removes content, audio, URI and resource identifiers from reliability metadata', () => {
    expect(sanitizeClientEventMeta('voice_input_terminal', {
      phase: 'completed',
      duration_bucket: '1_3s',
      action_type: 'dictation',
      content: '我的健康隐私',
      transcript: '我的健康隐私',
      audio: 'base64-secret',
      uri: 'file:///private/voice.m4a',
      resource_id: 42,
    })).toEqual({
      phase: 'completed',
      duration_bucket: '1_3s',
      action_type: 'dictation',
    });
  });

  it('drops invalid reliability values instead of forwarding arbitrary strings', () => {
    expect(sanitizeClientEventMeta('write_receipt_terminal', {
      phase: 'not-a-phase',
      duration_bucket: 'forever',
      action_type: 'diet.update\nsecret',
      error_code: 'x'.repeat(100),
      verified: 'yes',
    })).toEqual({});
  });

  it.each([
    ['verified', false],
    ['unverified', true],
    ['failed', true],
  ])('drops contradictory write receipt phase %s / verified %s', (phase, verified) => {
    expect(sanitizeClientEventMeta('write_receipt_terminal', {
      phase,
      duration_bucket: '1_3s',
      action_type: 'diet.update',
      verified,
    })).toEqual({});
  });

  it('posts only sanitized reliability metadata', async () => {
    await emitClientEvent('write_receipt_terminal', {
      phase: 'verified',
      duration_bucket: '3_10s',
      action_type: 'diet.update',
      verified: true,
      content: '不能上传',
      resource_id: 'meal-123',
    });

    expect(mockPost).toHaveBeenCalledWith('/client-events', {
      event_name: 'write_receipt_terminal',
      meta: {
        phase: 'verified',
        duration_bucket: '3_10s',
        action_type: 'diet.update',
        verified: true,
      },
    });
  });

  it('keeps existing event metadata backward compatible', () => {
    const meta = { source: 'chat', has_image: false };
    expect(sanitizeClientEventMeta('chat_message_sent', meta)).toBe(meta);
  });
});
