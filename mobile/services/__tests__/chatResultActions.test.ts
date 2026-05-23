import api from '../api';
import { saveAssistantReplyAsMemory } from '../chatResultActions';

jest.mock('../api', () => ({
  __esModule: true,
  default: { post: jest.fn() },
}));

describe('chatResultActions', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('saves an assistant reply as a working memory fact', async () => {
    (api.post as jest.Mock).mockResolvedValueOnce({ data: { id: 12 } });

    await saveAssistantReplyAsMemory('建议今晚 23:00 前睡觉。');

    expect(api.post).toHaveBeenCalledWith('/memory-facts', {
      tier: 'working',
      subject: 'assistant_reply',
      predicate: 'suggests',
      object_value: '建议今晚 23:00 前睡觉。',
      confidence: 0.6,
      tags: ['chat', 'assistant_suggestion'],
      is_sensitive: false,
    });
  });
});
