/**
 * Chat 客户端能力声明 (X-Reva-Client-Caps header).
 *
 * 后端据此决定在 ```reva-ui fence / done.cards 里下发哪些 GenUI 组件块 —— 声明了才发,
 * 未声明的块会被后端跳过 (renderer 可以先随包发布, cap 暗置到 eval 过闸再点亮)。
 *
 * `genui-table-v1`: rank1 GenUI-first 的 metric_table 卡片能力位。
 * 渲染器 (MetricTableCard + revaUiBlocks parser) 已随包发布, 但 cap 暗置:
 * 不声明该 token → 后端不下发 metric_table 块。eval 过闸后把
 * REVA_UI_TABLE_CAP_ENABLED 翻 true 才点亮 (renderer ships, cap stays dark)。
 *
 * `genui-diet-summary-v1`: 汇总类卡 v1 的「今日饮食汇总」(diet_daily_summary) 能力位。
 * 渲染器 (DietSummaryCard) 已随包发布, 但 cap 暗置:不声明该 token → 后端不下发
 * diet_daily_summary 卡。eval 过闸后把 REVA_UI_DIET_SUMMARY_CAP_ENABLED 翻 true 点亮。
 */

/** metric_table 客户端能力位。false = 渲染器就绪但暗置 (不声明 genui-table-v1)。 */
export const REVA_UI_TABLE_CAP_ENABLED = true;

/** diet_daily_summary 客户端能力位。点亮 (2026-07-16):composer/renderer/契约/emission 就绪,
 *  后端 emission e2e + 黄金样本闸绿、安全评审 GO → 声明 genui-diet-summary-v1。 */
export const REVA_UI_DIET_SUMMARY_CAP_ENABLED = true;

/** sleep_summary 客户端能力位(汇总卡族·睡眠)。点亮:renderer(SleepSummaryCard)+ parser
 *  分支(v===1)+ 后端 composer/emission/契约就绪 → 声明 genui-sleep-summary-v1。 */
export const REVA_UI_SLEEP_SUMMARY_CAP_ENABLED = true;

/** medication_list 客户端能力位(汇总卡族·在用药物)。点亮:renderer(MedicationListCard)+
 *  parser 分支(v===1)+ 后端确定性取数/emission 就绪 → 声明 genui-medication-list-v1。 */
export const REVA_UI_MEDICATION_LIST_CAP_ENABLED = true;

/** 存量已上线的能力位 —— 顺序 / 分隔与历史请求头保持一致 (byte-for-byte)。 */
const BASE_CLIENT_CAPS = 'genui-v1, genui-components-v1, genui-record-quality-v1';

/**
 * 组装 X-Reva-Client-Caps 头。暗置的 cap 不追加,返回与历史完全一致的字符串;
 * 点亮后按声明顺序追加对应 token (', genui-table-v1' / ', genui-diet-summary-v1')。
 */
export function buildClientCapsHeader(): string {
  const caps = [BASE_CLIENT_CAPS];
  if (REVA_UI_TABLE_CAP_ENABLED) caps.push('genui-table-v1');
  if (REVA_UI_DIET_SUMMARY_CAP_ENABLED) caps.push('genui-diet-summary-v1');
  if (REVA_UI_SLEEP_SUMMARY_CAP_ENABLED) caps.push('genui-sleep-summary-v1');
  if (REVA_UI_MEDICATION_LIST_CAP_ENABLED) caps.push('genui-medication-list-v1');
  return caps.join(', ');
}
