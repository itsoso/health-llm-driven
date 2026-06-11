jest.mock('../api', () => ({ __esModule: true, default: { get: jest.fn() } }));

import { verdictLabel, verdictColor } from '../chronicHealth';
import { semanticColors, darkSemanticColors } from '../../constants/theme';

describe('verdictLabel', () => {
  it('verdict → 人话标签', () => {
    expect(verdictLabel('improving')).toBe('好转');
    expect(verdictLabel('worsening')).toBe('恶化');
    expect(verdictLabel('stable')).toBe('平稳');
  });
});

describe('verdictColor', () => {
  it('默认用亮色语义调色板:好转绿 / 恶化红 / 平稳灰', () => {
    expect(verdictColor('improving')).toBe(semanticColors.success.solid);
    expect(verdictColor('worsening')).toBe(semanticColors.danger.solid);
    expect(verdictColor('stable')).toBe(semanticColors.neutral.solid);
  });
  it('传入暗色调色板时跟随', () => {
    expect(verdictColor('improving', darkSemanticColors)).toBe(darkSemanticColors.success.solid);
    expect(verdictColor('worsening', darkSemanticColors)).toBe(darkSemanticColors.danger.solid);
    expect(verdictColor('stable', darkSemanticColors)).toBe(darkSemanticColors.neutral.solid);
  });
});
