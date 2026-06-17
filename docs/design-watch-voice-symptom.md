# 设计 · 王牌⑤ 腕上语音记症状 → SafetyGuardian 确定性裁决

日期: 2026-06-17 · 来源: [apple-watch-health-opportunities-roadmap.md](plans/2026-06-16-apple-watch-health-opportunities-roadmap.md) §5 王牌⑤

> 标准流程: 系统设计(本文)→ 测试先行(TDD)→ **严格安全审核(blocking,本刀全场安全 stakes 最高)** → 发布。后端本地 TDD + 部署;watch 语音 UI 走 EAS 异步。

## 四问

- **做什么**: 腕上一句话报症状(「胸口闷」「反酸」)→ 落 `SymptomEntry` 进时间线 → SafetyGuardian 确定性规则即时裁决(急症红线 + 个性化红线)→ 返回分级 + 就医动作。
- **为什么**: 对长期 PPI + 胃溃疡(HP-)+ 心血管风险锚点用户,瞬时主诉抬腕一句比掏手机打字摩擦低一个量级;症状文本进时间线成锚点,与用药/饮食/睡眠纵向关联(反酸×晚餐×PPI 依从)= 个人因果账本高价值边。
- **谁用**: 腕上锚点用户。watch 经 iPhone 中继携 token;后端从 token 取 user_id。
- **边界(不做)**: 腕上**不诊断、不解读、不开方**(R4);只搬运确定性规则裁决,分级措辞,critical → 引导就医。语音转文字在 watch 端(speech)。本刀**不做** symptom_micro_logs 新表(复用 SymptomEntry)、不做症状结构化分级 UI(那是 🟡 症状微日志)。

## 数据流

```
Watch 语音「胸口闷」→ speech-to-text
   ▼  iPhone WatchPhoneBridge(白名单加 /watch/symptoms POST)+ token
POST /api/v1/watch/symptoms { text }
   │  token→user_id
   ├─① 持久化: SymptomEntry(user_id, description=text, occurred_at=now, source="apple_watch", body_part 安全默认)  → flush
   ├─② 评估(禁 build_twin): t = HealthTwin(meta=...); t.acute.symptom_texts_all=[text]
   │         builder._fill_problem_red_lines(db, user_id, t, set())   ← 个性化红线(传 request db)
   │         alerts = evaluate_rules(t)   ← 极简 twin 上只有 symptoms.py + problem_red_lines.py 命中
   ├─③ 审计: SafetyGuardian 评估旁路审计(失败不影响主流程,不存原文)
   └─④ commit(一次性)→ 返回 { symptom_id, alerts:[{severity, title, action, citation}], evaluation_failed?, message }
   ▼
Watch: critical → 强震 + 「可能需要就医」+ 动作;非 critical → 轻提示;evaluation_failed → 「评估未完成,必要时就医」非绿灯
```

## 契约

**端点**: `POST /api/v1/watch/symptoms`
- 鉴权 `get_current_user_required`;user_id 取自 token。
- body `{ "text": str }`;空/超长(>500)→ 400(fail loud,不静默记空症状)。
- 持久化 `SymptomEntry`(先核对真实必填列;`body_part` 必填给安全默认 `"general"`;`occurred_at` 列名;`severity` **不臆造**留 None)。
- 评估**只在请求 db 内**:`HealthTwin(meta=...)` + `acute.symptom_texts_all=[text]` + `_fill_problem_red_lines(db, user_id, t, set())`;**严禁 `build_twin`**(自开 SessionLocal,看不到刚 flush 的症状 + 缺列 psycopg2 红 —— 见 [[project_build_twin_sessionlocal_ignores_db]])。
- `evaluate_rules(t)` 在极简 twin 上跑:其它分区空 → 各规则 early-return None,只 symptoms.py(5 急症)+ problem_red_lines.py 可能命中。
- 返回 `{ symptom_id, alerts: [ {severity, title, action, data_citation} ], evaluation_failed?, message }`,severity 降序;无命中 → `alerts:[]` + 中性确认。

**WatchPhoneBridge 白名单**: 加 `/watch/symptoms` POST(精确,非通配)。

## 不变量(安全 · reviewer 核对,本刀最高优先)

1. **R4 不诊断**: 措辞「**可能**需要就医 / 建议就医沟通」,非「确诊」「你患了 X」;critical 给**就医动作**不给诊断结论。
2. **critical 真命中才强震**: CRITICAL 仅来自 symptoms.py 真命中急症关键词或 P0/P1 problem red line;普通不适不得升 critical(R15)。
3. **不漏报(under-alarm 是医疗危险)**: 症状持久化**与**评估都必须发生;评估抛错不能吞成「已记录无告警」——置 `evaluation_failed`,症状仍落库,返回明确就医引导,**绝不静默当安全**。参 [[feedback_safety_dedup_additive_not_subtractive]]。
4. **请求内禁 build_twin**: HealthTwin() + `_fill_problem_red_lines(db,...)`(确认 helper 用传入 db、只填 red_lines、不自开 session)。
5. **user_id 边界**: SymptomEntry 与 red_lines 查询都按 token user_id;不信任客户端。
6. **隐私(症状=敏感)**: 审计/日志不存症状原文超必要(审计记 symptom_id/severity/命中规则)。
7. **幂等非强需求**: 同句快速双发落两条 SymptomEntry 可接受(时点事件);评估结果一致。

## 测试计划(TDD,先红后绿)

1. 心脏急症(acute_cardiac_event)→ CRITICAL + action 含就医、title 非诊断;落 1 条 SymptomEntry。
2. 急腹症(acute_abdomen)→ CRITICAL。 3. 卒中 FAST → CRITICAL。 4. 急性呼吸困难 → CRITICAL。
5. 普通不适 → alerts 空或非 critical,不误升。
6. 个性化红线(active HealthProblem P0,red_lines=[{condition,action}])命中 → CRITICAL + 红线 action。
7. **不漏报**: mock `evaluate_rules` 抛错 → `evaluation_failed:True` + 症状仍 committed + 就医 message,不返回「无告警=安全」。
8. 空/超长 → 400,不落空症状。 9. 无 token → 401。
10. **禁 build_twin**: 链路无 build_twin(AST);未提交 HealthProblem 经 request db 仍命中。
11. 措辞安全(critical 无「确诊/治愈/保证」,含「可能/建议/就医」);极简 twin evaluate 不崩;user_id 隔离。

## 范围与延后

**本刀(后端,本地 TDD + 部署)**: POST /watch/symptoms(持久化 + §9 评估 + 审计)+ bridge 白名单 + watch 语音屏(Swift,EAS 异步真机验)。

**延后**: symptom_micro_logs 结构化分级表(🟡)· 症状趋势叙事 · critical 家人通知(王牌④ 守护通道,需 entitlement)· 症状×用药×饮食关联面板(Web)。
