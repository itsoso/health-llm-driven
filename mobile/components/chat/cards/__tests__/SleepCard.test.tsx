import React from 'react';
import { render } from '@testing-library/react-native';
import { Circle } from 'react-native-svg';
import { SleepCardView, SleepCardSpec } from '../SleepCard';
import { semanticColors } from '../../../../constants/theme';

// light mode
jest.mock('react-native/Libraries/Utilities/useColorScheme', () => ({
  __esModule: true,
  default: () => 'light',
}));

// 取 ScoreRing 的进度弧颜色 = 第二个 Circle 的 stroke
function ringColor(tree: ReturnType<typeof render>): string {
  const circles = tree.UNSAFE_getAllByType(Circle);
  return circles[circles.length - 1].props.stroke;
}

describe('SleepCardView ScoreRing semantic color', () => {
  it('score >= 80 → success solid', () => {
    expect(ringColor(render(<SleepCardView score={85} duration_h={7.5} />))).toBe(
      semanticColors.success.solid,
    );
  });

  it('score 60-79 → warning solid', () => {
    expect(ringColor(render(<SleepCardView score={70} duration_h={6} />))).toBe(
      semanticColors.warning.solid,
    );
  });

  it('score < 60 → danger solid', () => {
    expect(ringColor(render(<SleepCardView score={40} duration_h={5} />))).toBe(
      semanticColors.danger.solid,
    );
  });
});

describe('SleepCardSpec.match', () => {
  const make = (q: string) => ({
    query: q,
    query_lower: q.toLowerCase(),
    toolsUsed: new Set<string>(),
    data: {},
    api: {},
  });

  it('matches sleep queries, skips 记录/打卡', () => {
    expect(SleepCardSpec.match(make('我昨晚睡眠怎么样'))).toBe(20);
    expect(SleepCardSpec.match(make('记录睡眠'))).toBeNull();
  });
});
