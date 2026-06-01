import { OUTCOME_COLORS } from '../my-progress';
import { semanticColors } from '../../constants/theme';

// my-progress 的 outcome → semantic tone 映射契约 (batch 3 迁移后).
// 防回归: "改善" 必须 success、"反向" 必须 danger —— 用错色会误导用户对结果的判断.
describe('OUTCOME_COLORS tone mapping', () => {
  it('improved → success', () => {
    expect(OUTCOME_COLORS.improved.tone).toBe('success');
    expect(OUTCOME_COLORS.improved.arrow).toBe('↑');
  });

  it('worsened → danger', () => {
    expect(OUTCOME_COLORS.worsened.tone).toBe('danger');
    expect(OUTCOME_COLORS.worsened.arrow).toBe('↓');
  });

  it('unchanged / inconclusive → neutral', () => {
    expect(OUTCOME_COLORS.unchanged.tone).toBe('neutral');
    expect(OUTCOME_COLORS.inconclusive.tone).toBe('neutral');
  });

  it('every tone resolves to a real semanticColors entry', () => {
    for (const key of Object.keys(OUTCOME_COLORS)) {
      const tone = OUTCOME_COLORS[key].tone;
      expect(semanticColors[tone]).toBeDefined();
      expect(semanticColors[tone].bg).toMatch(/^#[0-9A-Fa-f]{6}$/);
    }
  });
});
