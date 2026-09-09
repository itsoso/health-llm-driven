# Dossier: 饮食修正重算与餐食大图滑动关闭

| 字段 | 值 |
|---|---|
| slug | `diet-correction-recalculation-photo-dismiss` |
| 创建日期 | 2026-08-20 |
| 当前阶段 | G5 已通过；G6 真机用户路径待确认 |
| 状态 | deployed_device_smoke_pending |
| 负责 | Codex + 用户 |
| 反馈环 | Backend focused tests + Mobile Jest/TypeScript + production OTA after Gates |

## 2026-09-09 · 图片轻触关闭补充（仅本机实现）

- 用户截图对应 MealPhotoGallery：已有纵向滑动关闭，但照片没有轻触入口。
- 图片页改为可轻触关闭，图片周围页内留白也可点；保留上下拖动关闭、横向翻页、
  短拖动回弹、右上角关闭及 Android 返回。拖动标记维持到下一次触摸，防止松手误判轻触。
- 不改变图片权限、存储、上传、健康记录或分享写路径；此块不改变原 G6 真机待确认状态。
- TDD：新增轻触/拖动误触回归和提示更新，首轮 3 failed；实现后卡片注册/交互 93 passed，
  TypeScript 检查通过。手势证据为组件事件回归，不宣称手机实体手势已验证。
- 实现阶段未 commit、push、OTA 或发包；随后用户要求发布并确认改走 TestFlight 新包。

### 本次 TestFlight 发布准备

- 用户已确认发布图片关闭修复；production OTA 继续冻结，不包含正式 App Review 提交。
- 新鲜 CI-mode Mobile 全量回归：304 suites、2819 passed、1 个既有 skipped，71.662 秒；
  TypeScript 检查通过。基础 App Store release-pack / iOS 配置检查通过。
- 本机 ASC 私钥检查未通过；本轮采用既有 EAS 托管签名及 Submit API Key 路径，
  不把本机凭据缺失或历史上传成功当作本次上传证明。最终送审材料闸不在本轮范围。
- 发布执行器与已独立 G4 GO 的 `30af34486` 字节一致；本轮不修改发布授权协议。
  仍须完成新鲜发布集成闸、精确 main CI、临时发布授权、构建/上传及厂商终态核验。

### 发布前依赖阻断及兼容补丁

- 图片交互修复固定于 `f23fc9d2d`，尚未 push。新鲜 OSV 闸检出 XML 八项高危公告与
  YAML 两条受影响版本路径，发布暂停；按 safety-gate 补充独立复审，不新增例外。
- 仅升级既有 override：xmldom 0.8.13 → 0.8.15（含旧 alias）、js-yaml
  3.15.1 → 3.15.2 / 4.3.1 → 4.3.2；不升级 Expo 或原生 SDK。
- 恶意 XML 序列化与两条 YAML merge 限额用例首先 3 RED，升级后 5/5 PASS
  （含两种正常 plist roundtrip）。首轮兼容性断言忽略了 Expo 的 null-prototype
  字典，修正为比较数据后正常用例在旧依赖上通过，未以补丁掩盖测试问题。
- 补丁后 CI-mode Mobile 全量 305 suites / 2824 passed / 1 既有 skipped / 64.944 秒；
  TypeScript、针对新测试的 lint、Expo 配置及既有图片解析补丁 2/2 全通过。
- 新鲜发布集成闸 865 passed / 52 subtests / 344.38 秒 / exit 0；执行器与发布测试源码
  未改变。OSV 闸通过，保留原有两项限期 image-size 例外；npm 全树与 production 审计
  各 15 项（1 low、9 moderate、5 high 传递路径），high 均归于上述既有例外，不宣称零漏洞。
- 待固定依赖提交独立 G4 GO、精确 main CI 和本次临时 Expo 发布令牌授权；尚未构建或上传。

### 2026-09-09 · 继续模拟审核与证据纠偏

- 固定 `501cd647502918500459e91ace1bf3bc5ae43664` 的独立 G4 GO 已完成：
  98 项聚焦测试、四条真实 plist 消费路径、alias 安全拒绝及 OSV/图片补丁回归通过。
- 该 SHA 的 CI `34289329318` 为 FAILURE，不能发布：release-invariants 仍断言旧
  YAML 3.15.1 / 4.3.1；frontend-build 检出 Next 16.2.11 的两项 CRITICAL
  `GHSA-2xp9-vwfh-vxw4` / `GHSA-p293-qw3h-jr36` 与 sharp 0.35.3 的 HIGH
  `GHSA-rgj7-g3m4-5g8c`。本轮仅修正遗漏的 Mobile 版本断言并增加两项 XML pin
  约束，24 项文件级回归通过；本任务未修改 Web 依赖，远端主干红时不 push/deploy。
- 纠偏：上一节 865 项集成在依赖补丁写入前已启动，不能绑定最终候选。此次冻结
  Mobile 测试/依赖输入后重新执行完整 CI-mode 集成：865 passed、52 subtests passed、
  438.94 秒、exit 0。日志 `/tmp/xiaoba-photo-corrected-release-integration.log`。
  收尾发现工作树另有 frontend package/lock 并发改动，来源未确认，保留且未暂存；
  本次证据不覆盖该 Web 候选，也不替代最终固定 revision 的完整 CI。
- 新建独立原生 QA 制品：真实组件源码来自上述 SHA；复用兼容的 iOS Simulator 原生壳，
  仅更换 QA entry、合成路由和本机图片服务器，非正式 IPA。未改主 App、登录、草稿、
  生产 API 或健康记录。图片来自仓库图标，不验证食物识别。
- iOS 26.5 XCTest 6/6 PASS、0 failure、81.40 秒：编辑取消、分享复盘回 root Agent
  并再次打开、图片单击关闭/重开、上下两向关闭、横向翻到第 2 张且不误关、短拖回弹
  后轻触关闭。截图人工查看确认真实图片加载、1/2 → 2/2。证据：
  `/tmp/xiaoba-photo-native-qa.psDbTt/first.xcresult`；源码与运行日志留同目录。
- 审核边界 111 PASS（医学来源、AI 同意与外发守门、发布资料校验）；SQLite 跳过的
  2 项授权并发语义在独立 PostgreSQL 17 / UTF8 临时库补测 2/2 PASS，无跳过。
  首轮本机默认数据库连接失败、临时库 SQL_ASCII 不支持中文注释，均在测试收集前失败；
  明确切换隔离内存库及新建 UTF8 测试库后验证，未改产品来绕过。
- Mobile AI 同意/分享额外 29/29 PASS，39 个设置路由验证通过；基础审核/config 闸
  PASS，线上隐私页 HTTP 200。Apple 当前 1.4.1 与 5.1.2(i) 的医疗方法披露、就医提醒、
  第三方 AI 共享前明确同意要求已复核；自动回归不是实际模型回答或线上账号验收。
- **本轮送审 NO-GO**：严格 final-submit 仍缺新候选制品/截图/同包真机证据、本机审核
  联系与凭据、ASC 已保存声明的本轮复核，资料仍 Draft。此结论不等于断言 ASC 字段为空。
  本次发布令牌尚未获确认，未创建令牌、云端构建、OTA、更新 ASC 或提交审核。
- 收尾已停止本次 localhost 图片服务器与隔离 PostgreSQL 实例；保留 QA、测试与数据库
  日志供复核，未触碰真机或生产数据。

## S0 · 用户需求（逐字）

### 2026-09-09 · 正式送审推进授权与候选接管

- 用户要求按顺序清除 CI 阻断、构建上传、同包验收、核对 ASC 材料并提交正式审核；
  此授权不将未验证结果视为通过，也不绕过短期凭据、独立安全复审与真机闸。
- 「全面扫描并加固系统安全」任务已明确停止修改并交接 Web/Mobile/release-tools
  依赖补丁、四处非安全用途 SHA1 标注及追加依赖断言；未覆盖本 Dossier 和既有 YAML/XML
  回归。并发来源已确认；当前候选尚未推送、构建或提交审核。
- 本发布任务新鲜验证：依赖约束 25/25 PASS、秘密扫描 PASS、diff whitespace PASS。
  先固定本地候选并按 safety-gate 独立复审，再核对完整集成与精确 CI。
- 固定 `8c326a9a63fe2e8fa3bca0ff9d748a473c12fd31` 独立复审为 NO-GO：
  query-string 的 CommonJS 消费者不能直接调用新版 decoder 的 ESM default；EAS 新项目
  配置生成仍调用 ts-deepmerge default，而安全新版只提供 named merge。此前常规全量测试
  （Mobile 2824、Web 385、发布集成 866 + 52 subtests）通过未覆盖这两条真实消费路径。
- TDD 追加真实 query-string / React Navigation 路由（2 RED）、EAS generateAppConfigAsync
  （1 RED）；修复保留 decode-uri-component 0.5.0 / ts-deepmerge 8.0.0 安全实现，
  仅做消费者导出适配。Mobile 复用 patch-package；EAS 适配固定版本与完整源 SHA256，
  未知 vendor 字节拒绝执行，补丁可幂等重用且事后回读验证。
- EAS 在可信 build/submit 的依赖安装后、任何 vendor 凭据/权限消费前显式应用并验证；
  同样接入 CI 的 Node 22.13.0 检查。新增恶意 URI 限时、合并原型键过滤、源漂移拒绝及
  接线回归；不增加安全例外、不回退到已知漏洞版本，也不扩大发布身份权限。
- 固定 `1d8820296cdbfc516bc25fab1cc9352314fb5fdf` 二次复审仍 NO-GO：根与 Mobile
  `.easignore` 历史规则排除了整个补丁目录，云端会遗漏 decoder 适配和 image-size 安全补丁。
  新增真实 EAS makeShallowCopyAsync 归档复制测试首先 RED；仅排除已知 Mac shell 专用补丁，
  保留两项安全/兼容补丁。测试同时比较入包 bytes，并确认原生构建、node_modules、Rokid
  APK 与根环境文件仍不入包；不拿本机 node_modules 通过替代云端构建输入证明。
- 第三轮新独立 reviewer 对 `32766656faaf2f3ad10f2d93d30244f5d40a5722` 裁定代码
  **GO**：Node 22.13.0 的 EAS 3/3、Mobile 解析与导航 7/7、工作流/依赖 71/71、图片
  安全 2/2 全通过，秘密扫描和工作树检查通过。GO 不替代精确远端 CI、云端安装与真机。
- 本发布任务完整 CI-mode 集成 869 passed、52 subtests passed、436.07 秒、exit 0；
  `/tmp/xiaoba-submit-compat-release-integration.log`。该运行开始后只调整了补丁文件末尾
  空白及归档规则/Node 归档测试，Python 集成输入未变；归档变化另有上述 Node 新鲜证据，
  仍须最终固定 SHA 的真实远端 CI，不将本地套件冒充它。
- Mobile 干净 npm ci 后 305 suites / 2826 passed / 1 既有 skipped，TypeScript PASS。
  Web 构建、385 项测试和 lint PASS；Web/发布工具 npm production 审计 0 漏洞，Mobile
  OSV 通过并保留两项既有限期 image-size 例外。未因例外隐藏云端漏打补丁问题。
- 正式发布仍暂停：远端 main `501cd6475` 的真实 CI 为失败；按 AGENTS §7，需明确允许
  仅推送修复提交以恢复 CI，不能顺带部署。release-production secrets 当前为空；ASC UI
  已回登录页。本轮没有创建令牌、安装发布授权、推送、云端构建、上传或正式提交。
- 后续用户明确确认仅推送已复审修复以恢复主干 CI。提交前秘密扫描、diff check、124 份
  Dossier 一致性、App Store release pack 与 iOS submission 基础 preflight 全通过；随后
  非 force 推送上述三项修复，远端 main 已核验为 `32766656faaf2f3ad10f2d93d30244f5d40a5722`。
  精确候选 CI：[34301253377](https://github.com/itsoso/health-llm-driven/actions/runs/34301253377)，
  本地本段证据未包含在该候选。未构建、部署、上传或送审。
- 该 CI 的 Web、Mobile、文档与类型漂移检查已通过；backend-quality 已失败，其余部分
  job 尚在运行。失败位于 LLM live-change gate：`backend/app/api/orchestrator.py` 的
  非安全用途 SHA1 标记触发路径规则，仓库 `HARNESS_LIVE_LLM_EVAL_CONFIRMED` 仍绑定
  `30af344869fcaca70ba0e8ad6a1e005fed4ade33`，不匹配候选 `32766656f`。不能以旧 live
  记录冒充当前版本，也未修改 gate 或仓库变量。后续须补跑固定候选的真实模型回归，
  保留通过证据，再更新对应确认变量并重跑失败 CI；此次仅推送授权不扩展为发布授权。
- 用户随后授权继续补跑并更新 CI 凭证。固定 `32766656f`、实际 TokenPlan / MiniMax-M2.5
  完成新鲜 live gate：orchestrator 5/5、平均质量 0.96、无 baseline regression；invariants
  12/12、health_agent_core 50/50、trajectory 12/12、goldens 9/9 均通过，exit 0。
  证据 `/tmp/xiaoba-live-32766656.j0h6jV/result.json`，stderr 为空；前后均核验 HEAD 与
  backend/scripts 字节未变。仅合成样例及独立临时 SQLite，未触碰生产健康数据；SQLite
  不作为生产数据库语义证明，后者已有该 SHA 的 PostgreSQL CI 通过证据。
  上次 CI 其他所有工作项均成功，backend-tests 聚合因 backend-quality 缺凭证而失败。
- 实测通过后将 `HARNESS_LIVE_LLM_EVAL_CONFIRMED` 更新为完整 `32766656faaf2f3ad10f2d93d30244f5d40a5722`
  并回读核验，仅 `gh run rerun 34301253377 --failed`。第 2 次尝试已终态 **SUCCESS**：
  backend-quality（job 102311269846）与 backend-tests（job 102312037561）成功，完整 CI
  结论为 success，不是仅局部测试通过。无需新增产品提交或重复已成功的构建。
  本轮未部署、构建、上传或送审；后续仍需短期发布身份、精确制品及 App Store 审核材料 Gate。
- 后续用户明确选择 Expo token 长期复用并授权创建、存入 GitHub。本次在既有 Developer
  robot `reva-release-20260908-r2` 创建 `xiaoba-health-github-release-reusable`，通过网页
  内存转存为 `release-production` 的 `REVA_RELEASE_EXPO_TOKEN`；API 回读仅名称及
  更新时间，确认已保存。未输出、提交或落地 token 明文，已清除脚本变量并关闭 Expo 页面。
  **该 token 与 GitHub secret 是用户明确要求保留的可复用凭据，禁止套用历史临时凭据
  清理步骤将其撤销或删除。** 此授权不改变服务器绑定精确 SHA、最长八小时的专用身份
  合同。当前只证明凭据创建和存储完成，尚未证明 EAS 身份验证、构建或上传成功。
- 用户明确要求直接使用该长期 Expo token 发布。服务器从 canonical GitHub 获取固定
  `32766656f`，bootstrap/server SHA256 与本地已复审源码完全一致，隔离 gate 验证 CI
  `34301253377` attempt 2 成功。旧 `30af34486` 已 SUCCEEDED、无 loopback 私钥、无业务
  lease；受审 rotate 返回新 SHA INSTALLED，旧安装留存审计。新单次身份有效期 7 小时，
  仅更新 `REVA_RELEASE_SSH_KEY`、`REVA_RELEASE_KNOWN_HOSTS`，复用既有 Expo secret。
  `target=validate` 的 `34302860013` 已成功；正式 `target=release` 已启动
  [34303916354](https://github.com/itsoso/health-llm-driven/actions/runs/34303916354)，
  当前尚无构建、上传或线上验证终态，禁止重复 dispatch。
- 本次发布已终态 SUCCESS：上述 workflow 的 preflight、build-permission、backend、
  ios-build、testflight 全成功。长期 Expo token 已通过锁定 CLI 的实际身份验证并用于
  构建/上传；EAS build ID `c9a8f659-a969-4ee0-80d9-c5845baae605`，production / IOS / STORE，
  source `32766656faaf2f3ad10f2d93d30244f5d40a5722`，App 1.3.3（266）。
- 已下载实际 IPA `/tmp/xiaoba-release-32766656.VMBVi4/Xiaoba-1.3.3-266.ipa`；SHA256
  `23a499396cfe7042ed619b5c5018471fde43f077bfb6386276b3f78967d53ef8`。实际 Info.plist
  核验小巴健康、life.executor.health、1.3.3/266、DTXcode 2620、SDK 26.2、最低 iOS 16.0、
  UIDeviceFamily=[1] 全通过。首次检查因二进制 plist 使用不可 seek 的 stdin API 失败，
  改为读取 bytes 后 plistlib.loads，断言全部通过；未修改制品。
- ASC 实际页面已核验 Build 266 上传 **Complete**，测试列表 **Ready to Submit**，已关联
  内部测试 / Team (Expo)。这是 TestFlight 构建上传成功，不是正式 App Review 已提交或通过。
- 服务器 revoke 回执 REVOKED；仅删除本次 GitHub SSH_KEY、KNOWN_HOSTS 与本地临时私钥。
  `REVA_RELEASE_EXPO_TOKEN` 继续保留复用；IPA、公钥和审计记录保留。严格 App Store
  final-submit 的同包真机、截图、审核账号/联系与已保存声明核验仍未由本次发布替代。

### 2026-09-09 · Build 266 USB 真机只读验收

- USB 确认已安装 1.3.3（266）；本次使用候选同 SHA 的 XCUITest harness，未重签或替换 App。
- 仅运行不依赖审核 fixture 的定向子集，没有执行 full suite、审核数据 reset、发送消息、健康写入或账号删除。
- 六个不同用例最新结果通过：启动入口、连续两次冷启动登录保持、历史搜索/列表控件及按钮/下滑关闭、附件控件/导入取消/按钮及下滑关闭、后台恢复未发送草稿、隐私政策及账号删除入口。
- 首轮 3 项中 2 项通过，历史页在系统通知横幅出现后报告 `kAXErrorServerNotFound`，真实退出码 65，失败证据保留；不能据此断定通知是唯一原因。未改代码或断言的导航复测 2/2 通过、退出码 0；草稿与隐私检查 2/2 通过、退出码 0。
- 外部原始证据目录 `/tmp/xiaoba-usb-build266.5bQrqa/`：`ReadOnly-Build266.xcresult`、`Navigation-Build266.xcresult`、`DraftPrivacy-Build266.xcresult`。截图含当前会话内容，仅留本机，不作为可公开的商店截图。
- 视觉检查发现一条历史非健康话题回复附有健康参考来源；生成时间/版本尚未核实，不能归因于 Build 266 的新生成路径，需在隔离审核账号复现引用相关性。
- 仍未验证本包的审核账号登录、饮食订单记录/修正/删除、餐食分享返回、图片关闭、语音/相机/系统分享和医学引用完整链路；这六项通过不代表最终送审 Gate 通过。

#### 同日 USB 补充：输入模式、已有图片与分享预览

- 全程仍为已安装 Build 266；临时扩展测试只放在上述外部 QA 目录，没有修改 App 或重签二进制，也没有把审核密码传入 XCUITest。
- `InputMealDiscovery-Build266.xcresult` 中键盘/按住说话模式往返用例通过，未触发录音；另一个历史定位探索用例只证明能打开已有会话，不算饮食功能验收。
- 图片探索前两轮停在测试素材准备：冷启动默认会话与搜索输入未确认造成选错会话。失败结果 `PhotoShare-Build266.xcresult`、`PhotoShare-FixtureSelected-Build266.xcresult` 原样保留。
- 按屏幕上确切的既有餐食会话标题定位后，`PhotoShare-ExactConversation-Build266.xcresult` 已依次执行并通过图片轻触关闭、下滑关闭、上滑关闭、横向滑动不误关闭和关闭按钮断言；有打开/返回截图。但该组合用例最终因脚本直接等待海报、遗漏中间照片编辑步骤而退出 65，不能标成整条通过。
- 从实际照片编辑页面继续，未做图片修改，点击完成进入海报，再关闭返回 Agent；`SharePreview-Continuation-Build266.xcresult` 1/1 通过、退出码 0。无保存相册、对外分享、消息发送或健康记录写入。
- 上述更新仅覆盖图片手势和分享编辑器普通关闭；“问小巴复盘今日饮食”会自动发送消息，本次未点击，不能冒充该历史 bug 的完整回归通过。审核账号登录、饮食写入/修正/删除、录音/转写/中断、相机、系统分享及最终送审 Gate 仍待验证。

#### 同日审核账号写路径实测 · BLOCK

- 用户自行登录并明确授权测试数据写入。USB 设置页截图核对当前审核账号，再用服务端既有凭据正常登录及 `/auth/me` 比对身份，二者一致；没有把账号密码交给 XCUITest，没有注入登录状态。`ReviewIdentity-Build266.xcresult` 1/1 通过。
- 实测前审核账号当日饮食列表为空；仅发送两条有唯一测试标记的记餐请求，未对个人账号写入。两条请求最终均无饮食记录、无成功写入回执；未通过其他入口替代写入来伪造手机验收成功。
- A 请求包含审核测试说明、明确午餐食物与份量、估算并保存要求。App 约 65.5 秒后给出“这轮没能整理成回答”的兜底；持久化 metadata 显示 `tools_used=[]`、`write_receipts=[]`，但 `turn_outcome.category=success`、`completion_status=complete`、`record_intent_no_tool=false`。本地同 revision 分类器将完整输入判成 `unknown/ambiguous`，仅证明分类缺口，不代表已定位所有执行器根因。
- B 使用更短的常规“记录今天午餐”指令，包含白米饭 100 克、鸡蛋 1 个及独立测试标记。本地分类为 `write/diet/create`。真机等待回执超时；继续回读至服务端终态后确认 `health_record` rejected、8 轮模型、约 131.9 秒、`tool_failed/error`、无回执；回复表示无法完成营养估算并要求再次补充已经提供的食物和份量。最终数据库仍为空，未重复提交 B。
- `ReviewMealBMI-Build266.xcresult` 2 项中 1 通过、1 失败，退出码 65：记餐失败；BMI 引用面板、医疗边界、国家卫健委来源链接及 Safari 官方域名打开通过。`ReviewSimpleMeal-Build266.xcresult` 常规记餐用例失败、退出码 65。全部结果保留于外部 QA 目录。
- 服务端既有 `validate_demo_account_live` 检查还确认审核固定简报不是默认最新会话，Gate FAIL。没有绕过已撤销的发布授权直接调用 seeder 或修改数据库排序。
- 裁决：当前候选不能宣布完整验收通过，不能正式送审。先修复记餐分类/营养估算及无回执完成状态问题，再通过受控流程恢复审核 fixture，并继续同候选真机写入、修正、删除、复盘返回、实际语音、相机、权限及系统分享验收。

#### 同日写路径修复 · implementation / 尚未发布

- 沿用本 Dossier，incident controller + safety overlay；本地 ledger：`docs/_generated/harness-runs/ace56217e26c.jsonl`（原始 trace 不提交）。
- A 根因细化：正向语法漏掉“并直接保存”；泛化后置归属检查又把“这是审核账号的测试记录”误认为人名归属。无回执终态还错误依赖 fast-model 路由。新增先红测试覆盖完整合成请求、直接记录、第三方/条件/撤销反例、非 fast 路由无回执与流式假成功。
- B 真实分段：营养估算 3001ms 超时、仅调用 1 次；后续模型修复 8 轮，模型累计约 128.6 秒，工具每轮仅数毫秒。正常授权下同一合成食物只读估算对比：3 秒预算超时，12 秒预算约 7.4 秒成功且五项营养完整。不是数据库写入耗时。
- 修复方向：保留现有 provider/同意校验/营养完整性与用户隔离，单次营养估算采用有界预算，重复不完整工具调用只允许一次修复机会；失败文案不再归咎已经提供的食物份量。
- 已启动仅 loopback 的隔离 PostgreSQL 测试实例，不使用生产库做回归。完整安全复核、目标 revision CI、受控部署、审核 fixture 与候选真机 G6 尚未完成，继续 BLOCK 送审。
- 第一轮独立 G4 对本地 `590c7ec55` 判 NO-GO：新直接表达的第三方/举例/短撤销反例、uncertain 持久化正文被重试文案覆盖，以及 A 虽通过分类仍被 Goal/目标校验拒绝。均补先红测试；新增餐食主体闭合校验、尾部撤销、保留 uncertain 正文及食物/备注分离，不用关闭目标校验来通过。
- 新鲜验证：授权解析全量 1161 项通过；Goal/capability/simple-record guard 2489 项通过；营养 20 项 PostgreSQL 通过；状态/澄清/uncertain 5 项 PostgreSQL 通过；邻近 API/adapter/multi-model/simple-record 140 项 PostgreSQL 通过。扩大回归暴露的 4 个旧 fixture 外键问题已按生产父子创建顺序和真实测试用户修正，没有放宽外键。此前大批次失败日志保留，不伪称原批次全绿。
- A/B 新增持久化贯通验证：仅估算器输出使用合成数据，正常 Agent → capability → 实际鉴权 Diet API → PostgreSQL → 回执；食物、营养、备注回读一致；重复同一 client turn 仅一条记录、一次 POST。两项通过。该本机证明不替代已安装 Build266 的生产真机 G6。
- `harness_llm_regression_gate.py --include-live-llm` 实际执行 FAIL：离线 invariants 12/12、health-agent-core 50/50、trajectory contract 12/12、goldens 9/9；live orchestrator 0/5，本机模型凭据未配置且 fallback 缺少 AI 同意上下文。不设置精确 SHA 放行变量、不 push 或部署，不把生产旧源码的只读营养探针当成当前提交 live gate。
- System Map / mobile navigation / 文档漂移和秘密扫描通过。下一步仍为新固定 SHA 独立复审及修复 live 验证环境，之后才能走精确 revision CI、受控发布和候选真机验收。
- 第二轮独立 G4 对 `0dfb4579f` 判 NO-GO：`仅举例/举个例子` 仍可授权；连续同类两餐会被 notes 吞并。补红测后扩大完整尾句限定形式；备注包含后续明确写入请求时，整个 simple-meal goal 退出，不截短后继续写首餐。重新合并运行 Goal/capability、授权解析、simple-record guard 与真实 PG 持久化测试，3657 项通过（exit 0）；等待该修复的独立复审，不复用前两次失败裁决。
- 闭环独立复审对固定源码 `2dccbb4f8ae9ec5e897cf0e10f3ee3fe0c388d8b` 的上述两项整改裁定 GO；独立重跑 Goal/utterance 两个完整测试文件 1105 项通过（exit 0），System Map 通过。主流程最终 3657 项退出码 0，秘密扫描与 diff check 通过。该窄范围源码 GO 不代表发布 GO：live LLM gate 退出码 1，当前源码未 push、未部署、未送审；后续须恢复真实模型凭据和合法 AI 同意上下文，再取得精确 revision CI、受控发布及真机 G6 证据。
- 用户后续明确授权解决阻断并部署；沿用本 Dossier，新阶段 ledger `docs/_generated/harness-runs/1f3dc2adb7a9.jsonl`。独立安全审查允许在服务器任务专属隔离目录运行精确候选的合成 live gate：普通 HTTPS 审核账号登录并核验身份，绑定真实 AI 同意与用量上下文，不伪造同意、不改 guard/provider、不修改生产服务；凭据和完整输出留在服务器，仅返回允许的聚合字段。允许普通模型用量审计，不写业务健康记录。
- 固定 `a25df99372b09a2511ecc110ea3e076bfea39a3c` 的归档 SHA256 `365ed1549053d449a35e350ef0466cdf35d0749b07e2145d26598839fe4a5593` 前后内容核验一致；真实 gate exit 0：invariants 12/12、health_agent_core 50/50、orchestrator 5/5（平均质量 0.94）、trajectory/goldens 均通过。实际 10 次调用均为 TokenPlan / MiniMax-M2.5 且成功；既有同意、接收方、额度校验均保留。此证据不替代后续提交的精确 SHA live 绑定。
- 新鲜 CI-mode 全增量合跑 4186 项中 4185 通过，唯一失败是旧测试要求“明确记录医生反馈但没有工具/回执”仍为正常完成。独立红测复现后，仅修正该测试契约：明确写入也必须未记录、无成功 outcome/正文、无工具和回执；普通临床上下文与歧义操作原有保护断言不变。38 项定向回归通过（exit 0）；等待更新候选的全增量重跑和独立复核，不把前次失败批次记为绿。
- 同仓库“解决ui问题 分享饮食”任务已确认两处 DietShareCard 移动端改动归属其任务且未提交；本轮完整保留，不暂存、不混入后端发布候选。
- 固定 `20153b4767fc9e16a84c2657de27fa09703e5f09` 的临床回执测试整改独立 GO（38/38）；新鲜 CI-mode 全增量 4186/4186、exit 0。新 SHA 再次真实 live gate exit 0：5/5 orchestrator、平均质量 0.94，10 次 TokenPlan 调用成功，其他 gate 均通过；归档摘要 `1ee843f19e74946bb5163107ba0e6f93e6a5336ec449ba3a0b18fbf31bfda61c` 前后匹配。放行变量精确绑定后，从干净发布副本 push main，未包含 Mobile 改动。
- 精确 CI [34314638986](https://github.com/itsoso/health-llm-driven/actions/runs/34314638986) 终态 failure：唯一实际失败 job 为 balanced-12，backend-tests 为依赖聚合失败，其余适用 job 成功。根因是 `test_agent_write_adapter_rejections.py` 仍要求营养估算失败时提示补充“具体食物/大致份量”。本地红测复现后仅更新测试：必须说明完整营养估算未完成、可重试/有变化时修正；不再断言用户缺少输入，内部工具字段不可泄漏的原断言完整保留，生产源码未改。
- 按原 CI worker 重跑 balanced-12 的四个分片，724 passed / 1 PostgreSQL-only skip，进程 exit 0；随后在隔离 PostgreSQL 单独运行该并发用例和修正文案用例，2/2 passed、exit 0。中间过宽的 180 项 PostgreSQL 补充批次主动中断（exit 2），不计为全批次通过；其日志保留。外部日志 `/tmp/meal-ci-balanced12-fixed.log`、`/tmp/meal-ci-copy-and-photo-focused-postgres.log`。
- 主干转红后按 AGENTS §7 暂停外部写入和部署，已向用户请求“允许推送此次 CI 修复、待新 SHA CI 绿后继续部署”的明确确认；未收到确认前仅保留本地修复。生产仍为 `32766656f`，没有授权轮换、重启、业务写入验收或正式送审。只读核验上次两把公钥授权均不存在且发布回执 SUCCEEDED，但旧 loopback 私钥文件仍存在；不复用旧 Dossier 的“私钥已删除”叙述，后续须按受审撤权/轮换流程清理精确旧私钥，长期 Expo Token 不变。

#### 同日受控部署及生产记餐回归 · backend PASS / App Review 仍 BLOCK

- 用户明确授权后续自主判断、推送修复及受控部署。最终候选 `4b2300012e2df7bc67e64452687761491261ffd8` 再次完成真实 live gate：exit 0、78.54 秒，invariants 12/12、core 50/50、orchestrator 5/5（平均质量 0.94）、trajectory/goldens 通过；10 次 TokenPlan 调用成功。隔离归档摘要 `2476858f5a92bc704877ed938bf3881d56b4eff2ea8da33a8248c86c15fc7148` 前后核验一致，无生产服务或业务健康数据改动。
- 从干净发布副本推送。精确 [CI 34316609333](https://github.com/itsoso/health-llm-driven/actions/runs/34316609333) 整体 success，后端分片、PostgreSQL runtime、质量/发布检查通过；[托管 validate 34317007544](https://github.com/itsoso/health-llm-driven/actions/runs/34317007544) success。独立安全复核对正常授权轮换及精确旧私钥清理 GO；系统 Git 从 canonical GitHub 取得新源码，bootstrap/executor 字节与受审版本一致。
- 旧 canonical revoke 成功；持有原 launcher/build 锁，完整核验旧成功阶段回执、实际生产 revision、无 lease/活动进程、已撤销身份及私钥公钥匹配后，仅删除旧 loopback 私钥，保留锁、业务数据与全部历史证据。首次 rotate 因公钥尾空格在参数校验阶段拒绝；本地精确复现并只读确认无 retirement intent、无新 workspace/安装、旧 policy 未变后，规范化参数，正常 rotate 成功。没有清除或重置消费记录。
- [后端发布 34317262332](https://github.com/itsoso/health-llm-driven/actions/runs/34317262332) 首次在只读 readiness 因服务器到 GitHub 低速超时失败，backend job 未启动；普通 loopback 认证通过，发布授权尚未消费。Git 读取恢复且精确主干匹配后，仅重跑该 run 的失败 job；attempt 2 终态 success，服务器精确 `SUCCEEDED` 回执、生产 SHA `4b2300012`、业务 lease 释放，backend/worker/beat active 且 NRestarts=0。
- 本次备份 dump 23 秒、恢复演练 21 秒、站外归档 332 秒（上传 149 秒、下载哈希校验 172 秒、manifest 校验 3 秒），全部通过；健康度三次 60/60。记录真实分段，不以跳过恢复或完整性校验优化发布时间。
- 普通 HTTPS 审核账号登录并核对身份，合成 API 验收 5 项通过：A/B 真实写入及独立回查（15.17 秒、7.48 秒）、同 client turn 重放 0.13 秒且同一记录无新增、食物份量修改后重新计算营养且回查一致、仅删除两条本次 API 测试餐食并回查无残留。没有管理员直接插入餐食或伪造回执。
- Build266 真机仍连接时，先用设置页邮箱的不可逆摘要核对审核身份。最初测试误把“用户名/邮箱两处均显示同一审核邮箱”当成身份异常，在发送前停止，无写入；修正为所有候选标签必须匹配同一审核身份，不接受其他账号。后续两项实际记餐用例通过；服务端独立回查 C/D 各只有一条本人记录、五项营养完整、持久化 verified receipt 与记录 ID 一致，耗时 9651ms / 9838ms，`llm_rounds=0`。测试餐食有唯一合成标记，保留供后续修正验收。
- 真机组合结果 `PostDeploy4b230-USBMealsVerified.xcresult` 2 passed / 1 failed、exit 65：失败项是额外的只读菜单定位，不是记餐；没有把该组合记为全绿。按实际菜单状态与存在性等待修正测试后，只读账号/页面复核 `PostDeploy4b230-ReadOnlyFinal.xcresult` 2/2 passed、exit 0。后续手机内份量修正用例尚未开始，设备已 unavailable，xcodebuild exit 70；因此不宣称完整真机闭环通过。原失败结果和日志均保留在外部 QA 目录。
- 受控审核 fixture 维护使用唯一 operation ID `b93b511cbe614d2fa0d4d210a5a09265`，在 mutation 前安全检查失败（exit 1）：无 operation 目录、无 business lease、未启动 seeder。只读拆分定位：应用代码目录本身没有不安全 metadata；维护脚本遍历整个 backend 时在应用账号拥有的 `private_media`（0700）处阻断，venv 检查另拒绝现有 `.pth` 启动 hook。没有改媒体权限、删除缓存/依赖文件或绕过检查重置账号；需要另行受审的受控维护环境治理，不能因此声称默认审核简报已恢复。
- 本轮不含其他任务的两处 Mobile 分享卡改动，不发 OTA、不重新构建原生包、不提交正式 App Review。后端故障修复和生产记餐验证通过，但审核 fixture 维护、剩余真机修正/复盘/权限路径仍待闭环，整体送审继续 BLOCK。
- 收尾：确认维护未进入 mutation 且部署已成功终结后，canonical revoke 返回 REVOKED；持有原锁并重复验证生产 revision、完整成功回执、撤权和私钥公钥匹配，仅清理本次 loopback 私钥。GitHub 两项短期 SSH secrets 及本机本次私钥已删除；历史安装/回执、公钥证据、工作树和业务数据保留，长期 Expo Token 的更新时间未变。没有遗留本次可用 SSH 发布身份。

#### 同日审核维护隔离修复 · implementation / 尚未发布

- 用户“继续”授权下启动独立的维护阻断整改阶段，仍沿用本 Dossier；primary controller 为 Health Harness，safety overlay。ledger：`docs/_generated/harness-runs/ec063f171827.jsonl`。
- 独立方案审查 GO（不等同固定代码 G4）：执行源收束到 canonical backend，完整验证 Git 文件/资源清单；保留生产 revision、tracked metadata、依赖所有权和锁/意图证明。禁止修改 `private_media` 权限、删除缓存或给未知 hook 加白名单。
- 三项先红回归复现媒体目录误入导入树、受管 `.pth` 被一律拒绝和 canonical ignored 模块漏检。实现改为系统 Python `-I -S -B`，显式只添加受管依赖目录，不执行 `.pth`，不导入 live backend；配置作为数据读取，不再 shell source；固定审核凭据及 PostgreSQL URL 缺失即失败。
- 初轮回归暴露 live tracked hardlink 检查随旧扫描移除而丢失，已补回逐 tracked 文件 metadata 校验，无需遍历媒体。定向集成回归 72/72、57 subtests、exit 0；新增真实子进程隔离/摘要/凭据前阻断等 5/5、exit 0。完整新鲜回归和固定 SHA G4 尚未结束；没有生产维护、部署或正式送审。

> 点击调整记录，修改食物的内容。比如把1碗改成两碗，那么在保存的时候要重新计算热量。当前只是修改了内容，但是没有修改和重新计算真实的营养物质和热量，要做这个优化。点击图片，展开午餐图，用手滑一下，图片应该自动消失，而不是再点击那个叉号再消失。要优化这个交互。

- 用户：在小巴聊天中查看、修正已记录餐食的 Mobile 用户。
- 当前绕过：食物改动后还要手工同步四项营养；大图只能点关闭按钮。

## S1 · Discovery

- `mobile/components/chat/cards/RecordQualityCard.tsx`：当前调整器把新食物描述与旧营养输入一起直接 `PUT`，没有重估步骤。
- `mobile/services/diet.ts`：现有调整路径只有普通 owner-scoped `updateDietRecord`，客户端分两次“估算→PUT”会留下并发覆盖和半完成窗口。
- `backend/app/api/diet.py`：普通更新只会清空不可信旧营养，不会重算；现有文字估算接口也尚未复用食物识别 sanitizer。
- `mobile/components/chat/cards/DietDraftCard.tsx`：`MealPhotoGallery` 仅支持横向翻页和关闭按钮。
- 硬约束：营养仍是估算而非测量值；估算失败不得写入半成品；横向翻图不得被纵向关闭手势误伤；保留关闭按钮。

## G1 · 准入裁决

- first_class_objects：`ExecutionEvent`、`HealthTwin`（纠正后的 `DietRecord` 是其饮食事实输入）。
- core_loop_step：Capture → corrected record → HealthTwin/下一餐建议。
- target_surface：Mobile；source of truth：Backend/PostgreSQL `diet_records`。
- safety_level：privacy-sensitive health write；autonomy：`manual_confirm`。
- spec_required：yes（用户可见行为 + 健康数据写路径）。
- smallest_end_to_end_slice：聊天内改食物 → 一条服务端命令安全重估并原子更新 → 完整回读刷新；餐食大图纵向滑动关闭。
- **裁决：PASS**。用户已明确要求实施。

## S2 · PRD

- 链接：`docs/prd/2026-08-20-diet-correction-recalculation-photo-dismiss.md`
- 非目标：不宣称营养为实测；不改图片存储/分享；不做自动保存或后台静默修正。

## S3 · 规划

- 链接：`docs/plans/2026-08-20-diet-correction-recalculation-photo-dismiss.md`
- 发布路由：Backend 先部署；纯 JS/TS Mobile 改动后走 production OTA。

## G2 · 可行性 + 安全压测

- 方案：新增 owner-scoped 原子重算命令。服务端先读取版本快照，在不持行锁时估算并清洗，随后重新加锁/CAS 校验，在一个事务内写入新描述与五项营养；估算失败或并发冲突均零写入。稳定 operation key + request digest 使丢响应重试可取回已提交结果，不重跑模型。
- 手势：只接管明确纵向滑动，横向仍交给分页 `ScrollView`，叉号保留。
- 硬阻断已进入验收：禁止沿用旧营养、禁止 LLM 原始 totals/健康提示直写、禁止估算失败后只改文本、禁止含酒文本重算时清空或伪造标准杯。
- 待拍板分叉：无。
- **裁决：PASS**。用户的保存动作是写入确认。

## S4 · 研发任务分解

- [x] T1 新增服务端原子重算接口，复用 sanitizer/calibration，补 fiber、CAS、action seed revision 与安全错误语义。
- [x] T2 聊天内调整器在食物变化时只调用重算接口，完整替换五项营养；失败零写入；409 不重放旧 revision；失效旧 progress/下一餐派生内容。
- [x] T3 餐食大图加入纵向滑动关闭且不破坏横向翻图。
- [x] T4 focused tests、OpenAPI 生成类型、TypeScript 与 G4 独立安全评审完成。
- [ ] T5 已从当前 `origin/main` 依次部署 Backend 与 Mobile OTA；待真机完成生产用户路径验证后关闭。
- 并发检查：已检查开放 PR，未发现同一修正链路的在途 PR。

## S5 · 实现

- 委托：`health-harness-orchestrator`（同一父 run）。
- Backend：owner-first 原子重算、required nullable revision、幂等回执/CAS、五项营养权威回读、含酒修正 fail-closed、action seed revision/fiber。
- Mobile：食物变化只走重算命令；同语义请求复用 operation key；409 保留输入且禁止旧 revision 重试；旧 progress/建议失效；餐食大图纵向滑动关闭并保留横向翻页/X/Android back。
- 契约：Mobile 与 Frontend OpenAPI 生成类型已同步。
- commit：本 feature commit（基于 `origin/main@4140bb7a3` 的干净集成候选）。

## G3 · 测试闸

- Backend focused 回归：最新远端主干干净集成后 `280 passed`（`test_diet.py`、`test_post_record_quality.py`、`test_agent_executor_food_vision.py`）。
- PostgreSQL 语义闸：重算相关 `38 passed`，覆盖真实 `FOR UPDATE`/双 Session 并发路径及扩展酒精 fail-closed 矩阵。
- Mobile：最新远端主干干净集成后 3 suites / `120 passed`；`tsc --noEmit` PASS；目标 ESLint `0 errors`（仅既有 9 warnings）。
- 契约/治理：OpenAPI generated types check、Ruff、`py_compile`、Dossier consistency `111/111`、System Map、`scripts/validate.py` blocking checks、`git diff --check` 全部 PASS。
- **裁决：PASS**。

## G4 · 安全闸

- 触发：健康数据写路径 + LLM 营养候选。
- 独立 Mobile/UX slice GREEN；Backend safety reviewer 与跨端最终 reviewer 对最新 diff 均未发现 BLOCKER/HIGH。
- **裁决：PASS / GO**。

## S6–S8

- 已在基于 `origin/main@4140bb7a3` 的独立干净工作树重放本 feature；远端新增饮食食材披露改动被保留，Backend/Mobile/PostgreSQL/类型/System Map 全部复测通过。
- feature commit `272782b33` 已进入主干；发布使用的精确主干为 `994c5665aef34fcf092679ba99edc12b7adfa9b8`，其 GitHub CI run `32356968903` 完成且结论为 success。

## G5 · 部署健康闸

- Backend 通过唯一入口 `./deploy.sh -b` 从干净 `main` 发布到生产；数据库备份、237 表恢复演练、站外加密归档哈希/HMAC、依赖锁、完整 runtime schema、runtime-only KB guard/staged contract、Skills manifest 均通过。
- 生产远端 revision 精确为 `994c5665aef34fcf092679ba99edc12b7adfa9b8`；`health-backend`、Celery worker、Celery beat 均为 active；重复健康评分为 `60/60 PASS`。
- 新端点 `POST /api/v1/diet/records/{record_id}/recalculate-nutrition` 在生产返回预期未授权 `401`，而非旧进程/未注册路由的 `404`；健康端点报告 API、PostgreSQL、Redis、Celery 正常。
- iOS production OTA 使用同一精确 source 发布到 runtime `1.3.3`；EAS group `d1d15b9c-e3bf-4190-be81-f96e3d16d504`、iOS update `01a01fe0-2dc2-74d6-970b-093eab295ff9`。独立 `update:view` 回读确认 branch、runtime、platform、commit 与发布记录一致。
- **裁决：PASS**。

## G6 · 生产用户路径验证

- 机器侧已证明 Backend 新路由生效且 OTA 对目标 production/runtime 可达。
- 尚未以真实用户记录执行“修改食物份量 → 服务端重算五项营养 → 保存后完整回读”，也尚未在真机验证餐食大图纵向滑动关闭与横向翻页不冲突。为避免修改真实健康数据或把发布成功冒充用户体验成功，本 Gate 保持 **PENDING**。
- 真机验证步骤：彻底关闭并重开 App 应用 OTA；选择可安全修改的测试餐食，将份量从 1 改为 2，确认热量/蛋白质/碳水/脂肪/膳食纤维共同变化且刷新后保持；打开餐食大图，纵向滑动关闭，再确认横向多图翻页仍正常。

## 2026-09-03 Correction Block · 已记录餐食缺少可发现的修正入口

### 触发

用户提供真机截图并指出：已记录餐食卡写着“可在记录页继续修正”，但卡面和紧邻操作区只有“编辑分享图 / 分享正文”，没有可发现的饮食修正入口；同时“午餐已记录”与底部“确认后才写入”存在终态语义冲突。

### 裁决与范围

- 回退阶段：S5；沿用本 Dossier 和既有原子重算写路径，不新建数据模型或写权限。
- G1：PASS。既有 `DietRecord -> HealthTwin` 核心闭环的可用性修复；用户本次明确要求实施。
- G2：PASS。主入口只展开现有 owner-scoped 修正编辑器，最终仍需用户点击“保存修正”；缺少记录身份或安全 seed 时不提供伪可用入口。
- 最小切片：已记录饮食卡 → 明显的“继续修正本餐” → 就地编辑 → 人工保存 → 卡面更新。
- UI 收敛：修正提升为主操作；分享降为次级；移除卡内重复的社交分享宣传块；已记录态统一为“已计入今日饮食 / 营养为估算，可继续修正”。
- 发布授权：本 correction block 不继承 2026-08-20 的历史发布授权；本轮不 commit、push、deploy 或 OTA。

### 待验证

- [x] Mobile 入口可见、点击即展开、保存后收起并刷新卡面。
- [x] Backend 新生成的已记录饮食卡同时携带 owner-matched `record_id`、revision 与修正 seed；不再依赖易丢失的通用 action bar 才可修正。
- [x] 旧卡即使仍携带“确认后才写入”，在 recorded 状态也会统一投影为“营养为图片估算，如有偏差请继续修正”。
- [x] TDD、TypeScript、目标 lint、Backend owner-isolation/重算回归、System Map/doc drift。
- [x] 仓库级 Dossier consistency：2026-09-05 对 122 份 Dossier 复核通过。
- [x] 固定提交独立 G4 safety/privacy review；此前 G4 不自动覆盖本次新入口。

### 2026-09-03 实现与验证证据

- Mobile：卡片内新增 52pt 一级入口“继续修正本餐”，直接展开既有 `DietRecordAdjustEditor`；缺少正整数记录 ID 或安全修正 seed 时 fail-closed。通用 action bar 的重复修正按钮在该卡型隐藏。
- UI/表达：移除“今日饮食打卡 / 小巴生成”重复宣传块；已记录状态改为“已计入今日饮食”；下一步改为“接下来 + 具体动作 + 依据”；分享入口改为“制作分享图 / 分享文字”；已记录态不再显示待确认写入文案。
- Backend：`post_record_quality` 与上下文餐食照片自动记录卡均把修正 seed 复制到 card data；后者在生成 seed 前验证 `record.user_id == current_user_id`，revision 仍来自当前记录。
- RED：Mobile focused 首轮 `5 failed, 163 passed`，失败点与缺入口/旧表达完全对应。
- GREEN：Mobile focused `2 suites / 169 passed`；`npx tsc --noEmit` PASS；目标 ESLint `0 errors`（测试文件 9 个既有 warning）；design token ratchet PASS。
- Backend：`test_post_record_quality.py + test_agent_executor_food_vision.py` 共 `124 passed`；重算、owner-first、CAS、幂等与失败零写入子集 `39 passed`。
- 治理：`py_compile`、`git diff --check`、System Map、mobile-nav、doc-drift PASS。
- LLM change gate：确定性 invariants `12/12`、health core `50/50`、trajectory `12/12`、goldens `9/9` PASS；2026-09-05 使用隔离进程与线上 TokenPlan 配置补跑 live orchestrator `5/5` PASS，平均质量分 0.96。
- 仓库级 Dossier consistency 当前由 `2026-08-29-app-review-medical-citations.md` 的 G6 判定冲突、`2026-09-03-agent-perceived-latency.md` 缺 G1 裁决阻断；两者属于其他在途改动，本切片未修改。
- 发布边界：本轮未 commit、push、deploy 或 OTA。固定提交独立 G4 与 live LLM gate 完成前不得发布。

## 2026-09-03 Correction Block · 分享照片编辑与海报预览体验

### 触发

用户提供两张 iOS 真机截图并指出：照片编辑器与分享预览 UI 层级、留白和操作表达较差；两个全屏步骤都缺少符合 iOS 习惯的滑动取消/返回。

### Quick Flow 裁决

- 回退阶段：S2/S3 合并 tech-spec；沿用现有分享资源生命周期、图片隐私遮挡和系统分享边界，不新增数据模型、API 或写权限。
- G1：PASS。目标用户是已记录餐食并准备分享的 Mobile 用户；命中 Capture → Review/Share 闭环；最小切片是照片编辑 → 海报预览 → 保存/分享/返回。
- G2：PASS。使用左缘右滑返回，避免与照片区域的拖动裁剪、双指缩放和隐私涂抹冲突；滑动调用与顶部返回相同的清理/确认路径，不允许绕过未保存编辑确认或在图片处理中强行退出。
- UI 目标：修复状态栏/标题冲突；五项编辑工具单行等宽呈现；明确“调整照片”和“分享这餐”两个阶段；海报预览顶部对齐并可在小屏滚动；公开分享前保留简洁隐私提醒；主按钮突出“生成分享图/分享”，保存与仅分享文字降为次级。
- 非目标：不改变营养估算、海报数据、相册权限、系统分享结果判断或服务端饮食记录。
- 发布授权：本 correction block 不继承历史发布授权；本轮不 commit、push、deploy 或 OTA。

### 验收与 Gate

- [x] 两个页面均支持从屏幕左缘右滑，达到距离/速度阈值后执行与顶部返回相同的取消路径；反向、纵向、双指和非边缘手势不误触。
- [x] 图片处理中禁止滑动退出；有未保存编辑时滑动仍触发丢弃确认。
- [x] 编辑工具保持原有旋转、遮挡、撤销、重做、重置能力与无障碍名称，视觉上单行不换行。
- [x] 海报预览消除大段顶部留白，小屏可滚动；分享、存图、文字分享和失败恢复语义不变。
- [x] Mobile RED/GREEN、TypeScript、目标 ESLint、design token、System Map/doc drift。
- [x] 固定提交独立 G4 privacy review；未发现新增的外发、越权读取或绕过取消确认路径。

### 2026-09-03 实现与验证证据

- 交互：新增复用的 `SwipeBackSurface`，左侧 28pt 内开始的单指触摸从开始阶段即保留给返回手势，避免被图片原生手势先行抢占；只有方向与距离/速度达标的右滑才返回，其他触摸回弹且不触发取消。取消动作仍进入原有确认或异步资源清理函数，照片 apply 阶段禁用。
- 照片编辑 UI：深色状态栏与安全区统一；标题改为“调整照片 / 裁剪与隐私处理”；隐私提醒收为轻量胶囊；旋转、遮挡、撤销、重做、重置改为单行图标工具；视口提供随模式变化的操作提示；主操作明确为“生成分享图”。
- 海报预览 UI：标题改为“分享这餐”，增加生成完成状态；海报从顶部开始并置于可滚动容器；加入发布前隐私复核；分享海报、存到相册、仅分享文字重新分层；失败态表达与按钮层级同步收敛。
- RED：首轮 focused 测试按预期 `7 failed, 34 passed`，失败覆盖新视觉表达、滑动入口和文字分享命名。
- GREEN：focused `2 suites / 41 passed`；后续按真实 `PanResponder` 释放阶段（`numberActiveTouches = 0`）补强回归后，修复前 `3 failed / 42`、修复后 `2 suites / 42 passed`；完整相关回归 `9 suites / 164 passed`；`npx tsc --noEmit`、目标 ESLint、design token ratchet、`git diff --check` 均 PASS。
- 治理：System Map、mobile navigation graph、doc drift 全部 PASS；此次未改变生成器覆盖的架构结构。
- 模拟器视觉证据：登录态下从 Chat“更多操作”进入“饮食记录”，打开真实餐食照片编辑器；确认新标题、隐私提醒、单行五项工具与主按钮均可见。首轮发现全屏 Modal 顶部安全区为 0，标题侵入状态栏；加入“当前上下文 inset + 启动窗口 inset 取较大值”后重新打包，截图确认标题完整避开动态岛/状态栏。有改动时点击返回可见“放弃图片编辑？”并可选择继续编辑。
- 模拟器补充证据：Expo 开发客户端 Reload 后虽执行到 `RootLayout`、登录态与路由，但 Fabric surface 丢失；改由 Xcode 增量构建重新安装后恢复正常，确认问题属于本地开发容器生命周期而非业务页面。真实登录态下重新走通 Chat → 饮食记录 → 午餐照片编辑 → 生成分享图，截图确认安全区、单行工具、生成完成状态、海报顶部对齐、隐私提示与按钮层级；未触发系统分享或任何外发。
- 手势补充修复：模拟器探针确认左缘触摸被正确接管（起点 4pt、单指），同时发现 `onPanResponderRelease` 的真实语义是活动触点归零；旧完成判定因此会拒绝本来合格的手势。测试先改为释放阶段 0 触点并稳定 RED，再把“单指资格”限定在开始/移动阶段，释放仅按已记录的左缘起点、方向、距离/速度裁决。
- 模拟器剩余边界：当前 Computer Use 拖拽只产生 touch start/release，释放位移固定为 `dx = 0`，无法生成连续 touch-move，因此不能把这次自动化拖拽冒充实体侧滑通过。代码级完成路径、脏编辑确认、apply 禁用与清理均已由真实释放语义单测覆盖；发布前固定提交 G4 与真机/可产生 touch-move 的执行器复核仍保持待办。
- 发布边界：本轮未 commit、push、deploy 或 OTA。

## 2026-09-04 Correction Block · Chat 主壳补充饮食记录入口

- 触发：模拟器登录后，为复核已保存餐食的修正与分享流程，仍需在大量历史对话中反复搜索；Chat 主壳“更多操作”没有稳定的饮食记录入口。
- G1/G2：PASS。复用既有 owner-scoped `/diet` 页面和读写路径，不新增数据模型、接口、自动写入或医疗判断；最小切片为“更多操作 → 饮食记录 → 既有餐食列表”。
- RED：`app/(tabs)/__tests__/chat.test.tsx` 新增入口测试，首轮 `1 failed, 53 passed`，失败原因为菜单中不存在“饮食记录”。
- 实现：在 Chat “更多操作”中加入“饮食记录”，关闭菜单后打开既有 `/diet`；副标题同步收敛为“记录、分享与个人中心”。
- 模拟器：真实打开 Chat“更多操作”，确认“饮食记录”入口可见并成功进入 owner-scoped 饮食页，再从既有餐食打开照片编辑器。
- 分享页追加修复：模拟器发现全屏编辑器标题侵入状态栏，新增启动窗口安全区回退；发现左缘触摸可能先被图片手势拿走，改为左侧 28pt 单指从触摸开始即保留，仍只允许合格右滑触发统一取消路径。
- 新鲜验证：Chat + 完整饮食组件 `9 suites / 164 passed`；`npx tsc --noEmit`、目标 ESLint、design token ratchet、System Map、mobile-nav、doc drift 全部 PASS；导航生成物已同步新增的 Chat → diet 边。
- 补充修复：发现手势释放阶段活动触点为 0，而旧实现仍要求 1，导致实体侧滑无法完成；测试先按真实释放语义复现 `3 failed / 42`，修复后 focused `42/42`、完整相关回归 `164/164`。
- 模拟器：通过 Xcode 干净构建绕过开发客户端 Reload 的 Fabric surface 丢失，已补齐海报预览截图与脏编辑退出确认；Computer Use 拖拽不产生 move 位移，实体侧滑仍保留为真机/可产生 touch-move 执行器复核项。
- G4：固定提交独立 privacy review 已完成；仓库密钥扫描、owner guard/失败零写入 427 个 Backend 用例、分享编辑与返回 42 个 Mobile 用例、Chat 54 个用例均通过。
- 发布边界：本轮不 commit、push、deploy 或 OTA。

## 2026-09-05 · 固定本地候选

- 经用户授权，本轮饮食修正入口、分享编辑体验与关联回归已随本地提交 `b9063c441` 固定。
- 2026-09-05 独立 G4 与真实 TokenPlan live gate 已通过；push、目标 SHA CI、OTA 与精确商店候选仍按各自 Gate 独立执行。
