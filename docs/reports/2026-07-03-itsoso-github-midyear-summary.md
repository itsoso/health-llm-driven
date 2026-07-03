# 2026 年中 GitHub 项目与提交总结

账号: `itsoso`
生成日期: 2026-07-03
统计窗口: 2026-01-01 至 2026-07-03
数据来源: GitHub CLI authenticated API (`gh repo list itsoso`, `repos/{owner}/{repo}/commits?author=itsoso`)

> 口径说明: 本报告按账号可见仓库、默认分支、`author=itsoso` 的 commit 统计；包含私有仓库，但不包含未合入默认分支的分支提交、未绑定到该 GitHub author 的本地提交、issue/PR 评论、review、release 和 Actions 工作量。因此它是“项目与默认分支代码活动总结”，不是 GitHub contribution graph 的严格复刻。

## 一句话总结

2026 年上半年，`itsoso` 的 GitHub 工作重心从“量化交易研究与自动化”逐步迁移到“AI Agent 驱动的个人系统产品化”，其中健康系统、量化系统、形象管理系统、教育/购物/社交自动化原型形成了清晰的产品组合。统计窗口内共扫描 41 个仓库，28 个仓库有提交，默认分支合计 1,855 次提交。

## 总体数据

| 指标 | 数值 |
|---|---:|
| 扫描仓库 | 41 |
| 活跃仓库 | 28 |
| 默认分支提交 | 1,855 |
| Public 提交 | 443 |
| Private 提交 | 1,412 |
| Public 仓库数 | 15 |
| GitHub 账号创建时间 | 2009-06-24 |

### 按月份

| 月份 | 提交数 | 主要特征 |
|---|---:|---|
| 2026-01 | 247 | 量化策略、本地记录系统、早期工具打底 |
| 2026-02 | 494 | 量化/交易系统高强度迭代，研究与回测密集推进 |
| 2026-03 | 426 | 自动化、社交/购物 agent、交易系统继续深化 |
| 2026-04 | 266 | 教育、知识库、agent 工具链和风格系统扩展 |
| 2026-05 | 225 | Style Executor、移动端、教育产品化推进 |
| 2026-06 | 196 | Health OS/Reva/阿衡进入高强度工程化阶段 |
| 2026-07 | 1 | 统计窗口仅覆盖 7 月初，不代表 7 月实际节奏 |

### 按语言

| 语言 | 提交数 | 解读 |
|---|---:|---|
| Python | 1,598 | 量化、后端、Agent、数据分析和服务编排的主语言 |
| TypeScript | 220 | Web、Mobile、React Native、Agent UI 和前端产品化 |
| HTML | 27 | 仪表盘和轻量 Web 控制面 |
| Go | 6 | 小型服务/实验 |
| CSS / Shell / Unknown | 4 | 原型、运维和少量未识别语言 |

### 按提交类型

| 类型/前缀 | 提交数 | 说明 |
|---|---:|---|
| `feat` | 473 | 新能力和新产品面最多 |
| `fix` | 232 | 快速修复和线上反馈闭环明显 |
| `docs` | 105 | 规划、架构、复盘和治理文档开始成体系 |
| `exp` | 72 | 实验性探索仍然活跃 |
| `feat(mobile)` | 50 | 移动端产品化成为重要方向 |

## 项目组合地图

| 方向 | 代表仓库 | 提交数 | 阶段判断 |
|---|---|---:|---|
| 量化与交易研究 | `macd-analysis-claude`, `crypto_quant`, `macd-analysis`, `crypto-trading-agent`, `quant_analysis`, `invest-chuan`, `eth-ops` | 1,228 | 从策略实验转向研究编排、回测、paper 运行和风险闸门 |
| 健康与个人运行时 | `health-llm-driven`, `ominime`, `life-executor-health` | 245 | 从健康记录/数据同步升级为 Health OS、动态 UI、可穿戴和多端闭环 |
| 形象/风格系统 | `style-executor`, `style-executor-mobile` | 131 | 从衣橱/推荐扩展到移动端、动态试穿视频和成本观测 |
| Agent 原型与工具 | `edu`, `claw_native_shopping`, `thomas-claw`, `techvoice`, `thomas-expect`, `proper-prompt`, `hire`, `ak-llm-knowlege-base`, `work_executor`, `self-evolve` | 235 | 多个垂直 agent 原型形成可复用方法论 |
| 其他专项 | `gun_train`, `security`, `chatkim`, `poker-llm`, `kwaishou-voice-prototype` | 16 | 兴趣/安全/交互方向的小规模实验 |

## 重点项目回顾

### 1. `macd-analysis-claude` - 量化研究主战场

提交数: 961
可见性: Private
主语言: Python
活跃月份: 2026-02 至 2026-06

这是上半年提交最多的仓库，承担了量化交易研究、策略验证、Theme Radar、反向套利、paper 监控和部署可复现等工作。提交记录显示项目经历了从单点策略到研究编排系统的升级:

- 加密板块热度、协同异动簇、CoinGecko 题材源等免费叙事流入能力。
- reverse-arb、DSR 门、funding/reverse-arb tooling 等策略工具。
- paper 监控、runner 纳入 git、部署脚本和 ops 修复。
- 多个 PR 合并，说明项目已经从一次性脚本进入持续迭代状态。

阶段判断: 已经不是“写策略脚本”，而是接近“量化研究操作系统”。下一步重点应是削减噪声、固定验证口径、把 paper-only 到 live 的闸门做成不可绕过的制度。

### 2. `health-llm-driven` - Health OS/阿衡核心产品

提交数: 206
可见性: Public
主语言: Python
描述: 大模型驱动的健康管理
活跃月份: 2026-05 至 2026-07

这个仓库是年中后段最重要的产品化方向。提交集中在 6 月，说明项目在上半年末进入密集建设期。代表性进展包括:

- Mobile、Mac、Rokid、Apple Health、动态卡片和多端体验建设。
- 基因解读、证据分级、PRS 正名、ALDH2 引用、actionability 与 evidence grade。
- fail-loud 安全路径、RLS 备份、spo2 测试、timeline 时区和 mobile typecheck 修复。
- 语音确认/跳过/等会接入 agenda completion loop。

阶段判断: 这是最接近长期产品愿景的项目，已经从“健康问答/记录”进入“个人健康运行时”的雏形。下一阶段应优先围绕 App Store 可发布版本、统一 UI、核心用户动线、HealthKit 自动同步、动态 UI 卡片和安全评估闭环收敛。

### 3. `crypto_quant` - 量化策略与回测基础设施

提交数: 207
可见性: Private
主语言: Python
活跃月份: 2026-01 至 2026-02

该项目在年初高强度推进，重点包括:

- Web 控制面板管理数据源开关。
- ETH 10m MACD divergence strategy design。
- backtest 性能优化、indicator 预计算和缓存。
- hot coin 风险过滤、peak drawdown exit、multi-timeframe data。

阶段判断: `crypto_quant` 更像量化研究的基础层，后续可以把成熟资产沉淀到 `macd-analysis-claude` 的研究编排/自动化运行体系里，避免两个量化主仓长期重复造轮子。

### 4. `style-executor` / `style-executor-mobile` - 个人形象管理产品化

合计提交数: 131
可见性: Private
主语言: Python / TypeScript
活跃月份: 2026-04 至 2026-05

这个方向已经形成“后端推荐 + 移动端 + 视频生成 + 成本观测”的产品闭环:

- V12 动态试穿视频，wan2.2/wan2.6 i2v flash。
- top-1 推荐自动生成 5 秒转身视频。
- 衣橱语义搜索、模板推荐、outfit embedding backfill。
- Mobile 端 VTON 试穿合成图、APNs 路由、微信分享视频修复。
- DashScope 成本 summary 和推荐链路观测。

阶段判断: 已经从个人工具进入“可演示产品”阶段。下一阶段适合做更清晰的用户动线和低成本生成策略，而不是继续无限扩展生成能力。

### 5. `edu` - Agent Native 教育产品

提交数: 45
可见性: Public
主语言: TypeScript
活跃月份: 2026-04 至 2026-05

主要进展:

- daily next-step learning flow。
- 课程日历、周末接送、单次调课。
- React Native MVP、bearer token auth、production shell。
- MathText/LaTeX 容错和推荐项渲染修复。

阶段判断: 这是“Agent Native 日常系统”的另一个垂直样本。它和健康项目共享同一类思想: 不是做静态管理页，而是围绕每日下一步行动组织体验。

### 6. `claw_native_shopping`, `thomas-claw`, `techvoice`, `thomas-expect`

合计提交数: 134
主语言: TypeScript / Python
活跃月份: 2026-03

这些仓库体现了上半年在“Agent + 浏览器/移动端自动化 + 业务仪表盘”方向的探索:

- 购物补货 web demo、OpenClaw shopping copilot extension MVP。
- 社交/直播互动自动化、Dashboard、记录看板。
- tenant lounge、反馈墙、ticketing foundations。
- 快手/抖音/小红书打开搜索、browse hot path 性能优化。

阶段判断: 这些项目更像能力试验田。最有价值的资产不是某个单点 app，而是“可观察、可恢复、可运营的 Agent 执行链路”方法论。

## 活跃仓库清单

| 仓库 | 可见性 | 语言 | 提交数 | 最后提交时间 | 描述 |
|---|---|---|---:|---|---|
| `macd-analysis-claude` | Private | Python | 961 | 2026-06-02 | 量化研究/交易自动化主仓 |
| `crypto_quant` | Private | Python | 207 | 2026-02-25 | 数字量化、策略和回测基础设施 |
| `health-llm-driven` | Public | Python | 206 | 2026-07-01 | 大模型驱动的健康管理 |
| `style-executor` | Private | Python | 87 | 2026-05-10 | 个人形象管理系统 |
| `edu` | Public | TypeScript | 45 | 2026-05-17 | Agent Native 教育产品 |
| `claw_native_shopping` | Public | TypeScript | 44 | 2026-03-26 | OpenClaw shopping copilot |
| `style-executor-mobile` | Private | TypeScript | 44 | 2026-05-10 | Style Executor mobile |
| `techvoice` | Public | TypeScript | 31 | 2026-03-14 | tenant lounge / public wall 等 |
| `thomas-claw` | Public | TypeScript | 30 | 2026-03-15 | 社交/直播互动 agent 原型 |
| `thomas-expect` | Public | Python | 29 | 2026-03-13 | 多平台浏览/搜索自动化性能优化 |
| `macd-analysis` | Private | HTML | 27 | 2026-03-15 | 早期量化策略和 dashboard |
| `ominime` | Public | Python | 22 | 2026-01-25 | 记录我的一切 |
| `self-evolve` | Private | Python | 17 | 2026-04-25 | 自我进化/agent 实验 |
| `life-executor-health` | Private | TypeScript | 17 | 2026-01-15 | life executor 健康模块 |
| `crypto-trading-agent` | Private | Python | 15 | 2026-04-07 | 加密交易 agent |
| `proper-prompt` | Public | Python | 12 | 2026-01-07 | 群聊 prompts 自动化评测 |
| `invest-chuan` | Private | Python | 11 | 2026-01-18 | 王川投资理念实现 |
| `hire` | Public | Python | 10 | 2026-03-17 | 招聘/人才相关工具 |
| `work_executor` | Private | TypeScript | 8 | 2026-04-07 | 工作执行系统 |
| `ak-llm-knowlege-base` | Public | Python | 7 | 2026-04-07 | AK/X 知识库分享 |
| `gun_train` | Public | Python | 6 | 2026-01-06 | 规范化枪械训练 |
| `chatkim` | Private | Go | 6 | 2026-02-01 | inside |
| `quant_analysis` | Private | Python | 6 | 2026-01-06 | 数字量化 |
| `openclaw-executor` | Private | Unknown | 2 | 2026-02-26 | OpenClaw 执行相关 |
| `poker-llm` | Private | Python | 2 | 2026-01-24 | Rokid glasses / poker LLM 实验 |
| `kwaishou-voice-prototype` | Public | CSS | 1 | 2026-04-16 | 短视频语音交互原型 |
| `eth-ops` | Private | Shell | 1 | 2026-03-07 | ETH 节点运维 |
| `security` | Private | TypeScript | 1 | 2026-02-25 | 人身/家庭资产安全 |

## 上半年工作模式观察

1. **从脚本到系统的迁移明显。**
   年初很多提交集中在量化回测、策略筛选、数据源控制；到 6 月，健康系统开始把后端、移动端、Mac、可穿戴、Agent、动态 UI、部署和测试闸门组合成完整产品系统。

2. **Agent Native 是横跨项目的核心方法。**
   健康、教育、购物、社交自动化、风格管理的共同点不是“有聊天框”，而是把用户目标拆成可执行的下一步、工具调用、状态回写和动态 UI。

3. **工程治理意识在增强。**
   提交里 `docs`, `fix`, `test`, `perf`, `deploy`, `gate`, `backup`, `RLS`, `typecheck` 等词频很高，说明开发不只是加功能，也在补安全、验证、部署和失败可见性。

4. **产品线较多，需要收敛主线。**
   28 个活跃仓库说明探索面很广，但长期要形成复利，需要把仓库分为: 主产品、能力库、实验田、归档项目。否则上下文和维护成本会吞掉迭代速度。

## 最有价值的资产

- **Health OS 产品雏形:** `health-llm-driven` 已具备长期主产品潜力。
- **量化研究操作系统:** `macd-analysis-claude` 积累了研究、回测、paper 运行和风控闸门。
- **Agent Native 产品方法论:** 从健康、教育、购物、社交自动化里抽象出“目标 -> 工具 -> 状态 -> 动态 UI -> 反馈”的通用框架。
- **多端工程经验:** Mobile、Mac、Web、后端、OTA、部署、CI、RLS、成本观测都已经有实践。
- **真实个人需求驱动:** 项目都来自健康、投资、学习、形象、记录、安全等长期个人系统，不是一次性 demo。

## 下半年建议

### 1. 明确三条主线

建议把下半年 GitHub 工作收敛为三条主线:

1. `health-llm-driven`: 作为主产品，目标是可日常使用、可上架、可长期运营的阿衡/Health OS。
2. `macd-analysis-claude`: 作为量化研究系统，严格保持 paper-only、安全闸门和可验证收益口径。
3. `style-executor`: 作为第二产品线或技术展示，沉淀动态生成、推荐和移动端体验。

其余项目按“能力复用 / 实验 / 暂停”标记状态。

### 2. 给每个活跃仓库补齐项目首页

每个主仓建议至少有:

- `README.md`: 目标、当前能力、运行方式、状态。
- `docs/ROADMAP.md`: 未来 4-8 周路线。
- `docs/ARCHITECTURE.md`: 系统结构和数据流。
- `CHANGELOG.md`: 用户可读更新。
- GitHub topics: 方便未来回顾和自动归类。

### 3. 建一个 GitHub 年度仪表盘

建议后续自动生成:

- 每周/每月 commit、PR、release、deploy 统计。
- 按项目线聚合的进展摘要。
- 大模型自动提取“本周用户可感知变化”。
- 主产品的测试、部署、线上健康度、移动 OTA 状态。

### 4. 主产品优先做“可发布版本”

对 `health-llm-driven`，下半年第一目标不是继续扩大能力边界，而是形成稳定可用版本:

- 统一 Mobile UI。
- 核心用户动线闭环: 今日 -> 阿衡 -> 记录 -> 我。
- HealthKit 自动同步。
- 饮食/运动/补剂/用药快速记录。
- 动态 UI 卡片稳定可交互。
- App Store 上架要求、安全边界、隐私说明和 demo account。

### 5. 保留探索，但减少上下文切换成本

探索是优势，但需要设置边界:

- 新实验默认有 1 页 spec 和停止条件。
- 连续 30 天无推进的实验进入 parked 状态。
- 能力成熟后迁入主产品或统一 skill/agent harness。
- 不再让每个 repo 都拥有一套不同的部署、测试和文档制度。

## 可用于对外的精简版总结

2026 年上半年，我围绕“AI Agent 驱动的个人系统”持续构建了一组产品和基础设施。GitHub 上 41 个可见仓库中有 28 个在半年内活跃，默认分支累计 1,855 次提交。工作重点覆盖四个方向: 个人健康操作系统、量化研究与交易自动化、个人形象管理、以及教育/购物/社交等垂直 Agent 原型。

其中，`health-llm-driven` 正在从健康记录工具升级为多端 Health OS，支持 Mobile/Mac/Web、可穿戴数据、动态 UI 卡片和安全评估闭环；`macd-analysis-claude` 则沉淀为量化研究操作系统，覆盖策略研究、回测、paper 运行和风险闸门；`style-executor` 形成了衣橱推荐、动态试穿视频和移动端体验闭环。整体上，上半年最大的变化是从“单点脚本和 demo”转向“可部署、可验证、可长期演进的个人系统产品”。

下半年应继续收敛到主产品，尤其是阿衡/Health OS 的可发布版本: 统一 UI、打通核心用户动线、强化 HealthKit 和动态卡片能力、完成 App Store 上架准备，并把其他项目里沉淀出的 Agent Native 方法论迁移进主产品。
