import React from 'react';
import { render } from '@testing-library/react-native';
import { Polyline } from 'react-native-svg';
import { WeightCardView, WeightCardSpec } from '../WeightCard';
import { semanticColors } from '../../../../constants/theme';

// light mode
jest.mock('react-native/Libraries/Utilities/useColorScheme', () => ({
  __esModule: true,
  default: () => 'light',
}));
// expo-router useRouter (WeightCardView 调用)
jest.mock('expo-router', () => ({ useRouter: () => ({ push: jest.fn() }) }));

// Sparkline 的趋势色 = Polyline 的 stroke
function sparkColor(tree: ReturnType<typeof render>): string {
  return tree.UNSAFE_getByType(Polyline).props.stroke;
}

describe('WeightCardView sparkline semantic color', () => {
  it('downward trend → success solid (减重)', () => {
    expect(sparkColor(render(<WeightCardView trend_7d={[70, 69, 68]} />))).toBe(
      semanticColors.success.solid,
    );
  });

  it('upward trend → danger solid (增重)', () => {
    expect(sparkColor(render(<WeightCardView trend_7d={[68, 69, 70]} />))).toBe(
      semanticColors.danger.solid,
    );
  });

  it('flat trend → neutral solid', () => {
    expect(sparkColor(render(<WeightCardView trend_7d={[70, 70, 70]} />))).toBe(
      semanticColors.neutral.solid,
    );
  });
});

describe('WeightCardSpec.match', () => {
  const make = (q: string) => ({
    query: q,
    query_lower: q.toLowerCase(),
    toolsUsed: new Set<string>(),
    data: {},
    api: {},
  });

  it('matches weight/bmi queries', () => {
    expect(WeightCardSpec.match(make('我体重趋势'))).toBe(15);
    expect(WeightCardSpec.match(make('bmi 多少'))).toBe(15);
  });

  it('skips pure 记录/打卡 intent', () => {
    expect(WeightCardSpec.match(make('记录体重'))).toBeNull();
  });
});
