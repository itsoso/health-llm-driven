# 我的进度页面优化

| 字段 | 值 |
| --- | --- |
| 状态 | verifying |
| 当前阶段 | G3 回归及 G4 独立审查 |
| Controller | health-harness-orchestrator; safety-gate overlay |

## G1 准入

裁决: PASS

用户截图要求优化现有进度页，范围是执行回顾、指标观察和建议详情的信息层级、
空状态及错误比例。规格：docs/specs/2026-11-01-my-progress-clarity.md。
不新增健康写入或自主建议，不将指标相关变化宣称为 AI 导致的改善。

## 范围与基线

已授权的隔离 worktree 续用，基线 bd4a4f4f795f6ae25e6825a7adf35bcff0efd738。
共享 main 的其他未提交改动保持原样。源码确认 graded 与 completed 并非子集，
原页面有 0/0、2/0、零行动 0% 和不恰当因果文案；当前任务仅调整展示与读取边界。

## 验证及发布

- UI RED: 原页面 8 个行为用例失败；随后补前后记录完整性及专业复核提示 RED。
- Session RED: 原服务 10 个隔离用例失败，另补两个旧 refresh 回调失败用例。
- 新鲜定向 GREEN: 页面、结果颜色、session hook/service、既有 review 共 5 suites / 45 tests。
- TypeScript、设计 token、System Map / 导航与文档漂移检查通过；新增页面测试引起地图路由计数由生成器同步。
- CI=true 移动端全量主套件及四个状态隔离套件正在运行，最终结果待补。
- Simulator Release 构建正在进行；Mac 锁屏阻挡实际点击，未视为 UI 通过。
- 尚未 push/deploy/OTA；待独立 G4 和精确主干完整 CI。

## 展示及数据边界

本期行动、身体变化与建议进展分区；不把零分母变成零分，不使用 graded/completed
漏斗。前后记录必须完整、有限且至少两次；涨跌中性显示并保留观察性边界。
评估说明默认折叠，专业复核提示保持可见。保留周期切换、建议详情及周导航。
双区块刷新，失败按区块展示安全重试，不暴露原始错误。按 owner/consent revision/
auth generation/window 隔离读取，旧响应及旧 refresh 回调不可进入新会话。
