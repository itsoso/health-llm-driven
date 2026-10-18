import React from 'react';
import { render } from '@testing-library/react-native';
import PrivacyPolicyScreen from '../privacy-policy';

jest.mock('expo-router', () => ({
  useRouter: () => ({ back: jest.fn(), replace: jest.fn(), canGoBack: () => false }),
  Stack: { Screen: () => null },
}));
jest.mock('../../hooks/useTheme', () => ({
  useTheme: () => ({ c: { bgPrimary: '#fff', bgCard: '#fff', brand: '#086', brandLight: '#eee',
    labelPrimary: '#111', labelSecondary: '#333', labelTertiary: '#555', separator: '#ddd' } }),
}));

describe('daily GPS privacy disclosure', () => {
  it('explains separate opt-in, private processing, retention and deletion controls', () => {
    const view = render(<PrivacyPolicyScreen />);
    const content = JSON.stringify(view.toJSON());
    for (const phrase of ['每日 GPS 行程默认关闭', '每天主动开启', '锁屏或切到后台', '精确坐标、采样时间',
      '加密', '不发送给 AI', '不用于广告', '从开启时起', '1 或 7 天', '到期后不可读取', '定时物理清理',
      '不会自动删除历史行程', '原始点、修正和复盘', '随机请求标识', '不含 GPS', '随账号删除', '2026-10-18']) {
      expect(content).toContain(phrase);
    }
  });

  it('does not deny all background location or claim new App Store verification', () => {
    const view = render(<PrivacyPolicyScreen />);
    const content = JSON.stringify(view.toJSON());
    expect(content).not.toMatch(/不会持续或后台定位|不持续定位，也不在后台收集位置/);
    expect(content).not.toContain('并与 App Store 隐私标签和权限说明保持一致');
    expect(content).toContain('城市足迹');
  });
});
