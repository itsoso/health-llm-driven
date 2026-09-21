import { parseDietPortion, splitDietPortion } from '../dietPortion';

describe('personal share of a whole meal', () => {
  it.each([['1/5', 0.2], ['20%', 0.2], ['0.2', 0.2], ['100%', 1], [' 1 / 3 ', 1 / 3]])(
    'parses explicit share %s', (input, expected) => expect(parseDietPortion(input)).toBe(expected),
  );
  it.each(['', '0', '-1', '1/0', '120%', '5', 'Infinity', 'NaN', '1/5abc', '1e-2'])('rejects %s', input => {
    expect(parseDietPortion(input)).toBeNull();
  });
  it('separates only the canonical whole-meal suffix, without changing individual food amounts', () => {
    expect(splitDietPortion('牛肉1/2碗 + 青菜（按实际食用1/5计）')).toEqual({
      food: '牛肉1/2碗 + 青菜', fraction: 0.2, text: '1/5',
    });
    expect(splitDietPortion('牛肉1/2碗')).toEqual({ food: '牛肉1/2碗', fraction: 1, text: '1' });
    expect(splitDietPortion('青菜（按实际食用0计）').food).toBe('青菜（按实际食用0计）');
  });
});
