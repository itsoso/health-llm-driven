import {
  uploadMedicalExamPdf,
  uploadMedicalExamImage,
  type MedicalExamImportResult,
  type MedicalExamImportSource,
} from './medicalExams';
import type { ServerCardDescriptor } from '../components/chat/cards/types';

export const CHAT_MEDICAL_EXAM_IMPORT_SKILL = {
  id: 'medical_exam_import',
  label: '导入体检报告',
  writeScope: 'medical_exam',
  requiresUserAction: true,
  safetyNote: 'OCR/AI 解析结果需要复核后再用于判断。',
} as const;

export interface ChatMedicalExamImportAsset {
  uri: string;
  name?: string | null;
  mimeType?: string | null;
}

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

function fileNameFor(asset: ChatMedicalExamImportAsset, fallback: string): string {
  const name = asset.name?.trim();
  return name && name.length > 0 ? name : fallback;
}

function lowerExt(name?: string | null): string {
  const n = (name ?? '').toLowerCase();
  const idx = n.lastIndexOf('.');
  return idx >= 0 ? n.slice(idx + 1) : '';
}

function isImageAsset(asset: ChatMedicalExamImportAsset): boolean {
  const mime = (asset.mimeType ?? '').toLowerCase();
  const ext = lowerExt(asset.name);
  return mime.startsWith('image/') || ['jpg', 'jpeg', 'png', 'heic', 'webp'].includes(ext);
}

function isPdfAsset(asset: ChatMedicalExamImportAsset): boolean {
  const mime = (asset.mimeType ?? '').toLowerCase();
  return mime === 'application/pdf' || lowerExt(asset.name) === 'pdf';
}

export function buildMedicalExamImportResultCard(
  result: MedicalExamImportResult,
): ServerCardDescriptor {
  const data: MedicalExamImportResultCardData = {
    exam_id: result.examId ?? result.exam_id,
    exam_date: result.examDate ?? result.exam_date ?? null,
    exam_type: result.examType ?? result.exam_type ?? null,
    hospital_name: result.hospitalName ?? result.hospital_name ?? null,
    items_count: result.itemsCount ?? result.items_count ?? null,
    abnormal_count: result.abnormalCount ?? result.abnormal_count ?? null,
    conclusions_count: result.conclusionsCount ?? result.conclusions_count ?? null,
    conclusion: result.conclusion ?? null,
    source: result.source,
    review_required: true,
    safety_note: CHAT_MEDICAL_EXAM_IMPORT_SKILL.safetyNote,
  };
  return { type: 'medical_exam_import_result', data };
}

export function buildMedicalExamImportSkillResult(
  result: MedicalExamImportResult,
): ChatMedicalExamImportSkillResult {
  const card = buildMedicalExamImportResultCard(result);
  return {
    skillId: CHAT_MEDICAL_EXAM_IMPORT_SKILL.id,
    card,
    prompt: '请基于我刚导入的体检报告，解释异常/关键指标、需要复核的地方，以及接下来 30 天最重要的健康行动。',
    context: {
      from: 'chat/runtime_skill/medical_exam_import',
      skill_id: CHAT_MEDICAL_EXAM_IMPORT_SKILL.id,
      import_result: card.data,
      safety_boundary: CHAT_MEDICAL_EXAM_IMPORT_SKILL.safetyNote,
    },
  };
}

export async function executeMedicalExamImportSkillForDocumentAsset(
  asset: ChatMedicalExamImportAsset,
): Promise<ChatMedicalExamImportSkillResult> {
  if (isPdfAsset(asset)) {
    const result = await uploadMedicalExamPdf(asset.uri, fileNameFor(asset, 'medical-exam.pdf'));
    return buildMedicalExamImportSkillResult(result);
  }
  if (isImageAsset(asset)) {
    const mimeType = asset.mimeType ?? 'image/jpeg';
    const result = await uploadMedicalExamImage(asset.uri, fileNameFor(asset, 'medical-exam.jpg'), mimeType);
    return buildMedicalExamImportSkillResult(result);
  }
  throw new Error('请选择 PDF、JPG、PNG、HEIC 或 WebP 格式的体检报告');
}
