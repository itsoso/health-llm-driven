<!-- Mobile access map facet. Live route/edge/journey counts live only in docs/_generated/mobile-access-map.json. -->
---
doc: system-map/mobile-access-map
last-reviewed: 2026-06-27
generated-source: docs/_generated/mobile-access-map.json
mobile-runtime-source: mobile/constants/mobileAccessMap.generated.ts
generator: scripts/dump_mobile_access_map.py
---

# Mobile Access Map — 页面、动线、知识图谱

本文件说明 Mobile 访问地图的设计与读法。所有会随代码变化的事实,包括页面节点、导航边、设置入口、用户旅程、低曝光路由和评估信号,都以 [`docs/_generated/mobile-access-map.json`](../_generated/mobile-access-map.json) 为准;本文只保留产品判断和维护协议。

## 1. 为什么需要这张图

Reva Mobile 已经不是几个页面的 App,而是 Personal Health OS 的日常执行面。新增页面、卡片、设置入口和 deep link 如果只靠人工记忆维护,很快会出现三类问题:

- 用户不知道下一步该去哪,只能在设置页里找功能。
- Agent 改页面时不知道它属于哪个业务闭环,容易重复造入口。
- 页面还在,但从主路径不可见,形成低曝光或死入口。

Mobile Access Map 的目标是把“用户能怎么走”变成代码派生事实:每个页面是节点,每次可静态识别的跳转是边,核心产品任务是一条可评估的 journey。

## 2. 图谱结构

生成器把 Mobile 结构分成四层:

| 层 | 内容 | 真源 |
|---|---|---|
| `nodes` | `mobile/app/**/*.tsx` 页面节点,含 route id、文件、domain、surface role、一等对象映射 | Expo 文件路由 |
| `edges` | Tab、Stack、设置行、`router.push/replace`、`Link href` 的静态导航边 | Mobile 代码 |
| `journeys` | 面向用户任务的 canonical journey,例如日常执行、快速记录、报告导入、用药补剂、运动执行、系统透明化 | 生成器内的产品模型 |
| `evaluation` | 主 Tab 合理性、设置 Hub 密度、低曝光路由、重复入口、未解析静态边、重构建议 | 生成器评估规则 |

移动端运行时读取 `mobile/constants/mobileAccessMap.generated.ts`,因此系统地图页面可以展示同一份快照,无需在 App 里读 docs 文件。

## 3. 用户路线图

当前 canonical journeys 覆盖这些高频或高价值路径:

- **日常执行闭环**:打开 App,查看今日最高杠杆动作,进入任务执行、记录或私教解释,最后回到结果追踪。
- **快速记录闭环**:用记录 Tab、症状页、语音页和私教把饮食、运动、症状等输入转成结构化事件。
- **检查报告到医生回路**:从导入报告到化验列表、报告解释、健康咨询和医生回路。
- **用药补剂治理闭环**:围绕用药、补剂库存、多药梳理和提醒,完成安全与依从性治理。
- **运动计划到执行闭环**:从运动计划、动作指导、实时运动到历史复盘。
- **系统透明化闭环**:人或 agent 从 Mobile 查看系统地图、诊断和生成事实,再决定下一步改造。

新增 Mobile 页面时,必须挂到已有 journey,或在生成器里声明新的 journey;否则它只是孤立功能点,不应默认进入主导航。

## 4. 合理性评估原则

评估不是为了给页面打分,而是为了约束产品继续向 Health OS core loop 收敛:

- **主 Tab 要服务 core loop**:今日负责执行,私教负责解释与协同,记录负责捕获,我负责账户、设备和低频管理。
- **设置页不能继续膨胀成全功能目录**:设置 Hub 的密度风险由生成器计算;高密度时优先拆成报告/设备/计划/诊断等用户任务入口。
- **低曝光路由要被处理**:保留为 deep link、并入某个 journey、隐藏为开发诊断,或删除。
- **未解析静态边必须为零**:如果 `router.push` 指向代码中不存在的页面,drift check 应阻断。
- **每条用户动线都要回到一等对象**:HealthAgendaItem、ExecutionEvent、HealthTwin、SafetyGuardian、InterventionCycle、WriteIntent 等对象必须能解释这条路径为何存在。

## 5. 维护协议

- 改 `mobile/app` 路由、Tab、设置入口或静态跳转后,运行 `python scripts/dump_mobile_access_map.py`。
- 生成的 JSON 和 Mobile TS 快照必须一起提交。
- `scripts/check_doc_drift.py` 会比对 committed 快照与代码;不一致即红。
- 叙事层只更新本文件的产品判断和 `last-reviewed`,不要手写 live 数字。
