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
- **结论:本地归档签名失败时,先试远端 `--auto-submit`;远端也修不动(见下)再走原生兜底。** 别在 `eas build --local` 上反复试同一个签名错。

## 发版路径:原生 xcodebuild + ASC key(✅ 终极兜底,EAS 凭据漂移时唯一能过的路)

> ⚠️ **先纠正一条曾经的错误断言(2026-06-18 复盘)**:本节原写"远端 `--auto-submit` 也会撞证书漂移"——
> **错的,是没测远端就臆断**(当时所有失败都是 `--local`)。实测:**远端 `eas build --profile production
> --non-interactive --auto-submit` 不撞本地证书漂移**(它用 EAS 服务端自洽的证书+profile 构建,与本机钥匙串无关),
> 且**正确打包多 target 手表 app** + `autoIncrement` 自动版本号。**带手表/复杂 target 的发版,远端就是首选,别走下面的本地原生路。**
> build 123(含 standalone watch)就是本地原生失败后改远端一把过的。下面这节只在**远端不可用**(断网/EAS 配额耗尽)时才用。
>
> ⚠️ **本地原生路的两条硬伤(只适合单 target app)**:① 需本机钥匙串证书与 profile 对得上(否则 `--local` 撞
> `doesn't include signing certificate`);② **命令行 `CODE_SIGN_STYLE=Automatic`/`DEVELOPMENT_TEAM=` 会串到所有 target**,
> 把 watch 子 app 错绑成主 app 的 bundle id(build 118 实测:`Watch/HealthPilot.app` 拿了 `life.executor.health`)→ 上传被拒。
> **有 watch/extension 子 target 时禁用本地原生归档,走远端。**

**触发场景(单 target、远端不可用时;2026-06-18 烧了 ~5 次 build 才定位)**:换过分发证书后,EAS 凭据库里存的
profile 仍绑**旧**证书(`eas credentials` 里看 Distribution Certificate 的 serial 和本机钥匙串
对不上,如 EAS 存 `1FA510…` 而本机是 `CD61BFA4…`)。结果:**`eas build --local`** 会撞 `Provisioning
profile doesn't include signing certificate "Apple Distribution: …"`(本机钥匙串那张新证书 ≠ EAS profile 绑的旧证书)。
**注意:远端 build 不受此影响**(见上)。本地彻底修法是交互式 `eas credentials` 重签发(要 Apple ID + 2FA,
assistant 做不了)——所以本地撞了**优先改走远端**,而不是死磕本地。

**绕过去**:完全不碰 EAS 凭据,用 **App Store Connect API Key(.env 里那把,只需 Key 不需 2FA)**
+ **本机钥匙串里的分发证书**,原生 `xcodebuild` 出包:

```bash
# 在 origin/main 的干净 worktree 里(npm install 过),ruby@3.3 在 PATH
bash <repo>/.claude/skills/mobile-testflight-release/scripts/native-archive-asc.sh
# 可选:WORK=/tmp/xxx BUILD_NO=118 APPLE_TEAM_ID=... 覆盖默认
```

脚本(`scripts/native-archive-asc.sh` + `scripts/asc_profiles.py`)逐个解掉这串坑,**每个都踩过**:

| 关卡 | 症状 | 解法(脚本已内置) |
|---|---|---|
| ruby 4 | pod install / fastlane 崩 | 先验证当前 Xcode/CocoaPods 支持矩阵；若仓库工具链仍固定 Ruby 3.3，再显式把 `ruby@3.3` 放到 `PATH` 前部 |
| cocoapods locale | `Unicode Normalization not appropriate for ASCII-8BIT` | `export LANG/LC_ALL=en_US.UTF-8` |
| Sentry build phase | `An organization ID or slug is required (--org)` → ARCHIVE FAILED | `export SENTRY_DISABLE_AUTO_UPLOAD=true` |
| 签名(archive) | profile 不含当前证书 | `xcodebuild archive -allowProvisioningUpdates -authenticationKeyPath <p8> -authenticationKeyID -authenticationKeyIssuerID` + `CODE_SIGN_STYLE=Automatic` → 用钥匙串真证书,ASC key 云端配 profile |
| 签名(export) | `exportArchive Cloud signing permission error / No profiles found` | 不用 automatic export;先用 ASC API **写**接口为 3 个 bundle id 建 profile(绑本机证书序列号匹配到的 ASC cert id)、下载装到 `~/Library/MobileDevice/Provisioning Profiles/`,再 `manual` 签名 export(`asc_profiles.py` 干这个) |
| altool 拒收 | `CFBundleVersion Mismatch` 手表 `1/1.0` ≠ 主 app `<build>/<version>` | archive 里直接 PlistBuddy 改 `RevaWatch.app` + `RevaComplication.appex` 的 Info.plist 对齐主 app(免重编重导) |

**前提**:ASC API Key 要有 **Certificates/Identifiers/Profiles 写权限**(`asc_profiles.py` 会先验,
建 profile 返回 201 即有)。Apple 分发证书上限 2 张,别为修这个再建第三张撞限。
**成功标志**:`✓✓ UPLOADED TO TESTFLIGHT`。全程零 Apple ID 登录。
**重导专用**:archive 已成、只 export/upload 失败时,别重跑整脚本(省 15 分钟 archive)——
archive 在 `$WORK/app.xcarchive` 还在,只重跑 [3.5]+[4]+[5]+[6] 那几步(patch 版本 → 建 profile → manual export → altool)。

## 发版前置 checklist

- 工作树**干净**(`git status --short` 空)—— build 打包的是工作树,未提交的 WIP 会进包。
- 要发的代码已 commit + push(远端 build 上传的是当前工作树,但养成先 push 的习惯)。
- 项目坐标(出问题时核对):EAS `@itsoso/health-pilot`(projectId `911ea84f-...`)· bundle `life.executor.health` · Apple Team `QA2U724DAN (baokun Pan)` · ascAppId `6763569720`。

## 排错速查

| 现象 | 处置 |
|---|---|
| `doesn't include signing certificate`(本地 **和** 远端都炸) | EAS 凭据库证书漂移 → 走上面「原生 xcodebuild + ASC key」兜底脚本;别指望远端自动修 |
| 远端 build 卡 `Skipping Provisioning Profile validation ... not authenticated` | 本地预检跳过是正常;但若最终 archive 仍 `doesn't include cert`,就是凭据漂移,转原生兜底 |
| `exportArchive Cloud signing permission error` | export 别用 automatic;用 `asc_profiles.py` 建 manual profile 后 manual 签名 export |
| altool `CFBundleVersion Mismatch`(手表 vs 主 app) | archive 里 PlistBuddy 把 watch/complication 版本对齐主 app,重 export |
| `eas submit` 缺 ASC key | 远端 `--auto-submit` 用服务端 key,无需本地配;若仍报错查 EAS credentials |
| build 红在 Xcode 编译 | 看日志 `ARCHIVE FAILED` 段的具体 error;native/plugin 改动先 `npx expo prebuild --platform ios --clean` 本地复现 |

> 相关:OTA 与本地 Sim 反馈环见 `docs/agent-skill-binding.md`；发版执行必须异步并由当前唯一 controller 记录结果。
