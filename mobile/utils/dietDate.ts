// Diet 记录的日期助手。全部走「本地日历日」语义 (本 App 时区 Asia/Shanghai)。
// 数据完整性教训: `new Date("YYYY-MM-DD")` 会按 UTC 午夜解析, 在负 UTC 时区里
// getDate() 已经是前一天 → 单次 "-1" 会跳 2 个日历日 (prod 上把午餐记到 2 天前)。
// 因此这里对 "YYYY-MM-DD" 一律拆成本地年月日构造, 绝不 `new Date(string)`。

export function formatLocalDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** 当前本地日历日 (YYYY-MM-DD)。`new Date()` 取当前瞬时 + 本地 getters → 本地日, 天生时区安全。 */
export function todayStr(): string {
  return formatLocalDate(new Date());
}

/**
 * 把 "YYYY-MM-DD" 平移 offset 个本地日历日。
 * ±1 tap 在任何时区都精确移动一个本地日历日 (不受 UTC 午夜解析影响)。
 */
export function offsetDate(base: string, offset: number): string {
  const [y, m, d] = base.split('-').map(Number);
  const dt = new Date(y, m - 1, d); // 本地组件构造, 非 UTC 字符串解析
  dt.setDate(dt.getDate() + offset);
  return formatLocalDate(dt);
}
