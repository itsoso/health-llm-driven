# 本地饮食端侧能力与评测契约

> Updated: 2026-07-18
> Scope: G2 capability/privacy spike only; no inference and no production health-data storage

## 结论

当前 SDK 足以支撑“手工/确定性路径 + Vision + 有条件的系统文字模型”，但不足以把 Foundation Models 多模态能力当作当前产品依赖。G2 仍为 **BLOCK**：没有可用真机性能证据，生产食物库再分发授权未解决，恢复口令 KDF 与本地索引泄露边界未通过安全评审。

这不否定完全本地饮食方向。它把首版可保证的能力收敛为：所有设备均可手工/确定性记录；Vision 用于 OCR、条码和通用分类；iOS 26 且运行时可用时，系统语言模型只增强文字草稿。

## 可重复的能力证据

探针位于 `mobile/modules/local-health-kernel/`，只查询可用性，不执行推理、不读取健康数据、不联网。Swift Package 是 G2 测试壳；后续 Expo 模块复用 `ios/LocalHealthCapabilityProbe.swift`。

```bash
cd mobile/modules/local-health-kernel
swift test
xcodebuild \
  -scheme LocalHealthCapabilityProbe \
  -destination 'platform=iOS Simulator,id=<DEVICE_ID>' \
  -derivedDataPath .build/xcode-derived \
  test
```

本次环境：Xcode 26.5、Swift 6.3.2、iPhoneOS SDK 26.5。

| 运行面 | OS | 系统语言模型 | Foundation Models 多模态 | Vision | 证据级别 |
|---|---|---|---|---|---|
| Apple Silicon Mac | 26.4.1 | 不可用：`device_not_eligible` | 不可用：`sdk_not_supported` | OCR/分类/条码可用 | 编译 + 运行时探针 |
| iPhone 17 Pro Simulator | iOS 26.4 | 探针报告可用 | 不可用：`sdk_not_supported` | OCR/分类/条码可用 | iOS 16 deployment 编译 + 模拟器测试 |
| 已登记 iPhone 17 Pro Max | 未采集 | 未采集 | 未采集 | 未采集 | 设备当前 `unavailable`，不可作为证据 |

模拟器的“系统模型可用”不能外推到真机。Apple 的运行时状态还会因设备资格、Apple Intelligence 开关和模型下载状态而变化，探针分别返回 `device_not_eligible`、`apple_intelligence_not_enabled` 和 `model_not_ready`，不会抛错或静默切云。

Xcode 26.5 本地 Foundation Models 接口只提供当前已编译的文字模型能力；本探针因此把多模态明确标为 `sdk_not_supported`。照片路径当前只允许走 Vision 或未来通过独立评测的 Core ML 模型。

Apple 参考：

- <https://developer.apple.com/documentation/FoundationModels>
- <https://developer.apple.com/documentation/Vision>
- <https://developer.apple.com/documentation/CoreML>

## 评测数据契约

`on-device-eval-contract.json` 是 JSON Schema。每次模型、OS、设备或提示词版本变化都产生一份独立 run，必须记录：

- 输入模态、期望食物身份、允许别名、份量歧义和非食物标记；
- 有效类型化草稿、预测身份、纠正次数；
- 冷启动/热启动时延、峰值内存增量、前后温度状态和崩溃；
- 设备、OS、能力快照与模型配置；
- 汇总准确性、遗漏率、纠正成本和 Gate 裁决。

初始质量阈值已写进 Schema 的 `x-initial-acceptance-policy`。真机峰值内存上限故意保持 `null`：必须先在代表性低/中/高端设备取得基线，再由 G2 设置，不能拍脑袋伪造预算。

评测素材只允许使用具有评测授权、公共领域或合成数据；`containsPrivateUserData` 被固定为 `false`。用户私人饮食照片不得提交到仓库。

## 安全威胁模型评审

目标边界是防止未授权的文件/备份读取、服务端运营者读取和普通设备丢失后的静态数据暴露；不承诺抵御已越狱设备、已解锁设备上的恶意操作者或系统级攻陷。

| 面 | 当前设计 | G2 评审 |
|---|---|---|
| 内容机密性 | CryptoKit AES-GCM 加密健康 payload；设备密钥放 Keychain | 方向可行，但实现必须使用随机 nonce、认证失败即硬失败，禁止明文日志 |
| 锁屏保护 | 受保护文件 + Keychain | 必须明确为 `NSFileProtectionComplete` 与 `kSecAttrAccessibleWhenUnlockedThisDeviceOnly`，尚未形成测试证据 |
| 可查询索引 | 当前设计允许日期、餐次、状态等明文索引 | **BLOCK**：这些元数据仍可暴露健康行为；需改为最小明文字段 + 从设备密钥独立派生的 HMAC blind index，或明确接受并更新隐私承诺 |
| 导出恢复 | 用户口令派生独立恢复密钥，不导出设备密钥 | **BLOCK**：CryptoKit 没有适合口令的 memory-hard KDF；必须选定并评审 Argon2id/scrypt 实现、参数、salt、版本化与暴力破解预算 |
| 删除/重装 | 本地身份、数据库、Keychain 生命周期 | **BLOCK**：需定义卸载后残留 Keychain 项、孤儿数据库、全量删除与恢复失败的确定行为 |
| 完整性与回滚 | AES-GCM 和版本化 envelope | 需绑定 schema/object/version 为 AAD，并测试篡改、重复导入、旧快照回滚和部分写入 |
| 服务端边界 | 只接收用户主动上传的密文或单次授权推理载荷 | 可行，但在产品实现前仍需出站断路器与零违规抓包证据 |

因此，Task 3 的加密内核不能按现有简写直接开工。先修订密钥生命周期、blind index 和恢复 KDF 方案，再写密码学与生命周期测试。

## 营养数据授权

现有服务端 seed 只能用于接口/测试，不足以作为生产端侧食物库，也没有在本次 spike 中证明可随 App 再分发。生产数据源必须记录来源、版本、再分发条款、署名要求和中国餐食覆盖；未完成前，Task 5 和 G2 保持阻断。

## 解除 G2 的最小证据

1. 在至少一台可用 iPhone 真机运行能力探针，并记录系统模型状态。
2. 用最小文字结构化推理 spike 采集冷/热时延、峰值内存和温升；不可用设备验证确定性降级。
3. 选定生产食物数据源并由授权条款明确允许 App 内再分发。
4. 修订并通过本页列出的密钥生命周期、blind index、恢复 KDF 和删除/重装威胁模型。
5. 在 `on-device-eval-contract.json` 中补齐真机内存上限，重新裁决 G2。
