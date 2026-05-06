/**
 * SpecialistChipRow.buildHero — 纯函数单测
 * (UI rendering 测试嫌重, 这里覆盖 3 个 state 分支 + 导航目标推断)
 */
import { buildHero } from '../specialistChipHero';
import { colors } from '../../../constants/theme';

const c = colors as any; // 测试用真 light palette

describe('buildHero', () => {
  it('graded state: 有评分 → 命中率文案, 跳 best specialist', () => {
    const r = buildHero(c, 12, 8, 0, 'recovery_coach', 'recovery_coach');
    expect(r.state).toBe('graded');
    expect(r.primary).toBe('AI 近 30 天准了 8/12');
    expect(r.navTarget).toBe('/specialist/recovery_coach');
    expect(r.iconName).toBe('trending-up');
  });

  it('graded but no best (low samples) → fallback 首个 significant', () => {
    const r = buildHero(c, 5, 3, 0, null, 'fuel_strategist');
    expect(r.state).toBe('graded');
    expect(r.navTarget).toBe('/specialist/fuel_strategist');
  });

  it('graded but no significant at all → fallback /alerts', () => {
    const r = buildHero(c, 1, 1, 0, null, null);
    expect(r.state).toBe('graded');
    expect(r.navTarget).toBe('/(tabs)/alerts');
  });

  it('pending state: 仅 pending → AI 正在观察 N 条, 跳 /alerts', () => {
    const r = buildHero(c, 0, 0, 4, null, null);
    expect(r.state).toBe('pending');
    expect(r.primary).toBe('AI 正在观察 4 条判断');
    expect(r.navTarget).toBe('/(tabs)/alerts');
    expect(r.iconName).toBe('hourglass-outline');
  });

  it('pending state: 即使有 best, 也走 /alerts (push 用户去看 pending 列表)', () => {
    const r = buildHero(c, 0, 0, 4, 'recovery_coach', null);
    expect(r.state).toBe('pending');
    expect(r.navTarget).toBe('/(tabs)/alerts');
  });

  it('empty state: 全空 → 仍在学习节奏 + 跳 /alerts (引导用户)', () => {
    const r = buildHero(c, 0, 0, 0, null, null);
    expect(r.state).toBe('empty');
    expect(r.primary).toBe('AI 还在学你的节奏');
    expect(r.navTarget).toBe('/(tabs)/alerts');
    expect(r.iconName).toBe('sparkles-outline');
  });

  it('a11y label 含核心数字, 不爆露 0/0', () => {
    const graded = buildHero(c, 12, 8, 0, 'recovery_coach', null);
    expect(graded.a11yLabel).toContain('12');
    expect(graded.a11yLabel).toContain('8');

    const pending = buildHero(c, 0, 0, 4, null, null);
    expect(pending.a11yLabel).toContain('4');

    const empty = buildHero(c, 0, 0, 0, null, null);
    expect(empty.a11yLabel).toContain('尚未');
  });

  it('secondary 文案随 state 变', () => {
    expect(buildHero(c, 12, 8, 0, 'r', null).secondary).toContain('擅长');
    expect(buildHero(c, 0, 0, 4, null, null).secondary).toContain('自动');
    expect(buildHero(c, 0, 0, 0, null, null).secondary).toContain('越来越准');
  });
});
