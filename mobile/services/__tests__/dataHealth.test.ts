jest.mock('../api', () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

import api from '../api';
import { buildDataPrompts, fetchDataHealthStatus, getSleepQuestionPrompt } from '../dataHealth';

const mockGet = api.get as jest.Mock;

describe('dataHealth service', () => {
  beforeEach(() => jest.clearAllMocks());

  it('fetches data health status from the backend', async () => {
    mockGet.mockResolvedValueOnce({ data: { garmin: { status: 'ok' } } });

    const status = await fetchDataHealthStatus();

    expect(mockGet).toHaveBeenCalledWith('/data-health/status');
    expect(status.garmin?.status).toBe('ok');
  });

  it('creates a blocking Garmin prompt when sync is unhealthy', () => {
    const prompts = buildDataPrompts({
      garmin: { status: 'error', message: '未绑定 Garmin 账号' },
    });

    expect(prompts[0]).toEqual({
      key: 'garmin',
      severity: 'blocking',
      title: '连接 Garmin',
      body: '未绑定 Garmin 账号',
      route: '/settings',
    });
  });

  it('creates useful daily record prompts for diet and water gaps', () => {
    const prompts = buildDataPrompts({
      garmin: { status: 'ok', message: '正常' },
      diet: { status: 'warning', message: '今天尚未记录饮食' },
      water: { status: 'warning', message: '今日饮水0ml/2000ml' },
    });

    expect(prompts.map(p => p.key)).toEqual(['diet', 'water']);
    expect(prompts[0].route).toBe('/diet');
    expect(prompts[1].route).toBe('/(tabs)/record');
  });

  it('creates an optional genetic data prompt without forcing a route', () => {
    const prompts = buildDataPrompts({
      genetic: { status: 'warning', message: '尚未录入基因数据' },
    });

    expect(prompts).toEqual([{
      key: 'genetic',
      severity: 'optional',
      title: '补充基因数据',
      body: '尚未录入基因数据',
    }]);
  });

  it('maps sleep analysis questions to context-aware destinations', () => {
    expect(getSleepQuestionPrompt('昨晚是否使用异丙托溴铵？')).toEqual({
      label: '去用药记录',
      route: '/(tabs)/record',
    });
    expect(getSleepQuestionPrompt('昨晚几点吃晚餐，是否饮酒？')).toEqual({
      label: '去饮食记录',
      route: '/diet',
    });
    expect(getSleepQuestionPrompt('昨晚睡眠中是否鼻塞或醒来？')).toEqual({
      label: '去睡眠记录',
      route: '/sleep',
    });
    expect(getSleepQuestionPrompt('昨晚是否做了高强度运动？')).toEqual({
      label: '去运动记录',
      route: '/workout-list',
    });
  });
});
