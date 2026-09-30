import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
const getMemberHealth = vi.hoisted(() => vi.fn());
vi.mock('@/services/api/family', () => ({ familyApi: { getMemberHealth } }));
import FamilyMemberRecords from './FamilyMemberRecords';
const records = { member: { user_id: 42, name: '测试成员', nickname: '小禾', relationship_type: 'daughter' }, reports: [{ id: 1, exam_date: '2026-09-20', notes: '报告备注', items: [{ id: 2, item_name: '指标甲', value: 12.3456, display_value: '12.35', unit: 'mg/L' }] }], episodes: [{ id: 3, name: '病程记录', start_date: '2026-09-19', status: 'active', notes: '初诊', updates: [{ id: 4, update_date: '2026-09-20', notes: '复诊情况' }] }], limit: 20 };
beforeEach(() => vi.clearAllMocks());
it('shows member identity, server precision and updates without an edit action', async () => {
  getMemberHealth.mockResolvedValue({ data: records });
  render(<FamilyMemberRecords userId={42} onClose={vi.fn()} />);
  expect(await screen.findByText('测试成员（小禾）')).toBeInTheDocument();
  expect(screen.getByText('12.35 mg/L')).toBeInTheDocument();
  expect(screen.getByText('复诊情况')).toBeInTheDocument();
  expect(screen.queryByText(/12.3456/)).not.toBeInTheDocument();
  expect(screen.queryByText('编辑')).not.toBeInTheDocument();
});
it('clears records after permission revocation and supports retry', async () => {
  getMemberHealth.mockResolvedValueOnce({ data: records }).mockRejectedValueOnce({ response: { status: 403 } });
  render(<FamilyMemberRecords userId={42} onClose={vi.fn()} />);
  expect(await screen.findByText('报告备注')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '刷新记录' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('家庭关系或共享权限可能已变更');
  expect(screen.queryByText('报告备注')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument();
});
