# 分享生态 + 入口 Context 透传 — 阶段性规划

**起草日期**: 2026-05-14
**所属主线**: Agent Native 食物链 (Information → Action)
**当前状态**: L1 + Context (Phase 0) 已上线 (commit `fefbe65d`, OTA `94262909`)

---

## 北极星

> **WSCLA — Weekly Safe Closed-Loop Actions**: 每周用户在 Agent 对话里完成"建议 → 分享 / 下单 / 执行 → 反馈" 完整闭环的次数。

L1 解决"建议变信息产物可分享"；L2 解决"信息产物变行动"；Context 透传保证每次入口跳转 LLM 不丢前页态。

---

## 已完成 (Phase 0, 2026-05-14)

### L1 微信分享菜单卡 (走系统 Share API, 不引 native wechat SDK)

| 模块 | 实现 | 文件 |
|---|---|---|
| ChatBubble 通用分享 | 每条 AI 气泡 footer 加 🔊 + share icon, 点 share → `Share.share` 系统菜单 → 用户选微信/朋友圈/短信 | `mobile/components/chat/ChatBubble.tsx` |
| MenuShareCard 结构化菜单 | LLM 输出 fenced \`\`\`menu_share JSON 块 → 后端 `extract_inline_card_blocks` 解析 → SSE done 事件 cards 字段下发 → 前端卡片渲染 title+items+totals+shopping_list, 底部「分享给家人」按钮 | `mobile/components/chat/cards/MenuShareCard.tsx`, `backend/app/services/inline_cards.py`, `backend/app/services/agent_executor.py` (system prompt) |
| 文本清理 | sanitizeAiContent 剥掉 fenced menu_share JSON, 不让用户看到源码 | `ChatBubble.tsx` |

### 入口 Context 透传 (打通"看到方案 → 跟 Agent 深化")

| 模块 | 实现 | 文件 |
|---|---|---|
| 后端 schema | AgentRequest 加 `extra_context` (max 4000) | `backend/app/api/agent.py` |
| 后端注入 | run_stream 接 extra_context → 注入 system prompt "## 入口上下文" 段, 强约束 "不要重新生成, 在已展示条目上深化" | `agent_executor.py` |
| 前端 service | streamChat 加 extraContext 参数, body 字段 `extra_context` | `mobile/services/chat.ts` |
| 前端 hook | useChatEngine.sendMessage 加 sendOpts.extraContext | `mobile/hooks/useChatEngine.ts` |
| 前端 deeplink | chat tab 接受 `?context=` 参数, 自动 sendMessage | `mobile/app/(tabs)/chat.tsx` |
| SNP 详情页 | 「跟 Agent 详细聊」序列化 `{gene, genotype, section, items}` 进 context, 顺带 `badge` 提示用户 | `mobile/app/snp/[rsid].tsx` |

### 杂项收尾

- 阿衡 tab 用 `useFocusEffect` 进 tab 即 scrollToEnd 看最新消息
- 饮食记录页支持左滑编辑/删除 + 删除二次确认 (上一轮)
- 后端 `update_diet_record` 加 user 归属校验 (修了之前的越权 bug, 上一轮)

---

## Phase 1 — Context 透传扩展到所有入口 (1-2 天, 优先做)

### 目标

让所有"分析卡片 / 详情页 → 跟 Agent 详细聊" 的入口都带上当前页结构化上下文。不让 LLM 再猜一遍页面到底显示了什么。

### 入口清单

| 入口 | 当前 prompt | 需要加的 context schema |
|---|---|---|
| ✅ SNP 详情页 | 已完成 | gene, genotype, section, items |
| 饮食记录页 (diet.tsx) | 无 | date, total_calories, meals[{meal_type, food_items, calories}], 推荐目标 (TDEE/protein_target) |
| 睡眠详情页 (sleep) | 无 | date, sleep_score, duration_h, deep/rem/light/awake_min, HRV |
| 运动记录页 (workouts) | 无 | recent_workouts, ACWR, readiness_zone |
| Safety alert 详情 | 已有 prompt | alert_id, rule_name, severity, triggered_metrics |
| 体检报告页 (medical-exams) | 无 | exam_date, abnormal_items[{name, value, ref_range, flag}] |
| Twin 仪表盘 (assistant) | 无 | active_alerts, today_metrics_summary |

### 工程模式 (复制粘贴即可)

每个入口都按这 4 步：

```tsx
// 1. 序列化当前页态
const chatContext = JSON.stringify({
  from: 'diet/2026-05-14',           // 来源标识
  date: '2026-05-14',
  totals: { kcal: 1820, protein: 92 },
  meals: daily.meals.map(m => ({...})),
  ...
});

// 2. 预填问题 (用户视角)
const chatPrompt = `今天饮食结构怎么样? 蛋白够吗?`;

// 3. 跳转
router.push({
  pathname: '/(tabs)/chat',
  params: { prompt: chatPrompt, context: chatContext, badge: '基于今日饮食 3 餐' },
});
```

### 验收

- 用户从饮食页问"今天饮食结构怎么样" → LLM 不调用 `health_query`, 直接基于 context 里的 totals/meals 回答
- 顶部 banner 显示"基于今日饮食 3 餐"
- 节省一次 LLM tool call, 响应时间 -2~3s

### 任务拆分

- [ ] T1: 饮食页 (diet.tsx) "跟 Agent 详细聊今日饮食" 入口 + serialize
- [ ] T2: 睡眠详情页 (sleep / sleep-deep-analysis) 同上
- [ ] T3: 运动页 (workouts) 同上 — 待确认页面是否存在 mobile/ 实现
- [ ] T4: 体检报告页 (medical-exams) 同上
- [ ] T5: Twin 仪表盘 (今日 tab) "跟 Agent 聊整体" 入口
- [ ] T6 (P2): 抽 `mobile/utils/agentContext.ts` 提供 `pushChatWithContext({prompt, context, badge})` 一键接入函数, 现有所有入口迁移过去

---

## Phase 2 — L2 一键下单 (1-2 周, L1 上线灰度看反应再启动)

### 目标

把"推荐 → 行动" 摩擦从 N 步压到 1 步: 用户看到菜单卡 → 点「去买」→ 跳美团/饿了么/叮咚等 App, 关键词预填好.

### 现实约束 (调研已完成上一轮)

- 美团/饿了么开放平台主要对商家, **不开放第三方 AI 下单**
- 现实可行: URL Scheme 跳搜索页, 关键词预填
  - `meituanwaimai://search?keyword=高蛋白沙拉` (已知可行)
  - `imeituan://www.meituan.com/take/search?keyword=...`
  - `eleme://search?keyword=...`
  - `dingdong://search?keyword=...` (叮咚, 待验证)
- 跳不上去 (App 没装) → fallback 网页 `https://h5.waimai.meituan.com/waimai/mindex/home?keyword=...`

### 设计

```
MenuShareCard 多一个底部按钮组:
  [ 📤 分享给家人 ]     [ 🛒 去买 ▾ ]
                                ├─ 美团外卖
                                ├─ 饿了么
                                └─ 叮咚买菜 (食材)
```

后端 LLM 生成菜单时 schema 加一个字段:

```jsonc
{
  "title": "今晚晚餐",
  "items": [...],
  // 新增
  "order_suggestions": {
    "delivery_keyword": "高蛋白低 GI 沙拉 30 元",      // 跳外卖搜索关键词
    "grocery_keywords": ["鸡胸肉 200g", "糙米 1 杯"]   // 跳生鲜
  }
}
```

前端组件 `OrderActionSheet`:
- 检测 App 是否已装 (`Linking.canOpenURL`)
- 已装: 直接拉起对应 App 搜索页
- 没装: 拉起 Web fallback

### 价值 + 风险

| ✅ 价值 | ⚠️ 风险 |
|---|---|
| 用户从看到建议到下单 3 步 → 1 步 | 美团 URL Scheme 不在公开文档, 可能被改 |
| 不需要美团/饿了么合作, 走系统 deeplink 即可 | iOS 用户拒绝跳转: `Linking.openURL` 弹一个授权确认弹窗 |
| 用户营养目标 + AI 翻译成 "关键词 + 筛选" 是壁垒, 美团自己搜索做不出 | 跳过去搜索结果不一定 100% 匹配 (用户体验落差) |

### 任务拆分

- [ ] L2-1: 调研 + 沉淀 URL Scheme 表 `mobile/services/orderDeeplinks.ts` (含 fallback)
- [ ] L2-2: 后端 system prompt 在 menu_share 输出里多带 `order_suggestions` 字段
- [ ] L2-3: 后端 `_validate_menu_share` 加 order_suggestions schema 校验
- [ ] L2-4: 前端 MenuShareCard 加「去买」按钮 + 弹 ActionSheet
- [ ] L2-5: 埋点 — 哪个外卖 App 被点最多, 用户从分享卡到点击的转化率
- [ ] L2-6: 不引 native — 全部走 OTA-friendly

---

## Phase 3 — 闭环数据回流 (与 L2 并行, 持续 1 个月)

### 目标

WSCLA 北极星不是"分享 / 点击"次数, 是 **完整闭环**. 必须能验证用户真的吃了 / 真的执行了.

### 实现

- 用户分享了菜单卡 → 1 小时后推送提醒 "刚才那餐吃了吗? 记一下" → 点击进 health-record skill (走 voice-chat 接 journal intent)
- 点击「去买」按钮 → 静默写 `intervention_event` (用户跳了哪个 App, 哪个关键词)
- 24h 后比对 diet_record: 是否有匹配的饮食记录? → 闭环命中标记
- 每周 WSCLA 看板: `admin/wscla` 已存在 (上一轮 Phase 0 落地), 加分享/下单/闭环命中维度

### 任务拆分

- [ ] T1: `intervention_event` 表加 source `share` / `delivery_deeplink` 类型
- [ ] T2: MenuShareCard 分享 / 下单时静默写事件 (fire-and-forget)
- [ ] T3: 后端定时任务 (Celery beat) — 1h 后推送饮食打卡提醒
- [ ] T4: WSCLA 看板加分享 → 闭环命中转化率 funnel

---

## Phase 4 (暂不做) — Native 微信 SDK / IoT 厨电

| 不做 | 原因 |
|---|---|
| `react-native-wechat-lib` 自定义分享卡 | 破坏 OTA 反馈环 (20 min vs 秒级); 系统 Share API 已覆盖 80% 场景; 微信开放平台审核周期长 |
| 米家 / Aqara 智能厨电 driver | 用户有完整智能厨房的 < 5%; 食材清洗切配 90% 工作量没解决; 演示好看实际使用率近 0 |
| 完整自营外卖供应链 | 公司是医疗健康 SaaS, 不是外卖平台; 跟存量玩家 (美团/盒马) 拼资金/物流是死路 |

如果 WSCLA 半年内做到 5+/week 且用户基数 1k+, 再回头看 Phase 4 是否必要.

---

## 度量

| 指标 | 当前 | Phase 1 完成 | Phase 2 完成 | Phase 3 完成 |
|---|---|---|---|---|
| Context-aware 入口数 | 1 (SNP) | 6+ | 6+ | 6+ |
| 菜单卡分享次数 / 用户 / 周 | - (待埋点) | 测量基线 | +30% | +50% |
| 外卖深链点击率 (CTR) | 0 | 0 | 测量基线 | - |
| WSCLA (闭环命中 / 周) | 0 | 0 | - | 测量基线 |
| LLM tool call 平均次数 | ? | -1 (省 health_query) | -1 | -1 |

---

## 风险 & 决策

### 决策 1: 不引 native wechat SDK

**结论**: 不引. 走 RN `Share.share` 系统分享菜单.
**理由**: native SDK = 必须 EAS build (20min/次), 破坏 OTA 反馈环 (秒级). 用户从系统分享菜单选"微信" 体验已经够好.
**变更条件**: 用户量 1k+ 且数据证明系统分享转化率 < 30% (相对于自定义微信卡).

### 决策 2: 不在后端做规则化菜单生成

**结论**: 菜单生成走 LLM, 用 fenced JSON schema 约束输出. 不写 FuelStrategist 规则代码.
**理由**: 营养搭配组合爆炸, 规则代码维护不可持续; LLM + 几条 schema 约束已足够; FuelStrategist 仍管 macros 目标 / 缺口判断, 不管"具体做什么菜".

### 决策 3: extra_context 上限 4000 字符

**理由**: token 控制 + 防止入口端塞太多无关数据; 当前 SNP 序列化大约 800-1500 字符, 留充足 buffer.
**变更条件**: 实际 P95 > 3500 → 看 prompt token 占比是否影响成本.

### 决策 4: order_suggestions 不在 Phase 1 做

**理由**: L1 还没数据证明用户用分享卡. L2 复杂度比 L1 高 5×, 先收集 L1 反应 1-2 周再启动 L2.

---

## 下一步立即可做

1. **Phase 1 T1 (饮食页 context)** — 复用 SNP 的模式, 1 小时内能完成 + OTA
2. 配套 (可同 PR): 后端在 system prompt 「## 入口上下文」段加更多"当 context 提到 diet/sleep/workouts 时怎么用"的引导, 让 LLM 知道这些字段什么意思
3. 验完 L1 1-2 天分享次数 → 决定 L2 是否启动
