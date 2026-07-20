<!-- system-map facet-6 mobile 子文档。计数引 docs/_generated/mobile-nav-graph.json,绝不手打。
     图谱(节点/边)代码派生可重生成;动线/审计/重设计=叙事层,带 last-reviewed。 -->
---
doc: system-map/mobile-nav-map
last-reviewed: 2026-07-20
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
| **日常脊柱**(daily-driver) | `/chat`(小巴单一主入口)、`/today`(今日详情)、`/agenda`(今日行动管理)、`/alerts`(安全告警)、`/voice-chat` | 从小巴动态卡片与顶部入口进入二级面 |
| **录入**(record) | `/record`(高频记录中枢)、`/diet`、`/body-measurements`、`/symptom-record`、`/import`、`/workout-list` | 小巴快捷记录托盘进入 |
| **议程/计划** | `/agenda`、`/timeline`、`/day-schedule`、`/goals`、`/reminders`、`/movement-plan`、`/fitness-plan` | `/agenda` 由小巴今日行动直达，其余按上下文进入 |
| **深度分析** | `/my-progress`、`/biological-age`、`/metabolic-profile`、`/liver-trend`、`/indicator-history`、`/longevity-next`、`/weekly-briefing`、`/monthly-reports`、`/intervention-cycle` | **几乎全埋 settings** |
| **设置/配置** | `/settings`(=`/me`)、`/ai-profile`、`/coach-persona`、`/llm-preference`、`/device-sources`、`/data-connections`、`/notification-settings` | 我 tab(超级抽屉) |
| **设备** | `/rokid-health`、`/rokid-pushup-coach`、`/rokid-diagnostics`、`/meal-monitor` | settings→ |
| **参考/外链/入口** | `/login`、`/reva-onboarding`、`/shared/[token]`、`/open/shared/[token]`、`/privacy-policy`、`/knowledge/entity` | 外部/深链 |

## 2. 知识图谱关联(节点=页面,边=跳转)

- **主枢纽**:`/chat` 是 agent-native shell，今日、记录、账户配置和动态 UI 都从对话上下文进入。
- **执行枢纽**:`/agenda` 只管理 `/agenda/today` 的今日事项；`/alerts` 只承载安全告警和长期行动卡，二者不混排。
- **关键接缝**:`/me` 仍复用 `/settings`，但底部 Tab Bar 已隐藏，不再作为日常主导航。
- 真源可重生成:改导航后 `python mobile/scripts/dump_nav_graph.py` → JSON 刷新。

## 3. 用户路线图(动线,模拟用户操作)

**当前 Shell**:底部 Tab Bar 已移除，小巴是唯一主入口；今日、记录、我保留为深链兼容和二级页面，不再同时竞争一级导航。

核心闭环动线(对照 governance §4 Core Loop)**现状**:
```
小巴(/chat) ──→ 今日行动卡 ──→ 完成(原地写回)
                          └─→ 管理今日行动(/agenda) ──→ 完成/稍后/跳过/调整
                                                      └─→ 返回小巴并刷新卡片
要补录 ──→ 小巴记录托盘 ──→ diet/body-measurements/symptom-record/...
看趋势/结果 ──→ 小巴按上下文生成趋势卡或进入对应分析页
```
canonical 动线:① 首次 login→onboarding→小巴 ② 每日闭环(上图)③ 小巴快捷记录→各录入 ④ 对话→voice-chat/memory ⑤ 今日安全入口→alerts→journal/trace ⑥ 深度分析由小巴上下文或设置进入 ⑦ 设备由设置进入。

## 4. 动线合理性审计(按严重度;每条带证据)

**HIGH**
1. **设置仍偏重**:低频分析与设备配置较多，需继续按上下文从小巴暴露，而不是让用户翻设置目录。
2. **二级页返回一致性**:所有从小巴进入的二级页必须提供原生返回栈；冷深链进入时回到 `/chat`，不得形成死胡同。
3. **动态路由语义**:今日执行必须进入 `/agenda`；安全告警才进入 `/alerts`，后端卡片 action 不得混用。

**MED**
4. **功能重叠**:`voice-chat` 与 `chat`、`movement-plan` 与 `fitness-plan` 仍需按任务边界继续收敛。
5. **安全入口可发现性**:`/alerts` 是隐藏路由，应从今日安全卡或小巴上下文进入，不作为今日行动列表替代品。

**LOW**
6. **深层终点页**:详情页可以是合理终点；`/agenda`、`/timeline` 等枢纽页必须同时有返回和下一步操作。

> 合法外部入口**未误报为 bug**:`/login`(_layout 渲染)、`/shared`+`/open/shared`(分享深链)、`/reva-onboarding`(从 /reva 进)归为正常。

## 5. 重设计:IA + 用户动线(从产品功能/核心环出发)

**当前目标 IA(小巴单入口，按上下文展开能力)**:
```
[小巴]
  ├─ 今日状态与下一步行动
  ├─ 管理今日行动 -> /agenda
  ├─ 快速记录 -> 对应 Capture 页面
  ├─ 安全告警 -> /alerts
  ├─ 趋势与复盘 -> 对应分析页
  └─ 账号/设备/隐私 -> /settings
```

**核心闭环动线重设计**(跨 3 tab → 单 tab 内闭环 + 议程兜底):
```
小巴(看状态)→ 动态行动卡完成(原地做)→ 自动回写并刷新卡片
           └ 需要管理 → /agenda → 完成/稍后/跳过/调整 → 返回小巴
```

**迁移提案**(promote/group/demote/merge):
| 动作 | 对象 | 产品理由 |
|---|---|---|
| **PROMOTE→context** | 议程/时间线 | 由小巴行动卡直接进入，不恢复底部 Tab |
| **SEPARATE** | `/agenda` 与 `/alerts` | 今日执行和安全告警职责分离 |
| **GROUP→context** | 进度/代谢画像/结果追踪/趋势 | 小巴按问题直接打开对应结果，不要求用户翻目录 |
| **SLIM** | settings | 只保留账号、设备、隐私和高级配置 |
| **MERGE** | voice-chat↔chat、movement-plan↔fitness-plan | 消除同任务多入口 |

**设计语言统一**:实拍证实**只有「今日」贴了 Claude Design handoff**(`docs/design/reva/colors_and_type.css`:focus-bg/等宽数字/活力绿/18px 卡);小巴/记录/我仍 legacy(系统字体)。重设计须把 `revaTheme.ts` 推到全 tab + 子卡,消除"首页精致、点进掉档"的断崖。

## 6. 自迭代机制

- **图谱**:改导航 → `python mobile/scripts/dump_nav_graph.py` 重生成 JSON(代码派生不漂)。
- **审计回归**:接 product-pipeline S8 —— 每加页/改导航后重跑,对比孤儿/死胡同/超级抽屉出边数,新增不可达即 finding。
- **死组件哨兵**(待加):扫"定义了 `router.push` 但无屏 import 的入口组件" → 列死代码债。
- **设计保真**:跨端视觉用 `sim-build.sh`(Rokid 排除)+ cliclick 点遍 + simctl 截图(本轮已通)。
