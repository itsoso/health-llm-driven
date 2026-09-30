import { isMedicationRecordItem } from '../services/medicationFilters';

const DIET_FOOD_HOMOGRAPHS_RE = /山药/g;

// Recommendation-only guard, aligned with is_reusable_food_description.
// Preserve history and unfamiliar food names; do not replay symptom or
// non-intake narratives ("没吃", "牛肉面吗", "准备吃火锅") as today's food,
// including when the app is displaying a stale cached response.
// Sources mirror backend intake_intent_classifier._REUSE_EXCLUSION_RES exactly
// (checked by test_reuse_exclusions_mirror_mobile_guard).
const REUSE_EXCLUSION_SOURCES = [
  String.raw`(?:肚子|腹部|胃).{0,4}(?:痛|疼|胀)|腹痛|腹胀|腹泻|拉肚子|胃痛|胃疼|反酸|烧心|恶心|想吐|呕吐|头晕|心悸|不舒服|睡不着|失眠|睡不好`,
  String.raw`(?:吃了|喝了|服了|用了|补了|吃|喝|服|用|补)(?:的|了|过|点|些)?\s*(?:啥|什么|多少|几|哪些|哪)`,
  String.raw`(?:吃了|喝了|服了|用了|补了|吃|喝|服|用|补)[^?？]{0,12}[?？]`,
  String.raw`(?:吃了|喝了|服了|用了|补了|吃|喝|服|用|补)(?:了|过|的)?\s*(?:吗|呢)\s*[?？]?$`,
  String.raw`(?:下次|以后|再也|从此|今后)(?:都)?不(?:吃|喝|碰)|(?:下次|以后|再也|从此|今后)?(?:都)?别(?:吃|喝|碰)|不(?:应该|想|该|能|要|会|再)(?:吃|喝|碰)|不(?:吃|喝|碰)\S{0,10}了`,
  String.raw`(?:吃了|喝了|服了|用了|补了|吃|喝|服|用|补).{0,24}(?:吗|嗎|么|麼|呢)[?？!！。.~～…]*$`,
  String.raw`(吃|喝|服|补|補|用)(?:没|沒|不)\1|(?:有没有|有沒有|是不是|是否|要不要|该不该|該不該|能不能|可不可以|用不用|需不需要)(?:已经|已經|按时|按時|再)?(?:吃|喝|服|补|補|用)|(?:吃|喝|服|补|補|用)(?:了|过|過).{0,20}(?:没有?|沒有?)[?？!！。.~～…]*$|(?:怎么|怎麼|怎样|怎樣|如何|为什么|為什麼|为啥|為啥|咋|何时|何時|什么时候|什麼時候)(?:才能|能|要|该|該)?(?:吃|喝|服|补|補|用)`,
  String.raw`(?:没|沒|未)有?(?:按时|按時|及时|及時|准时|準時|来得及|來得及|能|法|再|怎么|怎麼)?(?:吃|喝|服|补|補|用药|用藥)|漏(?:了|掉了?)?(?:吃|喝|服|补|補|用药|用藥)|忘(?:了|记了?|記了?|掉了?)?(?:吃|喝|服|补|補|用药|用藥|带|帶)|(?<!差点)(?<!差點)(?<!险些)(?<!險些)(?<!差一点)(?<!差一點)忘(?:了|记了?|記了?|掉了?)[。.!！~～…]*$|不(?:应该|應該|应|應|想|该|該|能|要|会|會|再|用|必|需要|需|打算|准备|準備|敢)?(?:吃|喝|碰|服|补|補)|停(?:掉|用|服|药|藥|吃|喝|补|補)|暂停|暫停`,
  String.raw`(?<![特分个個区區差性类類级級识識辨告鉴鑑])[别別](?:再|忘)|[记記]得(?:要|再|按时|按時)?(?:吃|喝|服|补|補)(?![了过過完])|提醒我?(?:要|按时|按時|记得|記得)?(?:吃|喝|服|补|補)|(?:准备|準備|打算|计划|計劃|想|[将將]|[该該]|(?<![记記觉覺晓曉懂舍捨值难難])得|(?<!主)要)(?:再|去|先|开始|開始|按时|按時)?(?:吃|喝|服|补|補)|(?:待会|待會|等会|等會|等下|等一下|一会|一會|过会|過會|稍后|稍後|晚点|晚點|回头|回頭|马上|馬上|立刻|今晚|明天|明早|明晚|后天|後天)儿?(?:再|就|要|会|會|去|得)?(?:吃|喝|服|补|補)(?![了过過完的])`,
  String.raw`[?？]|(?:吗|嗎|么|麼|呢)$`,
  String.raw`什么|什麼|啥|多少|哪|怎么|怎麼|如何|为什么|為什麼`,
];
const REUSE_EXCLUSION_RES = REUSE_EXCLUSION_SOURCES.map((source) => new RegExp(source));

export function isReusableDietFoodDescription(value: string): boolean {
  const normalized = value.replace(/\s+/g, '').toLowerCase();
  return Boolean(normalized) && !REUSE_EXCLUSION_RES.some((pattern) => pattern.test(normalized));
}

export function assertDietFoodItemsAllowed(
  foodItems: string,
  options: { ownerBoundPhotoDraft?: boolean } = {},
): void {
  if (looksLikeDietManagementIntent(foodItems)) {
    throw new Error('invalid_diet_food_items_management');
  }
  if (looksLikeNonDietIntake(foodItems)) {
    // Owner-bound photo drafts may contain food slice counts such as `胡萝卜
    // 约3片`. Defer only that ambiguous unit; known medication/supplement
    // signals remain blocked locally and by the canonical backend guard.
    const onlyAmbiguousPhotoSlice = options.ownerBoundPhotoDraft
      && looksLikeOnlyAmbiguousPhotoSlice(foodItems);
    if (!onlyAmbiguousPhotoSlice) {
      throw new Error('invalid_diet_food_items_non_diet');
    }
  }
  if (looksLikeHealthMetricIntent(foodItems)) {
    throw new Error('invalid_diet_food_items_health_metric');
  }
}

export function looksLikeDietManagementIntent(value: string): boolean {
  const normalized = value.replace(/\s+/g, '').toLowerCase();
  return [
    '删除',
    '删掉',
    '删了',
    '删去',
    '移除',
    '撤销',
    '取消记录',
    '取消这一餐',
    '取消这餐',
    '误删',
    '不小心删',
    '恢复',
    '找回',
  ].some((marker) => normalized.includes(marker.toLowerCase()));
}

export function looksLikeNonDietIntake(value: string): boolean {
  const normalizedValue = value
    .normalize('NFKC')
    .replace(/[\u2010-\u2015\u2212\uFE58\uFE63\uFF0D]/g, '-')
    .replace(/[\u200B-\u200D\u2060\uFEFF]/g, '');
  // The shared medication classifier intentionally treats `药` as a strong
  // signal. In a diet payload, remove only confirmed food homographs before
  // applying that classifier. Explicit residual signals still block entries
  // such as `山药胶囊` or `山药 + 阿司匹林 1片`.
  const medicationCandidate = normalizedValue.replace(DIET_FOOD_HOMOGRAPHS_RE, ' ');
  if (isMedicationRecordItem({ name: medicationCandidate })) return true;
  // 饮品里常见的维 C 茶/柠檬饮料不应被补剂关键词误杀。
  if (/维\s*c\s*(?:茶|饮|饮料|果汁|柠檬|柠)/i.test(normalizedValue)) return false;
  if (/鱼油|维生素|维\s*d|b族|益生菌|辅酶\s*q?\s*10|甘氨酸镁|钙片|叶酸|锌片/i.test(normalizedValue)) {
    return true;
  }
  const compactValue = normalizedValue.replace(/[\s-]+/g, '');
  if (/(?:vitamind|d[23]|b12|coq10)(?:and)?(?:fishoil|magnesium|nac|omega3)|(?:fishoil|magnesium|nac|omega3)(?:and)?(?:vitamind|d[23]|b12|coq10)/i.test(compactValue)) {
    return true;
  }
  return /(^|[^a-z0-9])(?:vitamin[\s-]*[a-z]\d*|d3|d2|b12|coq[\s-]*10|nac|magnesium|glycinate|fish[\s-]*oil|omega(?:[\s-]*3)?)(?=$|[^a-z0-9]|\d+(?:\.\d+)?\s*(?:mg|mcg|μg|ug|iu|ml|g|粒|片|颗|袋|包|滴|tablet|capsule|softgel))/i.test(normalizedValue);
}

function looksLikeOnlyAmbiguousPhotoSlice(value: string): boolean {
  // `片` alone is not a reliable medication signal in an owner-bound meal
  // photo: it is also part of legitimate food names (`萝卜片`) and food
  // portions (`胡萝卜 3片`). Remove only that ambiguous marker, then run the
  // complete medication/supplement guard again. Strong signals such as drug
  // names, dosage suffixes, fish oil, or vitamins remain blocked here and by
  // the canonical backend classifier.
  const withoutAmbiguousSliceMarker = value.replace(/片/g, ' ');
  if (withoutAmbiguousSliceMarker === value) return false;
  return !looksLikeNonDietIntake(withoutAmbiguousSliceMarker);
}

export function looksLikeHealthMetricIntent(value: string): boolean {
  const normalized = value.replace(/\s+/g, '').toLowerCase();
  return Boolean(
    /(?:跑步|晨跑|夜跑|快走|步数|运动|训练|健身|游泳|骑行)\d*(?:分钟|分|步|公里|km|千米)?/i.test(normalized)
    || /(?:体重|腰围|臀围|体脂|bmi)\d+(?:\.\d+)?(?:kg|公斤|斤|cm|厘米|%)?/i.test(normalized)
    || /(?:睡了|睡眠|入睡|起床|醒来|午睡|小睡)\d+(?:\.\d+)?(?:小时|h|分钟|分)?/i.test(normalized)
    || /(?:血压|收缩压|舒张压)\d{2,3}\/\d{2,3}/i.test(normalized)
    || /(?:血糖|空腹血糖|餐后血糖)\d+(?:\.\d+)?/i.test(normalized)
    || /(?:心率|静息心率|rhr)\d{2,3}/i.test(normalized)
  );
}
