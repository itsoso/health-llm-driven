# 上车前往住宿地点被误作健康查询

| 字段 | 值 |
| --- | --- |
| 状态 | released_acceptance_partial |
| 当前阶段 | G5 同版本后端与 OTA 发布成功，G6 自动线上复验通过；设备实际聊天待验 |
| 工作流 | quick_fix + safety-gate → backend-deploy |
| 基线 | d43aa9dd6ae3886ed19ff7215ad01f26c62911f6 |

## 问题与范围

截图最新消息“上车了 往酒店方向”是出行状态，却收到“本轮数据查询未完成”。
源码复现表明，该表达未被非写入背景状态解析器覆盖，会进入普通模型路径；
模型提出无关个人查询后，未解析读取的终态通知能够替换聊天回答。
本次没有读取生产聊天正文或健康记录，不将源码路径复现冒称生产trace调查。

只补充完整的已上车状态加固定住宿目的地（酒店、宾馆、民宿、住处）。
必须有上车完成标记；不接受任意地点槽、问题、假设、引用、第三人称、
未来计划、记录/查询/提醒附加请求或症状。共享意图仍为chat/context/none。
回复只回应用户自述，不推断抵达、地点、车程、司机或健康状态，不保存健康记录。

在已有owner校验的对话内，每条近期用户历史仍须正向证明为既有背景、普通餐次、
有回执闭合行程或本次新增的完整接站/摆渡事实。新增接站事实仅用于历史证明，
没有开放当前消息本地回复或工具权限。助手回复也须全文匹配来源绑定的有限闭合
旅行总结/下次建议；finalized与complete/failed元数据仅作辅助，不能单独证明闭合。
未知医疗历史、未知助手续问继续普通路径。所有近期pending/draft/uncertain写入状态
均阻止本地回复，不能用较旧assistant给之后未回答的user背书。旧失败不改为成功。

复用已授权隔离worktree；共享dirty main未改动。无Mobile、原生、数据库schema、
API契约或健康查询授权变化，因此首轮只发布后端；后续用户明确追加OTA的结果见末节。

## G3 验证

- 原实现：新增用例9 failed / 26 passed，覆盖解析和mobile/typed/mac真实流式入口。
- 旧失败回合新增回归先RED：3 failed / 38 passed；修正后通过。
- 相关合跑：4507 passed / 1 skipped，覆盖背景陈述、登机口、行程记录、pending choice、
  turn/write recovery、capability policy、health semantics与utterance classifier。
- 首轮定向44 passed；验证不调用模型或健康工具、无写入回执、
  流式与持久化文本一致、重放不重复、跨用户对话拒绝和读取权限不扩大。
- 测试数据均为合成用户与内存SQLite。无数据库查询/约束变化；完整目标CI仍须核验。
- 首次合跑误列不存在的test_agent_recovery_flow.py，collection退出4，未算通过；
  改为真实turn/write recovery测试后取得上述结果。
- System Map首次因PATH缺python3.12退出2；使用现有3.12环境重跑通过。
  秘密扫描通过；无架构生成物漂移。

## G4–G6

修订候选92b0f24b270198aa7ec107c369e18658292320a8已独立G4 GO并推送main。
独立复核198项测试、30个对抗负例及正向配对通过。
精确完整CI [41320719438](https://github.com/itsoso/health-llm-driven/actions/runs/41320719438) 32/32通过；
发布预检 [41321735100](https://github.com/itsoso/health-llm-driven/actions/runs/41321735100) 通过。
最终候选相对基线的真实模型评测需求判定闸PASS，live_llm_required=False、confirmed=False、waived=False；
未将旧候选模型结果充当新候选验证，也未设置确认或豁免。
后端 [41323179145](https://github.com/itsoso/health-llm-driven/actions/runs/41323179145) 成功。
生产完成回执为92b0f24b270198aa7ec107c369e18658292320a8 / SUCCEEDED，
原始回执SHA256为e0d8973339f27f02b42d4bc727d979453a135ce0c92c8fa80c8e772e67094c91。
独立只读复验确认生产clean HEAD为该候选、授权与executor匹配、业务lease已释放，
health-backend、celery-worker、celery-beat、reva-laya均active/running，内外健康接口healthy。
首轮未新增OTA：该轮无Mobile变化，现有App使用新后端；后续明确追加OTA见末节。
模拟器和用户设备实际聊天尚未验证，不将本地合成场景等同线上用户验收。


## 首轮独立审查 NO-GO 与整改

固定78ec5b676被拒绝：负面症状词表漏掉鼻子持续流血、快要晕倒等近期医疗内容；
“把你现在的位置发给我。”没有问号也被当作闭合。独立真实流式探针确认绕过普通
路径，而不是只测辅助函数。该NO-GO时未发布；随后与整改提交一同推送，唯一发布候选为修订后的92b0。

撤销整个负向历史放行分支，恢复逐条正向user证明；增加来源绑定的完整接站事实
及有限assistant闭合回复匹配。原agent_executor变更完全撤回。补充未知医疗、
未知追问、错误航班、附加请求、被较新回复遮住的pending和未答user用例。
初版78ec真实合成模型闸exit0仅是被否决候选的历史证据，不当作修订候选GO。

修订后相关回归4522 passed / 1 skipped（39.26秒）；System Map、Dossier一致性与diff检查通过。

## 发布操作证据

仅对固定候选执行一次stage、短期只读凭据更新、授权切换与backend发布；
每步分别独立GO后执行，未备份、未重试未知操作、未读取用户原始健康或聊天数据。

- Stage完成回执原始SHA256：b6fc8f0e8f661f4cfe06c70310faf5bb787e4d8c7b4928ea9abfa49f9111ac88。
- 凭据更新审计attempt：ride-progress-92b0f24b-read-credential-v1；
  完成回执原始SHA256：a8d2cdf21df4099324cdb44bafec53b528ede4517fce9d695c7a83b5079f7ebb。
- 授权切换回执：INSTALLED92b0，退休旧53eec38b；这一步不等同后端部署成功。
- 本机独立线上证明：/private/tmp/reva-ride-progress-92b0f24b-backend-acceptance.json。
- 产品路径证据是合成真实流式入口回归；实际用户会话和模拟器交互未验，不能声称设备验收完成。

## 2026-11-02 用户明确追加发布与 OTA

用户在首轮后端完成后明确要求“搞定之后发布和OTA”。因此继续发布production iOS OTA，
不是将首轮仅后端结果冒称OTA。候选f2f52eaed38924e627ad191ff3f0ca1e34907e1f
相对92仅修改本Dossier；mobile/shared运行树与上一OTA53相同，明确记录为相同运行内容的追加发布。
按唯一入口要求对齐当前main、完整CI、后端成功回执，再以同SHA先validate后publish。

- 完整CI：[41324130866](https://github.com/itsoso/health-llm-driven/actions/runs/41324130866)，32/32通过。
- 后端预检：[41324928259](https://github.com/itsoso/health-llm-driven/actions/runs/41324928259)，成功。
- 后端部署：[41326551895](https://github.com/itsoso/health-llm-driven/actions/runs/41326551895)，成功。
- OTA验证：[41324953445](https://github.com/itsoso/health-llm-driven/actions/runs/41324953445)，成功。
- OTA发布：[41327050059](https://github.com/itsoso/health-llm-driven/actions/runs/41327050059)，成功。
- backend completed原始SHA256：d3fc648b1c3853ded5d574662791bd130b2e2b9cda8d4c23f29b83d937b455a3。
- OTA completed原始SHA256：c24345c100ea2dc2798d0669250ecfa91369ad30493d8c5c077f9f63494a8abf。
- OTA verified原始SHA256：cad1f144e11ac192a922a85f6c6dfb6586266fae1c0385772090cd145167a550。
- production iOS runtime：1.3.6；group：002b9e3c-af67-45d1-837c-7fc45d6f7e38；
  update：01a197fc-29c4-7fee-85f8-0927663573ff。
- 公开manifest创建时间：2026-11-01T16:40:47.812Z；
  launch hash：4viQ983bfb4Yl60ajYrTwOlfX6kWXIwOlyYOjIny9cE；47项资源匹配。

每步固定脚本分别独立GO后单次执行；stage回执79c2f64cdc358332aa78fbd9c100b5ebb579175d6856951f3e73d8869a85c216，
凭据审计ride-ota-f2f52eae-read-credential-v1完成回执b2d7307a534b822692fbefa59e0f422114a9cd84bcf8a5ee9420034be0cad238。
明确证明旧92后端成功但未启动OTA且无build.lock，单独保留最后已发布53的OTA原回执；未虚构92 OTA。
未备份、未重试发布、未读取用户原始健康/聊天数据。GitHub只读查询曾TLS超时，
经连接器查询和服务器原回执确认部署完成，未重发任何生产操作。

独立只读复验确认生产clean f2、授权/executor匹配、四服务active/running、
内外健康接口healthy、业务lease释放；OTA原始回执和公开manifest中的bundle/asset hashes与发布产物证明一致；
未重新下载全部47项资源字节。
本机证据为/private/tmp/reva-ride-ota-f2f52eae-backend-acceptance.json、
同前缀ota-acceptance.server-proof.json与ota-acceptance.public-manifest-proof.json。
实际设备安装/接收更新及原用户聊天交互仍未实测，自动线上证据不能替代设备验收。
