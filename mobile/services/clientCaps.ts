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

/** diet_daily_summary 客户端能力位。false = 渲染器就绪但暗置 (不声明 genui-diet-summary-v1)。 */
export const REVA_UI_DIET_SUMMARY_CAP_ENABLED = false;

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
  return caps.join(', ');
}
