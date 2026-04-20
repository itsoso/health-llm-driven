import { scoreColor, scoreGrade, colors, darkColors } from '../theme';

describe('scoreColor', () => {
  it('returns green for score >= 80', () => {
    expect(scoreColor(80)).toBe(colors.green);
    expect(scoreColor(95)).toBe(colors.green);
    expect(scoreColor(100)).toBe(colors.green);
  });

  it('returns amber for score 60-79', () => {
    expect(scoreColor(60)).toBe(colors.amber);
    expect(scoreColor(79)).toBe(colors.amber);
  });

  it('returns red for score < 60', () => {
    expect(scoreColor(0)).toBe(colors.red);
    expect(scoreColor(59)).toBe(colors.red);
  });
});

describe('scoreGrade', () => {
  it('returns correct grade labels', () => {
    expect(scoreGrade(95)).toBe('优秀');
    expect(scoreGrade(85)).toBe('良好');
    expect(scoreGrade(65)).toBe('一般');
    expect(scoreGrade(45)).toBe('较差');
    expect(scoreGrade(20)).toBe('需关注');
  });

  it('handles boundary values', () => {
    expect(scoreGrade(90)).toBe('优秀');
    expect(scoreGrade(80)).toBe('良好');
    expect(scoreGrade(60)).toBe('一般');
    expect(scoreGrade(40)).toBe('较差');
    expect(scoreGrade(39)).toBe('需关注');
  });
});

describe('theme tokens', () => {
  it('exports all required color keys', () => {
    expect(colors.brand).toBeDefined();
    expect(colors.bgPrimary).toBeDefined();
    expect(colors.bgCard).toBeDefined();
    expect(colors.labelPrimary).toBeDefined();
    expect(colors.green).toBeDefined();
    expect(colors.amber).toBeDefined();
    expect(colors.red).toBeDefined();
  });

  it('darkColors has all the same keys as colors', () => {
    const lightKeys = Object.keys(colors).sort();
    const darkKeys = Object.keys(darkColors).sort();
    expect(darkKeys).toEqual(lightKeys);
  });
});
