---
name: mobile-testflight-release
description: "Mobile TestFlight/App Store 冻结期的本地候选材料与未来真机/submission 缺口审计。所有 production native/EAS/ASC writer 和 network observation 当前 exit 78。"
---

# Mobile TestFlight / App Store — Production Frozen

## 当前裁决

production native build、**所有 channel 的 OTA/rollback**、IPA upload、TestFlight build/group selection、ASC
metadata mutation、App Review submission 与审核账号 reset 均为 **BLOCK**。仓库受控入口、
legacy archive/upload helper 与 direct vendor CLI 都不得执行或绕过；writer 应在 mutation
前 `exit 78`。

现有 candidate 只能用**已经持有的本地材料做身份对账**，不得联网查询，更不得因此选择、
分发或提交。Build Gate、
TestFlight Gate、同构建发布验收 Gate、App Review submission Gate 当前均未放行；本地
测试或候选可见性不等于 Store 状态。

## 冻结根因

历史 ASC 分发二进制没有完整可信的 build ↔ source SHA ↔ native fingerprint ↔ installed
cohort authority。更底层地，同 UID writable repo 已复现：

- Git replacement refs 改变表面 SHA 对应的 tree；
- shared `.git/info/attributes` + local filters 在 clean/canonical 表象下替换执行文件；
- `.git/info/exclude` 隐藏 untracked import shadow；
- `BASH_ENV` 与 `PYTHONPATH`/`sitecustomize` 在 repo 内 guard 之前执行。

所以仓库内的 clean/source/lock/receipt 校验无法充当 production bootstrap trust root。
manual Gate 仅表示停止并上报，不授权手工 EAS/ASC、Xcode upload、raw SSH 或 helper。

`scripts/_run-mobile-tf.sh` 的 rc78 仅是 ordinary-invocation tombstone；Bash caller 可借
`BASH_ENV` 并覆盖 `exit`/`builtin` function。其旧 writer 只能留在 literal-false、语法级
不可达 block，runtime/operator 禁止 source/extract/eval。隔离测试 marker extraction 仅作
无 writer/网络的协议 fixture，不构成 release proof；这仍不能替代 external root-owned `env -i` Gate。

## 当前允许的证据工作

- 运行不带 `--final-submit` 的静态 release-pack 与纯静态 iOS submission config 检查；
- 从 already-downloaded IPA/已导出的本地 metadata 记录 existing candidate 的 app version、
  build number、bundle/profile、完整 source SHA、IPA native/toolchain metadata；有歧义即
  保持 BLOCK，不得调用 EAS/ASC network query；
- 只对 iOS Simulator 做不签名、不安装物理设备的 UI 验收和本地截图脱敏/尺寸检查；
  历史物理 iPhone 证据模板只能作为只读缺口清单，不能生成新的真机证据；
- 使用 `scripts/mobile-local-qr.sh --no-upload --ipa <EXISTING_IPA>` 读取现成 IPA 并生成
  离线检视 metadata/report；不生成 install manifest、安装二维码或可安装承诺。bare
  `--no-upload` 也冻结，且不得 archive/export/signing/provisioning、调用
  `mobile-fast-device.sh`、`mobile-local-device.sh` 或使用 `-allowProvisioningUpdates`；
- Mobile JS/TS 只可用本地 Metro、iOS Simulator/测试。`npm run ios` 固定走 Simulator
  wrapper，不得向 npm/Expo 追加 `--device`；wrapper 锁定 exact available Simulator
  UDID，物理 iOS repo CLI、连接/安装/验收冻结。EAS channel→branch 映射可能
  漂移或共用，preview/development 也不能证明不会触达 production，因此所有 OTA writer
  均冻结。

`check_app_store_release_pack.py --final-submit` 会登录 production reviewer 并取得可写
bearer token，须在登录/凭证读取前冻结；credential-aware readiness 也不是纯静态检查。
禁止修改 App Store Connect 元数据、隐私问卷、年龄分级、测试组、build selection、
Review Notes 或 submission 状态；禁止重置 production 审核账号。静态工具即使通过，也不
产生 mutation authority。

## iPhone / Watch 边界

标准 production 设计仍是 iPhone-only。Watch、Rokid、Siri extension 或其他 target 必须
另立 dossier 与 native/真机/Store Gate；冻结期任何 profile 都不能创建 production
candidate。

Android 尚不是 shipped/audited Mobile surface；`npm run android`/`expo run:android` 会进入
native generation、debug signing 与 ADB install，故 repo entry 必须 earliest `exit 78`，
不得将 Android 模拟器或设备当作本冻结的旁路。

## 解冻条件

另立 dossier，并让独立 G4 评审 repo-external、root-owned launcher：固定绝对解释器，
从 `env -i` 最小 allowlist 启动，在仓库外 materialize/verify canonical Git archive/tree，
再绑定签名工具链、native fingerprint、ASC candidate、artifact bytes、recovery 和 installed
cohort。完成新的 G3/G4 前，G5/G6 与 App Store submission 必须记录 **BLOCK**，Dossier
不得写 `shipped`/`complete`。
