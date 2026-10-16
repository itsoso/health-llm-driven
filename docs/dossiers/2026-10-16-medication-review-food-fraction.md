# 用药页本人查询与指定食物份量修正

| Field | Value |
| --- | --- |
| status | shipped |
| current_stage | G6 release verification |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

## G1 Scope admission

裁决: PASS。修复已有用药页查询入口和餐食续接，不扩大用户数据权限、不推断服药完成、不将单项食物修正应用于整餐。

## 验收输入

- 用药页内置“请基于我的在用药品列表，帮我整理今天的用药执行情况、可能需要向医生确认的问题、近期不适该如何描述。不要建议我自行停药、换药或改剂量。”被错误判定为非本人查询。
- 已记录餐食后“水饺吃了一半”未执行修正。
- 截图中已收到拒绝正文但状态栏仍显示处理中，核查终态投影。

## 实现边界

认证用户为唯一查询主体，今天按用户时区；药品列表不代表服用记录。指定水饺只允许修改可靠绑定的水饺份量，不得将混合餐整体减半；不确定时明确要求补充。

## 当前证据

两个独立实现任务已开始，先写失败测试。Harness run aa5c56720302。目标候选尚未冻结，G4、完整 CI、部署与 OTA 尚未完成。

- 根因：内置用药提问未被封闭查询范围识别，且日历查询适配器和完成证据投影均缺少该用药查询。仅修正主体判断不足以打通完整请求。
- 根因：续接份量语法仅识别不带食物名的整餐表述；指定水饺未绑定已完成餐食回执。
- 当前 Mobile 终态恢复专项 8 passed，覆盖 refused、blocked、failed 等终态恢复后清除处理中标签；尚无证据证明此截图存在新的状态机缺陷，不根据正文文字猜测终态。
- System Map 检查检测到新模块导致生成物漂移，候选冻结前重新生成并验证。
- LLM change gate 识别为高风险变更；真实模型评测按既有用户约束不执行，尚无候选绑定豁免，不将该检查记作通过。

## 发布约束

沿用本会话统一发布授权、不备份、不真实模型评测、不读取真实健康记录。保留其他会话改动。既有发布交接证据缺口未解决前，不启动并行发布，不重放旧候选发布步骤。

## G3 候选验证

裁决: PASS。最终 c2b6f8746 精确完整 CI 与本地 CI-mode 通过；以下保留历史修复过程。

- 用药 SQLite 30 passed；PostgreSQL 29 passed，实例停止成功。覆盖产品原句经 Gateway、查询、完成证据、回复保存，单查/批查、空记录/在用列表无打卡、双重归属过滤、时区及篡改参数。
- 餐食 PostgreSQL 85 passed；包括单水饺修正、混合餐澄清、跨账号、绝对份量重复提交。协议测试历史消息夹具原来传入带时区时间到 naive UTC 字段，PG 会按会话时区转换并打乱历史顺序；统一夹具时间语义后完整通过，未跳过失败。
- 日志：/tmp/med-review-final-verified.log、/tmp/reva-medication-review-pg-verified.log、/tmp/reva-dumpling-pg-final4-tests.log、/tmp/reva-med-review-terminal-state.log。
- 阻断级 Ruff、System Map 生成与检查、dossier consistency、diff check 通过。
- 大范围组合回归运行中；G4 和候选绑定 CI 尚未完成，不将针对性通过替代这些闸。
- 首轮本地 CI-mode 候选 84efd37d4 的 dossier 裁决格式检查失败；改为治理解析器要求的显式裁决格式。审查另发现混合餐澄清可能被最终通用失败文案覆盖，已退回实现；该候选的本地 CI 主动中止（退出 2），不作为绿色发布证据。
- 独立 G4 对 84efd37d4 正式 BLOCK，唯一项为上述终态覆盖。已补 food_component_unverified 标记；真实 stream 的两条混合餐 RED 均复现旧通用失败，修复后 SQLite 97 passed / 3 PG-only skipped、PostgreSQL 87 passed，验证保存后的澄清、零工具写入、零回执及原餐不变。新候选须重新 G4。

## 最终本地检查点

- 候选 c2752ba0b7005b345ffe9cc65e66b8e07a76a52b 独立 G4 GO，127 passed / 3 PG-only skipped；审查回执 /tmp/reva-med-review-fraction-g4-final.json。
- 本地精确候选 CI-mode 发布不变量 4018 项、0 errors、0 failures、23 skipped，dossier 两项检查通过，528.63 秒；不代替远端完整 CI 和 Linux 专属检查。
- 广范围组合回归 3583 passed / 1 failed：唯一失败来自运行时仍未修复的 raw-args 校验；后续最终 SQLite30/PG29 已复测通过，保留失败日志，不称该组合全绿。
- 11:22:30 UTC 只读核查：production b294，policy 与远端 main 为622170bb；外部 Web operation94c0e2210b5e3a44c09784ac6b9373bd 尚无可确认终态，publisher 归属/交接未知。无锁不等于交接。远端新增 CI 分片提交尚待整合，停止外部写入。
- 本次未 push、部署或发布 OTA。后续须确认旧发布终态及交接，再整合当前 main、绑定新候选审查与真实完整 CI，不能使用旧发布阶段脚本。
- 汇总回执：docs/reviews/2026-10-16-medication-review-food-fraction-release-receipt.json。

## 继续交付：主干整合

- 用户要求继续后，无冲突整合远端 622170bb，候选为 01afa5345ca58f03b216427ab246551898ea24b1。新增仅 CI 分片及其测试，应用运行树与已审 c275 相同。
- 上游精确 CI 38889146291 为 success；整合候选独立 G4 GO，分片测试 22 passed。候选本地 CI-mode 正在执行，结果路径 /tmp/reva-unified-merge-ci-result.json。
- 11:29:30 UTC 只读复核 production 仍 b294，policy622，各服务 active，无运行中事务或 launcher 锁；未获得外部 publisher 终态及交接。
- 发现相关 PR #284 修复 KBase 登录页发布校验；不能将 PR 描述当作 operation94c0 的终态或发布者交接。已请求原流程提供最终结果或会话名称。未 push、修改仓库变量、部署或发布 OTA。
- 此次合并没有原生依赖、权限或配置变化；后续 OTA 仍按当前 main 精确绿色 SHA，后端完成后先 validate 再 publish。
- 整合候选本地 CI-mode 已结束：4018 项、0 failures、0 errors、23 skipped，dossier 检查均通过，517.05 秒，runner 退出 0。远端候选完整 CI 尚未启动；发布仍由外部流程终态/交接阻断。

## 最新 main 全量整合与发布准入

- 无冲突合入远端 513f4e4a2（PR284–286），候选 d8e4d64f4f7ff4903922bad6b1702404258e1331。保留本地待发布修复及无关未提交改动。
- 上游精确完整 CI38907175638 success；整合候选独立 G4 GO、214 项发布/认证回归通过，System Map 与移动导航图通过。完整本地 CI-mode 运行中。
- 15:11 UTC 新证据：94c0 仅已准备且未 claim，无 publication；后继 c140 已有 FINALIZED_NO_BACKUP_PUBLICATION 终态，当前 installed executor 的 Web/OTA 历史检查 PASS。KBase 配置 journal 为 CONFIGURATION_SUCCEEDED、pending=null；policy513f 与 installed/canonical 摘要一致。
- 独立复审确认后继完成证据结合用户统一发布授权可解除旧阻断，不是以无锁推断交接。不重放旧 stage/revoke/key/rotate。
- Mobile 原生配置、依赖及平台源码较已部署 b294 无变化；适用 OTA 仍需新候选精确完整 CI、同 SHA 后端发布、trusted-ota validate 与 publish。

- 推送前 main 前进至5b8f7c430（通知解锁后落地修复），首次 push 被 fast-forward 检查拒绝，无覆盖。再次无冲突整合为 c2b6f87469999f134bd1853274def9e0f4153f95。该增量9个Mobile文件，独立G4 GO、7 suites/52 tests通过、TypeScript通过；移动全量回归运行中。发布/后端CI源码较d8e4d64无变化。

- c2b6f8746 已推送 main；精确完整 CI38922978423 success。精确本地 CI-mode 4060项、0failures/0errors、23skipped；移动全量362suites/3740passed/1skipped。
- 新当前绑定 transport 独立GO，依次完成 canonical staging、旧513f授权撤销、旧私钥退役、新c2b6授权安装；各阶段退出0，有小型审计，无备份。后端可信工作流38926157732已触发，尚未宣称部署成功；OTA待后端。

## G4 最终整合安全审查

裁决: GO。c2b6f8746 整合通知修复通过独立审查；发布代码增量和新绑定 transport 分别独立 GO。

## G5 部署

裁决: PASS。精确 main c2b6f87469999f134bd1853274def9e0f4153f95 完整 CI38922978423 success。后端38926157732 success，生产 SUCCEEDED、运行态 COMMITTED 同 SHA，服务 active。

## G6 发布后核验

裁决: PASS。范围为本次发布交付：公网 healthy、新提醒接口未登录401、OTA validate38927046827及publish38927440294成功，服务器OTA SUCCEEDED并释放租约。

- OTA group: 85055500-5e6c-4852-87f5-a354f38f8088；iOS production。
- 当前发布汇总：`docs/reviews/2026-10-16-unified-main-release-receipt.json`。
- 未验证设备实际拉取、Face ID/相机硬件，也未读取真实健康记录或运行真实模型评测；不据此宣称拍照性能或真实模型效果已验证。
- 全过程无备份；保留其他会话工作树修改。历史阻断和失败记录保留，当前结果以本节及统一回执为准。
