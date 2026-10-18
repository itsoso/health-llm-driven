# 推送详情与历史解读

- 当前阶段：S5 verification；G3/G4 本地代码候选通过，G5/G6 待外部条件。
- 用户原话：“睡眠质量下滑等推送需要有一个landing页面点进去可以分析，现在无法点击。”
- 四问：对象为本人推送；场景为历史行和推送点击；结果为读原文并解读；不新增自动完成或处方。
- 父 trace：`docs/_generated/harness-runs/40a67f45f448.jsonl`。
- [Spec](../specs/2026-10-18-notification-detail.md) · [PRD](../prd/2026-10-18-notification-detail.md) · [Plan](../plans/2026-10-18-notification-detail.md)。

## S1 根因与 Gates

agent_loop 的 ai_advice 只映射营养/运动域；sleep domain 为空无 link，历史列表无 link 时 disabled。NotificationLog 可复用，但发送在创建日志前；旧趋势正文有提前截断。独立只读 discovery 确认这些路径。System Map 局部未索引，完整 system-map-check exit 0。

G1 PASS：用户明确要求这一产品行为；对应观察和解读核心循环，复用 HealthTwin / SafetyGuardian，无写自治提升。G2 PASS：最小范围和风险边界已纳入 Spec/Plan，无待拍板产品分叉；沿用用户“直接接管和发布”及 AGENTS 持续授权，不机械重复询问。G3/G4/G5/G6 待完成。

## 并发与发布断点

基线 HEAD `3e34b83697da80eef751c19768548021f451d07c`，main 比 origin/main `25b85536e3722dc111c528b8a915062a3f971397` 超前 5 个 GPS 候选提交；来源及 Gate 记录在 daily-gps-journey Dossier。既有未提交 benchmark、Dossier、回执不属于本任务。

GPS 候选已遇 GitHub OAuth workflow scope 不足；native runtime 变化不适合直接 OTA 到旧包。此处继续实现与可执行验证，发布前重新核验候选/凭据/CI/后端与运行时兼容。不开新备份，不 bypass 锁屏；不把本地通过写成发布或模拟器成功。

## S5 实现和新鲜验证

- 增加本人通知详情 API、移动落地页、ID-only 对话选择器；现有历史消息只做跳转投影，未改写日志。按用户隔离查询/缓存，加载、失败、无导航栈、跨账号切换均有组件覆盖。
- 推送前创建 pending 记录，通道完成更新同一行；延迟复用原记录。shared privacy choke point 保留应用内原文，渠道 payload 剔除 full_title/full_content，锁屏仍经过原隐私规则。
- 小巴只解读服务端重读的历史文本，公开知识可检索，其它个人读写在工具执行边界拒绝。标准解读问题被编辑时解除旧选择并走原健康流程。无记录时不调用模型、不换日期查询。
- RED：详情 API 404、历史点击禁用、客户端 multi_model 可进入无关历史路径、投递前无日志、原文进入渠道。对应测试先失败再实现。两次整批运行期间 delivery writer 仍在修改路由优先级，产生混合源码失败；冻结后重新整批执行，未把这些失败冒充成功。
- 冻结运行的 CI-mode 相关集成：412 passed（`/tmp/reva-notification-ci-mode-frozen.log`）。包括 notification/push 全套、Agent 安全/健康证据流程、所选报告兼容。
- PostgreSQL：本人详情/选择器/API 16 passed；独立 delivery/静默/去重 74 passed。旧 quiet-hours 测试用 naive 模拟真实 aware 时钟，PG 先失败；仅修正测试时钟与本地小时断言后通过，生产时间规则未改。
- Mobile：4 suites / 64 tests passed，TypeScript 与定向 ESLint exit 0；fatal Python Ruff、git diff-check、System Map/nav/doc drift 通过。API 类型生成器在锁定环境同步 Mobile/Web 生成物。
- 初始候选 `c24b8e211d2d84ee98ed51689d598fe2d582e094` 已提交；后续兼容性和真实模型发现见下节。测试使用合成数据，未修改真实用户通知。

## 尚未解除的交付 Gate

- G3 初始 live LLM 因测试环境缺少模型配置失败，保留 `recipient_not_disclosed` 证据；随后仅载入既有模型配置白名单、隔离内存数据库并使用正式合成同意流程，官方 gate 67/67 和 trajectories 通过。没有绕过 consent/disclosure 或使用 waiver。
- 当前 GitHub OAuth scopes 新鲜只读回查为 `admin:public_key, gist, read:org, repo`，无 workflow；前置 GPS 提交修改 workflow，不能推送整批候选。未重试被拒发布或切换身份绕过。
- 模拟器：CUA 实际返回 Mac locked，已请求手动解锁；未进行界面验收，未用其他工具绕过。
- G5/G6：未 push/deploy/OTA，不能宣称用户截图问题已在线解决。完成局部审查后保留可恢复候选，待 workflow 授权和模拟器可用后续行；native runtime 兼容仍须按 GPS 候选发布条件核验。

## G4 反馈与兼容修正

- 初次固定提交独立审查给出 GO，追加旧版 App 兼容审查后改判 NO-GO：服务端直接返回新增详情路由，会令尚未升级的 App 显示页面不存在。改用既有 history 路由携带 detailId；新版认证后一次跳转详情，旧版至少可打开历史。没有以初次 GO 覆盖后续发现。
- 桥接测试先 RED（Mobile 7 项、delivery 12 项），再 GREEN。保留 screen/运动/用药专属目的地；校验非法、数组、溢出 ID；覆盖登录、StrictMode、重复渲染、账号切换及迟到响应。Mobile 4 suites / 79 passed，tsc 与 ESLint 无错误。Delivery 聚焦 52 passed。
- 定向真实 Agent 使用合成旧睡眠推送、正式同意及真实供应商，完成回答且无写回执。首次测试缺少临时 HMAC key，修正隔离测试配置后通过；不使用生产密钥或数据库。实际回答暴露完整性误读和对空 sent_at 的投递猜测，已收窄证据投影并明确未知，不把本轮未截断等同完整原文。新增回归断言与最终真实模型复测。
- 最终冻结后相关 CI-mode 集成 414 passed（`/tmp/reva-notification-ci-mode-final.log`）；PostgreSQL 本人详情/选择器/API 28 passed（`/tmp/reva-notification-postgres-final.log`）。地图与导航生成物已同步，检查通过。
- 最终定向真实 Agent 复测完成：`/tmp/reva-notification-live-probe-final.log` exit 0，实际供应商调用 2 条 usage，turn complete / read_only=true、无写回执。人工核读回答明确“完整性未知”“保存时间不是采样时间”“投递状态未知”，未替换为今天的个人数据。样本为合成数据，不等同真实账户验收。

## 固定修正候选与交付断点

- 修正候选 `36cb449772811ade3e764982bf3fc4d6f0aa8363`；包含 history 兼容桥接及历史证据投影收窄。最终官方 live gate 67/67、trajectory contract 12/12、trajectory goldens 9/9 通过（`/tmp/reva-notification-live-gate-final.log`）；精确候选本地 LLM change gate 通过（`/tmp/reva-notification-llm-change-final.json`），未使用 waiver。仓库 CI confirmation 尚未写入，须在实际授权推送前绑定最终 SHA。
- GitHub 再次只读回查仍缺 workflow scope；整批 main 因前置 GPS workflow 变更无法推送。没有精确远端 CI，后端部署、OTA validate/publish 和原生分发均未执行。
- 前置 GPS 原生包为 1.3.6 (289)，仅在旧本地候选构建未上传；本次详情代码不在该旧包中。不能把该 IPA 或旧运行时 OTA 当成本次功能交付。
- 模拟器仍未获得解锁回复；没有 UI 点击/视觉验收结论。外部条件未解除前保留本地可审查候选，不声称已上线。
- 独立 G4 复审对 `36cb449772811ade3e764982bf3fc4d6f0aa8363` 裁决代码 GO：旧客户端 P2 已关闭，未发现新增阻断；检查增量源码、测试及真实 Agent 探针，没有宣称自行重跑整套测试。发布仍未获 GO，必须继续完成模拟器、精确远端 CI、原生运行时与实际分发证据。后续仅 Dossier 记录提交，不改变该受审功能字节。
