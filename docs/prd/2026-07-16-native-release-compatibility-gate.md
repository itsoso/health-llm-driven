# 原生版本兼容门 PRD

## 1. 背景

Remote Config 已能下发 `minimum_native_build` 和 `recommended_native_build`，但旧原生包目前只会静默跳过不兼容 OTA。用户看不到原因，运营也无法区分“当前无 OTA”与“必须原生升级”。这会把原生能力边界变成隐性故障。

## 2. 目标

让客户端在读取发布策略后明确判断原生包状态：

- 当前原生 build 低于最低版本，停止应用不兼容 OTA，并显示不可忽略的原生升级提示。
- 当前原生 build 低于推荐版本，显示可关闭的升级建议，但不阻断既有健康能力。
- 升级入口只能打开受限的官方应用商店链接；链接缺失时仍要解释原因，不能显示一个无效按钮。
- 原生升级判断和 OTA 下载状态分离，避免把“原生升级”误报成 OTA 下载失败。

## 3. 用户与产品能力

**用户**：使用旧版小巴、需要新原生能力或安全修复的用户。

**一级能力归属**：受控应用更新平面；属于“原生发版负责安全和能力边界”的客户端执行层。

**用户路径**：启动/回到前台 → 拉取或读取最后有效策略 → 判断 native build →

- `required`：显示“需要更新小巴”，停止 OTA，保留当前页面和健康数据可读性；有官方链接时提供“去更新”。
- `recommended`：显示“有可选的原生更新”，不影响聊天、记录和既有 OTA；可关闭。
- `none`：按现有 OTA 策略继续。

## 4. 范围

- 策略 API、模型和 PostgreSQL/SQLite managed migration 增加可选 `native_update_url`。
- 后端只接受 `https://apps.apple.com/` 或 `https://play.google.com/` 下的链接，并写入 Admin 审计日志。
- Mobile 增加原生版本状态、官方商店跳转、缺失链接的可见降级和 content-free telemetry。
- 最低版本不满足时不执行 OTA 下载；推荐版本不满足时仍可执行符合条件的 OTA。

## 5. 非目标

- 不通过 Remote Config 修改医疗规则、阈值、诊断、用药或推送内容。
- 不自动提交 App Store/Google Play，不自动关闭用户健康能力。
- 不把商店 URL 当作任意网页跳转；不接受 `javascript:`、自定义 scheme 或非官方域名。
- 不在本切片实现 crash-loop 自动回滚、自动灰度推进或 Mac/Web 原生更新。

## 6. 验收指标

- 最低 build 不满足时：`downloadAvailableUpdate` 不被调用，状态可被 UI 观察，提示不可通过“稍后”关闭。
- 推荐 build 不满足时：OTA 仍按策略检查，提示可关闭。
- 链接缺失时：不渲染跳转按钮，提示仍明确说明需从应用商店更新。
- API 对非法商店 URL 返回 422；合法 URL 能被客户端接收并缓存。
- 原生门事件不包含用户健康正文、账号标识、图片或诊断信息。

## 7. 安全与故障降级

- Remote Config 网络失败沿用 last-known-good / safe default；没有有效策略时不凭空阻断用户。
- 已缓存的 `required` 策略在有效期内继续阻断不兼容 OTA，但不阻断既有聊天和健康记录读取。
- 商店链接打开失败必须显示错误，不静默吞掉用户动作。
- `native_update_required` 和 `native_update_recommended` 作为更新终态的观察事件，但不计入 OTA 失败率分母。
