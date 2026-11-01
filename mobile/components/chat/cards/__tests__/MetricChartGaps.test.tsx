import { render } from '@testing-library/react-native';
import { Circle, Polyline } from 'react-native-svg';
import { RevaUiLineChartCardView } from '../MetricChartCard';

const chart = (points: (number | null)[]) => render(
  RevaUiLineChartCardView({
    title: '血氧饱和度', unit: '%', x: points.map((_, i) => `11-${i + 1}`),
    series: [{ name: '日均血氧', points }],
  }),
);

test('missing dates split the line instead of joining across unobserved days', () => {
  const view = chart([96, 97, null, 98, 99]);
  const lines = view.UNSAFE_getAllByType(Polyline);
  expect(lines).toHaveLength(2);
  expect(lines.map(line => line.props.points.split(' ').length)).toEqual([2, 2]);
});

test('isolated observations remain visible without an invented connecting line', () => {
  const view = chart([null, 96.12, null, null, 97]);
  expect(view.UNSAFE_queryAllByType(Polyline)).toHaveLength(0);
  expect(view.UNSAFE_getAllByType(Circle)).toHaveLength(2);
});

test('a single observation is displayed as a point, including its date axis', () => {
  const view = chart([97]);
  expect(view.UNSAFE_getAllByType(Circle)).toHaveLength(1);
  expect(view.getAllByText('11-1')).toHaveLength(2);
  expect(view.UNSAFE_queryAllByType(Polyline)).toHaveLength(0);
});
