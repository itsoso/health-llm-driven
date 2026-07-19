# 本地饮食端侧能力与评测契约

> Updated: 2026-07-19
> Scope: G2 capability/privacy spike and opt-in synthetic inference benchmark; no production health-data storage

## 结论

当前 SDK 足以支撑“手工/确定性路径 + Vision + 有条件的系统文字模型”，但不足以把 Foundation Models 当作当前产品依赖。2026-07-18 的 iPhone 17 Pro Max 真机运行返回 `device_not_eligible`；这证明即使新款硬件也不能获得通用可用性保证。

因此 G2 被拆成两个范围：不依赖生成模型的本地饮食基线 **PASS**，可进入加密 Local Health Kernel；智能增强仍为独立 **BLOCK**，必须先有可用真机的质量、时延、内存、温升和包体证据。首版可保证的能力收敛为：所有设备均可手工/确定性记录；Vision 用于 OCR、条码和通用分类；系统语言模型只在运行时报告可用时增强文字草稿。

2026-07-18 已为照片智能增强选定 `OFA-Sys/chinese-clip-rn50`，不再做 TinyCLIP 首轮对照实现。设备端只计划运行 Core ML 视觉塔，中文文本塔仅在构建阶段生成版本化标签向量。选择已确定，但放行状态不变：checkpoint/许可证、转换一致性、压缩质量、中文餐食质量和代表性真机性能全部取得证据前仍为 **BLOCK**。设计见 `docs/plans/2026-07-18-chinese-clip-local-food-vision-design.md`。

2026-07-19 八阶段独立 spike 已完成到最终裁决。工程可重复性、Core ML 转换和包体风险已经解除，但授权质量集与代表性真机不是代码可以替代的输入，最终 verdict 仍为 **BLOCK**，没有接入生产饮食页，也没有生成新的真机 run 文件。

同日的后续优化已按顺序完成：图像输入改为与固定上游一致的方形 bicubic（含缩小时 antialias）并批量写入 Core ML 张量；标签库升级为带非食物负类的 v2；原始设备报告删除自由填写的压缩差值，改由同一冻结 test split 的 FP16/int8 双报告确定性派生。上述变化提升了工程可信度，但没有生成缺失的授权质量和代表性真机证据，因此不改变 BLOCK。

| Gate 维度 | 结果 | 证据/缺口 |
|---|---|---|
| 来源、许可证、不可变摘要 | PASS（技术与声明核验） | 模型/代码 revision、checkpoint SHA-256、MIT/Apache-2.0 文本已固定；对外分发仍需最终授权审查 |
| PyTorch ↔ Core ML parity | PASS | FP16 最低 cosine `0.9999935626780782`；int8 `0.9950830876471225`，均过冻结阈值 |
| 安装资产 | PASS | v2 标签加入后，int8 编译模型 + 标签 39660136 bytes，小于 50 MiB；FP16 77074808 bytes 被拒绝 |
| 本地编排与失败模式 | PASS（确定性） | 37 个 Swift 测试中 36 通过、1 个显式真机测试按预期 skipped；iOS 16 package 与真实 int8 compile-only 隔离宿主通用构建成功 |
| 授权 300-case 质量集 | BLOCK | 工作区/环境无授权数据；禁止用私照、许可不明网页图或元数据占位 |
| FP16 ↔ int8 身份质量差 | BLOCK | 未在同一冻结 held-out test split 运行，不能拿 embedding cosine 代替 identity precision |
| 分层身份质量与纠正成本 | BLOCK | 无 single/composite/mixed/package/confusable/non-food/degraded 的真实 held-out 报告 |
| 低/中/高端 iPhone 性能 | BLOCK | 高端 iPhone 已于 2026-07-19 重新连接并完成宿主复测；授权数据缺失使 Chinese-CLIP 未进入推理，且仍无低/中端样本，内存 ceiling 保持未设 |
| 飞行模式与物理隐私 | BLOCK | 宿主源码无网络/相册/健康仓库接口且单测通过，但真机飞行模式、抓包与长时温升未执行 |
| **总裁决** | **BLOCK** | 任一 required evidence 缺失即 BLOCK，不按总体平均放行 |

## Chinese-CLIP 来源锁定

Task 1 已固定可重复的上游来源：模型 revision `717ba215769231e53b9b7c6b9d329b9cc5944418`，代码 revision `31863c707501bf1605d36842f43deb78793dbc5d`。原始 `clip_cn_rn50.pt` 为 308316425 bytes，SHA-256 为 `b196ee3ee528b70be1158ab1aafb1d2f1c801ad2d9ffb3bae31b0d305f82fc88`；文件只保存在被 Git 忽略的 `.build/models/`。

`model-manifests/chinese-clip-rn50.json` 把分发边界焊死为 `image_encoder`，文本塔和 tokenizer 仅允许构建时使用。仓库 MIT 文本、模型卡的 Apache-2.0 声明和标准许可证文本均已保存并校验摘要。该证据允许继续技术评测，但不是法律意见；对外分发仍需最终授权审查。

Task 2 的食物身份库已在 2026-07-19 升级为 `ModelSources/chinese-clip-food-labels-v2.json`：继续只含 owner-authored canonical ID、中文名、别名与类别，并新增人物、宠物、风景、文档、屏幕、日常物品和空餐具等非食物视觉负标签。食物/非食物使用不同的冻结中文 prompt；构建器会校验 ID/类别前缀并递归拒绝营养和份量字段。固定 RBT3 文本塔已生成 `CCLBV1` 单位向量库；二次完整生成得到相同 SHA-256。生成向量继续留在 `.build/models/`，仓库只保存 `model-manifests/chinese-clip-label-bank-v2.json` 的来源、维度和摘要。负标签让拒识分支可运行，但不替代授权对抗集的质量 Gate。

Task 3 已用固定 Python / PyTorch / Core ML Tools 环境导出纯视觉塔。FP16 对照的 PyTorch/Core ML 最低 embedding cosine 为 `0.9999935626780782`，编译模型加 v2 标签库为 77074808 bytes，超过 50 MB 预算。候选 int8 只量化参数量不少于 65536 的权重，采用 per-channel 非对称线性量化；最低 cosine 为 `0.9950830876471225`，编译模型加 v2 标签库为 39660136 bytes，转换一致性与包体 Gate 均通过。

全量 `linear_symmetric int8`、低阈值非对称 int8 和 8-bit k-means palettization 均因冻结一致性阈值失败而被放弃，没有为迁就模型下调阈值。Mac 的量化模型校验固定为 CPU-only，以规避已复现的 MPSGraph 编译器中止；产物本身不锁定运行单元，iPhone 真机仍须单独测量。精确路径、摘要、压缩配置和编译后大小见 `model-manifests/chinese-clip-coreml-variants.json`。int8 仍处于 **BLOCK**，尚未通过授权餐食质量和代表性真机 Gate。

Task 4/5 已实现纯 Swift cosine 候选排序与协议化的 Vision + Core ML 编排。每张图固定包含一次整图推理，最多再取三处通过面积和重叠检查的显著区域；图像使用固定上游的方形 bicubic 预处理，缩小时执行 antialias，归一化后的连续 Float32 张量一次写入 Core ML。向量统一归一化并跨区域去重。候选低于分数地板、Top-1/Top-2 间隔不足或非食物标签胜出时返回 `unknown`/`non_food`，禁止强猜。用户明确选择、本地条码映射、人工复核 OCR 依次优先于视觉候选。模型与标签库只从调用方给出的本地 file URL 加载；输出只含身份候选、证据类型和模型/标签/校准版本，不含像素、embedding、份量或营养字段。

Task 6 已把 `custom_core_ml` 真机证据接入统一 Schema。该引擎会额外强制模型 artifact SHA-256、标签库/校准版本、校准 manifest SHA-256、实际分数/间隔/候选阈值、安装后模型与标签字节数、精度变体和 1 秒完成率。FP16 与 int8 原始报告都明确拒绝压缩差值字段；差值只能由完整双报告的 `compare` 命令派生。Schema 同时拒绝私人数据集、UDID 和序列号形式的硬件标识，旧的系统模型报告无需新增这些字段，保持兼容。

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
| iPhone 17 Pro Max（iPhone18,2） | iOS 26.6 Beta | 不可用：`device_not_eligible` | 不可用：`sdk_not_supported` | OCR/分类/条码可用 | 2026-07-19 已重新签名安装并真机复测 |

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

宿主在源代码内显式开启固定合成基准，日志输出单行 `LOCAL_DIET_INFERENCE_BENCHMARK=<json>`。如果系统模型不可用，JSON 必须包含明确 `unavailableReason`；如果可用，`caseResult` 包含冷/热时延、峰值内存增量及前后温度。真机原始证据保存在 `runs/2026-07-18-iphone18-2-ios26-6-system-model.json` 与 `runs/2026-07-19-iphone18-2-ios26-6-system-model.json`，不含设备序列号、UDID 或私人饮食数据。

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

自定义视觉模型使用另一个完全隔离的 iOS 16 宿主。生成器只接受绝对路径；模型和标签必须位于本模块被 Git 忽略的 `.build/`，素材目录必须包含授权明确且 `containsPrivateUserData: false` 的 `dataset-manifest.json`。本地素材清单是 redacted 数据契约的 v2 扩展：至少 300 case，保留同一冻结 split/stratum/license/identity 元数据，额外加入 `file` 和 `allowedAliases`；每个文件必须留在素材根目录内。生成器校验全部 case，但宿主只打包并执行 test split，不访问相册、健康数据、生产饮食仓库或网络。

宿主是**原始证据采集器**，CLI 不再接受 `--fp16-delta`，FP16/int8 单次报告也不携带比较值。二者的身份 precision 差只能在两份完整 test report 产生后由确定性计分器派生。

```bash
cd mobile/modules/local-health-kernel
ruby scripts/tests/generate_food_vision_device_host_test.rb
ruby scripts/generate_food_vision_device_host.rb \
  --output .build/food-vision-host/LocalFoodVisionBenchmarkHost.xcodeproj \
  --team-id "$DEVELOPMENT_TEAM" \
  --model "$PWD/.build/models/chinese-clip-rn50/coreml/int8/ChineseClipRN50Image.mlpackage" \
  --label-bank "$PWD/.build/models/chinese-clip-rn50/chinese-clip-label-bank-v2.bin" \
  --fixtures "$AUTHORIZED_FOOD_EVAL_DIR" \
  --calibration-manifest "$FROZEN_CALIBRATION_MANIFEST"
```

证据宿主必须读取 `status: pass`、split 摘要与当前数据清单完全一致的 v2 校准 manifest，并把其中阈值焊进生成配置。仅验证工程可编译时可以显式传 `--compile-only`；该模式会在 App 启动时停在“evidence collection is disabled”，不会输出 benchmark report。

2026-07-19 已在重新连接的高端 iPhone 上用真实 int8 模型与 v2 标签资产完成 compile-only 宿主的签名构建、安装和启动。这只证明资产可被当前签名宿主打包并启动；compile-only 在加载和推理前停止，不能作为模型加载、时延、内存、温升、质量或隐私出站的运行证据。

宿主只输出一行 `LOCAL_FOOD_VISION_BENCHMARK=<json>`；报告使用不透明 case/fixture ID，不输出照片名、路径、像素或 embedding。其 JSON 可用以下命令直接验证：

```bash
backend/venv/bin/python scripts/test_local_diet_eval_contract.py
```

## Chinese-CLIP 质量集与校准状态

`chinese-clip-dataset-contract.json` 冻结了质量数据的准入边界：至少 300 个已授权、非私人 case；提交清单只保存不透明 case/fixture ID、授权状态、冻结身份、校准/测试 split 和分层，不保存图片、来源 URL 或文件路径。七个分层必须分别可报告：常见单品、复合菜、混合餐盘、包装食品/饮料、易混淆对、非食物对抗样本、退化/对抗输入。混合餐盘必须至少有两个期望身份，非食物不得带食物身份。

确定性计分器位于 `mobile/modules/local-health-kernel/scripts/score_local_food_vision_run.py`。它对每个 case 先去重预测，再计算身份 precision、missing-item、非食物拒绝、纠正次数、Top-1/Top-3、每个分层、crash-free、P95 热时延和 1 秒完成率。遗漏混合餐盘项目一定增加 missing-item，重复输出不能虚增 precision。质量阈值直接固定在代码中，CLI 不提供降低阈值的参数。

阈值搜索只读取 calibration split，最低分数/间隔不得低于 `0.5/0.03`；选定后必须冻结 calibration/test case ID 摘要，held-out test 只运行一次。FP16 与压缩模型必须使用同一 test split；压缩模型只有在绝对身份 precision 差异不超过 `0.02`、全部绝对质量门通过且模型加标签不超过 50 MiB 时才可选。

```bash
cd mobile/modules/local-health-kernel
python3 scripts/tests/test_score_local_food_vision_run.py
python3 scripts/score_local_food_vision_run.py score \
  --dataset "$AUTHORIZED_REDACTED_DATASET_MANIFEST" \
  --run "$CUSTOM_CORE_ML_RUN_JSON"

python3 scripts/score_local_food_vision_run.py compare \
  --dataset "$AUTHORIZED_REDACTED_DATASET_MANIFEST" \
  --fp16-run "$FP16_TEST_RUN_JSON" \
  --compressed-run "$INT8_TEST_RUN_JSON" \
  --variants-manifest model-manifests/chinese-clip-coreml-variants.json \
  --calibration-manifest "$FROZEN_CALIBRATION_MANIFEST" \
  --output .build/evidence/chinese-clip-variant-evidence.json
```

`compare` 会重新验证两份报告是否覆盖同一完整 test split，并核对模型 revision、v2 标签版本、artifact 摘要、实际安装字节数、校准 manifest 摘要和实际排名阈值；输出必须符合 `docs/evals/local-diet/chinese-clip-variant-evidence-contract.json`，包含所有输入文件摘要。缺任一报告、case 或 provenance 都会硬失败，不存在命令行手填差值的入口。

当前工作区没有授权的 300-case 中文餐食集，环境中也没有 `AUTHORIZED_FOOD_EVAL_DIR`。因此与 v2 标签集绑定的 `model-manifests/chinese-clip-calibration-v2.json` 明确保持 `blocked_pending_authorized_dataset`：`selectedThresholds`、两个 split 摘要、FP16/压缩质量报告和选择结果全部为 `null`。这不是实现失败，而是数据 Gate 的预期拒绝；不能用用户私照、许可不明的网页图片、转换 cosine 或合成元数据伪装质量证据。当前 `0.5/0.03` 只是测试宿主的保守 policy floor，不是已校准的生产阈值。

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
