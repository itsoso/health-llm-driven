# Harness 交付诊断与恢复索引

last-reviewed: 2026-10-10

这些工具为当前 Dossier/run 提供索引与测量，不建立第二套发布状态。发布许可与
恢复依据仍是原始受保护回执、精确 SHA CI 及 `docs/governance/deploy.md`。

## 本地环境

```bash
python3 scripts/harness_environment_doctor.py --profile ci
```

只检查工具是否存在及固定 Python 3.12 版本，不安装、不认证、不联网。解释器在
`.venv/bin/python3.12` 而不在 PATH 时会明确指出；可以显式调用它，或在当前命令
中加入 `.venv/bin`。`ready` 仅指工具可用，不证明依赖、签名或发布 Gate 已通过。

## 交付证据关联

在现有 run 上追加，不为每次恢复重新 init：

```bash
python3 scripts/harness_workflow_trace.py delivery \
  --run <existing-run.jsonl> --candidate-sha <full-sha> \
  --target ota --stage publish --status unknown --claim-state consumed \
  --ci-run-id <run-id> --ci-attempt 1 \
  --evidence docs/reviews/<original-receipt>.json
python3 scripts/harness_workflow_trace.py summary --run <existing-run.jsonl>
```

按实际证据补充 `--operation-id`、`--build-id`、`--update-id`、`--started-at`、
`--ended-at`。命令不读取或认证所引用的回执，记录始终为 `unverified_index_only`。
OTA 结果未知或 claim 已消费时建议检查原回执，不能生成新的 publish 或重放原 claim。
CI、预检、部署、上传、Apple processing、测试组可用和模拟器验收必须分别记录。
回执索引只存允许的标识和仓库相对路径，不写凭据、原始健康数据或供应商原输出。

## 真实 OTA 启动与 prepare

CI 的独立 `ota-runner-startup` 在 fresh Ubuntu runner 上复用发布 workflow 的目录
创建、Node 权限、依赖安装及补丁，再调用未修改 publisher 的真实 preflight/export/
制品验证。仅测试适配层明确省略 main-only 与循环 CI 准入；不带 Expo/SSH 凭据，
不执行 vendor 查询、claim、update。其 `TEST_EXPORT_VERIFIED` 不具发布授权效力。
该 job 失败会阻断 release-tests。真实 vendor 检查由当前精确绿色 SHA 的 trusted
OTA validate `--prepare` 执行；后端发布前提与一次性 publish 规则保持不变。

## CI 与发布耗时

导出 GitHub 的 run 元数据（包含 databaseId、workflowName、headSha、createdAt、
status、conclusion），每个 run 的完整 jobs API 响应保存为 `<run-id>.json`。
jobs 超过 API 一页时必须合并所有页并保留准确 total_count；截断输入会被拒绝。

```bash
python3 scripts/release_performance_report.py \
  --runs /tmp/runs.json --jobs-dir /tmp/jobs > /tmp/performance.json
```

报告按真实执行路径区分 preflight、backend、OTA admission/prepare/publish 和 native。
按 worker 数分组，首轮成功统计排除失败和重跑；保留重跑的完整墙钟，避免把用户等待
藏掉。不同版本、不同测试集合仍需人工确认可比性，样本分位数不能当成稳定性能承诺。
job/step 元数据能区分 native build claim、构建供应商步骤、upload claim 和上传步骤，
不能把供应商步骤的总时长擅自拆成 EAS 排队或 Apple processing；缺少独立证据时保留未知。

测试优化应先比较同一测试集合的多轮观测，保留进程隔离、真实 PostgreSQL/Redis、安全
审计与发布闸。不缓存测试成功状态，也不将当前仅用于测试的环境制品信任扩展到生产发布器。
