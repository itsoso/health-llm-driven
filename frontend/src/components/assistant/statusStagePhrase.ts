/**
 * statusStagePhrase — /agent/stream 新增 status 事件 → 中文实时状态短语。
 *
 * 后端 SSE: { event: "status", data: { stage, detail, round } }
 *   stage ∈ vision | thinking | tool | synthesis
 *   detail: string | null   round: int | null
 *
 * 纯函数, 无副作用, 便于单测。映射规则:
 *   - vision     → "识别图片中"
 *   - thinking   → detail 非空时**原样显示 detail** (后端会发"该模型整段生成…"之类文案),
 *                  否则 "小巴正在思考"
 *   - tool       → detail 存在时 `正在${detail}`, 否则 "调用工具中"
 *   - synthesis  → "整理回复中"
 *   - 其它未知 stage → null (安全忽略, 与事件链未知事件一致)
 */

export type StatusStage = 'vision' | 'thinking' | 'tool' | 'synthesis';

export interface StatusEventData {
  stage?: string | null;
  detail?: string | null;
  round?: number | null;
}

export function statusStagePhrase(data: StatusEventData | null | undefined): string | null {
  if (!data) return null;
  const stage = data.stage;
  const detail = typeof data.detail === 'string' && data.detail.trim() ? data.detail.trim() : null;

  switch (stage) {
    case 'vision':
      return '识别图片中';
    case 'thinking':
      // detail 非空 → 原样显示 (后端文案优先); 否则默认思考短语。
      return detail ?? '小巴正在思考';
    case 'tool':
      return detail ? `正在${detail}` : '调用工具中';
    case 'synthesis':
      return '整理回复中';
    default:
      return null;
  }
}
