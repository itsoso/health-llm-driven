jest.mock('../api', () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

jest.mock('../safety', () => ({
  getSafetyReport: jest.fn(),
}));

jest.mock('../actionCards', () => ({
  getActiveCards: jest.fn(),
}));

import api from '../api';
import { getActiveCards } from '../actionCards';
import { getSafetyReport } from '../safety';
import { getTodayCoachFocus } from '../todayCoach';

const mockGet = api.get as jest.Mock;
const mockSafety = getSafetyReport as jest.Mock;
const mockCards = getActiveCards as jest.Mock;

describe('getTodayCoachFocus', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGet.mockImplementation((url: string) => {
      if (url.startsWith('/health-score/enhanced/me')) {
        return Promise.resolve({ data: { total_score: 82, suggestions: ['保持今天的恢复节奏'] } });
      }
      if (url === '/data-health/status') {
        return Promise.resolve({ data: { garmin: { status: 'ok', message: '正常同步中' } } });
      }
      return Promise.resolve({ data: {} });
    });
    mockSafety.mockResolvedValue({ alerts: [] });
    mockCards.mockResolvedValue([]);
  });

  it('prioritizes high safety alerts over cards and score suggestions', async () => {
    mockSafety.mockResolvedValueOnce({
      alerts: [{
        title: '夜间血氧偏低',
        message: '最低血氧低于阈值',
        action: '查看夜间血氧分析',
        severity: 'high',
      }],
    });
    mockCards.mockResolvedValueOnce([{ id: 1, title: '今晚提前晚餐', card_type: 'plan' }]);

    const focus = await getTodayCoachFocus('2026-04-26');

    expect(focus.status).toBe('risk');
    // P3: title 升级为指令性 verdict
    expect(focus.title).toBe('今天注意：夜间血氧偏低');
    expect(focus.actionLabel).toBe('查看夜间血氧分析');
    expect(focus.evidence[0]).toEqual({ label: '安全告警', value: '高优先', tone: 'bad' });
  });

  it('uses the first active action card when there is no high safety alert', async () => {
    mockCards.mockResolvedValueOnce([{ id: 7, title: '连续 7 天记录晚餐时间', card_type: 'plan' }]);

    const focus = await getTodayCoachFocus('2026-04-26');

    expect(focus.status).toBe('attention');
    // P3: 指令性
    expect(focus.title).toBe('继续执行：连续 7 天记录晚餐时间');
    expect(focus.actionRoute).toBe('/(tabs)/alerts');
  });

  it('surfaces Garmin data gaps before generic score advice', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.startsWith('/health-score/enhanced/me')) {
        return Promise.resolve({ data: { total_score: 90, suggestions: ['状态不错'] } });
      }
      if (url === '/data-health/status') {
        return Promise.resolve({
          data: { garmin: { status: 'warning', message: '超过24小时未同步' } },
        });
      }
      return Promise.resolve({ data: {} });
    });

    const focus = await getTodayCoachFocus('2026-04-26');

    expect(focus.status).toBe('missing_data');
    expect(focus.title).toBe('先补齐 Garmin 数据');
    expect(focus.reason).toBe('超过24小时未同步');
  });

  it('falls back to the enhanced health score suggestion', async () => {
    const focus = await getTodayCoachFocus('2026-04-26');

    expect(focus.status).toBe('ok');
    // P3: score=82 (≥80) → 鼓励加量的指令式 title
    expect(focus.title).toBe('今天恢复良好，可以加点强度');
    expect(focus.reason).toBe('保持今天的恢复节奏');
    expect(focus.evidence).toEqual([{ label: '健康评分', value: '82' }]);
  });

  // ─────────────── P3: ok 状态按 score 分档 ───────────────

  it('ok status with mid score (60-79) shows "保持节奏"', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.startsWith('/health-score/enhanced/me')) {
        return Promise.resolve({ data: { total_score: 70, suggestions: ['继续保持'] } });
      }
      if (url === '/data-health/status') {
        return Promise.resolve({ data: { garmin: { status: 'ok', message: 'ok' } } });
      }
      return Promise.resolve({ data: {} });
    });

    const focus = await getTodayCoachFocus('2026-04-26');
    expect(focus.status).toBe('ok');
    expect(focus.title).toBe('今天保持节奏，无需特别动作');
  });

  it('ok status with low score (<60) shows "今天偏低"', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.startsWith('/health-score/enhanced/me')) {
        return Promise.resolve({ data: { total_score: 45, suggestions: ['注意休息'] } });
      }
      if (url === '/data-health/status') {
        return Promise.resolve({ data: { garmin: { status: 'ok', message: 'ok' } } });
      }
      return Promise.resolve({ data: {} });
    });

    const focus = await getTodayCoachFocus('2026-04-26');
    expect(focus.status).toBe('ok');
    expect(focus.title).toBe('今天偏低，注意休息和补水');
  });

  it('ok status without score falls back to default verdict', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.startsWith('/health-score/enhanced/me')) {
        return Promise.resolve({ data: {} });
      }
      if (url === '/data-health/status') {
        return Promise.resolve({ data: { garmin: { status: 'ok', message: 'ok' } } });
      }
      return Promise.resolve({ data: {} });
    });

    const focus = await getTodayCoachFocus('2026-04-26');
    expect(focus.status).toBe('ok');
    expect(focus.title).toBe('今天可以正常推进');
  });
});
