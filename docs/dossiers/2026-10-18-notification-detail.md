# 推送详情与历史解读

- 当前阶段：S5 implementation；状态 in_progress。
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
- 独立安全审查待固定提交后执行；这些结果是本地/合成证据，不是真实设备或真实模型成功。

## 尚未解除的交付 Gate

- G3 live LLM：实际运行 `harness_llm_regression_gate.py --include-live-llm`，offline 12+50 用例与 trajectory checks 通过，但 live orchestrator 5 errored。环境缺少 TOKENPLAN/OpenAI 配置，回退被 `recipient_not_disclosed` 阻断。未绕过 consent/disclosure，未设置已通过确认变量或 waiver。
- 当前 GitHub OAuth scopes 新鲜只读回查为 `admin:public_key, gist, read:org, repo`，无 workflow；前置 GPS 提交修改 workflow，不能推送整批候选。未重试被拒发布或切换身份绕过。
- 模拟器：CUA 实际返回 Mac locked，已请求手动解锁；未进行界面验收，未用其他工具绕过。
- G5/G6：未 push/deploy/OTA，不能宣称用户截图问题已在线解决。完成局部审查后保留可恢复候选，待真实模型配置、workflow 授权和模拟器可用后续行；native runtime 兼容仍须按 GPS 候选发布条件核验。
