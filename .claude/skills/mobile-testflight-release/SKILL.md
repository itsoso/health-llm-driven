---
name: mobile-testflight-release
description: "发布 mobile/ Expo iOS App 到 TestFlight，并衔接 App Store 送审。用户要求发 TestFlight、发新包、iOS 发版或上架时使用；默认让构建、上传和 Apple 处理与后端部署并行，正式送审仍需汇合验收。"
---

# Mobile TestFlight 发布

使用 `.github/workflows/trusted-release.yml` 的受审入口；安全边界以
`docs/governance/deploy.md` 为准。本 Skill 是发布 adapter，不另建 controller、
ledger 或完成状态。不要从带 WIP 的本机工作区直接运行 EAS build/auto-submit。

## 1. 先选择最小发布范围

| 需求 | 路径 |
|---|---|
| 仅 JS/TS/UI，符合 OTA 边界，用户未要求新包且不在审核冻结期 | `scripts/mobile-ota.sh production "<message>"` |
| 用户要求 TestFlight 新包、原生依赖/签名/权限变化或上架 | 本 Skill 的受审 build + submit |
| 用户只要可扫码安装的包，未指定 TestFlight | `scripts/mobile-local-qr.sh`，不要擅自 submit |
| 仅服务端变化 | trusted-release 的 `target=backend`，不创建 iOS 构建 |

审核候选冻结期间不发 OTA 改变受审行为；版本号和原生配置遵循仓库 release profile，
不因等待、上传重试或 CI 文档修订重复递增 build。
冻结期仅 JS 改动且未授权替换候选时，保留改动并暂停发布，说明需等待冻结结束或取得
替换候选的明确授权；不擅自取消 Apple 审核。

## 2. 固定 revision，一次预检后并行

先核对 main、开放 PR、工作树来源和授权范围，读取本次 Dossier。
从干净的目标 revision 跑 CI-mode 集成闸，核验该精确 main SHA 的真实 CI 绿色及独立安全裁决。
按 deploy 治理准备绑定该 SHA 的短期发布身份；不覆盖正在运行的 executor/policy。

```bash
gh workflow run trusted-release.yml --ref main -f sha=<exact-main-sha> -f target=validate
# 上一次 validate 成功、部署授权/兼容性就绪后，只触发一次：
gh workflow run trusted-release.yml --ref main -f sha=<same-exact-main-sha> -f target=release
```

实际依赖关系必须是：

```text
精确 SHA / CI / 服务器只读预检
  ├─ 后端部署、备份/恢复验证、健康检查 ──────────┐
  └─ iOS 构建 → 精确制品校验 → TestFlight 上传 ─┤ 发布结果汇合
                         └─ Apple 处理 / 下载核验可与后端重叠
发布汇合 + ASC 可用 + 同包验收 → App Review gate → 正式送审
```

- **构建一完成就上传，不等待后端部署成功。** 不增加手工串行等待，不把后端 job 加回
  testflight 的 `needs`。上传与 App Review 提交是两个不同动作。
- `claim-build` 和 `claim-testflight` 各自一次性、绑定同 SHA；上传复用短 `build.lock`，
  不抢长期 backend `launcher.lock`。锁内重验时间窗、既有 build claim 和未撤销授权。
- 新包必须兼容部署前的生产 API；依赖新服务端能力的功能先保留兼容处理/关闭开关并验证。
  TestFlight 上传后可能被既有测试组自动获取，不能假设“仅上传就不会被安装”。不兼容未解决则 BLOCK。
- 已知后端失败时不再领取上传权限；如果失败发生在上传开始之后，保留 build/submission ID，
  明确发布未完成，修复后端，不重新造包或清空 claim。最终汇合失败/取消/跳过均不得送审。
  后端修复走新受审 SHA 的 backend-only 授权；旧 run 保持失败，保留旧制品不等于自动放行
  跨 revision 组合。关联旧包与新后端并送审需另行受审的兼容性/验收证据，缺失时保持 BLOCK。
- 只上传本轮 job 返回、再次验证过的精确 EAS build ID：SHA、项目/App、FINISHED、IOS、
  STORE、production 必须匹配。禁止 `--latest`、裸 `--auto-submit` 或手动绕过 claim。

## 3. 缩短等待，而不重复副作用

- 复用已有长期 `REVA_RELEASE_EXPO_TOKEN`，先做不泄露身份的只读有效性检查。
  不为每次发版创建/删除 Expo token；短期 SSH 授权与长期 Expo token 分开管理。
- 记录 workflow run、EAS build、submission 和 ASC build ID，沿用同一异步任务/等待句柄。
  采用有界等待和退避查询；等待构建/Apple 处理时并行准备发布说明、验收用例和只读元数据检查。
- 构建 FINISHED 后可立即下载确切 IPA，核验版本、bundle、签名元数据；无须等后端或 Apple 处理。
  可先做同包静态检查和不依赖新服务端的本机测试，依赖后端的验收等真实健康检查成功。
- 响应丢失或超时先按已知 ID/SHA 查询真实状态。未知结果不是失败重试许可；禁止再次 create、
  重新 dispatch、清 marker 或换 ID 重放。已生成 archive/IPA 的排错应复用制品，但重新上传仍须独立授权。
- 保留干净 VM、锁定依赖、秘密隔离、备份和回滚验证；不得用共享发布缓存或跳过测试换速度。
  工具链/签名故障先读对应日志，只处理已定位原因，不盲目轮换证书或切换上传通道。

## 4. 验收、汇合与清理

分别报告：后端部署结果、上传结果、ASC processing、确切 build 的安装/测试结果。
`release-result` 成功只说明后端和上传成功，**不等于 Apple 处理完成、审核通过或上架**。
正式送审激活 `ios-app-review-gate`，要求后端健康、ASC 可用、同包核心路径/审核账号验收、
隐私和商店元数据检查均通过；未知项保持未完成，不能保证 Apple 一定批准。

自动清理只在整条 workflow 及 vendor 任务确认终结后执行：按 deploy 治理撤销本次短期身份，
只移除本次临时 secrets/私钥，保留长期 Expo token 和不可变审计。SSH 撤权或超时不证明 EAS 已终止；
STARTED/NEEDS_OPERATOR、准备失败伴随 vendor intent 等未知现场不得自动退役、轮换或删除消费证据。

每次记录预检、后端、构建、依赖等待、上传、Apple 处理、下载/验收耗时。
按同批真实发布比较关键路径；单次节省只能报告该次数据，不宣称 P95 改善。
停止/回退：重复构建、来源不符、权限或质量闸失败时停止外部写入，保留证据；
修复需要新的受审 revision/授权生命周期，不改写旧运行。历史本地归档脚本不是受审入口的绕行许可。
