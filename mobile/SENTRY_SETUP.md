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

在你执行 `eas build` / `expo run:ios` 前 export:
```bash
export EXPO_PUBLIC_SENTRY_DSN="https://abcd1234@..."
```

EAS Build 设置:
```bash
npx eas-cli env:create --scope project --name EXPO_PUBLIC_SENTRY_DSN \
  --value "https://abcd1234@..." --visibility plaintext \
  --environment production --environment preview
```

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

### 3. 重新 build + install

DSN 是构建时常量, 改完必须重 build:

```bash
# JS-only 改动: 不行, Sentry 初始化是 native module 加载, 必须 native build
cd mobile && npx expo run:ios --device suntice
```

之后崩溃/未捕获异常自动上报到 sentry.io 的 Issues 面板.

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
