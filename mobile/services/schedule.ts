/**
 * 每日时点日程 (timing-solver) 客户端。后端 GET /api/v1/schedule/today + PUT /profile/me。
 * 该端点尚未进 api.generated.ts(契约漂移待补 CI 闸),此处手写镜像后端 schema。
 * 只读时点;前端渲染须带 disclaimer hedge(后端已随响应带出)。
 */
import api from './api';

export interface WorkoutPrescription {
  intensity: string; // high | moderate | low | rest | unknown
  type?: string; // interval_or_strength | aerobic_z2 | easy_aerobic | recovery
  duration_min?: number;
  rpe?: string;
  guidance?: string;
  gene_note?: string;
}

export interface ScheduleItem {
  id: string;
  title: string;
  domain: string; // medication/supplement/diet/movement/sleep/checkup
  time: string; // "HH:MM"
  anchor?: string;
  degraded?: boolean;
  warning?: string;
  prescription?: WorkoutPrescription; // cut A:movement 块带处方,前端渲染强度/RPE/指导
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
