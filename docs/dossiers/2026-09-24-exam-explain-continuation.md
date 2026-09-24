# 体检解读返回与继续讨论回归

| 字段 | 值 |
| --- | --- |
| 当前阶段 | G3/G4 本地验证完成，未部署 |
| 状态 | building |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |
| Run | `docs/_generated/harness-runs/5b5be9f937ce.jsonl`（本地） |

## G1 / G2

裁决: PASS。修复既有体检解读页面返回主会话和只读继续解读能力，不增加自主诊断、
开药或健康记录写权限。主对象为既有体检记录和会话上下文，认证后端仍为数据真源。
用户截图中的“最近一周”读取拒绝一并核对既有修复，不扩大部署或发布权限。

## S5 范围

- Mobile：体检解读页面退出、主屏会话导航及上下文传递，先补失败测试。
- Backend：复现内置提示词被临床来源护栏误拦截，保留真实临床依据复合写操作的拒绝。
- 保留其他任务的前端发布恢复档案与 Android 构建现场，不修改生产健康数据。
- 外部 TDD/verification 能力未在本会话提供；使用仓库 RED/GREEN 与新鲜验证，
  不调用禁用的 superpowers。

## G3 / G4

- UI 根因：原页面仅成功时声明原生 header，加载/失败没有退出；讨论按钮 push
  主会话，保留上层 modal。改为固定页头覆盖各状态，并仅此入口 opt-in dismissTo，
  携带相同提示词、报告上下文、badge 和新会话参数。RED 6 failed/1 passed；
  三组 Mobile 回归 29 passed，TypeScript exit 0；未做模拟器原生验收。
- Backend 复现内置提示词为 `unresolved_clinician_action`：名词“复查安排”加
  “向医生确认的问题”误入动作拒绝。局部只读问诊问题准备分类不覆盖医生转述、
  临床依据变更或独立写动作；真实写权限仍由原 capability policy 裁决。
- 先测出现 5 failed/19 passed：四个只读用例失败；第五个是测试错误要求原有
  zero-tool clinician_context 必须命名为 ambiguous，修正为验证原零工具安全语义，
  未改变产品分类来迎合测试。组合回归 1719 passed，包含完整 run_stream 的
  上下文、输出与无写入回执验证，以及第三张截图“最近一周”的现有范围回归。
- 运行时测试使用受控模型 stub 和合成数据，不是实际模型医疗答案质量证明。
  没有 schema/API 变更，不把 SQLite 用作生产数据库语义证据。
- LLM change gate passed / live_required=false；结构、地图、秘密扫描通过。
  固定提交独立安全审查待执行；当前不宣称全部发布闸通过。

### 独立复审回退

固定 `017d2aa0e` 相对 `1bdd64af1` 的独立 G4 NO-GO：问题清单之后的命令式
“把复查安排在明天上午八点”和含零宽字符的修改命令可能被新只读例外接受。
写工具能力探针仍拒绝，不声称发生数据库越权；但丢失确定性零工具拒绝本身即阻断。
新增前缀/后缀反例先得到 6 failed/4 passed；修复将 deny-only 动作规范化扫描扩展到
所有分句，并把名词例外限制到医生对象之前、同一问题准备分句的明确列表位置。
需完整重跑与新固定提交复审，不沿用旧 GO。保留原 NO-GO 与失败证据。

首轮护栏覆盖率 97%（616 passed）；Ruff 最初报三处 import 排序问题，机械修复后通过。
本机有 iOS 26.5 模拟器，但默认 xcrun 指向 CommandLineTools；仅以局部
DEVELOPER_DIR 确认可用，未改全局配置。已安装应用不是本轮候选，未把它作为验收证明。

第二轮固定 `bbe5299a5` G4 仍为 NO-GO：同分句的“复查安排在明天”缺少名词终止
验证；跨换行的修改动作未被逐分句扫描捕获。新增反例 RED 7 failed/12 passed。
再修复采用仅拒绝用途的跨分句字母数字规范化检查，并要求“复查安排”后立即为
列表连接词/分隔符；原始同分句位置和写工具权限检查不变。新完整回归与复审待回读。

### 最终本地验证与审查

- 代码候选 `9bec52f4401685afc0d3200bd61df98475ff8ce8` 相对 `1bdd64af1`，
  指定六文件独立 G4 GO。审查者额外验证 650 个既有动作词前缀/后缀/混淆变体
  均维持拒绝或零工具上下文，4 个正常问题准备请求可继续解读，12 个模型提议写操作
  全部拒绝；独立 Backend 47 passed、Mobile 7 passed。
- 最终后端组合 1738 passed（`/tmp/reva-exam-review2-green.log`）；护栏覆盖率
  97%，635 passed（`/tmp/reva-exam-reviewed-coverage.log`）；Mobile 三组 29 passed，
  TypeScript exit 0。Ruff、结构/地图、秘密扫描与 diff 检查通过。
- 离线 LLM Gate invariants 12/12、health_agent_core 50/50、轨迹 12/12、goldens
  9/9；路径闸 live_required=false，没有伪造 live confirmation 或调用生产模型。
- 原始内置提示词及其安全声明未删除；只修复导航和确定性意图误判。
  “最近一周”截图原话在既有范围回归中通过，不证明线上目标 revision 已更新。
- 本次没有 push、后端部署、OTA、原生上传或生产用户数据操作；不复用其他线程
  发布权限。完整精确 CI、真实模拟器候选导航与发布后回答质量验收仍属后续 Gate。

## G5 / G6

未部署，未宣称线上或模拟器验收完成。

### 经授权的合并与发布续接

用户明确授权合并分叉代码、协调旧发布受控收尾，随后部署后端和 production OTA。
固定合并提交 `900ecdb20640edd4f47b3981226b98973be367de` 保留本地体检修复与远端
`3250d770f73146091ab4b86c05dba033e645ff27`；地图提示及其测试统一为远端已测试文案。
其他任务未提交的 frontend-publisher-recovery 档案保持原样，不纳入此次提交。

- 合并后 Backend 1917 passed；Mobile 35 passed；TypeScript、结构地图、秘密扫描通过。
- 体检增量独立 G4 GO：五个代码/测试文件与原受审候选同字节；独立 Backend 1738、
  Mobile 29、decision routing 10 均通过。另以合成 Laya provider 和真实 run_stream
  验证 decision_mode=on 的上下文、质量下限、无写回执/用药卡，1 passed。
- 恢复代码独立 G4 GO：固定 `3250d770f` 相对 `ba861b623` 的六文件在合并候选
  同字节；133 项恢复/安装器和 203 项 bootstrap/server 测试通过。此 GO 不等于
  生产证据匹配、发布或 PostgreSQL 业务验证通过。
- 生产只读检查仍为 `05b6e4d396084103975c43e4a5fc4d044d8e66da`，backend/worker/beat
  active、restart count 0。旧发布 lease 保留；未启动新的生产操作。
- 当前全量发布不变量测试与远端基线 CI 尚在运行；合并候选精确 CI 尚未触发。
  `run-all-tests.sh --ci` 不受该脚本支持（exit 2），不算验证；已改用 CI workflow
  中原样的 release-invariants 集成命令。没有关闭测试或放宽闸。
- OTA 本地历史锚点为 runtime 1.3.3，当前配置为 1.3.4；必须核对已分发原生候选，
  不以覆盖 runtime 或 OTA 推送替代原生权限/版本更新。
