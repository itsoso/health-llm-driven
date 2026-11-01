# 本周血氧绘图授权与展示修复

| 字段 | 值 |
| --- | --- |
| 状态 | released_acceptance_partial |
| 当前阶段 | G5 后端与 OTA 成功；G6 自动线上核验通过，模拟器业务路径未验证 |
| 工作流 | quick_fix + safety-gate → backend-deploy + trusted OTA |
| 基线 | 23202c56a97014c6e42454562c1ed1e14e786d8d |

## 范围与根因

截图中的绘图请求被拒绝为未授权读取。使用合成请求与冻结时间复现：
“绘制本周血氧饱和度数据”命中 `health_query_not_requested`；换成查询动词后，
完整指标名仍命中 `longitudinal_read_scope_unresolved`。既有“查询本周血氧数据”通过。

- 只将完整的本人周范围血氧绘图请求投影为查询；绘制/画出不加入通用读取动词。
  原始文本边界在 scope 与 gateway 重验，防止下游删去附加条件后意外生成授权。
- 血氧领域完整消费“血氧饱和度”，仍保留未知筛选条件、第三人称、引述、假设、
  撤回、模型 owner/date/timezone 注入的阻断。
- 图表仅投影本轮成功执行、已绑定 owner 与精确日期的只读结果，不再查数据库，
  不使用旧图、不走默认半年窗口。模型滚动 days 提示被规范为用户本周的冻结日期。
- 现有 line_chart 契约展示日均血氧，缺失为 null，数值经统一展示格式化；
  结果窗口不符、越界/重复日期、非法数值、失败结果和不合格来源不生成图。
  无日均值不由采样或缺失值编造。保留采样与日汇总非睡眠连续监测的边界。
- Mobile 在缺失日期断线，孤立观测与单点仍可见。没有原生、API schema 或 DB 迁移变化。
- 复用已授权隔离 worktree，未修改共享 dirty main。

## G3 验证

- 授权 RED：原实现 2 failed / 1 passed，准确覆盖两种拒绝原因。
- 图表投影 RED：14 failed；Mobile 缺口/单点 RED：3 failed。
- 后端相关 CI-mode 合跑：3868 passed，SQLite 合成记录；真实 Pi 协议运行，
  仅模型输出替换为测试响应。覆盖 capability policy、共享语义、只读 scope、
  GenUI 表格/用药投影及图表防伪造回归。
- 新流式用例通过真实 gateway/dispatcher/reader：冻结周一至当前业务日，
  排除前周、未来日期与另一用户记录；客户端声明能力时只发一张图，无能力时不发。
- Mobile Node22：3 suites / 126 passed；TypeScript、ESLint、design tokens、
  System Map 与 diff check 通过。生成物已同步。
- 本机初始 Pi runtime 依赖缺失导致协议测试失败；按锁文件 npm ci 后重跑通过。
  不将缺依赖的失败解释为产品快速路由问题。
- SQLite 仅证明合成单元/协议行为；未改数据库查询语义，PostgreSQL 与完整 CI
  已由目标 SHA 完整线上 CI 验证。模拟器实际业务操作与设备接收仍未核验。

## G4–G6

固定 `53eec38b12ac4d543e4a45df73f58446acc7d82c` 独立安全审查 GO；后端与 OTA
已发布并完成自动线上核验，精确证据见文末。下列 NO-GO 是保留的历史整改记录，
不代表当前候选仍被阻断。模拟器真实业务点击与设备接收未验证，不宣称通过。


## 历史：首轮 G4 NO-GO 与整改

独立 reviewer 拒绝 f786fffd5：将绘制/画出加入共享动词表后，化验/病史等旧消费者
存在取消、完成、是否安全/会返回什么与未知筛选漏判。该轮当时未 push、未发布。
新增跨领域及 speech-act 测试在首轮实现 21 failed / 8 passed。

整改撤回通用动词新增，改为完整闭合的周范围血氧请求投影，其他领域保持原有语义。
附加条件、引述/代码块/缩进材料、假设、撤回不匹配；原始请求另在 scope/gateway
拒绝未闭合的周血氧绘图，避免下游移除叙述片段后制造投影。
定向 125 passed；完整合跑结果与固定复审 SHA 在复审后确认。


## 历史：第二轮 G4 NO-GO 与原文闸收紧

8a6fd1954 已修复首轮跨领域扩张，但独立审查发现原文中读取动词豁免可被引号、
行内代码、fenced/blockquote/缩进材料里的查询字样触发；NFKC 指标变体也未覆盖。
精确基线对照表明这是未封住的既有名义问句路径，不是8a6新增泄漏。
删除该豁免；原文识别与完整命令匹配统一NFKC，但不去掉材料/缩进/附加文字。

新增材料、单查/批量及Unicode反例后，定向188 passed，完整合跑3850 passed。
原始请求到gateway、DB读取、单张图及缺失值的流式验证仍通过。
该阶段固定提交尚待独立复审；当时此前两候选均未推送或部署。


## 历史：第三轮 G4 原文完整性补强

ca99aa268 的字面候选检查仍可被拆分动词/周范围的Markdown材料绕开。
精确基线同样存在旧fallback，未宣称是本补丁新增泄漏。拒绝候选识别改为同时检查
原文与既有材料/Markdown/HTML规范化结果；规范化结果仅能触发拒绝，授权仍要求
原始完整命令匹配。加入格式、引述、代码和HTML拆词的单查/批量反例。
定向206 passed，完整相关合跑3868 passed；随后固定53通过独立复审。


## 最终 G4 与完整 CI

裁决：GO。独立 reviewer 对固定53复验206项，并检查33个拒绝、归属与窗口探针。
四个修复提交一并非 force 推送至 main；共享脏工作区未改动。

- 真实 TokenPlan MiniMax-M2.5 Harness：invariants 12/12、health_agent_core 50/50、
  orchestrator 5/5（均分0.92）、trajectory 12/12、golden 9/9；exit0，63.44秒。
  只使用仓库合成夹具、真实合成主体同意审计与内存 SQLite；没有生产健康数据读写，
  未继承生产数据库或其他服务凭据。对应main baseline文件不存在，只声明本次场景
  通过，不声明历史质量无退化。
- 本地汇总 `/private/tmp/reva-weekly-spo2-53eec38b-live-eval-summary.json`；日志摘要
  `ef592cdbf71480f95c52315af98541ea7538afe6dca743467030bdb8d1407447`。
- [完整 CI 41309894568](https://github.com/itsoso/health-llm-driven/actions/runs/41309894568)
  首次因缺本候选真实模型确认失败，原失败保留。真实评测后精确绑定确认变量，
  恢复原失败jobs，最终32/32成功；包含PostgreSQL、运行时与发布不变量检查。
  未使用waiver，未取消失败记录制造绿色。发布后已删除本次确认变量并读回确认不存在。

## G5 发布终态

裁决：PASS。全部发布绑定 `53eec38b12ac4d543e4a45df73f58446acc7d82c`。

- [部署预检41311011964](https://github.com/itsoso/health-llm-driven/actions/runs/41311011964)
  success；独立固定审批后，canonical staging、只读App凭据刷新与canonical授权轮换
  分别单次完成，无备份、无回滚副本。旧852发布回执保留，轮换返回INSTALLED。
- [后端41312450217](https://github.com/itsoso/health-llm-driven/actions/runs/41312450217)
  success；生产原始完成回执为精确53/SUCCEEDED，SHA256
  `415ee0edc7d1eab40212f7f5525dd569c0179d9acc2bc9b183d50eadcc6f81b4`。
- [OTA验证41312928064](https://github.com/itsoso/health-llm-driven/actions/runs/41312928064)
  与[正式发布41313130895](https://github.com/itsoso/health-llm-driven/actions/runs/41313130895)
  均success；原生兼容边界通过，production/iOS/runtime1.3.6。
- OTA group `429c80f1-ddea-47b5-9eaf-cc54b3d3e233`，update
  `01a19765-556b-7c66-896a-0e972c8bb4d6`。服务端completed原始摘要
  `cc153bbe6f7884fe4e5b730027b75384769f866c140718598b7df1b8eb34d117`，
  verified原始摘要 `a2b10ccfe4b9e302d9f01d7e2879dfdac1dfa27cb9bbf69a2546df31991568a4`。

## G6 自动核验与未覆盖项

自动线上核验 PASS，设备业务验收未验证，不将二者混同。

- 独立只读核对生产HEAD精确53、工作树干净、发布授权/安装器一致、业务lease释放；
  health-backend、celery-worker、celery-beat、reva-laya全部active/running，
  本地与公共health均healthy。证据：
  `/private/tmp/reva-weekly-spo2-53eec38b-backend-acceptance.json`。
- 独立读取公开Expo清单并与服务端真实artifact/receipt对应：runtime1.3.6、上述update、
  launch `4viQ983bfb4Yl60ajYrTwOlfX6kWXIwOlyYOjIny9cE` 及47项资源匹配；
  公开创建时间2026-11-01T13:56:03.051Z，发布lease absent。证据：
  `/private/tmp/reva-weekly-spo2-53eec38b-ota-acceptance.server-proof.json` 与
  `/private/tmp/reva-weekly-spo2-53eec38b-ota-acceptance.public-manifest-proof.json`。
- 默认iOS模拟器已启动但安装的是旧候选，本次真实图表业务点击和设备收到更新
  未验证；没有操作手机或用旧包截图冒充新版本验收。未向生产账户发起健康查询。
