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

  it('routes medication-like assistant replies to the medication draft confirmation page', async () => {
    await expect(createRecordFromAssistantReply(
      '好的，记录你刚服用了沃克 20mg。我准备记录：用药：沃克（富马酸伏诺拉生片）20mg。',
    )).resolves.toEqual({
      status: 'needs_manual',
      message: '已识别到用药草稿，请确认后写入',
      route: '/medications?draft=medication&name=%E6%B2%83%E5%85%8B%EF%BC%88%E5%AF%8C%E9%A9%AC%E9%85%B8%E4%BC%8F%E8%AF%BA%E6%8B%89%E7%94%9F%E7%89%87%EF%BC%89&dose=20mg',
    });

    expect(api.post).not.toHaveBeenCalled();
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

  it('preserves severe blood-pressure recheck and symptom triage in chat record feedback', async () => {
    (api.post as jest.Mock).mockResolvedValueOnce({
      data: {
        type: 'bp',
        message: '已记录血压 185/85 mmHg',
        record_id: 92,
        undo_path: 'blood-pressure/records/92',
        category: '血压严重升高',
        category_color: '#FF3B30',
        safety_guidance: {
          severity: 'high',
          title: '血压严重升高，请复测',
          recheck_instruction: '请静坐至少 1 分钟后复测。',
          emergency_instruction: '若同时出现胸痛，请立即拨打急救电话。',
          action_path: '/blood-pressure',
        },
      },
    });

    await expect(createRecordFromAssistantReply('血压185/85')).resolves.toMatchObject({
      status: 'created',
      type: 'bp',
      category: '血压严重升高',
      categoryColor: '#FF3B30',
      safetyGuidance: { severity: 'high', action_path: '/blood-pressure' },
      message: expect.stringContaining('复测'),
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
