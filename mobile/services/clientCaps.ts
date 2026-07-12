/**
 * Chat 客户端能力声明 (X-Reva-Client-Caps header).
 *
 * 后端据此决定在 ```reva-ui fence 里下发哪些 GenUI 组件块 —— 声明了才发,
 * 未声明的块会被后端跳过 (renderer 可以先随包发布, cap 暗置到 eval 过闸再点亮)。
 *
 * `genui-table-v1`: rank1 GenUI-first 的 metric_table 卡片能力位。
 * 渲染器 (MetricTableCard + revaUiBlocks parser) 已随包发布, 但 cap 暗置:
 * 不声明该 token → 后端不下发 metric_table 块。eval 过闸后把
 * REVA_UI_TABLE_CAP_ENABLED 翻 true 才点亮 (renderer ships, cap stays dark)。
 */

/** metric_table 客户端能力位。false = 渲染器就绪但暗置 (不声明 genui-table-v1)。 */
export const REVA_UI_TABLE_CAP_ENABLED = false;

/** 存量已上线的能力位 —— 顺序 / 分隔与历史请求头保持一致 (byte-for-byte)。 */
const BASE_CLIENT_CAPS = 'genui-v1, genui-components-v1, genui-record-quality-v1';

/**
 * 组装 X-Reva-Client-Caps 头。cap 暗置时返回与历史完全一致的字符串;
 * 点亮后追加 ', genui-table-v1'。
 */
export function buildClientCapsHeader(): string {
  return REVA_UI_TABLE_CAP_ENABLED
    ? `${BASE_CLIENT_CAPS}, genui-table-v1`
    : BASE_CLIENT_CAPS;
}
