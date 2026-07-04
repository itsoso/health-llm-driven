import api from '../api';
import {
  buildQuickRecordTextFromAssistantReply,
  createRecordFromAssistantReply,
  saveAssistantReplyAsMemory,
} from '../chatResultActions';

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

  it('extracts a diet quick record from an assistant recorded-meal sentence', () => {
    expect(buildQuickRecordTextFromAssistantReply(
      '✅ 已记录午餐 — 煎牛肉能量碗 + 姜黄鲜柠维C茶，770 kcal（蛋白 30g / 碳水 70g / 脂肪 17g）',
    )).toBe('午餐煎牛肉能量碗 + 姜黄鲜柠维C茶');

    expect(buildQuickRecordTextFromAssistantReply(
      '加餐已记录: 草莓奶油蛋糕 150g + 草莓 50g\n本餐蛋白偏低。',
    )).toBe('加餐草莓奶油蛋糕 150g + 草莓 50g');
  });

  it('does not infer a diet quick record from medication-like assistant text', () => {
    expect(buildQuickRecordTextFromAssistantReply(
      '✅ 已记录午餐 — 替普瑞酮胶囊（施维舒）。请按医嘱服用。',
    )).toBeNull();
  });

  it('creates a quick record from assistant text when a deterministic record can be inferred', async () => {
    (api.post as jest.Mock).mockResolvedValueOnce({
      data: {
        type: 'diet',
        message: '已记录午餐：煎牛肉能量碗 + 姜黄鲜柠维C茶',
        record_id: 91,
        undo_path: 'diet/records/91',
      },
    });

    await expect(createRecordFromAssistantReply(
      '已记录午餐 — 煎牛肉能量碗 + 姜黄鲜柠维C茶，770 kcal',
    )).resolves.toEqual({
      status: 'created',
      type: 'diet',
      message: '已记录午餐：煎牛肉能量碗 + 姜黄鲜柠维C茶',
      recordId: 91,
      undoPath: 'diet/records/91',
    });

    expect(api.post).toHaveBeenCalledWith('/quick-record', {
      text: '午餐煎牛肉能量碗 + 姜黄鲜柠维C茶',
    });
  });

  it('falls back to the record page when no quick record can be inferred', async () => {
    await expect(createRecordFromAssistantReply('这是一段泛化建议，不包含明确记录。')).resolves.toEqual({
      status: 'needs_manual',
      message: '没识别到可直接写入的记录，已打开记录页',
      route: '/(tabs)/record',
    });
    expect(api.post).not.toHaveBeenCalled();
  });
});
