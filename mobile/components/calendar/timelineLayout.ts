/**
 * Calendar 时间轴布局纯函数 —— 分钟数学 + 重叠泳道分配。
 * 无 RN / 无副作用,可单测(见 __tests__/timelineLayout.test.ts)。
 *
 * 坐标系:一天 0..1440 分钟,top = startMin * pxPerMin。
 * 重叠用贪心泳道:把时间上交叠的块分到不同列,等分列宽,块互不完全遮盖。
 */

export const DAY_MINUTES = 24 * 60;

/** 时间轴上一个待定位的块(已归一成分钟,与数据来源无关)。 */
export interface TimelineBlock {
  key: string;
  startMin: number; // 0..1440(clamp 到当天)
  endMin: number; // > startMin,clamp 到 1440
}

/** 泳道布局结果:第 i 个块占 lane 列(共 lanes 列,同一重叠簇内)。 */
export interface PlacedBlock<T extends TimelineBlock = TimelineBlock> {
  block: T;
  lane: number; // 0-based 列序
  lanes: number; // 该块所在重叠簇的总列数(列宽 = 1/lanes)
}

/** 把 "HH:MM" 解析成当天分钟数;非法返回 null。 */
export function hhmmToMinutes(hhmm: string): number | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(hhmm.trim());
  if (!m) return null;
  const h = Number(m[1]);
  const min = Number(m[2]);
  if (h < 0 || h > 23 || min < 0 || min > 59) return null;
  return h * 60 + min;
}

/**
 * 把 ISO datetime 转成"当天分钟数"(取本地时区的 H*60+M)。
 * 跨天事件由调用方先按当天窗口裁剪;这里只取时分。非法返回 null。
 */
export function isoToMinutesOfDay(iso: string | null): number | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  return d.getHours() * 60 + d.getMinutes();
}

/** 把分钟数(当天)夹到 [0, 1440]。 */
export function clampDayMinute(min: number): number {
  if (min < 0) return 0;
  if (min > DAY_MINUTES) return DAY_MINUTES;
  return min;
}

/**
 * 贪心泳道分配:输入块按 start 升序处理,找一簇时间上互相交叠的块,
 * 在簇内为每个块分配最小空闲列;簇结束后所有块共享该簇的列数。
 * 同 start 的稳定按输入顺序。返回与输入同序无关,可按 key 对回。
 */
export function assignLanes<T extends TimelineBlock>(blocks: T[]): PlacedBlock<T>[] {
  const sorted = [...blocks].sort((a, b) => a.startMin - b.startMin || a.endMin - b.endMin);
  const result: PlacedBlock<T>[] = [];

  let i = 0;
  while (i < sorted.length) {
    // 收集一个连续重叠簇:cluster 内任意块都与前面某块交叠(传递闭包)。
    const cluster: T[] = [sorted[i]];
    let clusterEnd = sorted[i].endMin;
    let j = i + 1;
    while (j < sorted.length && sorted[j].startMin < clusterEnd) {
      cluster.push(sorted[j]);
      clusterEnd = Math.max(clusterEnd, sorted[j].endMin);
      j += 1;
    }

    // 簇内贪心列分配:laneEnds[k] = 第 k 列当前已占到的 endMin。
    const laneEnds: number[] = [];
    const placed: { block: T; lane: number }[] = [];
    for (const b of cluster) {
      let lane = laneEnds.findIndex((end) => end <= b.startMin);
      if (lane === -1) {
        lane = laneEnds.length;
        laneEnds.push(b.endMin);
      } else {
        laneEnds[lane] = b.endMin;
      }
      placed.push({ block: b, lane });
    }
    const lanes = laneEnds.length;
    for (const p of placed) {
      result.push({ block: p.block, lane: p.lane, lanes });
    }
    i = j;
  }

  return result;
}
