import { formatHealthActionTitle } from '../actionCopy';

describe('actionCopy', () => {
  it('removes duplicated today/training prefixes from generated health action titles', () => {
    expect(formatHealthActionTitle('今日训练:今天恢复/休息,暂停高强度;优先睡眠与轻活动')).toBe(
      '恢复/休息:暂停高强度;优先睡眠与轻活动',
    );
  });

  it('preserves normal user-facing titles', () => {
    expect(formatHealthActionTitle('午饭后步行 10 分钟')).toBe('午饭后步行 10 分钟');
  });

  it('is idempotent after a generated title has already been cleaned', () => {
    expect(formatHealthActionTitle('恢复/休息:暂停高强度;优先睡眠与轻活动')).toBe(
      '恢复/休息:暂停高强度;优先睡眠与轻活动',
    );
  });
});
