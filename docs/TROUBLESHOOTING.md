# 故障排查指南

> **CURRENT SAFETY OVERRIDE (2026-08-12): 本文的 SSH、Git reset、build、restart、cache
> clear、upload、`systemctl`、PM2 及 production `deploy.sh` 示例均为历史证据，当前禁止
> 执行。** 同 UID 可通过 Git refs/replace、shared `.git/info/attributes` + local
> clean/smudge filter、`.git/info/exclude` 隐藏的 untracked import shadow、`BASH_ENV`、
> `PYTHONPATH`/`sitecustomize` 绕过 repo bootstrap；因此 repo 内自动 server/Mobile/Mac/
> vendor release entrypoints 与本机签名/安装/provisioning 入口必须在 mutation 前 exit 78。
> 人工 release Gate 表示 **STOP/BLOCK**，不得改用 raw SSH 发布、vendor CLI 或 release helper。
> server-local DB migration/setup/admin utility 只可在生产主机的独立显式人工事件中使用，
> 且不得被自动 release 入口调用；本文历史排障命令不能整体视为获权 admin scope。
> 仓库 rc78 只是 ordinary-invocation tombstone；`BASH_ENV` 和 caller-defined
> `exit`/`builtin` function 可改变顶部 guard。writer legacy 必须 literal-false、语法级不可达；
> runtime/operator 不得 source/extract/eval。隔离测试 marker extraction 仅作无 writer/网络的
> 协议 fixture，不构成 release proof；`release-dmg.sh` 整体冻结，含 writer 的文件不能兼任 checker。
>
> `release.py`/`release.sh` plan/validate/publish、`release_production_state` 联网模式及
> `deploy.sh` status/logs/inspect 均冻结。当前只可用 offline evidence parser、公开未认证
> HTTPS、本地 Metro/iOS Simulator/test 和
> `mobile-local-qr.sh --no-upload --ipa <EXISTING_IPA>` 的离线 IPA metadata/report（无安装
> manifest、安装二维码或可安装承诺）。`npm run ios` 固定走 Simulator
> wrapper，不得向 npm/Expo 追加 `--device`；wrapper 只从 available inventory 解析并锁定
> exact Simulator UDID。物理 iOS repo CLI、连接/安装/验收冻结；仓库内 XCUITest 也只接受
> exact available Simulator UDID。物理验收须等解冻后由仓库外获权人工证据流程完成。bare
> `--no-upload` 与自动 archive/export/signing/provisioning（尤其
> `-allowProvisioningUpdates`）也冻结。EAS channel→branch 映射可能漂移或共用，因此所有
> OTA/rollback 网络 writer 均冻结。production 解冻必须另开 dossier，以仓库外
> root-owned launcher + fixed interpreter + `env -i` allowlist + 仓库外 canonical Git
> archive/tree materialization 完成 source/artifact/recovery proof，并通过新的独立 G4。
> 当前 G5/G6/App Store submission 均 BLOCK，不得写 `shipped`/`complete`。
> Mac/nginx direct Python production CLI 也冻结；不调用 `release-dmg.sh` 的独立 test-only
> protocol fixture 与本地 `create-candidate` 只在
> strict non-root + explicit test mode + 固定 non-production roots（macOS `/private/tmp` 或
> `/private/var/folders`；其他平台 `/tmp`，忽略 caller `TMPDIR`）下允许。`deploy.sh
> --inspect-release-lock` 也在读取 lock/env 前 exit 78；等待 repo-external root-owned
> inspector，不得用 raw SSH/helper 代查。
> Android 尚非 shipped/audited Mobile surface；`npm run android`/`expo run:android` 会自动
> native generation、debug signing 与 ADB install，因此同样 earliest exit 78。
> `check_app_store_release_pack.py --final-submit` 会登录 production reviewer 并取得可写
> bearer token，也冻结；仅非 final-submit 静态 pack 与纯静态 iOS config check 保留。
>
> 本文其余内容仅记录历史问题及当时做法；遇到类似问题可用于判断症状，不能作为当前
> 操作手册。

---

## 目录

- [前端部署问题](#前端部署问题)
- [后端问题](#后端问题)
- [小程序问题](#小程序问题)

---

## 前端部署问题

### 1. CSS/JS 文件 400 Bad Request 错误

**问题现象**：
```
GET https://health.westwetlandtech.com/_next/static/css/xxx.css net::ERR_ABORTED 400 (Bad Request)
GET https://health.westwetlandtech.com/_next/static/chunks/app/layout-xxx.js net::ERR_ABORTED 400 (Bad Request)
```

**原因分析**：
1. 前端重新构建后，CSS/JS 文件的 hash 值会改变
2. 旧的 HTML 页面（被缓存）仍然引用旧的文件 hash
3. 旧文件已不存在，服务器返回 400 错误

**可能的缓存层**：
- 浏览器缓存
- Nginx 缓存（`proxy_cache_valid` 配置）
- CDN 缓存
- Next.js 服务缓存（未完全重启）

**当前处理方式**：可用浏览器无痕窗口或强制刷新确认客户端缓存症状，并保存公开未认证
HTTPS 的状态码、响应头和引用的 asset 名称。server commit、磁盘 asset、进程、nginx cache
与 BUILD_ID 必须由未来 repo-external root-owned/restricted inspector 读取。不得使用 raw
SSH、Git reset、远端 build、进程终止、cache 删除或 service restart。记录 **BLOCK** 并移交
获权运维事件。

#### 步骤 6：客户端清除缓存
- **无痕模式**：`Cmd+Shift+N` (Mac) / `Ctrl+Shift+N` (Windows)
- **强制刷新**：`Cmd+Shift+R` (Mac) / `Ctrl+Shift+R` (Windows)
- **清除浏览器缓存**：浏览器设置 → 清除缓存

---

### 2. Git Pull 没有更新到最新代码

**问题现象**：
```bash
git pull
# 显示 Already up to date，但代码不是最新
```

**原因**：本地有未提交的更改或分支冲突

**当前处理方式**：不要在 production checkout 运行 pull/fetch/reset。保存“声明 revision 与
公开行为不一致”的离线证据，交由外部可信 inspector 对 canonical source 与 runtime receipt
复证；仓库内没有修复命令。

---

### 3. 部署后页面没有变化

**排查清单**：

1. 保存 local commit/CI 证据，但不要把它当 production identity。
2. 用公开未认证 HTTPS 保存页面与静态资源症状，不发送凭证或健康数据。
3. 将 runtime receipt、BUILD_ID、进程与磁盘 asset 检查列为外部 inspector 待办。
4. 在外部证据齐全前保持 G5/G6 **BLOCK**，不得重启或重新发布试错。

---

## 后端问题

### 1. API 返回 500 错误

**当前处理方式**：保存公开未认证 HTTPS 的状态码、request ID 与无敏感内容的时间窗口；
日志、进程状态和内部 health 只能由未来外部可信 inspector 读取。不得 raw SSH、读取
`journalctl` 或重启服务。

### 2. 数据库表不存在

**当前处理方式**：自动 release 不得创建/迁移 production schema。若确认为 schema 事件，
只能进入独立、显式获权且审计的 server-local manual-admin Gate，先解析精确目标、迁移文件、
备份与恢复证据；不能把 blocked release 政名后顺带执行 `create_all` 或任意 Python helper。

---

## 小程序问题

### 1. WXSS 编译错误：unexpected token `*`

**问题现象**：
```
[ WXSS 文件编译错误] 
./app.wxss(1:124): unexpected token `*`
```

**原因**：微信小程序 WXSS 不支持 `*` 通配符选择器

**解决方案**：移除 SCSS 中的 `*` 选择器
```scss
// ❌ 错误
* {
  outline: none;
}

// ✅ 正确 - 明确指定元素
view, text, button {
  outline: none;
}
```

### 2. TabBar 页面无法用 navigateTo 跳转

**问题现象**：使用 `Taro.navigateTo` 跳转到 TabBar 页面无效

**原因**：TabBar 页面只能用 `switchTab` 跳转

**解决方案**：
```typescript
// ❌ 错误
Taro.navigateTo({ url: '/pages/ai-assistant/index' })

// ✅ 正确
Taro.switchTab({ url: '/pages/ai-assistant/index' })
```

---

## 生产运维入口（当前冻结）

本仓库没有可复制执行的生产部署、status、logs、restart 或 cache-clear 命令。
`deploy.sh` writer/status/logs/inspect、raw root SSH、`systemctl`、`journalctl`、PM2、远端删除与
服务器构建均不在允许面；不要从 Git 历史、本文旧版本或测试 fixture 恢复这些命令。

生产观察、故障处置和变更必须等待 repo-external、root-owned/restricted 运维 launcher 与
inspector：固定解释器，从 `env -i` 最小 allowlist 启动，使用仓库外 materialized canonical
source，并由新的独立 G4 授权。当前只能保存 offline evidence 或公开未认证 HTTPS 结果；
它们不能形成 G5/G6，也不能授权重启、清缓存、发布或回滚。若服务当前异常，记录
**BLOCK** 并升级给获权运维事件，不要临时改用 provider console 或 helper。

---

## 更新日志

| 日期 | 问题 | 解决方案 |
|------|------|---------|
| 2026-01-18 | CSS 文件 400 错误 | 完全重启前端服务 + 清理 Nginx 缓存 |
| 2026-01-18 | Git pull 未更新 | 历史曾强制重置；已被当前 external trusted ops Gate 取代，无 repo 命令 |
| 2026-01-18 | WXSS `*` 选择器错误 | 移除通配符选择器 |
