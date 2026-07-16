# Mobile Update Manifest

`scripts/mobile-ota.sh` 在 EAS 成功并校验 group ID 与 iOS update ID 后，写入本地 `.mobile-release-manifest.json`。该文件默认被 `.gitignore` 忽略，属于发布机上的运行证据，不是客户端远程配置。

## 字段

- `platform` / `channel` / `environment`: 发布路由。
- `runtime_version`: 当前 native runtime 版本。
- `group_id` / `update_id`: EAS 发布物身份。
- `active_group_id` / `active_update_id`: 当前 channel 已指向的已知发布物。
- `commit_sha`: 生成 bundle 的 Git 提交。
- `published_at`: 发布完成时间。
- `previous_known_good_group_id` / `previous_known_good_update_id`: 下一次人工回滚默认目标。
- `status`: `published` 或 `rolled_back`。

## 发布

```bash
./scripts/mobile-ota.sh production "message"
```

脚本要求发布结果同时包含 update group ID 和 iOS update ID，缺任一项不会写 anchor 或 manifest。

## 回滚

先演练：

```bash
./scripts/mobile-ota-rollback.sh production
```

确认后执行：

```bash
./scripts/mobile-ota-rollback.sh production --confirm
```

也可以显式指定已验证的 group/update 对：

```bash
./scripts/mobile-ota-rollback.sh production \
  --group <verified-group-id> \
  --update-id <verified-ios-update-id> \
  --confirm
```

回滚命令只调用 EAS `update:republish`，不修改 Git、数据库或医疗规则；成功后把 manifest 标记为 `rolled_back`，保留回滚前后的发布身份。

## 边界

- Manifest 不是健康数据，也不得写入健康正文、图片、药物、基因、报告或用户标识。
- 这是一期人工回滚，不自动依据崩溃循环或失败率回滚。
- 原生能力、权限、Watch 扩展和 runtime 不兼容变更仍必须走原生发版。
