# 用药页本人查询与指定食物份量修正

| Field | Value |
| --- | --- |
| status | building |
| current_stage | G3 verification |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

## G1 Scope admission

PASS：修复已有用药页查询入口和餐食续接，不扩大用户数据权限、不推断服药完成、不将单项食物修正应用于整餐。

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

- 用药 SQLite 30 passed；PostgreSQL 29 passed，实例停止成功。覆盖产品原句经 Gateway、查询、完成证据、回复保存，单查/批查、空记录/在用列表无打卡、双重归属过滤、时区及篡改参数。
- 餐食 PostgreSQL 85 passed；包括单水饺修正、混合餐澄清、跨账号、绝对份量重复提交。协议测试历史消息夹具原来传入带时区时间到 naive UTC 字段，PG 会按会话时区转换并打乱历史顺序；统一夹具时间语义后完整通过，未跳过失败。
- 日志：/tmp/med-review-final-verified.log、/tmp/reva-medication-review-pg-verified.log、/tmp/reva-dumpling-pg-final4-tests.log、/tmp/reva-med-review-terminal-state.log。
- 阻断级 Ruff、System Map 生成与检查、dossier consistency、diff check 通过。
- 大范围组合回归运行中；G4 和候选绑定 CI 尚未完成，不将针对性通过替代这些闸。
