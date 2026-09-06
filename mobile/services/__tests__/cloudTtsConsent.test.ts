import api from '../api';
import { requireAIConsent } from '../aiConsent';
import { synthesize } from '../cloudTts';

jest.mock('../api', () => ({ __esModule: true, default: { post: jest.fn() } }));
jest.mock('../aiConsent', () => ({ requireAIConsent: jest.fn() }));

it('does not upload text for cloud speech after consent is refused', async () => {
  (requireAIConsent as jest.Mock).mockRejectedValue(new Error('ai_consent_required'));
  await expect(synthesize({ text: '私人健康建议', voiceKey: 'calm_male' })).rejects.toThrow('ai_consent_required');
  expect(api.post).not.toHaveBeenCalled();
});
