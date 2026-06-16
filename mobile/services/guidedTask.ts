/**
 * 引导式运动执行 service —— 消费后端 GET /movement/guided-task?domain=...
 * (Reva R17 任务线/JITAI 执行层 · phone-first 第一刀)。
 *
 * 从「今日时间线」的运动项点「开始」进入:readiness 门控 → 引导执行 → 即时完成反馈。
 * 内容(动作要领/计划/语音脚本)全部来自后端循证库,前端不写死动作要领。
 *
 * TODO: 部署后改用 api.generated.ts 的 paths['/movement/guided-task']
 *       (后端 OpenAPI 还没部署,这里先手写最小契约,字段对齐 backend movement guided-task)。
 */
import api from './api';

export type GuidedGateDecision = 'do' | 'modified' | 'rest_instead';
export type GuidedReadinessZone = 'green' | 'yellow' | 'red' | 'unknown';

export interface GuidedGate {
  /** do=照常做 / modified=降阶 / rest_instead=今日换休息 */
  decision: GuidedGateDecision;
  readiness_zone: GuidedReadinessZone;
  reason: string;
}

export interface GuidedExercise {
  id: string;
  name: string;
  /** 证据等级标(high/medium/low/medical_grade...) */
  evidence_tier: string;
  /** 动作要领清单(逐条) */
  cues: string[];
  /** 视频/图示引用(v1 可先不放,null 时不渲染) */
  media_ref: string | null;
  /** 禁忌/警示(如「肩急性痛→停」) */
  contraindications: string[];
}

export interface GuidedPlan {
  sets: number | null;
  reps: number | null;
  duration_sec: number | null;
  rest_sec: number | null;
  /** 进阶说明(如「上次 3×12 → 今天 +3」) */
  progression_note: string;
}

export interface GuidedCapture {
  mode: 'manual';
  fields: string[];
}

export interface GuidedTask {
  domain: string;
  gate: GuidedGate;
  title: string;
  exercise: GuidedExercise;
  plan: GuidedPlan;
  /** 逐步语音引导脚本 */
  voice_script: string[];
  capture: GuidedCapture;
  safety_note: string | null;
}

export async function fetchGuidedTask(domain: string): Promise<GuidedTask> {
  const resp = await api.get<GuidedTask>('/movement/guided-task', {
    params: { domain },
  });
  return resp.data;
}
