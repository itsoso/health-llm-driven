import React from 'react';
import { render, waitFor, fireEvent } from '@testing-library/react-native';

jest.mock('@expo/vector-icons', () => ({ Ionicons: 'Ionicons' }));

const mockFetchTaskLedger = jest.fn();
jest.mock('../../../services/taskLedger', () => ({
  fetchTaskLedger: (...args: any[]) => mockFetchTaskLedger(...args),
}));

import TaskLedgerPanel, { formatLedgerWhen, groupLedgerItems } from '../TaskLedgerPanel';

const LEDGER_FIXTURE = {
  items: [
    { kind: 'medical_report_import', title: '体检报告.pdf', status: 'running', when: '2026-07-11T09:00:00+08:00', source: 'desktop_job' },
    { kind: 'checkup_reminder', title: '建立复查提醒', status: 'pending', when: '2026-07-11T08:00:00+08:00', source: 'write_intent' },
    { kind: 'checkup', title: '复查:胃镜复查', status: 'scheduled', when: '2026-07-12', source: 'agenda' },
    { kind: 'measurement_prompt', title: '补测血压', status: 'executed', when: '2026-07-10T20:00:00+08:00', source: 'write_intent' },
  ],
  failed_sources: [],
};

describe('TaskLedgerPanel', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchTaskLedger.mockReset();
  });

  it('renders items grouped by 进行中 / 待确认 / 即将到来 (+ 最近动态 for terminal states)', async () => {
    mockFetchTaskLedger.mockResolvedValue(LEDGER_FIXTURE);
    const { getByText } = render(<TaskLedgerPanel />);

    await waitFor(() => expect(getByText('进行中 · 1')).toBeTruthy());
    expect(getByText('体检报告.pdf')).toBeTruthy();
    expect(getByText('待确认 · 1')).toBeTruthy();
    expect(getByText('建立复查提醒')).toBeTruthy();
    expect(getByText('即将到来 · 1')).toBeTruthy();
    expect(getByText('复查:胃镜复查')).toBeTruthy();
    expect(getByText('最近动态 · 1')).toBeTruthy();
    expect(getByText('补测血压')).toBeTruthy();
  });

  it('shows the honest empty state 「暂无进行中任务」 when the ledger is empty', async () => {
    mockFetchTaskLedger.mockResolvedValue({ items: [], failed_sources: [] });
    const { getByText, queryByText } = render(<TaskLedgerPanel />);

    await waitFor(() => expect(getByText('暂无进行中任务')).toBeTruthy());
    expect(queryByText(/进行中 ·/)).toBeNull();
  });

  it('surfaces failed_sources instead of pretending all sources loaded (fail-loud)', async () => {
    mockFetchTaskLedger.mockResolvedValue({
      items: LEDGER_FIXTURE.items.slice(0, 1),
      failed_sources: [{ source: 'agenda', error: 'boom' }],
    });
    const { getByText } = render(<TaskLedgerPanel />);

    await waitFor(() => expect(getByText(/部分来源加载失败/)).toBeTruthy());
    expect(getByText(/议程/)).toBeTruthy();
  });

  it('shows an explicit error state with retry when the fetch itself fails', async () => {
    mockFetchTaskLedger.mockRejectedValueOnce(new Error('network down'));
    mockFetchTaskLedger.mockResolvedValueOnce({ items: [], failed_sources: [] });
    const { getByText, getByLabelText } = render(<TaskLedgerPanel />);

    await waitFor(() => expect(getByText('任务账本加载失败')).toBeTruthy());
    fireEvent.press(getByLabelText('重试加载任务账本'));
    await waitFor(() => expect(getByText('暂无进行中任务')).toBeTruthy());
    expect(mockFetchTaskLedger).toHaveBeenCalledTimes(2);
  });

  it('calls onClose when the collapse button is pressed', async () => {
    mockFetchTaskLedger.mockResolvedValue({ items: [], failed_sources: [] });
    const onClose = jest.fn();
    const { getByLabelText } = render(<TaskLedgerPanel onClose={onClose} />);

    await waitFor(() => expect(getByLabelText('收起任务面板')).toBeTruthy());
    fireEvent.press(getByLabelText('收起任务面板'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('groupLedgerItems maps statuses deterministically', () => {
    const groups = groupLedgerItems(LEDGER_FIXTURE.items as any);
    expect(groups.inProgress.map(i => i.title)).toEqual(['体检报告.pdf']);
    expect(groups.pendingConfirm.map(i => i.title)).toEqual(['建立复查提醒']);
    expect(groups.upcoming.map(i => i.title)).toEqual(['复查:胃镜复查']);
    expect(groups.recentlyDecided.map(i => i.title)).toEqual(['补测血压']);
  });

  it('formatLedgerWhen handles date-only, datetime, and null', () => {
    expect(formatLedgerWhen('2026-07-12')).toBe('07/12');
    expect(formatLedgerWhen('2026-07-11T09:05:00+08:00')).toBe('07/11 09:05');
    expect(formatLedgerWhen(null)).toBe('');
  });
});
