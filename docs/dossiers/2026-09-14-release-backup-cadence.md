# Dossier: 发布备份分层策略

| 字段 | 值 |
|---|---|
| slug | `release-backup-cadence` |
| 日期 | 2026-09-14 |
| 状态 | implementation · focused verification in progress |
| 风险 | L3 健康数据恢复能力、发布前数据库保护 |

## Owner decision

用户接受建议的新策略：不再要求每次普通发布都重复上传站外加密备份，但不取消站外备份。
每次仍做本地备份和完整恢复演练；每日一次站外归档；普通发布只复用 24 小时内的已验证
凭证；数据库迁移发布必须同步上传。

## Gates

- G1 PASS：目标是降低普通发布阻塞时间，不改变数据保留和恢复目标。
- G2 PASS：现有备份、恢复、age/rclone、SHA/HMAC 和夜间任务均可复用。
- G3 IN PROGRESS：focused 脚本与发布事务测试执行中。
- G4 IN PROGRESS：凭证文件权限、篡改、过期、远端缺件和迁移 fail-closed 待复核。
- G5/G6 PENDING：未提交、未部署，不能把本地实现当作生产策略已生效。

## Implementation evidence

- `backup_db.sh` 新增显式 `upload|skip`，且只允许在 dump 和恢复演练之后决定站外步骤。
- 站外完整验证成功后写入 root-only 原子凭证。
- 发布脚本比较生产 SHA 与候选 SHA 的 managed migration 范围；不确定时按迁移处理。
- 普通发布先验证 24 小时凭证和远端三件套；失败会同步补做站外归档。
