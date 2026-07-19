# Dossier: 本地优先私有模式与完全本地饮食

| 字段 | 值 |
|---|---|
| slug | `local-first-private-mode` |
| 创建日期 | 2026-07-18 |
| 当前阶段 | G2 Chinese-CLIP 探索性候选验证完成 |
| 状态 | 本地基线 PASS；Chinese-CLIP 手工确认候选 PASS；自动识别 BLOCK |
| 负责 | User / Codex |
| 反馈环 | iOS real-device spike / EAS-TestFlight / airplane-mode validation |

## Correct Course

- [x] Correction Block：真机证明系统模型不可通用依赖；G2 拆为本地基线与智能增强两个范围。
- [x] 2026-07-18 用户选定 Chinese-CLIP RN50 作为唯一首轮打包视觉模型；只分发视觉塔，文本塔仅用于构建标签向量。
- [x] 2026-07-19 Chinese-CLIP 八阶段 spike 已执行到裁决；工程与可重复性闸通过，授权质量集和代表性真机证据缺失，按规则保持 BLOCK，未接生产饮食页。
- [x] 2026-07-19 已按“识别质量 → 非食物拒识 → 证据链”顺序完成优化。复核固定 Chinese-CLIP revision 后纠正旧假设：官方预处理是 `Resize((224, 224), BICUBIC)`，不是等比中心裁切；实现现已匹配官方方形 bicubic 语义。v2 标签库加入本地非食物负类；FP16/int8 差值改为由两份完整冻结报告确定性派生。优化设计与实施计划见 `docs/plans/2026-07-19-chinese-clip-local-food-vision-optimization-design.md`、`docs/plans/2026-07-19-chinese-clip-local-food-vision-optimization.md`。本 correction 已完成 S3/S5 与预设备 G3，未改变既有 G2 BLOCK。
- [x] 2026-07-19 用户明确把目标收窄为“本地模型给候选、允许不精确、用户确认后再记录”。隔离宿主增加 `exploratory` 模式，不伪造 300-case 校准：高端 iPhone 用真实 int8 模型试跑 5 张非私人样图，炒饭、粽子、香蕉 Top-1 命中，椅子正确拒识，白米饭误判为非食物。该结果允许把 Chinese-CLIP 作为可选候选来源，不允许自动写入。

## S0 · 用户需求（逐字）

> 思考这个方向，能否让这个App增加一个本地模式，下载即可用，完全跑在本地，不需要注册，私有信息全部本地，只有调用大模型部分才走服务端？做出一些规划

> 按照第三种进行规划，另外也思考能否完全本地，甚至于连模型推理也走本地，换用一个很小的模型，解决饮食记录问题？

> 不用特别复杂的方式了，直接用Chinese clip就可以了，试试效果，不用那么精确，因为本地模型毕竟受限的。

- 谁用 / 解决什么 / 现在怎么绕过：隐私敏感的健康记录用户希望先在设备上获得完整饮食记录价值，而不是先注册并上传健康数据；当前只能登录后使用服务端真源路径。
- 锚点用户相关性：饮食是既定 Personal Health OS `Capture -> Confirm -> Review` 的高频入口，并已有人工确认和来源边界。

## S1 · Discovery（现状勘察）

- 已有可复用：
  - `mobile/hooks/useAuth.tsx`：当前 App 入口由 token 决定。
  - `mobile/app/_layout.tsx`：未认证直接渲染登录页，HealthKit 等根级能力受认证状态控制。
  - `mobile/services/api.ts`：HTTP 客户端从 SecureStore 注入 Bearer token。
  - `mobile/applib/queryClient.ts`：只提供短期查询缓存，不是长期本地真源。
  - `mobile/app/diet.tsx`, `mobile/services/diet.ts`, `mobile/hooks/useDietEstimate.ts`：已有照片/语音/文字饮食入口和服务端 API。
  - `docs/specs/active/2026-07-11-diet-capture-excellence.md`：已有草稿、校准、人工确认、幂等和来源不变量。
  - `backend/app/services/food_nutrition_lookup.py`：营养表确定性校准可作为端侧实现参考。
- 缺什么：本地身份、本地加密真源、仓储接口、端侧模型桥、隐私出站断路器、导出恢复、可授权的生产食物库。
- 硬约束：当前最低 iOS 16；Apple 系统模型只覆盖部分设备/系统；新增原生模块必须走新 iOS 包；端到端加密同步会阻止现有服务端直接计算明文 Health Twin。
- 外部平台证据：Apple Foundation Models、Vision 和 Core ML 官方文档，见设计文档引用。

## G1 · 准入裁决

- first_class_objects: `WriteIntent`, `ExecutionEvent`, `HealthTwin`, later `HealthAgendaItem`
- core_loop_step: `Capture -> Confirm -> ExecutionEvent -> local projection -> Review`
- target_surface / safety_level / autonomy_tier: Mobile+iOS native / privacy_sensitive / manual_confirm
- spec_required: yes，新用户行为、新认证边界、新本地写路径和隐私契约。
- smallest_end_to_end_slice: 无账号、无网络记录一餐，重启后仍可读取。
- stale_surface_to_remove: 对本地新用户而言，登录不再是唯一入口。
- **裁决**：PASS。
- 用户确认：2026-07-18 已确认采用第三种“本地优先 + 可选同步”，并同意完全本地饮食作为第一切片。

## S2 · PRD

- 链接：`docs/prd/2026-07-18-local-first-private-mode.md`
- Feature Spec：`docs/specs/active/2026-07-18-local-first-private-mode.md`
- 权威定位：`docs/prd/reva-personal-health-os-prd.md` 的数据自持、双轨录入与 Capture/Execution/Review 核心循环。
- 边界：不承诺照片精确称重，不第一期迁移完整 Health OS，不静默创建云账户，不打包未授权数据。
- 未决问题：无产品定义级未决问题；G2 技术阻断见下。

## S3 · 规划

- 设计：`docs/plans/2026-07-18-local-first-private-mode-design.md`
- 实施计划：`docs/plans/2026-07-18-local-first-private-mode.md`
- Chinese-CLIP 设计：`docs/plans/2026-07-18-chinese-clip-local-food-vision-design.md`
- Chinese-CLIP 独立实施计划：`docs/plans/2026-07-18-chinese-clip-local-food-vision.md`
- Chinese-CLIP 优化设计与实施计划：`docs/plans/2026-07-19-chinese-clip-local-food-vision-optimization-design.md`、`docs/plans/2026-07-19-chinese-clip-local-food-vision-optimization.md`
- 顺序：G2 spike -> 加密内核 -> 本地身份 -> 饮食仓储 -> 食物库 -> 离线记录 -> 端侧模型/Vision -> 出站断路器 -> 导出恢复 -> 新 iOS 包。
- 智能增强选择：`OFA-Sys/chinese-clip-rn50`，Core ML 只运行视觉塔；不再做 TinyCLIP 首轮对照实现。
- 长杆：Chinese-CLIP 权重许可锁定、Core ML 压缩质量、真实设备内存/延迟和中文餐食覆盖评测。

## G2 · 可行性 + 安全压测

- 评审方式：Codex challenge + Task 1 Swift capability spike + 本地存储/恢复威胁模型评审。
- Task 1 证据：
  - 新增可独立运行的 Swift Package 探针测试壳；先确认因探针不存在而 RED，再以最小实现转绿。
  - macOS 与 iOS Simulator 均通过 7 个能力契约测试；探针为系统模型不可用返回明确原因，不抛错、不静默走云。
  - 新增 opt-in 结构化文字推理基准；先确认因 benchmark 类型不存在而 RED，再实现 fixed synthetic fixture、guided generation、冷/热运行、10ms 峰值内存采样和 thermal state 采集。
  - 基准确定性测试覆盖不可用、冷/热时延、峰值内存、温度、JSON、模型错误和指标错误；内存采样失败硬失败，不会产生 0 MB 假证据。
  - macOS 完整 Swift Package 为 15 tests / 0 failures / 1 live test skipped；显式开启的 Mac run 返回 `device_not_eligible` JSON。iPhone 17 Pro Simulator iOS 26.4 测试通过，generic iOS 16 deployment build 通过。
  - Xcode 26.5 / iPhoneOS SDK 26.5 下，Foundation Models 多模态明确为 `sdk_not_supported`；当前照片路线只能是 Vision 或另行评测的 Core ML。
  - Mac 26.4.1：系统模型 `device_not_eligible`，Vision OCR/分类/条码可用。
  - iPhone 17 Pro Simulator / iOS 26.4：系统模型探针报告可用，Vision 可用；模拟器结果不外推到真机。
  - iPhone 17 Pro Max（iPhone18,2）/ iOS 26.6 Beta：已用独立签名宿主在真机运行；2026-07-19 重新连接后复测仍返回系统模型 `device_not_eligible`，Vision OCR/分类/条码可用。用户确认开启飞行模式后，USB 控制保持在线，合成能力宿主仍离线输出同一明确不可用报告。非私人原始报告：`docs/evals/local-diet/runs/2026-07-18-iphone18-2-ios26-6-system-model.json`、`docs/evals/local-diet/runs/2026-07-19-iphone18-2-ios26-6-system-model.json`、`docs/evals/local-diet/runs/2026-07-19-iphone18-2-ios26-6-airplane-mode-system-model.json`。
  - Swift Package 独立 test target 无 iOS host，真机 XCTest 会被 Xcode 拒绝；已补充经过测试的临时 iOS App project 生成器和只读合成基准宿主，避免把测试壳接入产品 App。
  - 详情与评测 Schema：`docs/evals/local-diet/README.md`、`docs/evals/local-diet/on-device-eval-contract.json`。
- 已焊进规划的硬阻断：
  - 生产食物数据库必须来自可再分发来源，并逐行保存来源/version；G2 已选定 USDA FoodData Central CC0 子集，现有人工 seed 仍禁止进入生产包。
  - 本地保险库必须要求设备密码；使用 App 生成的 256-bit 恢复密钥、Keychain `WhenPasscodeSetThisDeviceOnly`、完整文件保护、HMAC blind index 和空库原子恢复。用户于 2026-07-18 已确认这两个产品取舍。
  - 系统模型不可用必须降级到确定性/手工，而不是强制云端。
  - 自定义视觉模型必须经过纠正成本、内存、温升和下载体积 Gate。
- Chinese-CLIP 已取得的独立 spike 证据（2026-07-19）：
  - 固定模型 revision `717ba215769231e53b9b7c6b9d329b9cc5944418`、代码 revision `31863c707501bf1605d36842f43deb78793dbc5d`、checkpoint SHA-256 与代码/模型许可证；分发边界只含 image encoder。
  - v2 owner-authored 中文身份标签已生成 1024 维单位向量库，并新增人物、宠物、风景、文档、屏幕、物品与空餐具等本地非食物负类；构建器拒绝营养/份量字段，二次生成摘要一致。
  - FP16 Core ML/PyTorch 最低 cosine `0.9999935626780782`；选定 int8 最低 cosine `0.9950830876471225`。v2 标签加入后，FP16 编译模型加标签为 77074808 bytes，仍超预算；int8 为 39660136 bytes，仍通过 50 MiB 包体 Gate。
  - 纯 Swift 排序、EXIF/官方方形 bicubic 224×224 预处理、Vision 显著区域、Core ML 本地加载与连续 Float32 张量写入、条码/OCR/人工选择优先级、未知/非食物、取消/内存/温控停止和无敏感输出均有确定性测试。iOS 16 通用 package 与只编译隔离宿主均已用真实 int8 artifact 构建成功；只编译宿主明确禁止产生质量报告。
  - 自定义模型原始报告会绑定模型、v2 标签、校准 manifest 摘要、实际排名阈值和安装字节；FP16/int8 原始报告都不接受自由差值。只有完整冻结 test split 的双报告才能生成符合独立 Schema 的派生变体证据。
  - 2026-07-19 优化后预设备闸为：模型来源 10 tests、标签 15 tests、导出 10 tests、计分 10 tests、证据 Schema 9 tests、Swift 37 tests（1 个显式真机测试 skipped）、Ruby 合成宿主 2 tests / 20 assertions、Ruby 视觉宿主 7 tests / 63 assertions、generic iOS 16 build、真实 int8 artifact 的 compile-only 宿主 build、doc-drift 与 dossier consistency 全部通过。
- Chinese-CLIP 仍缺的不可替代证据：
  - 工作区和环境变量中没有至少 300 个已授权、非私人中文餐食 case；因此校准/测试 split 摘要、held-out 质量和 FP16-to-int8 identity precision delta 均不存在。`chinese-clip-calibration-v2.json` 为 fail-closed BLOCK，未选择阈值或变体。
  - 2026-07-19 iPhone 17 Pro Max 已重新连接：合成能力宿主完成签名构建、安装和运行；带真实 int8 模型与 v2 标签资产的 compile-only Chinese-CLIP 宿主也完成真机签名构建、安装和启动，但该模式按设计禁止生成质量报告。授权质量集和 pass 校准仍缺失，因此没有 Chinese-CLIP 推理数据；低/中端 iPhone 仍缺失。内存 ceiling 不能从单台高端机或 compile-only 启动猜测，Schema 保持未设值。
  - 2026-07-19 已完成用户确认飞行模式下的宿主启动：合成能力宿主离线输出明确不可用报告；Chinese-CLIP compile-only 宿主离线启动并保持进程存活，观察窗口内没有输出 `LOCAL_FOOD_VISION_BENCHMARK`。但 compile-only 在模型加载和推理前停止，因此不能证明模型离线加载或推理；真机抓包零照片/crop/embedding/candidate 出站、长时间温升和推理中途取消仍未执行。
  - 当前真机此前也没有进入系统模型推理，因而系统模型增强同样没有可诚实记录的冷/热时延、峰值内存和温升。
- Chinese-CLIP 探索性真机结果（不属于正式质量 Gate）：
  - 新增 `--exploratory` 隔离宿主模式：只接受非私人、许可状态明确的本地 fixture；无需伪造 pass 校准；固定使用 `minimumScore=-1`、`minimumMargin=0` 展示候选，并在输出中强制标记 `notForQualityGate: true`。
  - iPhone18,2 / iOS 26.6 Beta 上，真实 int8 模型与 v2 标签库完成 5 张样图推理：炒饭、粽子、香蕉 Top-1 命中，椅子正确为 `non_food`，白米饭误判为 `non_food`；单张端到端时延为 1628.84–3312.21ms，包含 Vision 显著区域与最多四次 image tower 运行。
  - 原始非私人结果：`docs/evals/local-diet/runs/2026-07-19-iphone18-2-chinese-clip-exploratory.json`。报告不含图片、路径、像素、embedding 或设备唯一标识。
- 已解除的阻断：
  - 数据授权：USDA FoodData Central 官方许可明确为 public domain / CC0 1.0；使用 Foundation Foods/SR Legacy 固定版本子集，App 运行时不取数。
  - 安全设计：设备密码为前置条件；独立派生 record/index key；恢复密钥为随机高熵而非用户弱口令；只恢复到空库；删除 crypto-shred；完整设计见 `docs/plans/2026-07-18-local-first-private-mode-design.md`。
- **待拍板分叉**：无；用户已接受旧设备的严格本地照片能力可能较弱。
- **裁决**：**范围化 PASS / BLOCK**。
  - 本地饮食基线（无注册、加密本地存储、手工/确定性记录、Vision 可选）：**PASS**，允许进入 Task 2 加密内核。
  - Chinese-CLIP 作为最多三个候选、始终人工确认、失败可手工输入的本地辅助：**PASS（产品方向）**；不得自动创建饮食记录，不推断份量或营养。
  - Chinese-CLIP 自动识别或免确认写入：**BLOCK**，仍须通过正式质量、纠正成本、包体和代表性真机性能 Gate。
  - 该拆分不是降低标准：智能增强从首版保证路径移除，运行时不得静默走云；基础路径可在模型完全不可用时成立。
  - 2026-07-19 Chinese-CLIP 最终独立裁决：provenance/license、转换 parity、包体和工程失败模式 **PASS**；授权质量、压缩质量差值、分层真机性能与物理隐私检查 **BLOCK**。总裁决按最弱维度为 **BLOCK**，不是 FAIL，也不允许生产集成。

## S4 · 研发任务分解

- 实施任务见 `docs/plans/2026-07-18-local-first-private-mode.md`。
- Chinese-CLIP 独立 spike 已按 `docs/plans/2026-07-18-chinese-clip-local-food-vision.md` 完成八阶段实现与裁决；结果为 BLOCK，继续不得接入生产饮食页。
- 用户已授权把 Chinese-CLIP 作为低风险、手工确认候选继续纳入本地饮食实施；该授权不包括自动写入或营养/份量推断。
- G2 已授权进入 Task 2 加密 Local Health Kernel；智能增强继续留在独立评测支线。

## S5 · 实现

- 产品实现未开始；已完成不读写健康数据的 G2 capability probe、系统模型合成 benchmark、Chinese-CLIP Core ML 纯本地引擎和隔离真机宿主。探索性宿主已经真实加载 int8 模型并推理非私人样图；它仍是测试壳，不进入生产 App、不读 Local Health 数据、不访问相册、不提供云端 fallback。

## G3 · 测试闸

- Chinese-CLIP 独立 spike、本轮优化与探索模式：PASS（Swift 37 tests / 1 skipped；视觉宿主生成器 8 tests / 81 assertions；generic iOS 16 与签名真机构建成功）；完整产品计划 G3 未开始。

## G4 · 安全闸

- 必须触发：认证边界、健康数据本地写入、照片、模型出站、加密恢复。
- Chinese-CLIP 宿主静态边界与错误/取消测试：PASS；用户确认飞行模式下的宿主离线启动：PASS（只到启动级）；模型推理期间真机抓包与物理隐私：BLOCK。完整产品 G4 未开始。

## S6 · 部署

- 路由：新增原生模块，必须 EAS/TestFlight 或本地 QR 新包；不能只 OTA。
- 未开始。

## G5 · 部署健康闸

- 未开始。

## S7 · 上线验证

- Anchor：真机飞行模式首次启动、首餐确认、重启读取、模型不可用、导出恢复、网络抓包零违规出站。
- 未开始。

## G6 · 验证闸

- 需要用户真机确认。
- 未开始。

## S8 · 沉淀

- 饮食切片通过 G6 后再决定是否扩到身体测量、症状、HealthKit、Agenda 和 E2EE sync。
