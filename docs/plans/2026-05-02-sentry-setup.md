# Sentry DSN 设置指令 (T1.5)

> **状态**: 代码已 ship — backend `main.py:36-57` + mobile `_layout.tsx` + `@sentry/react-native@7.11.0`. **只差 DSN env var**.

## 5 分钟操作清单

### 步骤 1: 创建 Sentry 账号 + 2 个项目

1. 去 https://sentry.io/signup/ 免费注册 (Developer plan, 5k events/month 够个人用)
2. 创建 Organization (随便命名, 比如 `itsoso-health`)
3. 创建 **2 个项目**:
   - **`health-backend`** — Platform 选 Python > FastAPI
   - **`health-mobile`** — Platform 选 React Native
4. 每个项目创建后会显示一个 **DSN** (`https://xxx@o000.ingest.sentry.io/0000000`), 复制保存两个

### 步骤 2: 后端 DSN 写入 `.env-online`

```bash
# 本地编辑 (仓库根)
vi .env-online
# 或你平时怎么改
```

加一行:
```
SENTRY_DSN=https://<backend-dsn>@o000.ingest.sentry.io/0000000
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
```

### 步骤 3: 同步 env 到服务器 + 重启

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven
./deploy.sh -e   # 只同步 .env-online 到服务器 + 重启 backend (不拉代码)
```

### 步骤 4: 验证生效

```bash
ssh root@39.98.206.178 "journalctl -u health-backend -n 20 --no-pager | grep -i sentry"
```

应该看到:
```
[Sentry] 错误监控已启用，环境=production
```

故意触发一条错误验证:
```bash
# 打一个会 500 的 URL (需要登录 token)
/usr/bin/curl -X POST https://health.executor.life/api/v1/client-events \
  -H "Content-Type: application/json" \
  -d '{"event_name":"invalid_intentional"}'
# 应该返 400 (客户端错误, 不 Sentry); 但如果你想触发 500 可以构造一个 body 非 JSON 的请求
```

然后回 Sentry Dashboard (https://sentry.io/issues/) 看是否有事件.

### 步骤 5: Mobile DSN — 留到下次 native build

Mobile Sentry SDK 已安装但 **DSN 注入需要 EAS build** (不是 OTA 能带的). 看 `mobile/applib/sentry.ts` (如果存在, grep 确认) 里是否已经从 `Constants.expoConfig.extra.sentryDsn` 读取.

操作:
1. `mobile/app.json` 的 `extra` 字段加:
   ```json
   "extra": {
     "sentryDsn": "https://<mobile-dsn>@o000.ingest.sentry.io/0000000"
   }
   ```
2. 下次 `eas build --profile production` 时会 bake 进包

**不要** 把 DSN commit 进 git (它相当于 public API key 但泄露还是不优雅). 放在 `.env-online` / `eas secret` 里.

## 验收

1 小时后回 Sentry Dashboard:
- 应该有 ≥1 条 event (哪怕是健康检查 WARN 级)
- Issues 页面应该显示 `health-backend` / `health-mobile` 有数据

若 24h 零事件 → 说明注入没成功, 查 journalctl 看 Sentry init 日志.

## 隐私/合规

代码已经硬性关了 PII:
- `send_default_pii=False` — 不传 IP / cookie / header
- `FastApiIntegration(transaction_style="endpoint")` — 只记 endpoint 名不记完整 URL
- 健康数据 (HRV / 化验 / 基因) 不会被 Sentry 抓 (Sentry 只抓 exception 堆栈 + 预定义 breadcrumb)

若后续想加 custom context, 记得脱敏 (`sentry_sdk.set_context("user", {"id": user.id})` 只传 id 不传姓名).

## Gotchas

- Sentry 每月 5k event 免费, 炸了会停. 可以在 Sentry UI 设 `inbound filter` 过滤健康度 WARN 级日志.
- `traces_sample_rate=0.1` 是 10% 性能采样. 想调就改 env.
- Celery 任务的错误会通过 `CeleryIntegration()` 自动上报.

---

**完成标准**: Dashboard 24h 内有 ≥1 条 event. 观察期 (到 2026-05-09) 零 ERROR 级 issue = 健康.
