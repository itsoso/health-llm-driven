import {
  importMedicalExamFile,
  type MedicalExamImportResult,
  type MedicalExamImportSource,
} from './api/medicalExams';
import type { ServerCardDescriptor } from '@/components/assistant/inlineCards';

export const CHAT_MEDICAL_EXAM_IMPORT_SKILL = {
  id: 'medical_exam_import',
  label: '导入体检报告',
  writeScope: 'medical_exam',
  requiresUserAction: true,
  safetyNote: 'OCR/AI 解析结果需要复核后再用于判断。',
} as const;

export interface MedicalExamImportResultCardData {
  exam_id: number;
  exam_date?: string | null;
  exam_type?: string | null;
  hospital_name?: string | null;
  items_count?: number | null;
  abnormal_count?: number | null;
  conclusions_count?: number | null;
  conclusion?: string | null;
  source: MedicalExamImportSource;
  review_required: boolean;
  safety_note: string;
}

export interface ChatMedicalExamImportSkillResult {
  skillId: typeof CHAT_MEDICAL_EXAM_IMPORT_SKILL.id;
  card: ServerCardDescriptor;
  prompt: string;
  context: Record<string, any>;
}

export function buildMedicalExamImportResultCard(result: MedicalExamImportResult): ServerCardDescriptor {
  const data: MedicalExamImportResultCardData = {
    exam_id: result.examId,
    exam_date: result.examDate ?? null,
    exam_type: result.examType ?? null,
    hospital_name: result.hospitalName ?? null,
    items_count: result.itemsCount ?? null,
    abnormal_count: result.abnormalCount ?? null,
    conclusions_count: result.conclusionsCount ?? null,
    conclusion: result.conclusion ?? null,
    source: result.source,
    review_required: true,
    safety_note: CHAT_MEDICAL_EXAM_IMPORT_SKILL.safetyNote,
  };
  return { type: 'medical_exam_import_result', data };
}

function buildPrompt(card: ServerCardDescriptor): string {
  const d = card.data as MedicalExamImportResultCardData;
  const parts = [
    `exam_id=${d.exam_id}`,
    d.exam_date ? `日期=${d.exam_date}` : null,
    d.hospital_name ? `机构=${d.hospital_name}` : null,
    d.items_count != null ? `指标=${d.items_count}` : null,
    d.abnormal_count != null ? `异常=${d.abnormal_count}` : null,
  ].filter(Boolean).join('，');
  return `请基于我刚导入的体检报告（${parts}），解释异常/关键指标、需要复核的地方，以及接下来 30 天最重要的健康行动。`;
}

export async function executeMedicalExamImportSkillForFile(file: File): Promise<ChatMedicalExamImportSkillResult> {
  const result = await importMedicalExamFile(file);
  const card = buildMedicalExamImportResultCard(result);
  return {
    skillId: CHAT_MEDICAL_EXAM_IMPORT_SKILL.id,
    card,
    prompt: buildPrompt(card),
    context: {
      from: 'web_chat/runtime_skill/medical_exam_import',
      skill_id: CHAT_MEDICAL_EXAM_IMPORT_SKILL.id,
      import_result: card.data,
      safety_boundary: CHAT_MEDICAL_EXAM_IMPORT_SKILL.safetyNote,
    },
  };
}
