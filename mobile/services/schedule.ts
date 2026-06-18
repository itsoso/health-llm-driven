/**
 * 每日时点日程 (timing-solver) 客户端。后端 GET /api/v1/schedule/today + PUT /profile/me。
 * 该端点尚未进 api.generated.ts(契约漂移待补 CI 闸),此处手写镜像后端 schema。
 * 只读时点;前端渲染须带 disclaimer hedge(后端已随响应带出)。
 */
import api from './api';

/**
 * 处方对象 —— 形状随 domain 变(后端 Smart Schedule cut A/D1/D2):
 *  - movement: intensity/type/duration_min/rpe/guidance/gene_note
 *  - diet:     kcal_target/protein_g/protein_per_meal_g/carb_timing/gene_note
 *  - sleep:    kind ("winddown"|"caffeine_cutoff")/cutoff_hours/guidance/gene_note
 * 字段全 optional;渲染按 domain/字段分支(见 formatPrescription)。沿用旧名以免破坏既有引用。
 */
export interface WorkoutPrescription {
  // movement
  intensity?: string; // high | moderate | low | rest | unknown
  type?: string; // interval_or_strength | aerobic_z2 | easy_aerobic | recovery
  duration_min?: number;
  rpe?: string;
  guidance?: string;
  gene_note?: string;
  // diet
  kcal_target?: number;
  protein_g?: number;
  protein_per_meal_g?: number;
  carb_timing?: string;
  // sleep
  kind?: string; // winddown | caffeine_cutoff
  cutoff_hours?: number;
}

export interface ScheduleItem {
  id: string;
  title: string;
  domain: string; // medication/supplement/diet/movement/sleep/checkup
  time: string; // "HH:MM"
  anchor?: string;
  degraded?: boolean;
  warning?: string;
  prescription?: WorkoutPrescription; // cut A:movement / D1:diet / D2:sleep 块带处方
}

/**
 * 把处方按 domain 渲成对齐风格的两段文本:`primary`(主行,如 "RPE 7 · …" 或 "~600 kcal · 蛋白 35g")
 * 和 `geneNote`(基因/机理注脚,单独一行)。三处渲染(day-schedule 行内 / calendar 块副标题 / calendar 明细)复用同一逻辑。
 * 返回空字符串表示该段无内容。措辞保持建议性、克制(这些是 advisory)。
 */
export function formatPrescription(
  domain: string,
  p?: WorkoutPrescription,
): { primary: string; geneNote: string } {
  if (!p) return { primary: '', geneNote: '' };
  const geneNote = p.gene_note ?? '';
  let parts: (string | null | undefined)[] = [];

  if (domain === 'diet') {
    parts = [
      p.kcal_target ? `~${Math.round(p.kcal_target)} kcal` : null,
      p.protein_per_meal_g
        ? `蛋白 ${Math.round(p.protein_per_meal_g)}g`
        : p.protein_g
          ? `蛋白 ${Math.round(p.protein_g)}g/天`
          : null,
      p.carb_timing || null,
    ];
  } else if (domain === 'sleep') {
    if (p.kind === 'caffeine_cutoff') {
      parts = [
        p.cutoff_hours ? `睡前 ${p.cutoff_hours} 小时内不再摄入咖啡因` : null,
        p.guidance || null,
      ];
    } else {
      // winddown 及其他
      parts = [p.guidance || null];
    }
  } else {
    // movement(及未知 domain 的兜底):沿用原有强度/RPE/指导渲染
    parts = [p.rpe ? `RPE ${p.rpe}` : null, p.guidance || null];
  }

  return { primary: parts.filter(Boolean).join(' · '), geneNote };
}

export interface RejectedOrDeferred {
  id: string;
  title: string;
  domain: string;
  reason: string;
}

export interface TodaySchedule {
  scheduled: ScheduleItem[];
  rejected: RejectedOrDeferred[];
  deferred: RejectedOrDeferred[];
  disclaimer?: string;
}

export async function getTodaySchedule(): Promise<TodaySchedule> {
  const { data } = await api.get('/schedule/today');
  return data;
}

export interface WorkHours {
  work_start_time: string | null;
  work_end_time: string | null;
}

export async function getWorkHours(): Promise<WorkHours> {
  const { data } = await api.get('/profile/me');
  return {
    work_start_time: data?.work_start_time ?? null,
    work_end_time: data?.work_end_time ?? null,
  };
}

/** 写上下班时点(HH:MM 或 null=清除)。后端 PUT /profile/me setattr 入 UserProfile。 */
export async function updateWorkHours(workStart: string | null, workEnd: string | null): Promise<void> {
  await api.put('/profile/me', { work_start_time: workStart, work_end_time: workEnd });
}
