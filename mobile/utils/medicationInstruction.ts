import { isMedicationRecordItem } from '../services/medicationFilters';

/** Query instructions cannot be medication names or cached intake cards. */
export function isMedicationInstructionName(name: string): boolean {
  const normalized = name.replace(/\s+/g, '');
  const read = normalized.match(/^(?:(?:请|麻烦|帮我|替我|先|只|仅|我想|我需要|提醒)[，,：:]*)*(?:查询|查阅|查看|查一下|查下|看看|核实|核对|检查|分析)(?:一下)?([^，,。；;]*)/);
  if (read && isMedicationRecordItem({ name: read[1] })) return true;
  return /(?:不要|不用|别|请勿|不需要|无需).{0,12}(?:记录|服药|停药|换药|剂量)|(?:查询|核实|核对|查看).{0,20}(?:药品|用药|计划|记录)|(?:记录状态|用药提醒|计划时间)/.test(normalized);
}
