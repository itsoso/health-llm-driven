import React from 'react';
import { render } from '@testing-library/react-native';
import { Text } from 'react-native';
import {
  pickText,
  pickNum,
  fmtNum,
  formatBeijingDate,
  parseObservations,
  StatusSummaryShell,
  StatusObservationList,
  StatusProgressBar,
} from '../statusSummary';

describe('statusSummary parse primitives', () => {
  it('pickText trims, rejects empty/non-string(non-finite)', () => {
    expect(pickText('  hi ')).toBe('hi');
    expect(pickText('   ')).toBeUndefined();
    expect(pickText(42)).toBe('42');
    expect(pickText(NaN)).toBeUndefined();
    expect(pickText(null)).toBeUndefined();
  });

  it('pickNum accepts finite number/numeric string, rejects junk/NaN/Inf', () => {
    expect(pickNum(3.5)).toBe(3.5);
    expect(pickNum('  12 ')).toBe(12);
    expect(pickNum('abc')).toBeUndefined();
    expect(pickNum(Infinity)).toBeUndefined();
    expect(pickNum(null)).toBeUndefined();
  });

  it('fmtNum: integer verbatim, else ≤1 decimal, missing → null', () => {
    expect(fmtNum(400)).toBe('400');
    expect(fmtNum(6.166)).toBe('6.2');
    expect(fmtNum(71.4)).toBe('71.4');
    expect(fmtNum(undefined)).toBeNull();
    expect(fmtNum('x')).toBeNull();
  });

  it('formatBeijingDate: ISO → M月D日, non-ISO passthrough, empty → undefined', () => {
    expect(formatBeijingDate('2026-07-16')).toBe('7月16日');
    expect(formatBeijingDate('2026-07-16T08:00:00Z')).toBe('7月16日');
    expect(formatBeijingDate('今天')).toBe('今天');
    expect(formatBeijingDate('')).toBeUndefined();
    expect(formatBeijingDate(null)).toBeUndefined();
  });

  it('parseObservations: needs label, maps severity, unknown → normal, drops junk', () => {
    const out = parseObservations([
      { severity: 'caution', label: '脂肪偏高', detail: '约 45%' },
      { severity: 'weird', label: '仅标题' },
      { severity: 'risk' }, // no label → dropped
      'garbage',
    ]);
    expect(out).toEqual([
      { status: 'caution', label: '脂肪偏高', detail: '约 45%' },
      { status: 'normal', label: '仅标题', detail: undefined },
    ]);
    expect(parseObservations(null)).toEqual([]);
  });
});

describe('statusSummary components', () => {
  it('StatusSummaryShell renders title, subtitle, children', () => {
    const { getByText } = render(
      <StatusSummaryShell icon="clipboard-outline" title="今日饮食汇总" subtitle="北京时间 · 7月16日">
        <Text>主体内容</Text>
      </StatusSummaryShell>,
    );
    expect(getByText('今日饮食汇总')).toBeTruthy();
    expect(getByText('北京时间 · 7月16日')).toBeTruthy();
    expect(getByText('主体内容')).toBeTruthy();
  });

  it('StatusObservationList renders each observation; empty → renders nothing', () => {
    const { getByText, queryByText } = render(
      <StatusObservationList
        items={[
          { status: 'caution', label: '脂肪偏高', detail: '约 45%' },
          { status: 'normal', label: '蛋白质充足' },
        ]}
      />,
    );
    expect(getByText('脂肪偏高')).toBeTruthy();
    expect(getByText('蛋白质充足')).toBeTruthy();

    const empty = render(<StatusObservationList items={[]} />);
    expect(empty.queryByText('关键观察')).toBeNull();
    expect(queryByText).toBeTruthy();
  });

  it('StatusProgressBar renders label, value, hint', () => {
    const { getByText } = render(
      <StatusProgressBar label="饮水进度" valueText="500/2000ml" pct={25} hint="还差约 1500ml" />,
    );
    expect(getByText('饮水进度')).toBeTruthy();
    expect(getByText('500/2000ml')).toBeTruthy();
    expect(getByText('还差约 1500ml')).toBeTruthy();
  });

  it('StatusProgressBar clamps out-of-range pct without crashing', () => {
    expect(() =>
      render(<StatusProgressBar label="x" valueText="y" pct={9999} />),
    ).not.toThrow();
    expect(() =>
      render(<StatusProgressBar label="x" valueText="y" pct={-50} />),
    ).not.toThrow();
  });
});
