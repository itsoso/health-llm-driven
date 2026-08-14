---
name: mobile-ota
description: "处理 Mobile OTA 请求的冻结裁决与本地替代反馈环。所有 EAS channel 的 OTA/rollback 网络 writer 当前 exit 78。"
---

# Mobile OTA — All Channels Frozen

## 当前裁决（2026-08-12）

`production`、`preview`、`development`、Rokid、Watch 及任何别名 channel 的 OTA 发布与
rollback 网络写入全部冻结；入口必须在 Git、状态、锁和 EAS 访问前 `exit 78`。到达
manual Gate 时记录 **BLOCK 并停止**。不得通过改 channel 名、branch、environment、runner、
内部 helper、直接 EAS CLI 或控制台恢复写权限。

这不是只有 production 才有的限制。EAS channel→branch 是仓库外状态，可能漂移、复用或
被重新映射；仅凭 `preview`/`development` 名称无法证明更新不会触达 production cohort。

## 更底层的信任缺口

same-UID writable repo 的 bootstrap trust 也无法在仓库内闭合，已复现：

- Git refs/replace 改变表面 SHA 对应的 tree；
- shared `.git/info/attributes` + local clean/smudge filter 在 clean 表象下替换执行字节；
- `.git/info/exclude` 隐藏 untracked import shadow；
- `BASH_ENV`、`PYTHONPATH`/`sitecustomize` 在 repo guard 前执行。

因此 repo 内 clean/source/lock/receipt/manifest 检查、协议绿测或同 UID 凭证都不能签发
OTA mutation authority。

shell rc78 只是 ordinary-invocation tombstone。`BASH_ENV` 与 caller-defined
`exit`/`builtin` function 可改变顶部 guard，所以 `_run-mobile-tf.sh` 的旧 writer 必须在
literal-false、语法级不可达 block，runtime/operator 严禁 source/extract/eval。隔离测试
marker extraction 仅作无 writer/网络的协议 fixture，不构成 release proof；外部 Gate 仍不可省略。

## 当前允许的 Mobile 反馈环

只做不访问 OTA/EAS 写接口的本地工作：

```bash
cd mobile
npm test
npx tsc --noEmit
npx expo start --dev-client
npm run ios
```

`npm run ios` 固定走 Simulator wrapper，不得向 npm/Expo 追加 `--device`。wrapper 从
available inventory 解析并锁定 exact Simulator UDID；物理 iOS repo CLI、连接、安装和
验收冻结。Simulator-only helper 的历史 `--device` 参数只可接受 Simulator 名称/UDID，
并必须先解析为 exact available UDID。仅允许离线检视现成 IPA：

```bash
./scripts/mobile-local-qr.sh --no-upload --ipa <EXISTING_IPA>
```

该命令只生成离线 IPA metadata/report；不生成 install manifest、安装二维码或可安装承诺。

bare `--no-upload` 会触发 archive/export，故同样冻结。不得调用 `mobile-fast-device.sh` 或
`mobile-local-device.sh`，
不得自动 archive/export/signing/provisioning 或使用 `-allowProvisioningUpdates`，不得公共
上传 IPA/QR。release planner 的 `plan`/`validate` 会进入 root SSH 或带 token 的 EAS
channel observation，必须与 publish 一样在 network/credential 前 earliest exit 78；
candidate/channel 的 EAS/ASC network query 也冻结。只可解析 already-downloaded IPA、已有
本地 metadata/offline evidence，且不得形成 G5/G6 或“已上线”结论。

Android 尚不是 shipped/audited Mobile surface。`npm run android`/`expo run:android` 可能自动
生成 native 工程、做 debug signing 并通过 ADB 安装，且没有 exact-iOS-Simulator 目标守门，
所以 repo entry 必须 earliest `exit 78`，无 Android native CLI 例外。

## Native 边界

`app.json` plugins、`Info.plist`、Podfile、新 native module、Expo SDK/runtime、Watch/Siri
extension 等变化只做静态检查或 Simulator compile/test；需要物理 iOS 的能力保持
BLOCK。不得自动
archive/export/signing/provisioning；production native/EAS/ASC writer 同样冻结。不要把
OTA BLOCK 转成另一条 build/upload/submission 命令。

## 解冻条件

必须另开 dossier，并由仓库外 root-owned launcher 使用固定解释器、`env -i` allowlist，
从 canonical Git archive/tree 在仓库外 materialize 实际执行字节。方案还必须绑定
source/artifact/native cohort、受信 channel→branch/installed-cohort authority 与 recovery
proof，并重新通过独立 G4。此前 G5、G6、App Store submission 均为 **BLOCK**；Dossier
不得标 `shipped`/`complete`。
