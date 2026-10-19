# 症状补充被误报为数据查询失败

| 字段 | 值 |
|---|---|
| 状态 | in_progress |
| 当前阶段 | 本地验证及独立安全审查 |
| 范围 | 症状补充的回答范围、工具权限及医疗输出缓冲 |

## 准入与根因

裁决：PASS。修复现有症状问答，不新增产品对象、接口、迁移或移动端行为。Router 为 quick_fix + safety；未加载禁用的 superpowers。System Map 局部 selector 未索引，完整 system-map-check 通过后核对真实源码和邻近测试。

当前输入建议只覆盖特定恢复问句等语法，未覆盖消化道症状及饭后疼痛时间的完整补充描述。该类文本被分类为含饮食词的模糊意图；模型提出的个人读取被权限网关拒绝后，没有当前输入回答范围证明，最终回复被未完成数据查询提示替换。本结论来自源码和合成回归，没有读取生产用户对话或健康数据，不宣称已取得截图那一轮的线上 trace。

## 实现与安全边界

- 增加有长度和子句数量上限的整句症状语法，覆盖嗳气、饭后相对时间、疼痛及排便描述；不删除未知附言来获得匹配。
- 复用 current-input 路由、个人背景隔离、工具筛选和 Gateway；仅允许通用知识查询，不授予健康数据读取或写入权限。
- 既有明确记录意图及症状自述写入契约优先；问题、查询病史、用药、他人、引用、假设及额外动作不被混同。
- 最终实现复用已有 current_input_local_advice 路径，普通及panel请求均返回服务器受审文字，不调用模型或读取私人背景。无危险征象时给症状追问和条件式就医警示；完整非否定输入已提及呕血、黑便或便血时优先给紧急就医提示。只选择固定文字，不插入模型、历史或客户端内容。
- 回复必须保存成功后才发布，复用 owner 隔离和幂等重放；旁路生成文本若不等于受审答案，已有 guard_current_input_answer 拒绝发布。保留流式医疗缓冲作为进入非本地路径时的额外保护。
- 就医警示参考 [NHS stomach ache](https://www.nhs.uk/symptoms/stomach-ache/)（2026-10-19查阅）；提示区分已描述危险征象和条件式警示。此为通用编辑依据，不是个人诊断或临床验证。

## 验证

- RED：15 failed / 18 passed，证明症状语法、Gateway、完成恢复和流缓冲缺口。日志 `/tmp/reva-symptom-red.log`。此前 Python 缺 pytest 及默认数据库未启动属于环境错误，不计行为证据。
- 初版关联回归142 passed；保留既有症状记录优先后，PostgreSQL第一轮37 passed。
- 扩展测试首轮453 passed / 1 failed，唯一失败为多模型夹具只替换流式provider，未替换panel provider；没有实际模型输出证据。补齐合成panel provider后，独立临时PostgreSQL专项41 passed，日志 `/tmp/reva-symptom-pg-verified.log`。覆盖真实Pi/Gateway、普通及panel入口、前轮失败、对话保存、幂等重放、截断和危险用药输出拒绝；未查真实健康数据。
- 分类与医疗边界888 passed，日志 `/tmp/reva-symptom-boundaries.log`。修正夹具后的完整关联回归454 passed（78.80秒），日志 `/tmp/reva-symptom-regression-final.log`，真实退出码0。
- System Map、差异空白、tracked-files秘密扫描和Dossier一致性检查通过，没有生成结构变化。无依赖、API、数据库结构、推送或移动端改动。专项临时PostgreSQL实例已正常停止。

## 发布边界

基线为1ba724dcb62ac389a72e41eecf40fea7aaca27e3。其GitHub CI39215378240和validate39216788903成功，只证明原基线。本次实现不包含在这些成功结果中。

同仓库“优化 README”任务仍活跃，正在处理原精确候选的发布凭据与staging；已只读核实，不接管、不重放、不更改原发布回执。本次先保留独立本地提交和审查证据。尚未执行本修复精确版本的完整CI/CI-mode、push、生产部署或模拟器验收。本次没有Mobile改动，不需单独OTA。

## G4 首轮 NO-GO 与修正

首版770a14d7b3dd31589728daa92a1a084f0dd2ec44独立审查NO-GO。审查者在普通及panel测试注入虚假确诊和错误安慰文字，两条链路仍complete并持久化，证明提示词和来源前缀不能作为安全验证。首版没有推送或部署。

新加9个失败用例复现任意诊断文本通过以及模型/背景仍会调用。随后改为上文的受审本地回答；相同能力已有睡前问答及日常安排使用，没有新建executor或接口。68项专项及既有本地回答测试通过；新增owner隔离和保存失败用例，完整关联及PostgreSQL验证重跑中。额外在health_evidence_runtime_enabled=True时禁用模型/Twin，确认本地回答先于临床提前分支；这不代表其他未匹配输入的功能开关路径通过。
