/**
 * statusStagePhrase — /agent/stream status 事件 → 中文实时状态短语。
 *
 * 后端发**两个** status 事件家族 (二者都进这里):
 *  1) 旧家族 (思考过程可视化): { event: "status", data: { stage, detail, round } }
 *       stage ∈ vision | thinking | tool | synthesis; detail/round 可空。
 *  2) P0-1 进度家族 (flat 契约): { type: "status", stage, round?, label? }
 *       stage ∈ accepted | tool | synthesis; tool 阶段带完整人话 label。
 *
 * 调用方把两种都归一成一个对象喂进来 (旧家族传 data, 新家族传 evt 本身), 本函数按
 * 字段兜底解析 —— label (新) 优先于 detail (旧)。纯函数, 无副作用, 便于单测。映射:
 *   - accepted   → "已收到，正在准备…" (首 token 前 8s 的确定性反馈)
 *   - vision     → "识别图片中"
 *   - thinking   → detail 非空时**原样显示 detail**, 否则 "小巴正在思考"
 *   - tool       → label 存在时**原样显示 label** (已是完整人话); 否则 detail 存在时
 *                  `正在${detail}`; 都无 → "调用工具中"
 *   - synthesis  → "整理回复中"
 *   - 其它未知 stage → null (安全忽略, 与事件链未知事件一致)
 */

export type StatusStage = 'accepted' | 'vision' | 'thinking' | 'tool' | 'synthesis';

export interface StatusEventData {
  stage?: string | null;
  detail?: string | null;
  round?: number | null;
  // P0-1 进度家族: tool 阶段的完整人话动词短语 (如 "查看健康数据…")。
  label?: string | null;
}

export function statusStagePhrase(data: StatusEventData | null | undefined): string | null {
  if (!data) return null;
  const stage = data.stage;
  const detail = typeof data.detail === 'string' && data.detail.trim() ? data.detail.trim() : null;
  const label = typeof data.label === 'string' && data.label.trim() ? data.label.trim() : null;

  switch (stage) {
    case 'accepted':
      return label ?? '已收到，正在准备…';
    case 'vision':
      return '识别图片中';
    case 'thinking':
      // detail 非空 → 原样显示 (后端文案优先); 否则默认思考短语。
      return detail ?? '小巴正在思考';
    case 'tool':
      // label (新进度家族, 已是完整人话) 优先; 否则回退旧 detail 拼接; 都无 → 默认。
      if (label) return label;
      return detail ? `正在${detail}` : '调用工具中';
    case 'synthesis':
      return '整理回复中';
    default:
      return null;
  }
}
