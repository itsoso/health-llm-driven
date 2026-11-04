# Mobile OTA receipt

Production iOS OTA 只通过 `.github/workflows/trusted-ota.yml`。本机
`scripts/mobile-ota.sh` 与 `scripts/mobile-ota-rollback.sh` 固定退出 78，不读取
production 凭据、不调用 EAS，也不维护本地发布 anchor。

## 发布顺序

```bash
gh workflow run trusted-ota.yml --ref main -f sha=<exact-main-sha> -f target=validate
# validate 成功、同 SHA 后端已部署并健康回读后，只触发一次：
gh workflow run trusted-ota.yml --ref main -f sha=<same-exact-main-sha> -f target=publish
```

`validate` 导出并核验 canonical iOS 制品，但不领取 OTA claim、不执行 vendor
publication。`publish` 在新的受信 runner 上重新建立并核验制品，领取一次性 claim，
调用 EAS，回读 vendor update，再由服务器核验 Expo 公网 manifest 后形成终态。

同一 workflow/target/SHA 的重复 dispatch 会在 production 凭据、依赖安装、SSH、
claim 和 vendor write 之前被阻断。失败、取消、超时、结果未知或已有更早 run 时，
不得自动重发或换 run ID 绕过；按 `docs/governance/deploy.md` 的固定收尾协议处理。

## 审计制品

成功 publish 的 GitHub artifact 仅包含封闭 JSON：

- `ota-claim.json`: SHA、project、runtime、channel、platform、branch 与制品证明。
- `ota-preflight.json`: production channel 到 branch 的受审映射。
- `ota-vendor-receipt.json`: 精确 `group_id`、iOS `update_id` 与 SHA。
- `ota-receipt.json`: `SUCCEEDED` 终态及 runtime/project/channel/platform/branch。

服务器同时保留 intent、claim、verified manifest、completed terminal 与 released
lease。GitHub workflow success 不是设备接收证明；完成声明还需核对服务器终态、
Expo 公网 manifest 和明确记录的设备验证范围。

## 回滚边界

本地 rollback 入口已冻结。需要回滚时必须选定此前已验证的 group/update，设计并
评审精确的受信 republish/receipt 流程；不得从本机开发环境直接执行
`eas update:republish`，也不得删除原发布 intent、claim 或失败审计。

Receipt 不得包含健康正文、图片、药物、基因、报告、用户标识、Token 或供应商原始
错误。原生能力、权限、Watch 扩展与 runtime 不兼容变更仍必须走原生发版。
