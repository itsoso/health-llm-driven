# Mobile UI 一致性审计 + 统一设计方案 (2026-05-31)

模拟器实跑 (iPhone 17 Pro, iOS 26.4, build 成功) + 全量静态扫描得出。基准是
`mobile/constants/theme.ts` 的 token 系统 (colors/darkColors/typography/spacing/radii/shadows/metricColors)。

## 现状结论

设计 token 系统**很完整**,但**大面积没被遵守** —— 问题不是"缺设计系统",是"收敛"。

| 类别 | 严重度 | 量级 | 重灾文件 |
|---|---|---|---|
| 硬编码颜色 (破坏暗色) | 🔴 严重 | ~368 个独立 hex | genetic-report(47)、movement-plan(43)、chat/ChatInputBar(12) |
| 静态 import colors (暗色不切换) | 🟠 高 | 26 个文件 | JudgmentFeedbackBar、NetworkBanner、ErrorFallback、多个 chart/card |
| 字号字面量 (不走 typography) | 🟡 中 | 22 个不同 fontSize (标准只 10) | genetic-report(37)、movement-plan(20)、settings(10) |
| 间距/圆角魔法数 | 🟡 中 | ~341 处 | genetic-report(56)、movement-plan(43) |
| Dynamic Type 上限不一 | 🟡 中 | 1.18 / 1.3 / 1.4 / 无 混用 | home=1.18, chat=1.3, outcome=1.4, 其余无 |
| 组件重复造 | 🟠 高 | 15 种 card / 4 种 pill / 3 套 status badge | chat/cards、genetic-report、movement-plan |

> 已有但**很少被用**的共享原子: `design-system/{MetricTile,SectionHeader,HealthCard,EmptyState,PaceChart}`。
> **缺的原子**: `AppText`(typography+Dynamic Type 上限统一)、`Pill/Badge`(状态徽章,现每屏各造硬编码色)。

## 模拟器实跑发现的真实视觉 bug (设置/"我"页截图)

1. **Garmin 显示 `-465 分钟前`** —— 负数相对时间 bug,不该出现负值。
2. **右上角齿轮图标位置怪** —— `settings.tsx` 被复用进"我" tab,header 没适配(tab 模式不该有齿轮/返回错位)。
3. 列表行 icon 颜色杂、分组间距不统一 —— 印证硬编码色/间距审计。

## 统一设计规范 (目标态)

- **颜色**: 一律 `useTheme()` 的 `c.*`,禁止组件内 `#hex`。状态色抽成 `theme.ts` 的 `semanticColors`(genetic/movement/vitals 各档),自动暗色适配。
- **暗色**: 组件不在 module 作用域 `StyleSheet.create` 烤死颜色;改 `const {c}=useTheme(); const styles=useMemo(()=>createStyles(c),[c])`。
- **字号**: 全部映射到 `typography.*`(11→caption, 13→bodySmall, 15→bodyMedium, 17→bodyLarge/titleSmall...)。新增 `AppText` 原子封装。
- **间距/圆角**: 只用 `spacing.*` / `radii.*`;消除 2/3/5/6/7/9/10/14 等 off-scale 值(常见 `gap:6` → 统一 `spacing.xs`/`sm`)。
- **Dynamic Type**: `theme.ts` 加 `FONT_SIZE_CAPS = { default: 1.2, metric: 1.18, compact: 1.15 }`,`AppText` 默认 1.2。
- **共享原子**: 先复用已有 5 个;补 `AppText` + `Badge/Pill`;chat 15 种 card 收敛到 `Card` base。

## 收敛路线 (按杠杆排序, 每步独立 PR + 测试)

1. **26 个静态 import colors → useTheme()** —— 暗色立刻对 ~30% 组件生效。最高杠杆。
2. **状态色字典抽成 `semanticColors`** —— 消 70+ 重复 hex,genetic/movement/vitals 暗色化。
3. **新增 `AppText` + `Badge` 原子** —— 后续逐屏迁移的地基。
4. **字号字面量 → typography.\*** —— 先攻 genetic-report / movement-plan / ChatInputBar。
5. **间距/圆角魔法数 → spacing.\*/radii.\*** + Dynamic Type 上限常量化。

## 独立优化点 (非 token, 但实跑/审计暴露)

- Garmin 负数时间戳修复 (设置页 + 可能首页 BodyStats 同源)。
- "我" tab 复用 `settings.tsx` 的 header 适配 (齿轮/返回按 canGoBack 判断,已有 `canGoBack` 逻辑可复用)。
- chat/cards 15 种卡片缺统一 `CardShell`,视觉/间距/暗色各异。

---
*环境备注: 本次模拟器 build 成功 (0 error)、app 实跑确认,但 dev-client 截图遍历受 shell 抖动限制,仅取到设置页高质量截图 + 静态全量扫描。后续逐屏迁移建议在稳定环境逐个 PR。*
