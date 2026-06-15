---
name: mobile-testflight-release
description: "把 mobile/ (Expo iOS App) 发到 TestFlight / App Store。当用户说「发 TestFlight」「发新版本」「发版」「iOS 上架测试」「提交 App Store」时使用。区分 OTA(JS 改动)与原生 build(plugin/SDK/native 改动)。"
---

# Mobile TestFlight 发版

`mobile/`(Expo SDK 55 + RN）发到 TestFlight。**先判断该不该发 build**,再选发版路径。

## 第一步:OTA 还是 build?(发错会浪费 20 分钟)

| 改动 | 走哪条 |
|---|---|
| 纯 `.ts/.tsx/.js`/样式/文案/API 调用/hooks/RN 组件 | **OTA**,不是 TestFlight:`./scripts/mobile-ota.sh production "msg"` |
| `app.json` plugins / `Info.plist` / Podfile / 新 native module / Expo SDK 升级 / `expo-*` 大版本 | **必须 build**(本 skill) |
| 发版给测试者 / 上架 | **build + submit**(本 skill) |

JS 改动能 OTA 就别 build。只有原生层变了或要正式发版才走下面。

## 发版路径:远端 EAS build + 自动 submit(✅ 首选,最稳)

```bash
cd mobile
npx eas-cli build -p ios --profile production --non-interactive --auto-submit
```

- **异步执行(15-25 分钟),触发后切别的活,别同步等。**
- 为什么这条最稳:EAS **服务端**存了全套凭据——签名证书 + provisioning profile(在 EAS infra 上**按当前证书重新配对**)+ App Store Connect submit API Key(`[Expo] EAS Submit`)。所以 `--auto-submit` 全自动,**本地不需要 IssuerID / .p8 / altool**。
- `production` profile `autoIncrement: true` → build 号自动 +1(无需手改版本)。
- 完成后看:https://appstoreconnect.apple.com/apps/6763569720/testflight/ios (几分钟处理)。
- 成功标志:日志出现 `✔ Build finished` + `✔ Submitted your app to Apple App Store Connect!`

## 发版路径:本地归档(可选,省 EAS credit,但脆)

```bash
./scripts/mobile-local-archive.sh    # 本地 eas build --local → .ipa → altool 上传
```

- 何时考虑:想省 EAS credit、本地 Xcode 环境齐(ios/ 已 prebuild)。
- **已知会失败的坑(2026-06-15 实测)**:
  1. **provisioning profile 过期/不匹配** → `❌ Provisioning profile "...AppStore..." doesn't include signing certificate "Apple Distribution: ..."`。根因:本地 build 直接用 EAS 下载的旧 profile,**不会按当前证书重新生成**;证书换过(新 `Apple Distribution` vs 旧 `iPhone Distribution`)profile 没同步就炸。
  2. **altool 上传缺凭据** → 脚本需 `APP_STORE_CONNECT_API_KEY`(KeyID)+ `APP_STORE_CONNECT_ISSUER_ID` 在 env;本仓库 .env / .zshrc **都没存**(.p8 在 `~/.appstoreconnect/private_keys/` 但缺 IssuerID),所以自动上传那步会停在 Transporter 手动指引。
- **结论:本地归档签名失败时,直接退回上面的远端 `--auto-submit`**(远端会自己修 profile)。别在本地 build 上反复试。

## 发版前置 checklist

- 工作树**干净**(`git status --short` 空)—— build 打包的是工作树,未提交的 WIP 会进包。
- 要发的代码已 commit + push(远端 build 上传的是当前工作树,但养成先 push 的习惯)。
- 项目坐标(出问题时核对):EAS `@itsoso/health-pilot`(projectId `911ea84f-...`)· bundle `life.executor.health` · Apple Team `QA2U724DAN (baokun Pan)` · ascAppId `6763569720`。

## 排错速查

| 现象 | 处置 |
|---|---|
| 本地 archive `doesn't include signing certificate` | 退远端 `eas build --auto-submit`(自动重配 profile) |
| 远端 build 卡 `Skipping Provisioning Profile validation ... not authenticated` | 正常(本地预检跳过),EAS 服务端会处理,继续等 |
| `eas submit` 缺 ASC key | 远端 `--auto-submit` 用服务端 key,无需本地配;若仍报错查 EAS credentials |
| build 红在 Xcode 编译 | 看日志 `ARCHIVE FAILED` 段的具体 error;native/plugin 改动先 `npx expo prebuild --platform ios --clean` 本地复现 |

> 相关:OTA 与本地 Sim 反馈环见 CLAUDE.md §"iOS 反馈环";`release-engineer` agent 负责发版执行(强制异步)。
