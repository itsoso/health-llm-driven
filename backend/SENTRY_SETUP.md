# Backend Sentry 接入

代码已经在 `main.py` 顶部初始化, 但需要 DSN 才会真正上报.
未配置 DSN 时是 noop, 完全无副作用.

## 配置 (5 分钟)

### 1. 复用 RN 项目还是新建?

**推荐新建**: `health-pilot-backend` 独立项目, 跟 `health-pilot-mobile` 分开统计.
两个项目可以在 sentry.io 同一 org 下, dashboard 切换看.

### 2. 获取 DSN

sentry.io → New Project → 选 `python` (或 fastapi) → 项目名 → 复制 DSN.

### 3. 注入到生产服务器

SSH 改 `.env-online`:

```bash
ssh root@39.98.206.178
cd /opt/health-app/backend
nano .env-online   # 加入:
# SENTRY_DSN=https://xxxxx@o123456.ingest.sentry.io/7654321
# SENTRY_ENVIRONMENT=production
# SENTRY_TRACES_SAMPLE_RATE=0.05
```

或者本地改 `.env-online` 然后 `./deploy.sh -e` 同步.

### 4. 重启

```bash
./deploy.sh -r
```

启动日志会出现:
```
[Sentry] 错误监控已启用，环境=production
```

## 已经配置的部分

- 启用条件: `settings.sentry_dsn` 非空时才 `sentry_sdk.init`, 否则 noop
- `send_default_pii=False`: 不上传 IP/cookie/headers (健康数据合规)
- `traces_sample_rate=0.05`: 性能采样 5%, 控制额度
- 集成: FastAPI (transaction_style=endpoint) + SQLAlchemy + Celery
  → 自动捕获所有 endpoint 异常 + Celery task 失败 + DB 慢查询

## 验证

部署后随便 `curl` 一个错误路由:

```bash
curl https://health-api.executor.life/this-route-does-not-exist
```

或者在 Python shell 里手动:

```python
import sentry_sdk
sentry_sdk.capture_exception(Exception("backend smoke test"))
```

5 秒内 sentry.io Issues 应能看到.

## 与 RN 的关联

如果给两个项目都设了同一个 `release` (e.g. git commit SHA),
同一次发版的前后端错误会在 Sentry release 页面汇总, 排查问题时一键关联.

后续可以做的:
- 在 deploy.sh 里 export `SENTRY_RELEASE=$(git rev-parse --short HEAD)`
- 加 `release` 参数到 `sentry_sdk.init`
