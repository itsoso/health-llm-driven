import api from './api';

export interface RelatedCard {
  id: number;
  title: string;
  status: string | null;
  user_decision: string | null;
  outcome: 'improved' | 'unchanged' | 'worsened' | 'inconclusive' | null;
  effect_size: number | null;
  accuracy_score: number | null;
  metric_key: string | null;
  baseline_value: string | null;
  actual_value: string | null;
  evidence_level: 'high' | 'medium' | 'low' | 'medical_grade' | null;
  created_at: string | null;
  completed_at: string | null;
  graded_at: string | null;
}

export interface GeneticReportItem {
  rsid: string;
  gene: string;
  variant_name: string;
  category: string;
  description: string;
  hit: boolean;
  genotype: string | null;
  result_label: string | null;
  risk_level: 'high' | 'medium' | 'low' | 'info' | null;
  variant_nature: 'protective' | 'risk' | 'neutral' | null;
  related_cards: RelatedCard[];
  evidence_refs?: string[];
}

export interface Cluster {
  category: string;
  category_zh: string;
  total: number;
  hits: number;
  high_count: number;
  medium_count: number;
  rsids: string[];
}

export interface GeneticReport {
  profile: {
    id: number;
    test_provider: string;
    test_date: string | null;
    notes: string | null;
  } | null;
  items: GeneticReportItem[];
  clusters: Cluster[];
  stats: {
    total_known: number;
    hits: number;
    miss: number;
  };
  agent_summary: string | null;
}

export interface GeneticPredictions {
  profile: GeneticReport['profile'];
  height: {
    status: 'insufficient_model' | string;
    message: string;
    required_inputs?: string[];
  };
  education: {
    status: 'unsupported' | string;
    message: string;
    allowed_use?: string;
  };
  disease_risk: {
    status: 'screening' | 'no_data' | string;
    message: string;
    top_risks: {
      rsid: string | null;
      gene: string;
      variant_name: string | null;
      genotype: string | null;
      result_label: string | null;
      risk_level: 'high' | 'medium' | 'low' | 'info';
      evidence_level: string;
      message: string;
    }[];
  };
}

export interface SnpActions {
  headline: string;
  nutrition_actions: string[];
  supplement_actions: string[];
  exercise_actions: string[];
  lab_to_check: string[];
  drug_caution: string[];
  confidence: 'high' | 'medium' | 'low';
}

export interface SnpDetail {
  rsid: string;
  gene: string;
  variant_name: string;
  category: string;
  description: string;
  genotype_meanings: {
    genotype: string;
    display: string;
    label: string;
    risk: string;
  }[];
  user: {
    hit: boolean;
    genotype: string | null;
    result_label: string | null;
    risk_level: 'high' | 'medium' | 'low' | 'info' | null;
  };
  actions: SnpActions | null;
  related_cards: RelatedCard[];
  siblings: { rsid: string; gene: string; variant_name: string }[];
}

/**
 * G-W1 (2026-05-12): 拉 Mobile 基因报告页所需全部数据.
 * include_summary=false 跳过 LLM (省钱, 用于预览).
 */
export async function fetchGeneticReport(
  includeSummary = true,
): Promise<GeneticReport> {
  const { data } = await api.get<GeneticReport>(
    `/genetic/report/me?include_summary=${includeSummary}`,
  );
  return data;
}

/**
 * G-W4 (2026-05-12): 单 SNP 详情. 后端 LLM 缓存 24h, 返回静态信息 +
 * 用户命中 + 个性化 actions + 关联 cards + 同 cluster siblings.
 *
 * actions 可能为 null (LLM 失败或用户未命中) — UI 需 fallback.
 */
export async function fetchSnpDetail(rsid: string): Promise<SnpDetail> {
  const { data } = await api.get<SnpDetail>(`/genetic/snp/${rsid}`);
  return data;
}

export async function fetchGeneticPredictions(): Promise<GeneticPredictions> {
  const { data } = await api.get<GeneticPredictions>('/genetic/predictions/me');
  return data;
}

export const CATEGORY_LABELS: Record<string, string> = {
  nutrition: '营养',
  disease_risk: '疾病风险',
  exercise: '运动',
  drug_sensitivity: '药物敏感',
  cognition: '认知',
  sleep: '睡眠',
  recovery: '恢复',
  personality: '人格',
  other: '其他',
};

export const RISK_COLORS: Record<string, { bg: string; text: string; label: string }> = {
  high: { bg: '#FEE2E2', text: '#991B1B', label: '高风险' },
  medium: { bg: '#FEF3C7', text: '#92400E', label: '中等' },
  low: { bg: '#DBEAFE', text: '#1E40AF', label: '低风险' },
  info: { bg: '#F1F5F9', text: '#475569', label: '中性' },
};
