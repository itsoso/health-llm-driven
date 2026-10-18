import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import PrivacyPage from './page';

describe('daily GPS privacy disclosure', () => {
  it('explains separate opt-in, private processing, retention and deletion controls', () => {
    const { container } = render(<PrivacyPage />);
    const content = container.textContent;
    for (const phrase of ['每日 GPS 行程默认关闭', '每天主动开启', '锁屏或切到后台', '精确坐标、采样时间',
      '加密', '不发送给 AI', '不用于广告', '从开启时起', '1 或 7 天', '到期后不可读取', '定时物理清理',
      '不会自动删除历史行程', '原始点、修正和复盘', '随机请求标识', '不含 GPS', '随账号删除', '2026-10-18']) {
      expect(content).toContain(phrase);
    }
  });

  it('distinguishes city annotations from opt-in background GPS', () => {
    const { container } = render(<PrivacyPage />);
    expect(container.textContent).not.toMatch(/不会持续或后台定位|不持续定位，也不在后台收集位置|不使用全天后台追踪/);
    expect(container.textContent).toContain('城市足迹');
  });
});
