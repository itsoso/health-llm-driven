# 本地饮食端侧能力与评测契约

> Updated: 2026-07-18
> Scope: G2 capability/privacy spike only; no inference and no production health-data storage

## 结论

当前 SDK 足以支撑“手工/确定性路径 + Vision + 有条件的系统文字模型”，但不足以把 Foundation Models 多模态能力当作当前产品依赖。营养数据授权和本地存储威胁模型已有明确解法；G2 仍为 **BLOCK**，原因收敛为没有可用 iPhone 真机的推理时延、内存和温升证据。

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
| 内容机密性 | 随机 256-bit root；HKDF 分离 record/index keys；AES-GCM 自动随机 nonce | **PASS（设计）**：AAD 绑定 schema/table/object/version；认证失败硬失败，禁止明文日志 |
| 锁屏保护 | `NSFileProtectionComplete` + `kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly` | **PASS（设计）**：用户已确认本地模式要求设备密码；禁止弱保护回退 |
| 可查询索引 | 随机 ID 与 envelope 元数据明文；日期、餐次、状态使用独立 index key 的 HMAC blind index | **PASS（设计）**：显示与排序值保留在密文；实现需配无明文与相同值稳定匹配测试 |
| 导出恢复 | 每次导出由 App 生成新的 256-bit 恢复密钥，HKDF 派生 export key；恢复密钥不进入导出文件 | **PASS（设计）**：不接受弱口令，因此无需第三方 password KDF；恢复必须同时持有导出文件与对应密钥 |
| 删除/重装 | root key crypto-shred 后删文件；install sentinel 缺失时清理 service-scoped orphan keys | **PASS（设计）**：现有库缺 key 时只开放恢复，绝不生成新 key 覆盖旧库 |
| 完整性与回滚 | 先全量认证/校验，后单事务恢复并以新设备 key 重加密 | **PASS（设计）**：v1 仅恢复到空保险库，不合并、不覆盖现有记录 |
| 服务端边界 | 只接收用户主动上传的密文或单次授权推理载荷 | 可行，但在产品实现前仍需出站断路器与零违规抓包证据 |

用户于 2026-07-18 选择 App 生成高熵恢复密钥，并确认没有设备密码时拒绝创建本地保险库。以上为 G2 设计级 PASS；密码学、锁屏、删除和恢复测试仍是 G3/G4 硬闸。

Apple 依据：

- <https://developer.apple.com/documentation/security/restricting-keychain-item-accessibility>
- <https://developer.apple.com/documentation/foundation/fileprotectiontype/complete>
- <https://developer.apple.com/documentation/cryptokit/aes/gcm>
- <https://developer.apple.com/documentation/cryptokit/hkdf>

## 营养数据授权

首版生产基线选定 USDA FoodData Central 的 Foundation Foods 与 SR Legacy 版本化子集。USDA 明确声明 FoodData Central 数据属于公共领域并以 CC0 1.0 发布，可随 App 离线分发；manifest 仍须保留 release、FDC ID、转换版本和 USDA attribution。构建脚本联网取数，App 运行时不联网。

中文名称、别名与复合菜配方由项目自行编写；复合菜营养必须由有来源的 FDC 食材与明确重量计算。现有 `china_food_composition_manual_v1` 继续只用于测试，不能直接进入生产包。授权问题在 G2 源级别 PASS，实际 manifest/provenance 检查留在 G3/G4。

- <https://fdc.nal.usda.gov/api-guide/>
- <https://fdc.nal.usda.gov/download-datasets/>

## 解除 G2 的最小证据

1. 在至少一台可用 iPhone 真机运行能力探针，并记录系统模型状态。
2. 用最小文字结构化推理 spike 采集冷/热时延、峰值内存和温升；不可用设备验证确定性降级。
3. 在 `on-device-eval-contract.json` 中补齐真机内存上限，重新裁决 G2。
