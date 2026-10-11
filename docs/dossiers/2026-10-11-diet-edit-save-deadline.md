# Dossier: 饮食修改保存等待上限

| 字段 | 值 |
|---|---|
| slug | diet-edit-save-deadline |
| 创建日期 | 2026-10-11 |
| 当前阶段 | G6 PASS，已部署并发布OTA |
| 状态 | shipped |
| 负责 | root |

## 用户证据与诊断

用户截图：饮食记录修改拌面从1盘到2盘，按钮停在“保存中…”。现有路径 await 旧营养回填，再调用原子重估接口；Axios默认30秒仅限制已发出的HTTP请求，无法限制之前的revision join及异步拦截器。后端原子重估使用同步文字模型估算，未传已有可选timeout_seconds。截图本身不能确认具体等待阶段；今日固定journal窗口无匹配接口完成或文字超时事件，也不能证明请求未发生。

## G1 准入

裁决: PASS。这是既有饮食人工编辑/确认路径的等待故障修复，保留健康观察、人工确认及写入回执边界；不增加健康建议或新数据用途。用户直接提供触发场景要求修复。

## G2 实现边界

裁决: PASS。复用现有原子重估、幂等和CAS；只增加客户端等待与取消边界，不以超时推断写入结果。

仅Mobile编辑保存路径新增覆盖全流程的35秒deadline及AbortSignal。旧回填晚到后先检查signal，禁止超时后才发送修正；已发出请求的晚到结果不得触发成功关闭或清除重试标识。原子重估和手动更新都传输signal，保留原CAS/幂等语义，不自动重发、不伪称未写入。超时恢复操作、保留修改，提示先核对记录再决定重试。等待时显示重新估算提示。没有改模型、营养推断、后端写入规则、接口schema或原生依赖。

## G3 验证

deadline测试先RED（缺少功能模块）后GREEN。新增屏幕回归覆盖用户“1盘→2盘”、永久pending、35秒恢复、传输abort、晚到结果及重试key；纯逻辑回归覆盖迟到revision join不得发送，以及成功/错误清理timer。五个Mobile suite43 passed，tsc exit0、System Map及diff-check通过。日志 `/tmp/reva-diet-edit-deadline-red.log`、`/tmp/reva-diet-edit-final.log`、`/tmp/reva-diet-edit-tsc-final.log`。未执行真实模型评测；无数据库变更。

## 交付边界

独立审查GO，后端部署、OTA发布及后台模拟器采用已验证。原始超时不等于服务端未写入；本轮不声称真实重估速度已改善或实际手机路径通过。默认后台模拟器验收；Mobile纯JS/TS候选满足闸后通过trusted OTA交付，发布阶段分别记录精确CI、后端部署、OTA及模拟器采用证据。

### 首轮审查阻断与修订（已解决）

首轮独立审查 NO-GO：deadline未绑定会话/卸载，旧等待及回调可能影响新编辑界面。修订绑定owner、token、consent revision、operation controller；订阅会话失效、切号及组件卸载，立即取消。join后、派发前及成功/错误/ finally前均验证当前操作；手动与原子请求携带subject/revision，服务端owner/CAS不变。会话取消静默结束旧操作，不向新会话展示旧错误；35秒超时保留重试key/修改及不确定文案。新增切号、同owner换token、consent失效、卸载的迟到join，以及新编辑界面中的旧响应回归。首轮审查日志 `/tmp/reva-diet-edit-independent-safety.log`；新增回归先RED `/tmp/reva-diet-session-red.log`。首轮修订随后进入新的独立复审。

修订验证：5 suites / 51 passed；tsc exit0，System Map与diff-check通过。日志 `/tmp/reva-diet-session-final3.log`、`/tmp/reva-diet-session-tsc3.log`。

复审期间补充同一记录保存中重复编辑防护（handleEdit锁），新增幂等重试key保留及正常成功关表单回归。先RED `/tmp/reva-diet-same-edit-red.log` 后GREEN；5 suites / 52 passed，tsc、地图、diff-check通过。日志 `/tmp/reva-diet-edit-final52.log`、`/tmp/reva-diet-edit-tsc52.log`。

### G4 最终审查

裁决: GO。

新的独立 reviewer 对 `e26c422b7..bd7a2a49b` 裁决GO，候选 `bd7a2a49bbc6617ac587503dff4e23715b850a25`。独立6 suites /81 tests、tsc、累计diff-check通过；隔离旧同记录重开RED、新候选GREEN，成功仍正常关表单。证据 `/tmp/reva-diet-edit-fresh-review-bd7.log`、`/tmp/reva-diet-edit-review-same-record-green.log`。锁定Axios1.20.0的独立干净候选tsc及52项相关测试通过，日志 `/tmp/reva-diet-edit-locked-final.log`。未执行真实模型或真实健康读写。

### G5 发布闸

裁决: PASS。

精确候选完整CI [38140131653](https://github.com/itsoso/health-llm-driven/actions/runs/38140131653)成功；本地CI-mode 3579 passed、22 skipped、84 subtests passed，退出0。运营wrapper独立GO，canonical stage、旧候选撤权、对应旧key销毁与新SHA轮换均成功，保留原launcher inode及业务锁。

后端 [38142151340](https://github.com/itsoso/health-llm-driven/actions/runs/38142151340) attempt1 SSH连接超时发生于claim前；原始失败回执保留。独立审查确认候选workspace、进程、意图及业务lease均不存在，canonical process及OTA历史证明通过，允许仅原workflow失败job恢复一次。attempt2成功，服务端持久回执SUCCEEDED，约346秒；生产工作树干净、SHA为候选，四项服务active，公开健康接口200/healthy，业务lease已释放。未重建workflow或重置已消费claim。

OTA validate [38143284886](https://github.com/itsoso/health-llm-driven/actions/runs/38143284886)成功，导出诊断PREPARATION_PASSED；随后仅单次publish [38143453237](https://github.com/itsoso/health-llm-driven/actions/runs/38143453237)，成功，workflow attempt1、vendor回读及服务端completed/verified一致，持久回执SUCCEEDED，业务lease释放。production/iOS/runtime1.3.5，group `2b3942a9-d1e9-4b27-920e-1d9b41d77dd8`，update `01a12b2c-e629-7401-9f70-df26289ced43`。

### G6 上线验证

裁决: PASS。后台iPhone17模拟器冷启动下载后再次启动，Expo本地数据库确认采用本次update，runtime1.3.5，successful_launch_count=1、failed_launch_count=0；截图检查登录页正常，证据 `/tmp/reva-diet-edit-simulator-proof.json`、`/tmp/reva-diet-edit-ota-simulator.png`。用户1盘改2盘、成功保存、永久等待35秒恢复、迟到join/响应、幂等key保留与会话切换由候选绑定回归证明。真实账号模型重估和真实手机操作未验证；按用户要求未运行真实模型评测，不将超时解释为服务端回滚，也不声称重估速度改善。

私有交付索引 `docs/reviews/2026-10-11-diet-edit-release-receipt.json` 保存原始失败attempt1及成功attempt2，完整CI、后端健康、OTA和模拟器分阶段记录；最终文档提交为代码候选后继，不再次触发无运行时代码变更的发布。
