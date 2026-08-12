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
# 跨端变更先让 planner 判路由；纯 Mobile JS 会只得到 mobile_ota action
./scripts/release.sh plan --base <last-published-sha> --target origin/main

./scripts/mobile-ota.sh production "改动说明"
# 也可:无参=用 commit msg 作 message;preview=内部 channel
```
也可以用 `release.sh publish` 让 planner 在验证通过后调用同一 OTA mutation authority。
脚本只发 iOS；native/package/lock/Watch 命中时 planner 抑制 OTA 并要求原生发版。

## 单次事务、复证与耗时证据

`mobile-ota.sh` 每次生成唯一 transaction ID，在私有临时目录只 export 一次：

- 任何新 `eas update` 前先用结构化 `update:list` 查询 transaction marker：0 个才允许
  发布，1 个必须经 `update:view` + `channel:view` 复证后直接补齐本地
  manifest/anchor/audit，多个匹配则 fail closed。这样 release transaction 因本地审计
  追加失败而重入时不会重复发布。若上次进程退出前未留下 artifact，恢复的 manifest 会
  明确记录 `artifact_evidence=unavailable_after_remote_adoption` 与空 digest，不伪造字节证据。
- 明确的瞬时上传失败会先查询该 transaction；无唯一命中时才校验同一目录的
  metadata/bundle/assets、source tree、runtime 和稳定 digest，并用 `--skip-bundler`
  重试同一字节一次。禁止第三次盲发，禁止跨发布缓存 artifact。
- auth、runtime、Metro、语法和配置错误不可重试。symlink、路径穿越、空/缺失资源、
  source/artifact 漂移或 EAS 查询歧义都会停止，且不更新 anchor/manifest。
- 成功必须同时通过结构化 publish JSON、`update:view` 与 `channel:view`；随后原子写
  private schema-v2 manifest，包含 transaction、commit/tree/runtime、artifact digest、
  active/known-good group+update、EAS CLI 和 UTC `published_at`。这里不得写健康内容、
  用户标识或凭证。

验证流水线会输出每项耗时、墙钟耗时和私有日志路径；OTA 以 transaction ID、
`published_at` 和 manifest 作为时序/审计锚点。不要把发布命令接到 `tail`。

## 关键坑

- **OTA 打包的是工作树(working tree),不是 HEAD**。未提交的 WIP 会漏进生产 OTA。**先 commit 或 stash 再推**(记忆 [[project_deploy_mobile_ota_bundles_worktree]])。
- **设备拉取时机**:cold start 或退后台 30s+ 才拉新 bundle。**下拉刷新只重取数据,不换 bundle**——验证 OTA 生效要杀进程重开。
- runtime version 必须匹配(`app.json` runtimeVersion policy=appVersion);跨 runtime 的改动 OTA 推不动,要发新 build。
- channels:`development`(dev client / sim 允许)· `preview`(内部分发)· `production`(App Store,见 `mobile/eas.json`)。

## 回退与人工回滚

失败若没有唯一远端 transaction 证明，保持当前 known-good，不写新 manifest。回滚先
dry-run，再显式确认：

```bash
./scripts/mobile-ota-rollback.sh production
./scripts/mobile-ota-rollback.sh production --confirm
```

回滚不是切回旧 ID，而是验证历史 source group/update 后 republish；脚本再校验新建
active group/update 与 channel mapping，manifest 分开记录 source IDs 和新 active IDs。
缺少/损坏 manifest 或 source pair 不完整时 fail closed；需要时可成对提供已验证的
`--group` 与 `--update-id`。

## 和后端配套

涉及前后端的功能:**两条都走** —— 后端 `backend-deploy`(路由生效)+ 移动端 OTA(渲染代码)。漏任一条 → 手机看到旧行为或「加载失败」。本会话踩过:合并了没部署 + 没 OTA → 功能不可用。

> 改了后端 schema → 先 `cd mobile && npm run generate-types` 再 OTA(防手写类型漂移)。
