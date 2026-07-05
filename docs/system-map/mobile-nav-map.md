<!-- system-map facet-6 mobile 子文档。计数引 docs/_generated/mobile-nav-graph.json,绝不手打。
     图谱(节点/边)代码派生可重生成;动线/审计/重设计=叙事层,带 last-reviewed。 -->
---
doc: system-map/mobile-nav-map
last-reviewed: 2026-06-29
generated-source: docs/_generated/mobile-nav-graph.json
generator: mobile/scripts/dump_nav_graph.py
extend-via: docs/specs/product-pipeline-contract.md (S8 回写) + governance §7 Surface Ownership
---

# Mobile 用户动线知识图谱 + 信息架构审计 + 重设计

> **一句话**:把 mobile 全部页面(代码派生)建成「访问地图 + 知识图谱」,模拟用户动线,评估合理性,从产品功能/核心环出发重设计 IA 与动线。
> **读法**:计数/节点/边一律以 [`docs/_generated/mobile-nav-graph.json`](../_generated/mobile-nav-graph.json) 为准(`python mobile/scripts/dump_nav_graph.py` 重生成);本文是其上的动线/审计/重设计叙事。
> **校验真源边界**:本图的边 = 代码里 `router.push`/`<Link href>`/`Redirect` 的**静态字面量**跳转;`router.push(变量)` 等动态跳转 + 通知深链不在内(故个别"孤儿"实由通知深链可达)。**入边判定只认"被某挂载屏 import 的组件触发",写好但没挂载的组件不算入边。**

## 1. 全局页面地图(代码派生,全覆盖)

`mobile/app/**/*.tsx` 派生出全部页面节点(计数见 JSON `counts.nodes`),按产品职能分类:

| 类别 | 代表页面 | tab 可达性 |
|---|---|---|
| **日常脊柱**(daily-driver) | `/`(今日时间线)、`/chat`(小巴)、`/alerts`(安全告警,隐藏 tab)、`/sleep`、`/voice-chat` | 今日/小巴一跳;alerts 仅 settings→ |
| **录入**(record) | `/record`(高频记录中枢)、`/diet`、`/body-measurements`、`/symptom-record`、`/import`、`/workout-list` | 记录 tab→ |
| **议程/计划** | `/agenda`、`/timeline`、`/day-schedule`、`/goals`、`/reminders`、`/movement-plan`、`/fitness-plan` | **多数仅 settings 抽屉深进** |
| **深度分析** | `/my-progress`、`/biological-age`、`/metabolic-profile`、`/liver-trend`、`/indicator-history`、`/longevity-next`、`/weekly-briefing`、`/monthly-reports`、`/intervention-cycle` | **几乎全埋 settings** |
| **设置/配置** | `/settings`(=`/me`)、`/ai-profile`、`/coach-persona`、`/llm-preference`、`/device-sources`、`/data-connections`、`/notification-settings` | 我 tab(超级抽屉) |
| **设备** | `/rokid-health`、`/rokid-pushup-coach`、`/rokid-diagnostics`、`/meal-monitor` | settings→ |
| **参考/外链/入口** | `/login`、`/reva-onboarding`、`/shared/[token]`、`/open/shared/[token]`、`/privacy-policy`、`/knowledge/entity` | 外部/深链 |

## 2. 知识图谱关联(节点=页面,边=跳转)

- **枢纽页(hub,高出边)**:`/settings`(=`/me`,**44 出边 / 0 入边**——超级抽屉)、`/record`(11 出边)、`/`(10 出边)。
- **汇点(sink,高入边)**:`/card/[id]`(被 7+ 页指向的通用卡片详情渲染器)。
- **关键接缝**:`/me` = `export {default} from '../settings'` → `/me` 和 `/settings` 是同屏;图谱里 `/settings` 顶 44 出边却"无入边",因为大家走 `/me` tab 进。**IA 真相:几乎所有非 tab 功能唯一入口是「我」抽屉。**
- 真源可重生成:改导航后 `python mobile/scripts/dump_nav_graph.py` → JSON 刷新。

## 3. 用户路线图(动线,模拟用户操作)

**实测点击验证**(cliclick 真点 + simctl 截图,非 deep-link):4 tab 全部真点遍 —— 今日(时间线脊柱)/ 小巴(健康参谋+动态卡片)/ 记录(高频记录中枢)/ 我(设置超级抽屉)。

核心闭环动线(对照 governance §4 Core Loop)**现状**:
```
看今日(/今日) ──→ 现在该做卡 完成(原地写回)        [闭环的"看+做"在今日 tab 内]
要补录 ──→ 切「记录」tab(/record)──→ 子页(diet/sleep/...)  [跨 tab]
看趋势/结果 ──→ 切「我」tab ──→ 抽屉里翻 我的进度/结果追踪    [深埋 2 跳]
```
canonical 动线:① 首次 login→reva-onboarding→reva/今日 ② 每日闭环(上图)③ 记录(record→各录入)④ 对话(chat→voice-chat/memory)⑤ 安全(alerts→journal/trace;alerts 是隐藏 tab,仅 settings 进)⑥ 深度分析(几乎全 settings 深进)⑦ 设备 Rokid(settings→rokid-*)。

## 4. 动线合理性审计(按严重度;每条带证据)

**HIGH**
1. **超级抽屉**:`/settings` 44 子页 0 入边,议程/进度/本周建议/结果追踪/代谢画像等**该高频的功能埋设置长列**(实拍「我」tab 印证)→ 违反 governance §7「Mobile = Today/Agenda/Capture/Programs/Review」。
2. **核心环跨 3 tab**:看(今日)→做(今日)→补录(记录 tab)→看反馈(我→抽屉)动线断裂,违和核心环应顺滑。
3. **真·不可达功能(≥4)**:`/reva-agent`、`/calendar-connect`、`/specialist/[name]`、`/episode/[id]` —— 零真实入边、不在通知深链 → 用户点不到(代码在、功能死)。
4. **死代码入口组件(5)**:`WeeklyFitnessPlanCard` / `SpecialistChipRow` / `OpenEpisodeCard` / `AgentSurface` / `HomeTimelinePreview` —— 写了 `router.push` 但**没有任何屏幕挂载**它们 → 既是死代码,也是上面那些页"不可达"的根因。要么挂上、要么删。

**MED**
5. **功能重叠**:`reva`/`reva-agent`/`reva-onboarding` 三件套语义重叠;`voice-chat` vs `chat`;`movement-plan` vs `fitness-plan` —— 候选合并。
6. **`/alerts` 是隐藏 tab**:安全告警(产品安全脑的出口)只能 settings 进,可发现性低。

**LOW**
7. **52 死胡同**:多数是合理终点(detail/[id] 页);但 `/agenda`、`/timeline`、`/day-schedule` 等枢纽性页无前进 affordance,逛到了出不去只能返回。

> 合法外部入口**未误报为 bug**:`/login`(_layout 渲染)、`/shared`+`/open/shared`(分享深链)、`/reva-onboarding`(从 /reva 进)归为正常。

## 5. 重设计:IA + 用户动线(从产品功能/核心环出发)

**理想态 IA(5 tab,把核心环摊平、分析归枢、设置瘦身)**:
```
现状:[今日] [小巴] [记录] [我=44 项超级抽屉]
理想:[今日]     [议程]      [记录]      [小巴]    [我]
       时间线脊柱  议程/时间线  统一录入     健康参谋  账号/设备/
       +现在该做   +完成回路    (草稿→确认)  +简报     隐私/AI配置
       +安全告警   (从抽屉提上来 (语音/拍照              (~8 项,
       (提上来)    =核心环的"做") /手动)                 非功能)
分析类(我的进度/代谢画像/结果追踪/抗衰/趋势)→ 收进「今日」内一个 /insights 枢纽,不散落抽屉
设备 Rokid → 归「我」内 /data 子枢纽(待 Codex 硬件线稳定后再动 IA)
```

**核心闭环动线重设计**(跨 3 tab → 单 tab 内闭环 + 议程兜底):
```
今日(看脊柱)→ 现在该做 完成(原地做)→ 自动回写时间线(原地看反馈)
            └ 要批量补录 → 议程 tab(而非翻记录 tab)
```

**迁移提案**(promote/group/demote/merge):
| 动作 | 对象 | 产品理由 |
|---|---|---|
| **PROMOTE→tab** | 议程/时间线 | 核心环的"做",§7 要求 Mobile 有 Agenda |
| **PROMOTE→今日** | alerts 安全告警 | 安全脑出口不该藏隐藏 tab |
| **GROUP→/insights** | 我的进度/代谢画像/结果追踪/抗衰/趋势 | 分析类聚一枢纽,出抽屉 |
| **SLIM** | settings → ~8 项非功能配置 | 消超级抽屉 |
| **MERGE** | reva 三件套、voice-chat↔chat | 消重叠 |
| **FIX/DELETE** | 5 个未挂载死组件 + 4 真孤儿 | 挂上(可达)或删(去债) |

**设计语言统一**:实拍证实**只有「今日」贴了 Claude Design handoff**(`docs/design/reva/colors_and_type.css`:focus-bg/等宽数字/活力绿/18px 卡);小巴/记录/我仍 legacy(系统字体)。重设计须把 `revaTheme.ts` 推到全 tab + 子卡,消除"首页精致、点进掉档"的断崖。

## 6. 自迭代机制

- **图谱**:改导航 → `python mobile/scripts/dump_nav_graph.py` 重生成 JSON(代码派生不漂)。
- **审计回归**:接 product-pipeline S8 —— 每加页/改导航后重跑,对比孤儿/死胡同/超级抽屉出边数,新增不可达即 finding。
- **死组件哨兵**(待加):扫"定义了 `router.push` 但无屏 import 的入口组件" → 列死代码债。
- **设计保真**:跨端视觉用 `sim-build.sh`(Rokid 排除)+ cliclick 点遍 + simctl 截图(本轮已通)。
