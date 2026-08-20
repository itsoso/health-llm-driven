---
name: mobile-ota
description: "推 mobile JS 改动到生产 (OTA, eas update)。当用户说「发 OTA」「推 OTA」「JS 改动上线手机」「热更新移动端」时使用。只发 iOS bundle;原生/插件/SDK 改动不能 OTA,走 mobile-testflight-release。"
---

# Mobile OTA

`.ts/.tsx/.js`/样式/文案/API 调用/hooks/RN 组件 的改动,走 OTA(秒级生效,不用重 build/发版)。

## 先判断:能 OTA 吗?

✅ 能 OTA:纯 JS/TS、RN 组件、navigation、React Query、状态、样式、文案、API 调用。
❌ 不能 OTA(必须 build,走 `mobile-testflight-release`):`app.json` plugins / `Info.plist` / Podfile / 新 native module / Expo SDK 升级 / `expo-*` 大版本。

## 推

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven
./scripts/mobile-ota.sh production "改动说明"
# 也可:无参=用 commit msg 作 message;preview=内部 channel
```
脚本 = `eas update --platform ios --channel <channel>`。**只发 iOS**(`react-native-maps` 会炸 web bundler,Android 也没分发)。

## 关键坑

- **OTA 打包的是工作树(working tree),不是 HEAD**。未提交的 WIP 会漏进生产 OTA。**先 commit 或移出 WIP 再推**；以脚本的 source/dirty-worktree guard 为准。
- **设备拉取时机**:cold start 或退后台 30s+ 才拉新 bundle。**下拉刷新只重取数据,不换 bundle**——验证 OTA 生效要杀进程重开。
- runtime version 必须匹配(`app.json` runtimeVersion policy=appVersion);跨 runtime 的改动 OTA 推不动,要发新 build。
- channels:`development`(dev client / sim 允许)· `preview`(内部分发)· `production`(App Store,见 `mobile/eas.json`)。

## 和后端配套

涉及前后端的功能:**两条都走** —— 后端 `backend-deploy`(路由生效)+ 移动端 OTA(渲染代码)。漏任一条 → 手机看到旧行为或「加载失败」。本会话踩过:合并了没部署 + 没 OTA → 功能不可用。

> 改了后端 schema → 先 `cd mobile && npm run generate-types` 再 OTA(防手写类型漂移)。
