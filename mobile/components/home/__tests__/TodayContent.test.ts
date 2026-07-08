import {
  shouldRenderMedicationSummary,
  type TodayContentMode,
} from '../TodayContent';

describe('TodayContent helpers', () => {
  it.each([
    ['screen', true],
    ['sheet', false],
    ['inline', false],
  ] as Array<[TodayContentMode, boolean]>)(
    'renders medication summary only in %s mode when it would not duplicate the agent page timeline',
    (mode, expected) => {
      expect(shouldRenderMedicationSummary(mode)).toBe(expected);
    },
  );
});
