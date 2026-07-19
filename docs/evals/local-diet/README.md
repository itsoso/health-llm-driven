# 本地饮食端侧能力与评测契约

> Updated: 2026-07-18
> Scope: G2 capability/privacy spike and opt-in synthetic inference benchmark; no production health-data storage

## 结论

当前 SDK 足以支撑“手工/确定性路径 + Vision + 有条件的系统文字模型”，但不足以把 Foundation Models 当作当前产品依赖。2026-07-18 的 iPhone 17 Pro Max 真机运行返回 `device_not_eligible`；这证明即使新款硬件也不能获得通用可用性保证。

因此 G2 被拆成两个范围：不依赖生成模型的本地饮食基线 **PASS**，可进入加密 Local Health Kernel；智能增强仍为独立 **BLOCK**，必须先有可用真机的质量、时延、内存、温升和包体证据。首版可保证的能力收敛为：所有设备均可手工/确定性记录；Vision 用于 OCR、条码和通用分类；系统语言模型只在运行时报告可用时增强文字草稿。

2026-07-18 已为照片智能增强选定 `OFA-Sys/chinese-clip-rn50`，不再做 TinyCLIP 首轮对照实现。设备端只计划运行 Core ML 视觉塔，中文文本塔仅在构建阶段生成版本化标签向量。选择已确定，但放行状态不变：checkpoint/许可证、转换一致性、压缩质量、中文餐食质量和代表性真机性能全部取得证据前仍为 **BLOCK**。设计见 `docs/plans/2026-07-18-chinese-clip-local-food-vision-design.md`。

## 可重复的能力证据

探针与基准位于 `mobile/modules/local-health-kernel/`。探针只查询可用性；基准只有在 `LOCAL_DIET_ENABLE_LIVE_BENCHMARK=1` 时才执行推理。它固定使用一条合成中文餐食，只输出食物名、数量、单位和设备性能，不读取健康数据、相册或营养值，也没有网络降级路径。Swift Package 是 G2 测试壳，不是生产功能。

```bash
cd mobile/modules/local-health-kernel
swift test
swift test --filter LocalDietInferenceBenchmarkTests
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
| iPhone 17 Pro Max（iPhone18,2） | iOS 26.6 Beta | 不可用：`device_not_eligible` | 不可用：`sdk_not_supported` | OCR/分类/条码可用 | 已签名安装并真机运行 |

模拟器的“系统模型可用”不能外推到真机。Apple 的运行时状态还会因设备资格、Apple Intelligence 开关和模型下载状态而变化，探针分别返回 `device_not_eligible`、`apple_intelligence_not_enabled` 和 `model_not_ready`，不会抛错或静默切云。Apple 对 `deviceNotEligible` 的定义是设备不支持 Apple Intelligence；Apple 同时说明，中国大陆购买的受支持设备目前无法使用 Apple Intelligence。因此产品只消费运行时结果，不根据机型猜测资格。

Xcode 26.5 本地 Foundation Models 接口只提供当前已编译的文字模型能力；本探针因此把多模态明确标为 `sdk_not_supported`。照片路径当前只允许走 Vision 或未来通过独立评测的 Core ML 模型。

## 结构化文字推理基准

`ios/LocalDietInferenceBenchmark.swift` 使用 Foundation Models 的 guided generation，把固定文本“午餐吃了150克米饭、120克清蒸鲈鱼和一碗约200克西兰花”解析为类型化食物数组。冷运行创建会话，热运行复用会话；每次运行以 10ms 间隔采样 Mach `phys_footprint`，并记录单调时钟时延和运行前后 thermal state。内存指标读取失败会让基准显式失败，禁止用 0 MB 伪装证据。

确定性测试注入假模型、时钟、峰值内存和温度状态，覆盖：不可用原因、冷/热时延、峰值内存增量、温度、JSON round-trip、模型失败透传、指标失败透传和显式开关。2026-07-18 的证据为：macOS 完整 Swift Package 15 tests / 0 failures / 1 live test skipped；iPhone 17 Pro Simulator iOS 26.4 测试通过；generic iOS 16 deployment build 通过。模拟器仍不构成性能证据。

Swift Package 的独立测试 target 在真机上没有宿主 App，Xcode 会以 `Tool-hosted testing is unavailable on device destinations` 拒绝执行。因此真机使用专门的、不会进入生产包的合成基准宿主：

```bash
cd mobile/modules/local-health-kernel
gem install xcodeproj # 本机尚未安装时执行一次
ruby scripts/tests/generate_device_host_test.rb
ruby scripts/generate_device_host.rb \
  --output .build/device-host/LocalDietBenchmarkHost.xcodeproj \
  --team-id <DEVELOPMENT_TEAM>
xcodebuild \
  -project .build/device-host/LocalDietBenchmarkHost.xcodeproj \
  -scheme LocalDietBenchmarkHost \
  -destination 'platform=iOS,id=<DEVICE_ID>' \
  -derivedDataPath .build/device-host-derived \
  build
xcrun devicectl device install app \
  --device <CORE_DEVICE_ID> \
  .build/device-host-derived/Build/Products/Debug-iphoneos/LocalDietBenchmarkHost.app
xcrun devicectl device process launch \
  --device <CORE_DEVICE_ID> \
  --console --terminate-existing \
  life.executor.health.local-diet-benchmark
```

宿主在源代码内显式开启固定合成基准，日志输出单行 `LOCAL_DIET_INFERENCE_BENCHMARK=<json>`。如果系统模型不可用，JSON 必须包含明确 `unavailableReason`；如果可用，`caseResult` 包含冷/热时延、峰值内存增量及前后温度。真机原始证据保存在 `runs/2026-07-18-iphone18-2-ios26-6-system-model.json`，不含设备序列号、UDID 或私人饮食数据。

Apple 参考：

- <https://developer.apple.com/documentation/FoundationModels>
- <https://developer.apple.com/documentation/foundationmodels/systemlanguagemodel/availability-swift.enum/unavailablereason>
- <https://developer.apple.com/documentation/Vision>
- <https://developer.apple.com/documentation/CoreML>
- <https://support.apple.com/zh-cn/121115>

## 评测数据契约

`on-device-eval-contract.json` 是 JSON Schema。每次模型、OS、设备或提示词版本变化都产生一份独立 run，必须记录：

- 输入模态、期望食物身份、允许别名、份量歧义和非食物标记；
- 有效类型化草稿、预测身份、纠正次数；
- 冷启动/热启动时延、峰值内存增量、前后温度状态和崩溃；
- 设备、OS、能力快照与模型配置；
- 汇总准确性、遗漏率、纠正成本和 Gate 裁决。

初始质量阈值已写进 Schema 的 `x-initial-acceptance-policy`。系统模型真机峰值内存上限保持 `null`：当前真机没有进入推理，不能用不可用报告伪造预算。该增强保持关闭；后续系统模型或打包小模型必须在代表性低/中/高端设备取得基线后另行设限。

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

## 智能增强解除 BLOCK 的最小证据

1. 固定 Chinese-CLIP RN50 的不可变 revision、checkpoint SHA-256、代码/模型许可证和转换 provenance。
2. 证明 Core ML FP16 与 PyTorch embedding 一致，并证明所选压缩版相对 FP16 的 identity precision 下降不超过 0.02。
3. 用完整的合成/获授权中文餐食集评测结构化候选质量和纠正成本；输出只能是身份候选，不含份量或营养推断。
4. 在代表性低/中/高端真机采集冷/热时延、峰值内存、温升、崩溃率和安装资产体积；视觉模型与标签资产不超过 50 MB。
5. 在 `on-device-eval-contract.json` 中补齐引擎对应的内存上限后，单独裁决智能增强。
