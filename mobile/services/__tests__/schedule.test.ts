/**
 * schedule.ts 单测 —— formatPrescription 按 domain 分支渲染。
 * 守门:diet/sleep 处方加进来后,三处渲染(day-schedule/calendar 块/明细)复用此逻辑,
 * 任何 domain 分支回归都会在这里红。movement 沿用旧行为不破坏。
 */
import { formatPrescription } from '../schedule';

describe('formatPrescription', () => {
  it('returns empty for missing prescription', () => {
    expect(formatPrescription('diet', undefined)).toEqual({ primary: '', geneNote: '' });
  });

  it('movement: RPE + guidance + gene_note (unchanged behavior)', () => {
    const r = formatPrescription('movement', {
      intensity: 'moderate', rpe: '7', guidance: '间歇或力量', gene_note: 'ACTN3 偏爆发',
    });
    expect(r.primary).toBe('RPE 7 · 间歇或力量');
    expect(r.geneNote).toBe('ACTN3 偏爆发');
  });

  it('diet: kcal + per-meal protein + carb_timing, rounds floats', () => {
    const r = formatPrescription('diet', {
      kcal_target: 599.6, protein_per_meal_g: 34.7, carb_timing: '训练后补碳', gene_note: 'FTO',
    });
    expect(r.primary).toBe('~600 kcal · 蛋白 35g · 训练后补碳');
    expect(r.geneNote).toBe('FTO');
  });

  it('diet: falls back to daily protein_g when per-meal absent', () => {
    const r = formatPrescription('diet', { kcal_target: 500, protein_g: 120 });
    expect(r.primary).toBe('~500 kcal · 蛋白 120g/天');
  });

  it('sleep caffeine_cutoff: cutoff hours + gene_note', () => {
    const r = formatPrescription('sleep', {
      kind: 'caffeine_cutoff', cutoff_hours: 8, gene_note: 'CYP1A2 慢代谢',
    });
    expect(r.primary).toBe('睡前 8 小时内不再摄入咖啡因');
    expect(r.geneNote).toBe('CYP1A2 慢代谢');
  });

  it('sleep winddown: shows guidance', () => {
    const r = formatPrescription('sleep', { kind: 'winddown', guidance: '调暗灯光、远离屏幕' });
    expect(r.primary).toBe('调暗灯光、远离屏幕');
    expect(r.geneNote).toBe('');
  });
});
