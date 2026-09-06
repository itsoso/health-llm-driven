import { afterEach, expect, it } from 'vitest';
import api from './client';
import { setAiConsentUser } from '@/services/aiConsent';

afterEach(() => setAiConsentUser(null));

it('stops speech upload at the HTTP boundary without consent', async () => {
  setAiConsentUser(null);
  const dispatched: string[] = [];
  await expect(api.post('/chat/transcribe', { audio_base64: 'synthetic' }, {
    adapter: async config => {
      dispatched.push(config.url || '');
      return { data: {}, status: 200, statusText: 'OK', headers: {}, config };
    },
  })).rejects.toThrow('未发送');
  expect(dispatched).toEqual([]);
});

it('continues manual non-AI record writes without permission', async () => {
  setAiConsentUser(null);
  const response = await api.post('/daily-health/water', { amount_ml: 100 }, {
    adapter: async config => ({ data: { saved: true }, status: 200, statusText: 'OK', headers: {}, config }),
  });
  expect(response.data.saved).toBe(true);
});
