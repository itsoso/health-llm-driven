/**
 * 跳过原因枚举(单一可信源)。
 *
 * ⚠️ 镜像后端 SKIP_REASONS(backend/app/...agenda_service 的 skip_reason 校验,
 * 上线于 commit 4d940a79)。8 个枚举值喂 P6 学习闭环 —— value 必须与后端逐字对齐,
 * 否则 /agenda/complete 422。label 是给用户看的中文。
 *
 * 复用 services/agenda.ts 的 AgendaSkipReason 类型,保证 value 集合不漂移
 * (这里漏一个/多一个,tsc 立刻红)。
 *
 * R4:跳过是纯记录动作(没做 + 为什么),无医疗内容。
 */
import type { AgendaSkipReason } from '../services/agenda';

export interface SkipReasonOption {
  value: AgendaSkipReason;
  label: string;
}

export const SKIP_REASONS: readonly SkipReasonOption[] = [
  { value: 'no_time', label: '没时间' },
  { value: 'forgot', label: '忘了' },
  { value: 'no_supply', label: '没备货' },
  { value: 'too_tired', label: '太累' },
  { value: 'wrong_place', label: '不在场所' },
  { value: 'too_hard', label: '太难' },
  { value: 'unwell', label: '身体不适' },
  { value: 'social', label: '社交场合' },
] as const;
