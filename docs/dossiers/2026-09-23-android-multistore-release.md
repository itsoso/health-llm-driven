# Android 多市场正式发布

| 字段 | 值 |
| --- | --- |
| slug | android-multistore-release |
| 创建日期 | 2026-09-23 |
| 当前阶段 | S2 原生构建前置确认；内测配置已验证，正式商店准入未关闭 |
| 状态 | defining |
| 负责 | 用户（发布主体与资质）；Codex（工程准备与证据） |
| Controller | product-pipeline；safety-gate overlay |
| Run | `docs/_generated/harness-runs/e5d534881f60.jsonl`（本地，不提交） |
| 反馈环 | Android 安装验证 → Play 测试轨道 / 国内市场审核 → 公开商店回读 |

## S0 · 用户需求与授权

> 发一个 android 版本

> 可以 最后要发到应用商店 包括 google play 和中国的 android 市场

> 小巴健康 上架过 appstore 其他没搞过

用户随后对“有没有可用于上架的公司和营业执照”回答“没有”。
公司主体缺失已确认，不再重复询问公司全称。正式多市场发行的主体准入保持阻断；
本地开发/受限内部安装验证应与公开商店发行分开定义，不能把私下 APK 测试当作上架。

最新澄清：应用名称沿用“小巴健康”；Android 按首次发行准备，Play 与国内市场
账号/发行流程尚未办理。用户这句话不能证明 iOS 相关备案、软著或云端 Android
签名已经存在或不存在，均不得猜测。App Store 的既有上架不等于 Android 已获准入。

用户已同意补齐 Android 构建、签名与发布流程，并要求最终正式上架。
这不是仅导出测试 APK，也不以 OTA、上传成功或审核提交代替正式可下载。
不自动注册付费账号、购买服务、生成替代已有签名、变更法律主体、提交虚构资质，
也不借用 iOS/后端的一次性发布权限。既有并发后端发布由其原任务负责。

## S1 · 源码与现状证据

### Correction Block · 2026-09-24 内测优先

- 用户对“先完成可直接安装的内测 APK，正式商店另行准备”回答“好”。
  本修正只允许内部候选准备，不豁免原正式多市场 G2 BLOCK。
- 内测配置沿用 `life.executor.health.preview`，明确 Preview 显示名；
  APK 为 standalone release 配置，非 dev-client，不依赖 Metro。
- 内测候选关闭 OTA，防止安装后改变受验代码；不变更 production/iOS 配置，
  不生成或替换正式签名，不调用商店 submit、不部署后端。
- S4/S5：先添加失败配置测试 → 专用 Android 内测 profile/隔离配置 →
  配置回归、Android JS 导出、原生 prebuild → SDK/签名/安装验收。
- 内测配置实现 G2: PASS；原生构建/分发仍需工具链、候选签名及 G3/G4 证据。
  本机发现 JDK 26 和 11，未发现 Android SDK/Android Studio；SDK 安装和许可
  已单独请求用户确认。不能把配置测试通过宣称 APK 交付。
- 只读核验远端 main `05b6e4d396084103975c43e4a5fc4d044d8e66da`，CI
  `35885497343` success；相较本地前向 8 提交，无 mobile 变更。
  发布前仍须更新干净基线并重验，不上传当前混有他人 Dossier 改动的工作树。
- 验收：profile 明确 APK、Preview 包名/名称、禁用 OTA；production 保持不变。
  原生验收另需 manifest、签名指纹、API/ABI、冷启动/登录/核心路径、覆盖升级；
  Android 推送、Health Connect、iOS 专用 PCM/Watch 未验证，不承诺支持。
- 原生构建前置未满足，父流程回到 S2；不是一边保留正式 G2 BLOCK 一边进入
  正式交付。内测配置准备是已授权的窄范围产物，后续签名/分发仍未启动。

### 内测配置验证证据 · 2026-09-24

- 用户已明确同意安装官方 Android SDK 并接受许可；开始安装兼容 JDK 17 和
  官方命令行工具。许可确认阻断解除，工具链安装、原生编译和安装验收仍待结果。
  不把该授权扩展到付费账号、正式签名更换或商店提交。
- 已安全 fast-forward 到 `05b6e4d396084103975c43e4a5fc4d044d8e66da`，
  其真实 CI `35885497343` success；保留另一任务的前端恢复 Dossier 改动。
  本轮配置单独固定本地提交供 G4 评审，不自动推送或执行现有生产 publisher。
- 原生依赖只读预检：API/build-tools 36/36.0.0、NDK 27.1.12297006、CMake
  3.22.1；地图未配置 Android Google Maps key、PCM 仅 iOS、系统语音依赖设备服务，
  需在候选能力说明与验收中保留，不宣称 Android/iOS 完全等价。

- 先增测试：9 个新增用例按预期失败（缺 profile、名称/OTA/错误配置隔离）；
  实现后 `app-config.test.ts` 35/35 通过，production 既有配置回归通过。
- `mobile/eas.json` 增加 `android-internal`，继承 preview，明确 standalone APK；
  `mobile/app.config.ts` 仅该候选使用 Preview 名称、关闭 OTA 和后台定位能力，
  拒绝 production/development、iOS EAS 构建及额外 Watch/Siri/Rokid 开关。
- `tsc --noEmit` 通过；Android `expo export --platform android` 通过，生成 Hermes
  bundle。未读取 `.env`，未上传制品，不把 JS 导出当作 APK。
- `CI=true bash scripts/run-all-tests.sh --mobile` exit 0：311 suites、3026 tests
  通过，1 skipped，Mobile typecheck 通过。不是全栈集成/精确候选远端 CI 证明。
- 初次结构闸发现父 Dossier 同时声明交付阶段与正式 G2 阻断；已如实回到 S2
  原生构建前置确认，保留全部阻断，不修改校验器。再次 `validate.py`：system-map、
  Dossier consistency、Skill governance 全部通过；`git diff --check` 通过。
- 临时目录 `/tmp/reva-android-internal.hnZIVP/mobile` 由 HEAD tracked mobile 加本次
  两份配置复制生成；共享本机 node_modules，仅作构建勘察，**不是可信签名隔离区**。
  `expo prebuild --platform android --no-install` 通过，确认 native app name 为
  小巴健康 Preview、applicationId 为 `life.executor.health.preview`、updates disabled。
- 生成工程默认仍指向 debug keystore，不能交付为正式签名。原生 Gradle 编译、
  安装、签名/升级验证均未执行；预构建也提示缺 expo-system-ui，尚未证明主题一致性。
  未引入正式 Android publisher，未借用 iOS/OTA/后端发布权限。

本地检查基线 `1f4ff88a4e99fff07f1af6c5f90a4156f7d4d737`。
远端 `b9511a62b38fbddbf00963efd2445ab98bdab857` 在前序只读检查中 CI
`35874063101` 已通过；两者比较为前向 6 个提交，差异仅后端、测试和相关文档，
本次所查 Mobile / 发布入口未变化。此记录不作为未来发布的实时主干证明。
保留工作树中原前端恢复 Dossier 改动；没有合并、推送或触发原生构建。

- `mobile/app.json`：应用版本 1.3.4，Android 包名 `life.executor.health`。
  是否已有同包名线上应用、其 versionCode 与签名，仍须账号侧核验。
- `mobile/app.config.ts`：production / preview / development 的包身份不同；
  已有 Android App Links 配置。不能把 preview 包上传为正式应用。
- `mobile/eas.json`：production 有 Android 版本自增，但缺少明确分开的
  Play AAB / 国内正式 APK 构建合同；submit 配置只有 iOS。
- `.github/workflows/trusted-release.yml`：原生 job 为 iOS；现有声明并不授予
  Android 构建/上传权限。注册表也没有 Android terminal，必须受审补齐，
  不能把 Android 当作 mobile-testflight 或借 OTA 绕过原生闸。
- `scripts/release-tools/package.json` 已锁定 EAS CLI，可评估复用依赖锁；
  不把本机同 UID 开发目录直接执行的发布脚本视为可信签名环境。
- `mobile/hooks/useNotifications.ts` 的远程 token 注册明确只支持 iOS，
  `mobile/services/notifications.ts` 绑定的是 `/notification/bind/ios`。
  Android 推送需独立设计、测试与隐私评审；不能把 FCM token 发给 APNs 接口。
- `mobile/services/appleHealth.ts::isHealthKitAvailable` 只在 iOS 为真。
  Android 首版不能宣传 Apple Health/Watch 原生读取，也未证明 Health Connect 支持。
- `docs/release/app-store/submission-pack.md` 是旧 iPhone 候选材料，不能沿用其
  ready 标记、截图或 iOS 专属能力作为 Android 证据。公司简称不是法人资质证明。
- `frontend/src/app/privacy/page.tsx` 与账号删除 runbook 可作审计起点；
  App 内删除申请不自动证明 Play 要求的网页删除申请路径已经验收。
- `mobile/assets/rokid/rokid-pushup-glasses.apk` 是眼镜端制品，不是手机发布包。

System Map 不索引 `mobile/eas.json`；已回到配置、源码及邻近测试调查，
运行完整 `system-map-check.sh` 通过。没有执行含凭据的 EAS CLI 或读取私钥。

## G1 · 准入

裁决: PASS。用户明确要求 Android 正式发行，按 infrastructure 分类；不新增医疗行为。

- first_user_fit：让 Android 用户通过正式渠道安装现有日常健康产品。
- core_loop_step：Mobile 执行与复盘；first_class_objects：沿用 HealthAgendaItem、
  ExecutionEvent、WriteIntent、SafetyGuardian，不另建产品对象。
- target_surface：Android Mobile 与发行基础设施；source_of_truth：认证后端数据、
  固定提交、签名证书指纹、同候选验收、各市场真实发布状态。
- safety_level：privacy_sensitive / medical_boundary；autonomy_tier：manual_confirm。
- prescription_or_causal_verdict：none；claim_hedging：hedged。
- evidence_provenance：源码、构建产物、官方政策、授权开发者控制台。
- verification_window：每个候选构建及每个市场上架后；success_metric：可找到并安装
  精确候选，核心路径通过，升级不丢数据；不以“提交审核”作为完成。
- added_user_burden：主体、资质、密钥保管及账号授权确认，属于发行所必需。
- smallest_end_to_end_slice：受控候选 APK 安装 → 同源 Play AAB 测试 → 分市场正式审核。
- non_goals：不改健康数据；不替代医疗监管判断；不默认扩展 HarmonyOS NEXT 原生适配、
  新支付、广告 SDK、后台定位或新健康数据接入。
- stale_surface_to_remove：无；spec_required：正式跨渠道发布/签名状态合同实现前需要。

## G2 · 当前阻断与必要决策

裁决: BLOCK。定义环可继续；不得先生成不可逆身份或直接上传。

已向用户询问：

1. 已确认没有公司/营业执照。待决策：正式发行所需合法主体如何落实；不自动注册、
   借用或购买他人账号。Google Play 当前健康功能应按组织账号路径准备，最终分类
   须如实核验，不通过隐藏功能或改成工具类规避审核。
2. `[NEEDS CLARIFICATION: 国内是否首批覆盖华为、小米、OPPO、vivo、应用宝]`
3. `[NEEDS CLARIFICATION: APP 备案、软著、既有 Android 包名与正式签名是否已有]`

2026-09-23 公开 App Store 页面核验：应用记录可在美区找到，开发者展示为个人姓名，
不将该展示当作法律主体类型的最终证明，也不把个人姓名写入仓库。
中国区直接页面与 lookup 本次未能访问，不能据此断言中国区已上架或不存在备案。
来源：[现有 App Store 页面](https://apps.apple.com/us/app/id6763569720)。
主体有无及 Android 账号开通状态均已澄清，不再重复询问。
国内手机 APK 各市场个人主体准入仍待逐项验证；搜索到的快应用或手表规则
不能用来断言手机 APK 一定可上架或一律不可上架。

补充待核验：Play 分发国家/地区、隐私联系人和审核账号；是否付费及有无订阅；
已有签名证书指纹与备份归属；中国/海外服务可达性和数据处理披露。
只询问状态和公开主体资料，不要求在聊天中发送密码、私钥或 service-account JSON。

推荐保留正式包身份，但以既有商店记录为准；同包跨商店更新应先固定应用签名策略。
区分 app-signing key 与 Play upload key，不能把两者误当同一身份。
华为 Android 分发与 HarmonyOS NEXT 原生发行需要单独核实，不承诺 APK 覆盖后者。
国内厂商推送方案与额外 SDK 的个人信息处理，不在未确认时自动引入。

## 官方要求核对（2026-09-23）

以下为准备项，不是法律意见、资质裁决或已满足声明；提交时复核官方页和控制台。

- Google Play：新应用以 AAB / Play App Signing 规划；同签名跨市场分发时，
  先选择可保留、备份的应用签名方案。参见 [Android 签名说明](https://developer.android.com/studio/publish/app-signing)
  和 [App Bundle FAQ](https://developer.android.com/guide/app-bundle/faq)。
- 当前官方 target API 页面写明手机新应用/更新自 2026-08-31 起要求 API 36；
  必须检查最终 manifest，不凭 Expo 版本推定。参见
  [Play target API 要求](https://support.google.com/googleplay/android-developer/answer/11926878?hl=en)。
- 原生 `.so`、ZIP 对齐与 16 KB 页兼容需在真实构建及运行环境检查，不能用 JS 测试替代。
  参见 [Android 页大小兼容](https://developer.android.com/guide/practices/page-sizes)。
- Play 账号类型需按实际健康功能核对；官方将 Medical / Human Subjects Research 等
  健康服务列入组织账号要求，组织通常需要 D-U-N-S。不能直接默认个人账号可提交本产品。
  参见 [账号类型](https://support.google.com/googleplay/android-developer/answer/13634885?hl=en)。
- 需按真实能力填写 Health apps declaration、Data safety 和权限用途，提供公开隐私政策；
  不把本应用声明为无健康功能。参见 [健康声明](https://support.google.com/googleplay/android-developer/answer/14738291?hl=en)
  和 [健康内容政策](https://support.google.com/googleplay/android-developer/answer/16679511?hl=en-GB)。
- 有应用内注册时，账号及关联数据删除需覆盖 App 内与外部网页申请路径，并如实披露保留范围。
  参见 [Play 删除账号要求](https://support.google.com/googleplay/android-developer/answer/13327111?hl=en)。
- 中国发行需要核实 APP 备案及主体/应用名称一致性；医疗等分类的附加资质按实际功能和
  市场规则判定，不把所有市场的软著要求一概而论。参见
  [工信部 APP 备案通知](https://ahca.miit.gov.cn/xxgkhlwgl/wzgl/art/2023/art_00c93cb439bd4943a0d8ab569561349b.html)、
  [小米 APP 备案指引](https://dev.mi.com/xiaomihyperos/documentation/detail?pId=1739)、
  [小米名称一致性指引](https://dev.mi.com/xiaomihyperos/documentation/detail?pId=1798)。
  工信部正文直连本次超时，使用其官方搜索摘要和小米官方指引交叉核对，正式办理前重读原文。
- 华为需分别核对当前可选平台、发行区域与行业资质，参见
  [华为分发入口](https://developer.huawei.com/consumer/cn/appgallery/devstart/)
  和 [资质说明](https://developer.huawei.com/consumer/cn/doc/harmonyos-center-guides/50111-overview)。
  OPPO / vivo / 应用宝逐项控制台材料与当前细则尚未验证，不冒充已调研完成。

## 后续交付顺序（待 G2 决策，不表示已启动）

| 阶段 | 产出与通过条件 |
| --- | --- |
| 发布合同 | PRD/spec/计划；明确渠道、主体、签名保管、版本号与候选状态；受审新增 Android terminal |
| Android 适配 | 登录、文字/语音、图片、饮食编辑/份额、长图、足迹、拒绝权限/后台恢复；推送及健康源边界明确 |
| 受控构建 | 固定干净 SHA、锁定工具链、隔离构建与签名权限；AAB/APK 校验包名、版本、证书、API、debuggable、ABI/页兼容 |
| G3/G4 | 相关 CI-mode 集成、精确主干真实 CI、独立隐私/签名评审；Android 安装、覆盖升级及无 GMS 环境验证 |
| 材料 | Android 实机/模拟器真实截图，中英文能力文案；主体、备案、SDK/权限清单、删除 URL、健康声明、审核访问 |
| 分渠道提交 | Play 测试→所需生产准入→正式发布；国内各渠道上传、审核和驳回修复独立记录，不重复未知上传 |
| G5/G6 | 每个市场记录 app/version/build/hash、审核结果、实际可下载页面和安装验证；不能汇总成假“全部完成” |

默认沿用模拟器优先验收偏好；iOS 模拟器通过不能代替 Android 验收。
不支持的第三方交接、厂商推送或硬件项目标明未验证，必要时由用户明确接受范围或补验证。

## G3 / G4 / G5 / G6

裁决: BLOCK。内测配置已有实现与静态验证，原生编译/安装/签名验收未完成；系统地图通过不等于 Android 测试通过。
无正式签名核验、无 AAB/APK 构建 ID、无商店上传、审核或公开上架证据。

本次新鲜准备验证：Mobile `app-config` 与 `useNotificationsPermission`
两组既有测试 27/27 通过（CI=true）；权限测试使用 iOS mock，不能证明 Android
推送可用。Dossier 一致性 144 份通过，Skill 治理与 `git diff --check` 通过。
上述 27 项为先前准备证据；本轮配置、JS 导出、原生 prebuild 的新鲜证据见 Correction Block。
本轮改动限本档案、内测配置和配置回归测试；固定本地提交用于独立审查，未推送或分发。

## 恢复点

### 2026-09-24 SDK 许可授权后的续跑证据

- 用户回复“同意”，明确授权安装官方 Android SDK 并接受所需许可。已安装并验证
  JDK 17、Android 命令行工具 15859902、Build Tools 36.0.0、CMake 3.22.1；
  官方命令行工具 ZIP 的 SHA-256 与官方公布值一致。Gradle 9.0.0 下载首次中断，
  使用断点续传恢复后验证官方 SHA-256，通过版本检查；没有跳过完整性检查。
- API 36、NDK 27.1.12297006 及 Android 模拟器/系统镜像仍在下载，安装未全部完成。
  NDK 原 SDK Manager 下载已明确中止，改用官方 URL 的可恢复下载，待完整校验后安装。
  本轮不注册账号、不读取/更换正式签名、不调用商店上传、不部署后端或 OTA。
- 内测配置固定提交 `3e18eb5c035188ff2f4e09780deada57a68445f6` 经独立审查 GO，
  仅限配置与无发布凭据的本地准备；不代表签名、分发或商店 G4 通过。
- Android 未配置地图 key 时不挂载原生地图，保留其他运动数据并显示不可用提示。
  先观察 15 项失败，再通过 51 项定向测试及类型检查；固定提交
  `d52151052d1f03d3925593aefb67f48a7484c682` 的地图变更经独立审查 GO。
  capability 只证明配置存在，不证明 key 有效、GMS 或中国网络可达。
- 同仓库有另一任务提交后端/聊天变更。工作区混合测试曾失败并中止（退出 130），
  不作为候选证明。新快照由精确 `d52151052d1f03d3925593aefb67f48a7484c682`
  导出 tracked Mobile 与 Watch 构建辅助文件，包含该提交祖先中已提交的聊天变更；
  不继续追踪后续 HEAD，不把本任务独立审查范围扩展到另一任务的变更。
- 新快照 `/tmp/reva-android-candidate.QcECJ4` 的 Android prebuild 通过。
  按 CI 拆分执行 Jest：主组 308 suites / 2863 passed / 1 skipped；独立组
  ChatInputBar 75、chat 64、useAuth 33、GPS onboarding 7 项均通过，共 3042 passed；
  `tsc --noEmit` exit 0。这不是最终 APK 安装证明或精确远端全栈 CI。
- 首次原生依赖下载/编译仍在旧准备快照中进行，日志在
  `/tmp/reva-android-internal.hnZIVP/gradle-build.log`；仅作工具链勘察和缓存预热，
  不能把其制品作为新候选。后续必须对新固定快照重新构建。
- 新候选源 manifest 确认 Preview 包名、版本 1.3.4 / versionCode 1、OTA disabled；
  最终 merged manifest / APK 尚未检验。默认生成工程仍使用 debug keystore，
  尚未生成独立内测签名；没有 APK、安装/启动/升级、ABI/页大小通过证据。
- 该 Preview 默认仍连接生产 API，且保留共享 deep link；包名隔离不代表数据隔离。
  后续验收只用合成/专用测试账号，不修改真实健康记录。Android 推送、Health Connect、
  iOS 专属 PCM/Watch 仍不宣称可用。生成 manifest 的媒体/悬浮窗/备份等权限需在
  最终合并结果中审计，不能凭配置测试判定权限最小化已完成。
- 新增测试后的代码派生地图存在计数漂移，已运行生成器同步，不手写计数。
  `validate.py` 初次因 PATH 缺 Python 3.12 失败，补正确解释器路径后检测出地图漂移；
  生成后 system-map、Dossier consistency、Skill governance 均通过。
  模拟器原单连接下载已明确终止（退出 130），保留部分 ZIP 后从官方地址断点续传；
  ARM64 API 35 AOSP 系统镜像也按官方摘要下载，未安装完成、未创建 AVD。

用户已同意内测 APK 优先及 SDK 许可。继续完成官方组件下载和原生构建，再补独立
内测签名与 Android 验收。正式发行仍待主体/渠道/正式签名路径落实。
不能复用前端事故 run 或将其成功封存算作 Android 发布进展。

续跑更新（2026-09-24）：API 36 SDK Manager 安装 exit 0；NDK 官方 ZIP 完整下载，
SHA-1 `c70c9791b0d258858678f6df31c4319140e2926e` 匹配官方 metadata，解压安装至
SDK `ndk/27.1.12297006`，`clang --version` exit 0。原中断安装目录仅移动保留，
没有覆盖/删除既有完整 NDK。旧快照预热构建已明确中止 exit 130，确认其 daemon 退出，
现对 `d52151052d1f03d3925593aefb67f48a7484c682` 快照重新执行 arm64 release 构建，
日志 `/tmp/reva-android-candidate.QcECJ4/gradle-build.log`；完成状态待回读。
模拟器与 AOSP 镜像为优先保障构建下载已暂停，保留 ZIP 与 `.aria2` 续传数据；
此前 aria2 退出 7 表示未完成，不记成功。APK、独立签名与安装验收仍未完成。

当前恢复入口：固定候选 Gradle 构建仍在运行，React Native / Expo 多个插件编译通过，
`expo-updates-gradle-plugin` 阶段仍获取原生依赖，未出现终态；先回读上述日志和该进程，
不可重复并发构建。SDK/NDK 已完成后，模拟器 ZIP 已从原续传文件恢复下载，日志
`/tmp/reva-android-internal.hnZIVP/emulator-download-resume.log`；AOSP 镜像仍暂停。
无需再次请求 SDK 许可，不把后台进程存在算作构建成功，也不自动进行签名/分发。
