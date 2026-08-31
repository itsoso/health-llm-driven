export interface MedicationRecordLike {
  name?: string | null;
  category?: string | null;
}

const MEDICATION_CATEGORIES = new Set([
  'medicine',
  'medication',
  'drug',
  'rx',
  'otc',
  '药品',
  '药物',
  '用药',
  '处方药',
  '非处方药',
]);

const NON_MEDICATION_CATEGORIES = new Set([
  'supplement',
  'supplements',
  'nutrition',
  'nutraceutical',
  'food',
  'health_product',
  '保健品',
  '补剂',
  '营养品',
  '营养补充剂',
  '食品',
]);

const NON_MEDICATION_NAME_RE = /维生素|vitamin|甘氨酸镁|magnesium|glycinate|褪黑素|melatonin|益生菌|probiotic|akk|鱼油|omega|辅酶|coq10|叶黄素|lutein|钙片|钙剂|calcium|锌片|zinc|硒|selenium|膳食纤维|fiber/i;

const MEDICATION_NAME_RE = /药|片|胶囊|喷雾|鼻喷|乳膏|软膏|滴眼液|滴鼻液|口服液|颗粒|注射|胰岛素|抗生素|华法林|阿司匹林|阿奇霉素|西替利嗪|氯雷他定|非索非那定|孟鲁司特|莫米松|布地奈德|氟替卡松|异丙托溴铵|特比萘芬|西地那非|替普瑞酮|施维舒|沃克|伏诺拉生|富马酸伏诺拉生|加斯清|伊托必利|盐酸伊托必利|莫沙必利|多潘立酮|吗丁啉|瑞巴派特|拉唑|瑞酮|霉素|沙星|洛芬|司特|他汀|地平|沙坦|普利|格列|替丁|止痛|warfarin|aspirin|azithromycin|metformin|insulin|cetirizine|loratadine|fexofenadine|montelukast|mometasone|budesonide|fluticasone|ipratropium|terbinafine|sildenafil/i;

function normalizedCategory(item: MedicationRecordLike): string {
  return String(item.category ?? '').trim().toLowerCase();
}

export function isMedicationRecordItem(item: MedicationRecordLike): boolean {
  const category = normalizedCategory(item);
  if (NON_MEDICATION_CATEGORIES.has(category)) return false;
  if (MEDICATION_CATEGORIES.has(category)) return true;

  const name = String(item.name ?? '').trim();
  if (!name) return false;
  if (NON_MEDICATION_NAME_RE.test(name)) return false;
  return MEDICATION_NAME_RE.test(name);
}

export function filterMedicationRecordItems<T extends MedicationRecordLike>(items: T[] | null | undefined): T[] {
  if (!Array.isArray(items)) return [];
  return items.filter(isMedicationRecordItem);
}
