# Prompt 优化上线验收记录

2026-10-04：已将 `a10e642cde189c9b414dc8d41346e22f088eaa0e` 发布到后端和 Web。两端均有成功回执，独立部署健康复核 G5 GO。G6 真实用户体验与生产性能仍待验收。

## 已交付行为

保留工具范围投影、历史去重、JSON 传输 CPU 优化、公共工具说明解析缓存、Laya 质量地板及 Markdown 流式显示改进。修复“复盘/总结”日期范围解析、batch 维度别名、读取异常收尾与参数修正后的回答交接。参数正确仍不代表数据成功；真实读取失败继续保存 failed/error，不重置修参上限。

写入工具说明精简保持否决；P1/P2 和参数传输实验未进入运行路径，报告复用保持 shadow。

## 验证与收益边界

- 最终 CI-mode 关联集成：1054 passed、2 skipped；PostgreSQL：71 passed；最终定向：165 passed。发布合同本地：2274 passed、15 个平台跳过；实际 Linux 隔离由精确主干 CI 覆盖。
- 固定合成真实模型配对：候选 6/6 契约及独立语义筛查通过，主干 5/6；标准 MiniMax 5/5。最终窄控制流差异有独立实际 provider/Pi 合成回放，不把它称为再次运行完整真实模型矩阵。
- 正常双调用样本输入 14614→12270，下降 **16.04%**；空数据 Max 下降 **16.49%**，空数据 Flash 因额外修参增加 **38.64%**。耗时有升有降，整体提速、统计非劣和生产 p95 未证实。

完整逐对耗时、API 用量、失败历史及源码摘要见[发布质量证据](2026-10-04-release-readiness.json)。

## 发布证明

| 项目 | 结果 |
| --- | --- |
| 精确 CI | [37204244154 attempt 1](https://github.com/itsoso/health-llm-driven/actions/runs/37204244154)、[37204525289 attempt 2](https://github.com/itsoso/health-llm-driven/actions/runs/37204525289) success |
| Trusted validate | [37205448925](https://github.com/itsoso/health-llm-driven/actions/runs/37205448925) success |
| Trusted backend | [37206256120](https://github.com/itsoso/health-llm-driven/actions/runs/37206256120) success；服务器 `SUCCEEDED` |
| Web operation | `1302b9e763454e829e5c7f1e25e98a45`；`FRONTEND_SUCCEEDED` |
| Frontend tree | `26b12bed72ee3aa7502d44dc4ef94ba66cc5b6d8` |
| 制品摘要 | `1b44e1a849d82d9eae93a54cc77a27c89c92306b05a0563c95932b40753489cf` |
| 健康检查 | 部署日志三次 60/60 PASS；四个服务 active/running、无自动重启 |
| 生产复验 | SHA 与 executor 摘要正确、tracked tree 干净、租约释放；Web 发布保持后端进程与配置 |
| 页面和 API | 内外网 privacy/connect 页面 200 且标识正确；应用公开 API health=200，未认证 stream=401，TLS 校验通过 |

第二个 CI 的第一次 attempt 因误读第一条 CI 的进度而多触发并取消；随后完成 attempt 2，满足所有当前 attempt 绿色。首次授权轮换在 intent 前被缺少 revoke/private-key 退休步骤阻断，按原协议补齐后成功，旧审计和锁均保留。数据库备份、恢复演练及站外归档按[现行默认](../governance/deploy.md)跳过；本次无 schema/迁移修改。

一次外部复验误用了旧资料中的 `health-api.executor.life`，本机 TLS 失败且服务器 DNS 不可解析。核对客户端源码后，对实际应用地址 `health.executor.life/api` 的验证通过；没有更改生产网络或降低 TLS 校验。历史失败探测与成功回执均保存在[机器可读证据](2026-10-04-prompt-deployment-verification.json)。

## 剩余验收与恢复

生产 smoke 未访问真实用户健康数据，也未执行已登录聊天。实际流式显示、回答保存、失败状态和用户感知延迟仍需真实使用路径验收，G6 尚未闭合。此项不影响已经完成的两端发布和 G5 部署健康结论。

旧后端 `a8853dea1207163aaa412974dddfbc050ce3eeea` 的成功/退休证据以及 Web 旧制品均保留。若发现回归，依据原操作回执走受控恢复；不要重放已消费的发布、换 operation ID 或清锁。未发布 Mobile OTA、原生包或 TestFlight。

发布后文档提交仅推送 `codex/reva-prompt-optimization`；main 和生产保留精确已验证的 a10e642c。后续工作从[现有 Dossier](../dossiers/2026-10-04-prompt-optimization-handoff.md)接续。
