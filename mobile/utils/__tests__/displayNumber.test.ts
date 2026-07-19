import { formatDisplayNumber } from '../displayNumber';

it('shows at most two decimals without trailing zeroes', () => {
  expect(formatDisplayNumber(58)).toBe('58');
  expect(formatDisplayNumber(71.4)).toBe('71.4');
  expect(formatDisplayNumber(6.166666)).toBe('6.17');
});
