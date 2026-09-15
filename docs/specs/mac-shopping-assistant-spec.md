# Mac 购物助手接入

> Status: implementation; 2026-09-12. 用户明确要求先完成 Mac 适配，正式服务凭据与签名依赖另行确认。

## 当前增量：官方窗口显示（2026-09-12）

用户最新约束为不修改服务端和 RN，先打通小巴输入与当前窗口查看。沿用既有深链提问，仅在 Mac 新增 ScreenCaptureKit 单窗口预览；不使用 RN 本机桥，也不复制凭据或实现签名。

- 用户点击“发送并查看”或“显示快手购物窗口”才请求系统录屏权限。限定官方 bundle 的唯一可见主窗口，每帧只对顶部标题做本地 OCR，确认购物助手页面后显示。
- 画面仅在内存预览，不进入聊天记录、不上传、不保存，不把当前画面或历史标为本轮新回复或服务端完成。
- 离开页面、切换小巴身份、退出购物、进入演示/桥接、停止、录屏失败、无法确认购物页时清除画面；迟到捕获不得重新显示。
- 每轮有界刷新；只读画面，长回复滚动、商品点击与交易仍由官方快手窗口承接。最小化窗口、页面标题变化、多个主窗口可能中止显示。
- 验证分别记录：深链产生真实新回复；单窗口捕获可读；小巴内实际显示；权限拒绝和旧任务不回写。任何一项未验证必须单独说明。

## 决策与准入

在小巴 Mac 侧栏加入独立购物助手，复用现有 IG 服务；本轮不修改购物服务。
这是用户明确授权的独立购物入口扩展，不将购物行为归入健康干预，也不声称通过健康效果验证。

```yaml
RequirementAdmission:
  request: 在 Health Mac 适配快手购物助手，凭据问题并行确认
  classification: explicit-user-scope-extension
  first_user_fit: 当前用户桌面购物需求
  core_loop_step: outside-health-loop
  first_class_objects: none
  target_surface: Mac
  source_of_truth: IG Java controller and existing RN command handlers
  safety_level: authentication-and-privacy
  prescription_or_causal_verdict: none
  autonomy_tier: explicit-user-send-and-link-open
  evidence_provenance: local-source-plus-native-login-probe
  claim_hedging: 网页登录不等于购物登录；未经真实验证不声明联通
  verification_window: 本地构建和隔离测试；真实网关另行验收
  success_metric: 独立入口可用，命令和卡片正确显示，跨账号数据不残留
  added_user_burden: 购物账号独立登录
  burden_justification: 两个服务认证域不同
  non_goals: 支付、订单修改、健康信息传递、服务端改造
  smallest_end_to_end_slice: 入口到独立消息显示、官方网页登录、请求适配与停止接收
  stale_surface_to_remove_or_archive: none
  spec_required: yes
```

## 流程与端职责

Mac 购物入口 → 明确标识的离线演示或快手网页登录 → 配置已确认网关与 entrySrc → 获取当前 WebKit Cookie → 按域和路径匹配请求 → IG 命令更新文字/商品 → 用户点击官方网页承接。

Mac 负责显示、会话内凭据及取消接收；IG 继续负责认证、风控、Agent、工具与历史。健康后端和其他客户端无契约变化。

## 数据契约

- 独立 ShoppingService、ShoppingTranscript、ShoppingChatViewModel；不依赖健康 Token、上下文或对话存储。
- 初始化 `/load`；聊天 `/chat`；推荐问题 `/questions`；历史 `/session/history?pcursor=...`；反馈 `/feedback`。
- `entrySrc/carrierType/sourceId` 按 controller 从 query 读取；正文只提交购物输入及购物 globalParams。
- show/set/update 命令依据现有 RN handler；原生 KStreaming 字节封装与完成信号仍待真实网关验收，不以断连伪装完成。
- 服务端按快手用户解析 sessionId；本地清屏不声称创建服务端新会话。Mac 与手机可能共享历史和运行。
- 无数据库迁移，无凭据导入或跨域改写。

## 隐私与确定性边界

Cookie 只保留在非持久 WebKit 会话和短期请求内；不保存到文件、UserDefaults 或日志。健康退出/切换身份、购物退出销毁浏览器存储及会话；代际校验拒绝旧请求回写。只展示安全摘要，不展示 Cookie 值。
所有网络请求独立且拒绝重定向；请求只携带目标 URL 匹配的 Cookie。`webday7_st` 不冒充 `token/api_st`。认证或协议错误显示脱敏错误，禁止静默成功。
不执行购物消息内的脚本或自动跳转；卡片只能由用户主动打开允许的 HTTPS 页面。未知卡片可读降级。没有健康数据、医疗建议或交易写入的自动联动。

## 验收与验证

- 侧栏购物入口、文字/商品/推荐问题、独立输入、停止接收可用。
- 未配置/无购物凭据禁止发送；网页 Cookie 存在也不显示购物已认证。
- 离线演示显式标识且不发网络请求；退出演示清除演示数据。
- scoped Cookie、重定向、协议增量替换、旧回调隔离、退出清空均有测试。
- `cd apps/mac && swift test --filter HealthAgentMacCoreTests`、`swift build`、`git diff --check`、System Map 漂移检查、独立隐私评审。
- 本地 UI 验收与真实联通分别记录到 Dossier。

## 交付与未决项

2026-09-12 原任务仅本地修改、构建与验证；2026-09-15 用户已授权提交并合入 main。合并不包含新的应用或服务发布。移除 shopping 路由与独立服务即可回退，无持久数据迁移。
仍待确认：正式网关、桌面 entrySrc、购物凭据授权方式、实际流结束标记、商品网页承接。以上不阻塞 Mac 实现，但阻塞“真实购物已打通”的声明。

## 官方客户端交接（2026-09-12 追加）

快手官网生产导航 `PC/pc_navigation_config` 的“快手Mac版”指向 App Store `440948110`；商店允许 Apple Silicon Mac 运行。增加用户主动点击的“在快手打开购物助手”，按 `com.jiangjia.gif` 定位已安装官方应用，指定该应用打开源码现有的固定 `kwai://krn?bundleId=KwaishopCAIChatPageV2&componentName=KwaishopCAIChatPageV2&entrySrc=HOME_SHORTCUT`。没有安装或启动失败必须显示明确提示。

这是独立快手窗口的交接，不向 Health 导入其凭据，不把外部启动成功算作 Health 原生购物服务已认证，不传递草稿、身份、Cookie 或健康资料。离线演示不显示此出口。官方应用由用户独立登录；真实初始化与新消息返回分别验收。

直接 API 配置精确允许原生源码中出现的 `api1.kwaishop.com` 和 `api2.kwaishop.com`，继续独立匹配 Cookie 域；这不意味着本机已获得这些网关的购物凭据。

## 输入无法提交修复（2026-09-12）

直接购物 API 未配置或未取得服务凭据时，输入框使用明确的“发送到快手”动作，不再保留无法使用的灰色原生发送按钮。点击或 Return 将显式购物草稿按官方入口既有 `sugText` 与 `sugExtData.inputContent` 契约交给指定快手客户端；入口在 load 响应中取得 SEND_MSG 后由 RN 提问，回复在快手窗口显示。普通打开按钮保持无问题参数。

只允许当前输入的内容，无健康上下文或账号凭据；输入通过 JSON 和 URL 查询项编码，空白、超长和控制字符拒绝。派发前再次校验账号与操作代次、草稿及模式；退出、切换账号、清空、切换演示或修改草稿使排队动作失效。保留草稿；启动回执不冒充聊天回包。网页登录移至接入调试菜单，主界面说明回复位置。


## 2026-09-12 本机 RN 桥接增量

用户接受“官方快手作为登录/网络宿主，小巴在当前窗口显示新回复”的本机桥方案，并授权改购物页面。此增量不修改 Java 服务，不复制官方 App 凭据，不绕过客户端签名，不包含远端分发授权。

- Swift Network.framework 只监听 loopback 随机端口；Mac 菜单显式启动，RN 独立页面核对六位码并由用户允许。
- 256 位一次性配对能力随固定官方深链传入，不保存到偏好、日志或业务埋点。它仅证明持有配对能力，不能宣称操作系统对快手进程的身份认证。
- RN 通过动态 system.getAppInfo 检查同一账号，使用已有原生 normalRequest/StreamRequestInstance；初始化只保留内部会话参数，不把历史回传。
- 单个新问题经 request/chat 发送；仅投影展示消息到 chunk；stream_end 表示网络层返回结束，Mac 明示业务完成状态未确认。停止只结束本机转发。
- 消息 ID 使用 mac-UUID，两端约束一致；取消后迟到帧不写入新请求。Origin 限制、一次性配对、帧/队列/整轮容量与超时均有校验。
- 桥接与原生网页登录是显式选择的独立接入方式，断线后不得自动启用旧原生凭据。切换账号或显式重连清理购物会话；不隐式使用健康资料。
- 第一版展示文字、问题、商品名称/价格，所有服务端 URL、嵌套动作与未知卡片不透传；商品购买仍在官方快手中完成。

实际联调依赖：将这版 RN 经正式流程分发给受控测试对象，或提供可在此 Mac 运行且有真实登录与原生网络能力的官方 DEBUG/BETA 宿主。已验证 App Store release 无本地 server/扫码测试包路由，不能直接加载本地修改。真实回复回小巴、后台存活和平台分发均未验收。
