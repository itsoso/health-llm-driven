# Reva Mobile — 信息架构 + 用户动线 重设计(实现 spec)

> **这是 [`docs/system-map/mobile-nav-map.md`](../../system-map/mobile-nav-map.md) §5 重设计的落地版**:分阶段、每页处置、安全验证、需拍板项。
> 依据:代码派生导航图 [`docs/_generated/mobile-nav-graph.json`](../../_generated/mobile-nav-graph.json)(89 页/104 边/12 孤儿/52 死胡同)+ 实测点遍 4 tab + governance §7 Surface Ownership + Claude Design handoff(`colors_and_type.css`)。
> **不变量**:① 不破坏既有导航(每阶段 sim 点遍验证)② 设计走 `revaTheme.ts` 单一真源 ③ R4/安全:动线改不碰写入语义(草稿→确认恒在)④ 每阶段独立可上线可回滚。
> `last-reviewed: 2026-06-27`

## 目标态 IA(对齐 governance §7「Mobile = Today / Agenda / Capture / Programs / Review」)

```
现状:[今日] [阿衡] [记录] [我=44项超级抽屉]      核心环跨 3 tab,功能埋抽屉
目标:[今日]     [议程]      [记录]      [阿衡]    [我]
      时间线脊柱  议程/时间线  统一录入     健康参谋  账号/设备/隐私/AI配置(~8项)
      +现在该做   +完成回路    草稿→确认    +简报     +/insights 入口(分析归此)
      +安全告警
```

## 分阶段(每阶段独立可上线,从低风险高价值起)

### P0 — 债务清理(零 IA 改动,纯减法)· 需拍板每项处置
扫出的"代码在、用户点不到"项,逐一定性(**这步需你拍板**,因涉及"删 vs 接 vs 暂留"产品判断):

| 项 | 类型 | 建议处置 | 待你定 |
|---|---|---|---|
| `WeeklyFitnessPlanCard` | 死组件(无屏挂载) | 删 | ✅删 / 挂哪屏 |
| `SpecialistChipRow` | 死组件 | 删 | ✅删 / 挂 chat |
| `OpenEpisodeCard` / `AgentSurface` | 死组件 | 删 | ✅删 / 接 episode 闭环 |
| `HomeTimelinePreview` | 死组件 | 删或挂今日 | ✅ |
| `/specialist/[name]` | 真孤儿页 | 挂 SpecialistChipRow 入口 或 删 | 接 / 删 |
| `/episode/[id]` | 真孤儿页 | memory 标"episode 闭环 parked" → **暂留**别删 | 暂留 |
| `/calendar-connect` | 真孤儿页 | 查是否被 `/calendar` 取代 → 取代则删 | 查/删 |
| `/reva-agent` | 真孤儿页 | reva 三件套合并时一并处理(见 P2) | 合并 |

验证:`dump_nav_graph.py` 重跑,孤儿/死胡同数下降;CI 绿;sim 点遍无回归。

### P1 — 设计语言统一(零 IA 改动,视觉)· 低风险高感知
把 `revaTheme.ts`(Claude Design)从"只有今日"推到全 tab + 子卡,消除"首页精致点进掉档":
- 迁 `/chat`、`/record`、`/me(settings)` 顶层 + 子卡(`VitalsGrid`/`MedicationCheckin`/`BodyStatsRow`/`ActivityRingBar`)从 legacy `useTheme()` → `revaColors`/`revaType`。
- 出口:每屏首字体 gate `useRevaFonts()`,数字走 IBM Plex Mono,卡 r-lg 18px,focus 时刻用 focus-bg。
- 分批(一屏一 PR),每屏 sim 截图对比 handoff。纯 OTA(JS)。

### P2 — IA 重构(动线改,**最大风险**,放最后 + 灰度)
1. **议程提为 tab**:`/agenda`(+timeline/day-schedule)从 settings 抽屉提为第 2 tab。`(tabs)/_layout.tsx` 加 tab;settings 移除这些入口。
2. **分析归枢**:新建 `/insights` 把 my-progress/代谢画像/结果追踪/抗衰/趋势 收一处;今日 + insights 双入口;settings 移除散项。
3. **settings 瘦身**:只留账号/设备/隐私/AI 配置(~8 项)。
4. **reva 三件套合并**:`reva`/`reva-agent`/`reva-onboarding` 收敛(onboarding 留入口,agent 并入 chat 或删)。
5. **alerts 提升**:安全告警从隐藏 tab → 今日内常驻入口。
- 风险:改 tab 栏 + 动 50+ 入口 = 高回归面。**必须**:① 走 product-pipeline(spec→实现→QA→灰度)② 每步 sim 点遍 + 真机验 ③ 旧入口保留重定向一个版本,不硬删。

## 核心闭环动线(目标)
```
今日(看脊柱)→ 现在该做 完成(原地做,草稿→确认不变)→ 自动回写时间线(原地看反馈)
            └ 批量补录 → 议程 tab(不再翻记录 tab)
```

## 验证(每阶段)
- `python mobile/scripts/dump_nav_graph.py` → 孤儿/死胡同/超级抽屉出边数回归对比。
- `./scripts/sim-build.sh "iPhone 17 Pro"` + cliclick 点遍受影响动线 + simctl 截图对比。
- `npx tsc --noEmit`(mobile)+ CI。

## 与 Codex 协调
Codex 在做 app 内系统地图屏(读 `docs/_generated/*`)。本 spec 改的是**产品 IA/导航**,与它的 system-map 展示屏不重叠;若 P2 动 tab 栏,先同步避免撞 `(tabs)/_layout.tsx`。
