# 生产环境部署指南

本指南将帮助你将健康管理系统部署到生产环境。

---

## 📋 部署前检查清单

- [ ] 已准备好生产环境服务器（推荐：Ubuntu 22.04 LTS）
- [ ] 已安装 PostgreSQL 数据库
- [ ] 已安装 Redis 服务
- [ ] 已准备好域名和 SSL 证书
- [ ] 已获取 OpenAI API Key
- [ ] 已配置微信小程序（如需）

---

## 🚀 快速部署（5 步）

### 1️⃣ 克隆代码并配置环境

```bash
# 克隆仓库
git clone https://github.com/yourusername/health-llm-driven.git
cd health-llm-driven/backend

# 复制生产环境配置
cp .env.production .env

# 编辑配置文件
nano .env
```

**⚠️ 必须修改以下配置**：

```bash
# 数据库配置
POSTGRES_HOST=your-actual-database-host.com
POSTGRES_PASSWORD=your-actual-strong-password

# CORS 配置（改为你的域名）
CORS_ALLOW_ORIGINS=https://health.yourdomain.com,https://api.yourdomain.com

# OpenAI API Key
OPENAI_API_KEY=sk-your-actual-openai-key

# 微信小程序（如果使用）
WECHAT_SECRET=your-actual-wechat-secret

# Redis（如果使用云服务）
REDIS_URL=redis://:password@redis-host:6379/0
```

**✅ 已预配置的密钥（无需修改）**：
- `SECRET_KEY`
- `GARMIN_ENCRYPTION_KEY`
- `DEVICE_ENCRYPTION_KEY`

---

### 2️⃣ 安装依赖

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 验证安装
python -c "from cryptography.fernet import Fernet; print('✅ 依赖安装成功')"
```

---

### 3️⃣ 初始化数据库

```bash
# 创建数据库（在 PostgreSQL 中）
psql -U postgres -c "CREATE DATABASE health_db;"
psql -U postgres -c "CREATE USER health_user WITH PASSWORD 'your-password';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE health_db TO health_user;"

# 应用数据库迁移
python -c "from app.database import engine, Base; Base.metadata.create_all(bind=engine); print('✅ 数据库表创建成功')"

# 应用性能索引
psql -U health_user -d health_db -f migrations/add_performance_indexes.sql
```

---

### 4️⃣ 启动服务

#### 方法 A: 使用 Gunicorn（推荐）

```bash
# 安装 Gunicorn
pip install gunicorn

# 启动服务（4 个 worker，适合 4 核 CPU）
gunicorn main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --access-logfile logs/access.log \
  --error-logfile logs/error.log \
  --log-level info
```

#### 方法 B: 使用 Docker（推荐）

```bash
# 创建 Dockerfile（如果还没有）
cat > Dockerfile << 'DOCKER_EOF'
FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["gunicorn", "main:app", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
DOCKER_EOF

# 构建镜像
docker build -t health-api:latest .

# 运行容器
docker run -d \
  --name health-api \
  -p 8000:8000 \
  --env-file .env \
  health-api:latest
```

#### 方法 C: 使用 Systemd（Linux 服务）

```bash
# 创建 systemd 服务文件
sudo tee /etc/systemd/system/health-api.service << 'SERVICE_EOF'
[Unit]
Description=Health Management System API
After=network.target postgresql.service redis.service

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/var/www/health-llm-driven/backend
Environment="PATH=/var/www/health-llm-driven/backend/venv/bin"
ExecStart=/var/www/health-llm-driven/backend/venv/bin/gunicorn main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE_EOF

# 启动服务
sudo systemctl daemon-reload
sudo systemctl enable health-api
sudo systemctl start health-api
sudo systemctl status health-api
```

---

### 5️⃣ 配置 Nginx 反向代理

```bash
# 创建 Nginx 配置
sudo tee /etc/nginx/sites-available/health-api << 'NGINX_EOF'
# HTTP -> HTTPS 重定向
server {
    listen 80;
    server_name api.yourdomain.com health.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS 配置
server {
    listen 443 ssl http2;
    server_name api.yourdomain.com health.yourdomain.com;

    # SSL 证书配置
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # 安全头
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # 限制请求大小（防止大文件上传攻击）
    client_max_body_size 10M;

    # 限流配置（防 DDoS）
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    limit_req zone=api_limit burst=20 nodelay;

    # 日志
    access_log /var/log/nginx/health-api-access.log;
    error_log /var/log/nginx/health-api-error.log;

    # API 反向代理
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;

        # 超时配置
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # 健康检查（不记录日志）
    location /health {
        proxy_pass http://127.0.0.1:8000;
        access_log off;
    }

    # API 文档（可选：生产环境可禁用）
    location /api/docs {
        proxy_pass http://127.0.0.1:8000;
        # 可选：添加 IP 白名单
        # allow 192.168.1.0/24;
        # deny all;
    }
}
NGINX_EOF

# 启用站点
sudo ln -s /etc/nginx/sites-available/health-api /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 🔐 SSL 证书配置（Let's Encrypt）

```bash
# 安装 Certbot
sudo apt install certbot python3-certbot-nginx

# 获取证书
sudo certbot --nginx -d api.yourdomain.com -d health.yourdomain.com

# 自动续期
sudo certbot renew --dry-run
```

---

## 📊 监控和日志

### 1. 应用日志

```bash
# 查看实时日志
tail -f logs/access.log
tail -f logs/error.log

# 查看 systemd 日志
sudo journalctl -u health-api -f
```

### 2. 性能监控

```bash
# 安装 Prometheus + Grafana（可选）
# 参考：https://prometheus.io/docs/introduction/first_steps/
```

### 3. 健康检查

```bash
# 定期检查 API 健康状态
curl https://api.yourdomain.com/api/v1/health

# 预期响应
{
  "status": "healthy",
  "services": {
    "api": "running",
    "database": "connected",
    "redis": "connected"
  }
}
```

---

## 🔧 维护操作

### 更新代码

```bash
cd /var/www/health-llm-driven
git pull origin main

# 重启服务
sudo systemctl restart health-api
```

### 数据库备份

```bash
# 每日自动备份（添加到 crontab）
0 2 * * * pg_dump -U health_user health_db | gzip > /backups/health_db_$(date +\%Y\%m\%d).sql.gz

# 手动备份
pg_dump -U health_user health_db > backup_$(date +%Y%m%d).sql
```

### 清理日志

```bash
# 清理 7 天前的日志
find logs/ -name "*.log" -mtime +7 -delete
```

---

## 🚨 故障排查

### 问题 1: 数据库连接失败

```bash
# 检查数据库状态
sudo systemctl status postgresql

# 检查连接
psql -U health_user -d health_db -c "SELECT 1;"

# 查看日志
sudo tail -f /var/log/postgresql/postgresql-*.log
```

### 问题 2: Redis 连接失败

```bash
# 检查 Redis 状态
sudo systemctl status redis

# 测试连接
redis-cli ping

# 查看日志
sudo tail -f /var/log/redis/redis-server.log
```

### 问题 3: API 响应慢

```bash
# 检查数据库索引
psql -U health_user -d health_db -c "
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC
LIMIT 20;
"

# 检查慢查询
# 编辑 postgresql.conf
# log_min_duration_statement = 1000  # 记录超过 1 秒的查询
```

---

## 📈 性能优化建议

1. **启用 Redis 缓存**
   - 确保 Redis 已启动并正确配置
   - 监控缓存命中率

2. **数据库连接池**
   - 已配置：pool_size=10, max_overflow=20
   - 根据实际负载调整

3. **Gunicorn Worker 数量**
   - 推荐：2-4 × CPU 核心数
   - 示例：4 核 CPU → 8-16 workers

4. **Nginx 缓存**
   - 对静态资源启用缓存
   - 设置合理的 TTL

5. **CDN 加速**
   - 使用 Cloudflare 或 AWS CloudFront
   - 加速静态资源和 API 响应

---

## 📞 技术支持

如遇问题，请：
1. 查看日志文件
2. 检查 [IMPROVEMENTS.md](IMPROVEMENTS.md) 中的已知问题
3. 提交 Issue: https://github.com/yourusername/health-llm-driven/issues

---

## 🎉 部署完成！

访问以下地址验证部署：

- API 文档: https://api.yourdomain.com/api/docs
- 健康检查: https://api.yourdomain.com/api/v1/health
- 主页: https://api.yourdomain.com/

**祝你部署顺利！** 🚀
