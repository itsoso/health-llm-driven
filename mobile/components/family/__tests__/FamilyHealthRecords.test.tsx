import React from 'react';
import { render, fireEvent, screen, act, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import FamilyHealthRecords from '../FamilyHealthRecords';
import { fetchFamilyMemberHealth } from '../../../services/family';
import { colors } from '../../../constants/theme';
jest.mock('../../../services/family', () => ({ ...jest.requireActual('../../../services/family'), fetchFamilyMemberHealth: jest.fn() }));
jest.mock('../../../services/api', () => ({ __esModule: true, default: {} }));
const records = {
  member: { user_id: 42, name: '测试成员', nickname: '小禾', relationship_type: 'daughter' },
  reports: [{ id: 9, user_id: 42, exam_date: '2026-09-20', notes: '原始报告备注', conclusions: [{ title: '检查结论', description: '建议复查' }], items: [{ id: 1, exam_id: 9, item_name: '指标甲', value: 12.34567, display_value: '12.35', unit: 'mg/L' }] }],
  episodes: [{ id: 2, name: '随访病程', start_date: '2026-09-19', status: 'active', notes: '初诊记录', updates: [{ id: 3, update_date: '2026-09-20', notes: '复诊记录', status: 'recovering' }] }], limit: 20,
};
function show() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><FamilyHealthRecords viewerId={7} userId={42} c={colors} /></QueryClientProvider>);
}
beforeEach(() => jest.clearAllMocks());
it('renders subject identity, server display precision and full illness updates read-only', async () => {
  (fetchFamilyMemberHealth as jest.Mock).mockResolvedValue(records);
  show();
  expect(await screen.findByText('测试成员（小禾）')).toBeTruthy();
  expect(screen.getByText('女儿 · 只读健康记录')).toBeTruthy();
  expect(screen.getByText('12.35 mg/L')).toBeTruthy();
  expect(screen.queryByText(/12.34567/)).toBeNull();
  expect(screen.getByText('原始报告备注')).toBeTruthy();
  expect(screen.getByText('复诊记录')).toBeTruthy();
  expect(screen.queryByText('编辑')).toBeNull();
});
it('shows access denial distinctly and allows retry', async () => {
  (fetchFamilyMemberHealth as jest.Mock).mockRejectedValueOnce({ response: { status: 403 } }).mockResolvedValueOnce({ ...records, reports: [], episodes: [] });
  show();
  expect(await screen.findByText('暂时无法查看，家庭关系或共享权限可能已变更。')).toBeTruthy();
  fireEvent.press(screen.getByText('重试'));
  expect(await screen.findByText('暂无检查报告')).toBeTruthy();
  expect(screen.getByText('暂无病程记录')).toBeTruthy();
});

it('hides previously loaded records after the server revokes access', async () => {
  (fetchFamilyMemberHealth as jest.Mock).mockResolvedValueOnce(records).mockRejectedValueOnce({ response: { status: 403 } });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><FamilyHealthRecords viewerId={7} userId={42} c={colors} /></QueryClientProvider>);
  expect(await screen.findByText('原始报告备注')).toBeTruthy();
  await act(async () => { await client.invalidateQueries({ queryKey: ['familyMemberHealth', 7, 42] }); });
  await waitFor(() => expect(screen.queryByText('原始报告备注')).toBeNull());
  expect(screen.getByText('暂时无法查看，家庭关系或共享权限可能已变更。')).toBeTruthy();
});
