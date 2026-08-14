# Sentry RN 错误监控接入步骤

代码已经在 `app/_layout.tsx` 顶部初始化, 但需要 DSN 才会真正上报.
未配置 DSN 时是 noop, 开发环境完全无副作用.

## 一次性接入 (你来做的 5 分钟)

### 1. 创建 Sentry 项目

1. 注册 sentry.io (免费 5k events/月, 个人项目够用)
2. New Project → 选 `react-native` → 项目名 `health-pilot-mobile`
3. 复制创建出来的 DSN, 类似:
   ```
   https://abcd1234@o123456.ingest.sentry.io/7654321
   ```

### 2. 把 DSN 注入构建

**方案 A: 通过环境变量 (推荐, 不进 git)**

在本地 `expo run:ios` 前 export:
```bash
export EXPO_PUBLIC_SENTRY_DSN="https://abcd1234@..."
```

当前不通过 EAS env mutation 注入。所有 OTA/rollback channel writer 均冻结；EAS
channel→branch mapping 可能漂移或共用，preview/development 也不是安全隔离。需要远端
环境时先保留为待办，不能用 supplier CLI 绕过当前 release freeze。

production EAS/ASC 以及 repo 自动 server env release entrypoint 当前全部冻结；DSN 的 production 变更必须另立
配置 dossier/Gate，且 manual Gate 只表示 BLOCK。不得直接运行 production `eas
env:create`、改 ASC、由 release helper 同步 server `.env` 或绕过发布 authority。独立
server-local admin utility 仅可在获权人工事件中运行，且不得被自动 release 调用。解冻还需
repo-external root-owned launcher + fixed interpreter/`env -i` + canonical archive/tree
仓库外 materialization，并通过独立 G4。

**方案 B: app.json extra (会进 git, DSN 半公开但 Sentry 设计上允许)**

```json
{
  "expo": {
    "extra": {
      "sentryDsn": "https://abcd1234@..."
    }
  }
}
```

### 3. 仅做 Simulator build 验证

DSN 是构建时常量。冻结期只能用 iOS Simulator 检查本地接线：

```bash
# npm run ios 固定走 Simulator wrapper；不得追加 --device；wrapper 锁定 exact available Simulator UDID
cd mobile && npm run ios
```

由于开发环境配置为 `enabled: !__DEV__`，Simulator 结果不能证明 production 事件已上报。
production DSN/build、物理 iOS 安装与验收均保持 BLOCK，须在全局冻结解除后另走获权流程。

## 验证

进 App → 找一个不会触发的角落 → 在 dev tool 里手动 throw 测试:

```ts
import * as Sentry from '@sentry/react-native';
Sentry.captureException(new Error('test from HealthPilot'));
```

5 秒内 sentry.io 应该看到这条 event.

## 已经配置的部分

- DSN 来源: `process.env.EXPO_PUBLIC_SENTRY_DSN` 优先, 回退 `expoConfig.extra.sentryDsn`
- `enabled: !__DEV__` — 开发环境不上报, 避免噪音
- `sendDefaultPii: false` — 不上传 IP / 用户名等 PII (健康数据合规)
- `tracesSampleRate: 0.1` — 性能采样 10%, 控制额度
- `Sentry.wrap(RootLayout)` — 自动 ErrorBoundary + Profiler

## 后端版

后端 FastAPI 也建议接 sentry-python, 但那是另一个 ROADMAP 项, 这次先做 RN.
