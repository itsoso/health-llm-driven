/**
 * Twin 纯函数 helper — 不引 axios/react-query, 单测友好.
 *
 * twin.ts 还会 re-export 这些, 老调用点不受影响.
 */

/**
 * 把 freshness 原始字符串 (如 "1h ago" / "今日" / "2026-04-27") 归一化为 age_days 数值.
 * 未知格式返回 null (不做降级判断).
 */
export function freshnessAgeDays(text: string | null | undefined, now = new Date()): number | null {
  if (!text) return null;
  const t = text.trim();

  // "今日" / "今天" / "刚刚" / "1h ago" < 1 day
  if (/今日|今天|刚刚|just now|< ?1 ?day/i.test(t)) return 0;
  if (/(\d+)\s*h\s*ago/i.test(t)) return 0;
  if (/(\d+)\s*min\s*ago/i.test(t)) return 0;

  // "3d ago" / "3 天前"
  const daysMatch = t.match(/(\d+)\s*(d|天|day)/i);
  if (daysMatch) return parseInt(daysMatch[1], 10);

  // "2026-04-15" 形式
  const dateMatch = t.match(/(\d{4})-(\d{2})-(\d{2})/);
  if (dateMatch) {
    const [, y, m, d] = dateMatch;
    const dt = new Date(Number(y), Number(m) - 1, Number(d));
    const diffMs = now.getTime() - dt.getTime();
    return Math.max(0, Math.floor(diffMs / (1000 * 60 * 60 * 24)));
  }

  // "2 个月前" / "6 months ago"
  const monthsMatch = t.match(/(\d+)\s*(个月|months?|mo)/i);
  if (monthsMatch) return parseInt(monthsMatch[1], 10) * 30;

  return null;
}

// ───────────────────── PhenoAge / 身体年龄 ─────────────────────

/** PhenoAge(Levine 2018)的 9 项血检输入 → 中文展示名(缺值时列给用户)。 */
const PHENOAGE_INPUT_LABELS: Record<string, string> = {
  albumin: '白蛋白',
  creatinine: '肌酐',
  blood_glucose: '空腹血糖',
  crp: 'CRP',
  lymphocyte_pct: '淋巴细胞%',
  mcv: 'MCV',
  rdw: 'RDW',
  alp: '碱性磷酸酶',
  wbc: '白细胞',
};

export interface PhenoAgeView {
  status: 'ok' | 'incomplete';
  phenotypicAge: number | null;   // 身体年龄(岁)
  deltaYears: number | null;      // = 身体年龄 - 实足年龄;<0 偏年轻
  chronoAge: number | null;       // 实足年龄(由 phenotypicAge - delta 反推)
  claimBoundary: string;          // 诚实纪律:展示侧必须呈现
  missingLabels: string[];        // incomplete 时缺哪些血检项
}

/**
 * 从 Twin 快照提取"身体年龄"视图模型(纯函数,UI 无关)。
 * - labs.phenotypic_age 有值 → status='ok'
 * - 无值 → status='incomplete' + 列出缺失的血检项(供"去补检"引导)
 */
export function extractPhenoAge(twin: any): PhenoAgeView {
  const labs = twin?.labs ?? {};
  const pa = labs.phenotypic_age;

  if (typeof pa === 'number' && Number.isFinite(pa)) {
    const delta =
      typeof labs.phenotypic_age_delta_years === 'number'
        ? labs.phenotypic_age_delta_years
        : null;
    const chrono = delta != null ? Math.round((pa - delta) * 10) / 10 : null;
    return {
      status: 'ok',
      phenotypicAge: Math.round(pa * 10) / 10,
      deltaYears: delta,
      chronoAge: chrono,
      claimBoundary: labs.phenoage_claim_boundary || '',
      missingLabels: [],
    };
  }

  const missing: string[] = [];
  for (const key of Object.keys(PHENOAGE_INPUT_LABELS)) {
    if (labs[key] == null) missing.push(PHENOAGE_INPUT_LABELS[key]);
  }
  return {
    status: 'incomplete',
    phenotypicAge: null,
    deltaYears: null,
    chronoAge: null,
    claimBoundary: '',
    missingLabels: missing,
  };
}
