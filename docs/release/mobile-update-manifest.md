# Mobile Update Manifest

`scripts/mobile-ota.sh` 为每次发布创建私有临时事务目录。第一次 `eas update`
只在这个新目录中 bundle 一次；若上传发生明确的瞬时网络错误，脚本验证同一目录
的 iOS metadata、bundle、资源和 SHA-256 digest，再以 `--skip-bundler` 重试。
事务结束后目录删除，不做跨发布缓存。

脚本只有在以下事实同时成立后才原子写入
`.mobile-release-manifest.json` 和 production anchor：

- 工作输入的 HEAD、Git tree、runtime 和 Mobile/shared 工作树状态没有变化；
- export 只含 iOS，所有 metadata 引用均位于事务目录，且不存在空文件、软链接或路径穿越；
- 结构化 `eas update --json`、`eas update:view --json` 的 group/update/runtime/branch/commit 完全一致；
- `eas channel:view --json` 证明目标 channel 所映射的 branch 已指向该 group
  （channel 名和 branch 名不要求相同），且 channel 没有被暂停。

该 manifest 默认被 `.gitignore` 忽略，是发布机上的 `0600` 运行证据，不是客户端
远程配置，也不能包含健康内容、凭证或用户标识。
production 保留历史路径 `.mobile-release-manifest.json`；preview/Rokid 使用
`.mobile-release-manifest.<channel>.json`，避免跨 channel 污染回滚来源。

## Schema v2

- `schema_version`: 当前为 `2`。
- `status`: `published` 或 `rolled_back`。
- `transaction_id`: 单次发布唯一标识，同时写在 EAS message 开头；用于不确定失败后的去重查询。
- `platform` / `channel` / `environment`: 发布路由；artifact 固定为 `ios`。
- `runtime_version`: 当前 native runtime 版本。
- `commit_sha` / `source_tree`: bundle 的 Git commit 与 tree 身份。
- `artifact_digest`: 事务内所有导出文件按稳定相对路径和内容计算的 SHA-256。
- `artifact_file_count` / `artifact_total_bytes`: artifact 完整性摘要。
- `eas_cli`: 发布所用的精确 EAS CLI 标识；默认锁定 `eas-cli@21.8.0`，可通过
  `OTA_EAS_CLI_VERSION` 显式调整。
- `group_id` / `update_id`: 本次实际活跃的 EAS 发布身份；保留给旧消费者。
- `active_group_id` / `active_update_id`: channel 当前已验证指向的身份。
- `previous_known_good_group_id` / `previous_known_good_update_id`: 下次人工回滚的默认来源。
- `remote_verification`: `update:view` 和 channel mapping 结构化复证结果。
- `published_at`: UTC 发布时间。

回滚后另有：

- `rollback_source_group_id` / `rollback_source_update_id`: 被选来 republish 的历史来源；
- `rollback_source_verification`: 历史来源 group/update/runtime 在 republish 前的复证；
- `rollback_from_group_id` / `rollback_from_update_id`: 回滚前的活跃身份；
- `rollback_from_evidence`: 回滚前 artifact/transaction 证据的审计快照；这些字段
  不再保留在顶层，避免被误读为当前 republish 的证据；
- `active_group_id` / `active_update_id`: **republish 新创建**的 group/update 身份，而不是来源 ID；
- `previous_known_good_group_id` / `previous_known_good_update_id`: 继续指向已复证的
  历史来源，不会指回本次逃离的坏版本；
- `rollback_remote_verification` / `rolled_back_at`: 新身份远端复证与完成时间。

`rollback_target_*` 作为 schema v1 兼容别名继续表示历史来源；新代码应读
`rollback_source_*`。

## 发布

```bash
./scripts/mobile-ota.sh production "message"
```

正常路径由第一次 EAS 调用完成 bundling 和 publish。明确的临时上传失败会：

1. 在所有 branch 中进行有界轮询（默认 3 次、间隔 2 秒），查找带
   `[tx:<transaction_id>]` 的 recent updates；唯一
   group 命中时只做复证，避免 channel/branch 名不同时重复发布；
2. 无命中时复查 source 与 artifact digest；
3. 对同一 `--input-dir` 执行一次 `--skip-bundler` 重试；如重试响应也丢失，
   再做一次同 transaction 查询，只允许复证唯一命中，不发起第三次发布。

认证、runtime、Metro、语法、配置错误不重试；查询失败、多 group 命中、artifact
缺失或变化都会停止，且不写 manifest/anchor。显式调试
`OTA_FORCE_NO_BYTECODE=1` 仍支持单次 no-bytecode export，但不会在失败后换一份 bundle。

## 回滚

先演练：

```bash
./scripts/mobile-ota-rollback.sh production
```

确认后执行：

```bash
./scripts/mobile-ota-rollback.sh production --confirm
```

也可以显式指定已验证的来源 group/update 对：

```bash
./scripts/mobile-ota-rollback.sh production \
  --group <verified-source-group-id> \
  --update-id <verified-source-ios-update-id> \
  --confirm
```

EAS `update:republish` 会创建新的 group 和 iOS update。脚本读取结构化 republish
结果，并再次执行 `update:view` 与 `channel:view`；只有新身份全部匹配才更新 manifest。
因此审计时必须区分“历史来源 ID”和“当前 republish ID”。

## 边界

- 一次事务的 export 仅用于本次瞬时重试；EAS 环境可能变化，因此禁止跨发布缓存。
- 原生能力、权限、Watch 扩展、Expo SDK/native module 和 runtime 不兼容变更仍走原生发版。
- 这是人工回滚，不根据崩溃循环或失败率自动回滚。
