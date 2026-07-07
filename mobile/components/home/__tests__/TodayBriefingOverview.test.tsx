import React from 'react';
import { render } from '@testing-library/react-native';

import TodayBriefingOverview from '../TodayBriefingOverview';
import type { TodayBriefingRow } from '../../../services/todayBriefingOverview';

jest.mock('@expo/vector-icons', () => ({ Ionicons: 'Ionicons' }));

describe('TodayBriefingOverview', () => {
  const rows: TodayBriefingRow[] = [
    { id: 'weather', label: '天气', value: '27° · 多云', detail: '适合轻活动', icon: 'partly-sunny-outline' },
    { id: 'air', label: '空气质量', value: 'AQI 52 · 良', detail: 'PM2.5 20', icon: 'leaf-outline' },
    { id: 'plan', label: '今日规划', value: '把晚餐后血糖波动压低', detail: '晚饭后步行', icon: 'calendar-outline' },
    { id: 'advice', label: '建议', value: '晚饭后步行 10 分钟', detail: '晚饭后 30 分钟内完成', icon: 'sparkles-outline' },
    { id: 'yesterday', label: '昨日总结', value: '睡眠分数: 82分', detail: '身体电量峰值: 81', icon: 'moon-outline' },
  ];

  it('renders the fixed Today briefing sections', () => {
    const { getByTestId, getByText } = render(<TodayBriefingOverview rows={rows} />);

    expect(getByTestId('today-briefing-overview')).toBeTruthy();
    for (const row of rows) {
      expect(getByTestId(`today-briefing-row-${row.id}`)).toBeTruthy();
      expect(getByText(row.label)).toBeTruthy();
      expect(getByText(row.value)).toBeTruthy();
    }
  });
});
