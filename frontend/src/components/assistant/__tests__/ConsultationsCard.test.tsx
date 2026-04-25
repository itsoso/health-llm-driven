/**
 * ConsultationsCard 回归测试
 *
 * 锁住 2026-04-19 修过的 bug:
 *   "TypeError: e.reduce is not a function"
 *
 * 根因: 后端 /me/active 返回单个对象, 前端误当数组调用 .reduce.
 * 修复: 改用 listMine() + status==='active' 过滤 + Array.isArray 兜底.
 *
 * 这个测试断言任何回归（包括 API 改回旧契约）都立刻失败.
 */
// @vitest-environment jsdom

import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

// 必须在 import 组件前 mock
const listMineSpy = vi.fn();
vi.mock('@/services/api/records', () => ({
  healthConsultationApi: {
    listMine: (...args: unknown[]) => listMineSpy(...args),
    // getActive 故意保留, 验证我们没再调它
    getActive: vi.fn(() => Promise.reject(new Error('should not be called'))),
  },
}));

// next/link mock
vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) =>
    React.createElement('a', { href }, children),
}));

import ConsultationsCard from '../ConsultationsCard';

beforeEach(() => {
  listMineSpy.mockReset();
});

describe('ConsultationsCard 回归', () => {
  it('listMine 返回数组 → 正常渲染, .reduce 不崩溃', async () => {
    listMineSpy.mockResolvedValue({
      data: [
        {
          id: 1, version: 1, title: '替尔泊肽用药安全', topic: 't',
          consultation_type: 'urgent', triggered_by: 'manual', status: 'active',
          summary: 's', created_at: '2026-04-01',
          total_items: 15, hypothesis_count: 4, action_count: 6,
          prediction_count: 3, red_flag_count: 2, pending_count: 5,
        },
      ],
    });

    render(<ConsultationsCard />);

    await waitFor(() => {
      expect(screen.getByText(/健康咨询/)).toBeInTheDocument();
    });

    expect(listMineSpy).toHaveBeenCalled();
    expect(screen.getByText('替尔泊肽用药安全')).toBeInTheDocument();
  });

  it('listMine 返回非数组对象 → 不崩溃, 渲染为空', async () => {
    // 模拟后端契约破坏 (返回 {data: 单个对象} 而非数组)
    listMineSpy.mockResolvedValue({
      data: { id: 1, title: 'oops' },
    });

    render(<ConsultationsCard />);

    // Array.isArray 兜底应该让组件返回 null (no crash)
    await waitFor(() => {
      expect(listMineSpy).toHaveBeenCalled();
    });
    // 不抛异常 + 不出现"健康咨询"标题 (因为 list 长度 0 → null)
    expect(screen.queryByText('健康咨询')).toBeNull();
  });

  it('listMine 返回空数组 → 不渲染', async () => {
    listMineSpy.mockResolvedValue({ data: [] });

    render(<ConsultationsCard />);

    await waitFor(() => expect(listMineSpy).toHaveBeenCalled());
    expect(screen.queryByText('健康咨询')).toBeNull();
  });

  it('listMine 抛错 → 不崩溃, 渲染为空', async () => {
    listMineSpy.mockRejectedValue(new Error('network'));

    render(<ConsultationsCard />);

    await waitFor(() => expect(listMineSpy).toHaveBeenCalled());
    expect(screen.queryByText('健康咨询')).toBeNull();
  });

  it('过滤掉 status !== "active" 的咨询', async () => {
    listMineSpy.mockResolvedValue({
      data: [
        { id: 1, version: 1, title: '当前版本', status: 'active',
          consultation_type: 'urgent', triggered_by: 'manual',
          created_at: '2026-04-01', total_items: 1,
          hypothesis_count: 0, action_count: 0, prediction_count: 0,
          red_flag_count: 0, pending_count: 0 },
        { id: 2, version: 2, title: '旧版本被替代', status: 'superseded',
          consultation_type: 'urgent', triggered_by: 'manual',
          created_at: '2026-03-01', total_items: 1,
          hypothesis_count: 0, action_count: 0, prediction_count: 0,
          red_flag_count: 0, pending_count: 0 },
      ],
    });

    render(<ConsultationsCard />);

    await waitFor(() => expect(listMineSpy).toHaveBeenCalled());
    expect(screen.queryByText('当前版本')).toBeInTheDocument();
    expect(screen.queryByText('旧版本被替代')).toBeNull();
  });

  it('累计 red_flag 和 pending 计数显示在标题栏', async () => {
    listMineSpy.mockResolvedValue({
      data: [
        { id: 1, version: 1, title: 'A', status: 'active',
          consultation_type: 'urgent', triggered_by: 'manual',
          created_at: '2026-04-01', total_items: 5,
          hypothesis_count: 0, action_count: 0, prediction_count: 0,
          red_flag_count: 2, pending_count: 3 },
        { id: 2, version: 1, title: 'B', status: 'active',
          consultation_type: 'symptom_advisory', triggered_by: 'manual',
          created_at: '2026-04-02', total_items: 5,
          hypothesis_count: 0, action_count: 0, prediction_count: 0,
          red_flag_count: 1, pending_count: 4 },
      ],
    });

    render(<ConsultationsCard />);

    await waitFor(() => expect(listMineSpy).toHaveBeenCalled());
    // 红线累计 = 2 + 1 = 3
    expect(screen.getByText(/3 警戒/)).toBeInTheDocument();
    // 待办 = 3 + 4 = 7
    expect(screen.getByText(/7 待办/)).toBeInTheDocument();
  });
});
