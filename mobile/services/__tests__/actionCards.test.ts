import api from '../api';
import {
  buildActionCockpitSections,
  createActionCard,
  pickWeeklySuggestionCards,
  recordCardAdherence,
  reviewActionCard,
  getActionCardProgress,
  getActionCardVerificationLabel,
  type ActionCard,
} from '../actionCards';

jest.mock('../api', () => ({
  __esModule: true,
  default: { get: jest.fn(), patch: jest.fn(), post: jest.fn() },
}));

const mockPost = api.post as jest.Mock;

describe('actionCards helpers', () => {
  beforeEach(() => jest.clearAllMocks());

  it('counts completed checklist items', () => {
    const card = {
      checklist: [
        { item: '记录晚餐时间', done: true },
        { item: '睡前不饮酒', done: false },
      ],
    } as ActionCard;

    expect(getActionCardProgress(card)).toEqual({ completed: 1, total: 2 });
  });

  it('ignores blank checklist placeholders in progress', () => {
    const card = {
      checklist: [
        { item: '', done: false },
        { item: '  ', done: false },
        { item: '预约复查', done: true },
      ],
    } as ActionCard;

    expect(getActionCardProgress(card)).toEqual({ completed: 1, total: 1 });
  });

  it('returns null progress when checklist is missing', () => {
    expect(getActionCardProgress({} as ActionCard)).toBeNull();
  });

  it('prefers latest assessment over expiration date for verification label', () => {
    const card = {
      expires_at: '2026-05-01T00:00:00Z',
      latest_assessment: { score: 8, summary: '睡眠评分改善' },
    } as ActionCard;

    expect(getActionCardVerificationLabel(card)).toBe('已评估 8/10');
  });

  it('uses expiration date when no assessment exists', () => {
    const card = { expires_at: '2026-05-01T00:00:00Z' } as ActionCard;

    expect(getActionCardVerificationLabel(card)).toBe('待验证 2026-05-01');
  });

  it('keeps the home weekly suggestion queue to undecided current weekly advisor cards', () => {
    const cards = [
      {
        id: 1,
        title: '待决策建议',
        status: 'active',
        source_type: 'weekly_advisor',
        content: '',
        card_type: 'recommendation',
        priority: 5,
        created_at: '2026-05-22T00:00:00Z',
      },
      {
        id: 2,
        title: '已接受建议',
        status: 'active',
        source_type: 'weekly_advisor',
        user_decision: 'accepted',
        content: '',
        card_type: 'recommendation',
        priority: 5,
        created_at: '2026-05-22T00:00:00Z',
      },
      {
        id: 3,
        title: '其他来源',
        status: 'active',
        source_type: 'manual',
        content: '',
        card_type: 'recommendation',
        priority: 5,
        created_at: '2026-05-22T00:00:00Z',
      },
    ] as ActionCard[];

    expect(pickWeeklySuggestionCards(cards).map(card => card.title)).toEqual(['待决策建议']);
  });

  it('builds intervention cockpit sections with immediate alerts limited to high priority', () => {
    const sections = buildActionCockpitSections(
      [
        { rule_id: 'r1', severity: 'critical', category: 'vitals', title: '低血氧', message: '需要处理' },
        { rule_id: 'r2', severity: 'medium', category: 'sleep', title: '睡眠不足', message: '关注即可' },
        { rule_id: 'r3', severity: 'info', category: 'daily', title: '记录提醒', message: '日常提示' },
      ],
      [
        { id: 1, title: '今晚提前晚餐', status: 'active', card_type: 'plan', priority: 1, content: '', created_at: '2026-04-26T00:00:00Z' },
        { id: 2, title: '复盘血氧实验', status: 'active', card_type: 'plan', priority: 1, content: '', created_at: '2026-04-20T00:00:00Z', expires_at: '2026-04-27T00:00:00Z' },
      ],
    );

    expect(sections.map(section => section.title)).toEqual([
      '需要立即处理',
      '正在执行',
      '等待验证',
      '日常提示',
    ]);
    expect(sections[0].data.map(item => item.item.title)).toEqual(['低血氧']);
    expect(sections[3].data.map(item => item.item.title)).toEqual(['睡眠不足', '记录提醒']);
  });

  it('creates a manual action card through the backend', async () => {
    const card = { id: 9, title: '睡眠实验', status: 'active' } as ActionCard;
    mockPost.mockResolvedValueOnce({ data: card });

    const result = await createActionCard({
      title: '睡眠实验',
      content: '今晚侧睡',
      card_type: 'plan',
      source_type: 'sleep_spo2',
      source_id: '2026-04-25',
      priority: 2,
    });

    expect(mockPost).toHaveBeenCalledWith('/action-cards', {
      title: '睡眠实验',
      content: '今晚侧睡',
      card_type: 'plan',
      source_type: 'sleep_spo2',
      source_id: '2026-04-25',
      priority: 2,
    });
    expect(result).toBe(card);
  });

  it('submits an action card outcome review as a completed assessment', async () => {
    const card = { id: 9, title: '睡眠实验', status: 'completed' } as ActionCard;
    mockPost.mockResolvedValueOnce({ data: card });

    const result = await reviewActionCard(9, {
      status: 'met',
      actualValue: '84',
      summary: '睡眠评分达到目标',
      evidence: ['Garmin sleep_score'],
    });

    expect(mockPost).toHaveBeenCalledWith('/action-cards/9/review', {
      status: 'completed',
      outcome_status: 'met',
      actual_value: '84',
      latest_assessment: {
        score: 8,
        summary: '睡眠评分达到目标',
        evidence: ['Garmin sleep_score'],
      },
    });
    expect(result).toBe(card);
  });

  it('records self-reported action card adherence through the backend', async () => {
    const card = { id: 9, title: '7 天体重保持', status: 'active' } as ActionCard;
    mockPost.mockResolvedValueOnce({ data: card });

    const result = await recordCardAdherence(9, 70);

    expect(mockPost).toHaveBeenCalledWith('/action-cards/9/adherence', {
      kind: 'self_reported',
      confidence: 70,
    });
    expect(result).toBe(card);
  });
});
