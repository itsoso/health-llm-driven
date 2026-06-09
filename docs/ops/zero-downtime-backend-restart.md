# 零停机后端重启（消除部署期 502）

**问题（2026-06-09 修复）**：`health-backend` 是 `Type=simple` 的 uvicorn，`systemctl restart` 会先 SIGTERM 旧进程（`:8000` 监听套接字立刻关闭），新进程要 ~10s 才 import 完并重新 bind。这 ~10s 内 nginx 连 `127.0.0.1:8000` 得到 `ECONNREFUSED (111)`，于是**每个**经 `health.executor.life` 的请求（含 AI 对话、`/api/client-events`、`/api/auth/me` …）都返回 **502**。每次 `deploy.sh -b` 都会触发一次。

**修复**：改用 **systemd socket activation**。让 systemd（而非 uvicorn）持有 `127.0.0.1:8000` 监听套接字 —— 套接字在 service 重启期间**始终不关闭**，握手期的连接被内核 backlog 排队，等新 worker 就绪后再处理，而不是被拒绝。

**效果实测**：重启期间对 `/health` 每 0.2s 探测一次共 110 次 → **110 个 200，0 个拒绝**；落在 worker 重启窗口里的那一个请求排队 ~10s 后**成功**返回（不再是 502）。`deploy.sh` 无需改动 —— 它用的 `systemctl restart health-backend` 现在自动零 502。

## 服务器单元文件（`/etc/systemd/system/`）

> 这两份只活在生产机 `/etc/systemd/system/`，仓库不 track systemd 单元。服务器重建时按此重放。

`health-backend.socket`：

```ini
[Unit]
Description=Health App Backend Socket (zero-downtime restarts)

[Socket]
ListenStream=127.0.0.1:8000
Backlog=2048

[Install]
WantedBy=sockets.target
```

`health-backend.service`（相对旧版的改动：`ExecStart` 把 `--host/--port` 换成 `--fd 3`；加 `Requires=`/`After=health-backend.socket`）：

```ini
[Unit]
Description=Health App Backend
Requires=health-backend.socket
After=network.target health-backend.socket

[Service]
Type=simple
User=root
WorkingDirectory=/opt/health-app/backend
Environment=PATH=/opt/health-app/backend/venv/bin
ExecStart=/opt/health-app/backend/venv/bin/uvicorn main:app --fd 3 --workers 2 --limit-concurrency 100
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## 首次启用 / 重建时

```bash
systemctl daemon-reload
systemctl stop health-backend            # 释放 :8000（仅此一次有几秒计划内停机）
systemctl start health-backend.socket
systemctl start health-backend
systemctl enable health-backend.socket   # 开机自启
```

`--fd 3` + `--workers 2` 在 uvicorn 0.32 上验证可用（systemd 把监听套接字作为 fd 3 传入；uvicorn 父进程 `socket.fromfd(3)` 后共享给 worker）。

## 验证零 502

```bash
( sleep 4; systemctl restart health-backend ) &
for i in $(seq 1 110); do
  curl -s -o /dev/null -w '%{http_code}\n' --max-time 15 http://127.0.0.1:8000/health
  sleep 0.2
done | sort | uniq -c   # 期望：全部 200，无 000
```

## 回滚

```bash
cp /root/health-backend.service.bak-<TS> /etc/systemd/system/health-backend.service
systemctl stop health-backend health-backend.socket
systemctl disable health-backend.socket
rm -f /etc/systemd/system/health-backend.socket
systemctl daemon-reload
systemctl start health-backend
```

## 残留可优化项（非本次范围）

落在 worker 重启窗口的请求仍要等 ~10s（uvicorn worker 重新 import 全量依赖 + DB 迁移检查的耗时）。要进一步压缩排队延迟，可减小 import 成本（懒加载 chromadb / LLM 客户端）或改用 gunicorn `-k uvicorn.workers.UvicornWorker` 的 `HUP` 优雅重载（旧 worker 持续服务直到新 worker 就绪，零排队延迟）。当前 502 已彻底消除，此项优先级低。
