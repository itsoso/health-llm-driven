# 域名分离与备案号配置

**操作时间**: 2026-01-23 14:13  
**目的**: 将 executor.life 和 westwetlandtech.com 分离，executor.life 删除公安备案号

## 📋 配置变更

### 变更前

| 域名 | 配置方式 | 备案信息 |
|------|---------|---------|
| executor.life | 代理到 westwetlandtech.com | 浙公网安备33010602014186号 + 浙ICP备2025212705号-3 |
| westwetlandtech.com | 独立站点 | 浙公网安备33010602014186号 + 浙ICP备2025212705号-3 |

**问题**: executor.life 通过代理显示了公安备案号

### 变更后

| 域名 | 配置方式 | 备案信息 |
|------|---------|---------|
| executor.life | 独立站点 | ✅ **仅** 浙ICP备2025212705号-3 |
| westwetlandtech.com | 独立站点 | ✅ 浙公网安备33010602014186号 + 浙ICP备2025212705号-3 |

**结果**: 两个域名独立配置，备案信息分离

## 🏗️ 架构变更

### 变更前架构

```
executor.life (443/80)
    ↓ (proxy_pass)
westwetlandtech.com (443/80)
    ↓ (root)
/var/www/westwetlandtech/
```

### 变更后架构

```
executor.life (443/80)                    westwetlandtech.com (443/80)
    ↓ (root)                                  ↓ (root)
/var/www/executor.life/                   /var/www/westwetlandtech/
    ├── index.html (无公安备案)               ├── index.html (有公安备案)
    ├── about.html                            ├── about.html
    ├── privacy.html                          ├── privacy.html
    └── assets/                               └── assets/
```

## 📁 文件结构

### executor.life 目录

```bash
/var/www/executor.life/
├── index.html          # 删除了公安备案号
├── about.html          # 从 westwetlandtech 复制
├── privacy.html        # 从 westwetlandtech 复制
├── terms.html          # 从 westwetlandtech 复制
├── delete-data.html    # 从 westwetlandtech 复制
├── garmin-data-use.html # 从 westwetlandtech 复制
└── assets/             # 从 westwetlandtech 复制
    ├── styles.css
    └── script.js
```

### westwetlandtech.com 目录

```bash
/var/www/westwetlandtech/
├── index.html                          # 保留完整备案信息
├── index.html.backup-20260123-141055  # 旧版本备份（备案号-1）
├── about.html
├── privacy.html
├── terms.html
├── delete-data.html
├── garmin-data-use.html
└── assets/
    ├── styles.css
    └── script.js
```

## 🔧 执行的操作

### 1. 创建 executor.life 独立目录

```bash
mkdir -p /var/www/executor.life
```

### 2. 创建删除公安备案号的 index.html

**关键修改**（第 201 行）:

**westwetlandtech.com 版本**（保留公安备案）:
```html
<div class="beian-wrap">
  <a class="beian-pill" href="https://beian.mps.gov.cn/#/query/webSearch?code=33010602014186" target="_blank" rel="noreferrer noopener">
    <img class="icp-icon" src="https://img.alicdn.com/imgextra/i2/O1CN0108Mv2B1VBiUZxdc4j_!!6000000002615-2-tps-30-30.png" alt="" aria-hidden="true" loading="lazy" decoding="async"/>
    <span class="beian-text">浙公网安备33010602014186号</span>
  </a>
  <a class="beian-pill" href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer">
    <span class="beian-text">浙ICP备2025212705号-3</span>
  </a>
</div>
```

**executor.life 版本**（删除公安备案）:
```html
<div class="beian-wrap">
  <a class="beian-pill" href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer">
    <span class="beian-text">浙ICP备2025212705号-3</span>
  </a>
</div>
```

### 3. 复制其他文件

```bash
# 复制 assets 目录
cp -r /var/www/westwetlandtech/assets /var/www/executor.life/

# 复制其他页面
cp /var/www/westwetlandtech/about.html /var/www/executor.life/
cp /var/www/westwetlandtech/privacy.html /var/www/executor.life/
cp /var/www/westwetlandtech/terms.html /var/www/executor.life/
cp /var/www/westwetlandtech/delete-data.html /var/www/executor.life/
cp /var/www/westwetlandtech/garmin-data-use.html /var/www/executor.life/
```

### 4. 更新 nginx 配置

**新的 executor.life 配置** (`/etc/nginx/conf.d/executor.life.conf`):

```nginx
# executor.life - 独立配置（删除公安备案号）
server {
    listen 443 ssl http2;
    server_name executor.life www.executor.life;
    
    ssl_certificate /etc/letsencrypt/live/executor.life/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/executor.life/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    # 使用独立的网站目录
    root /var/www/executor.life;
    index index.html;

    location / {
        try_files $uri $uri/ $uri.html /index.html;
    }

    location /assets/ {
        try_files $uri =404;
    }
}

server {
    listen 80;
    server_name executor.life www.executor.life;
    
    location /.well-known/acme-challenge/ {
        root /var/www/executor.life;
    }
    
    location / {
        return 301 https://$host$request_uri;
    }
}
```

**关键变更**:
- ❌ 删除了 `proxy_pass https://westwetlandtech.com;`
- ✅ 添加了 `root /var/www/executor.life;`
- ✅ 添加了 `try_files` 配置

### 5. 重新加载 nginx

```bash
nginx -t
systemctl reload nginx
```

## ✅ 验证结果

### executor.life 备案信息

```bash
$ curl -s https://executor.life/ | grep -o '浙[^<]*'
浙ICP备2025212705号-3
```

✅ **仅显示 ICP 备案号，无公安备案号**

### westwetlandtech.com 备案信息

```bash
$ curl -s https://westwetlandtech.com/ | grep -o '浙[^<]*'
浙公网安备33010602014186号
浙ICP备2025212705号-3
```

✅ **显示完整备案信息（公安备案 + ICP 备案）**

## 📊 对比表

| 项目 | executor.life | westwetlandtech.com |
|------|--------------|---------------------|
| 公安备案号 | ❌ 已删除 | ✅ 保留 |
| ICP 备案号 | ✅ 浙ICP备2025212705号-3 | ✅ 浙ICP备2025212705号-3 |
| 网站目录 | /var/www/executor.life | /var/www/westwetlandtech |
| Nginx 配置 | 独立站点 | 独立站点 |
| 代理关系 | 无 | 无 |

## 🔄 如何更新内容

### 更新 executor.life

```bash
# 编辑文件
vi /var/www/executor.life/index.html

# 无需重启 nginx（静态文件）
```

### 更新 westwetlandtech.com

```bash
# 编辑文件
vi /var/www/westwetlandtech/index.html

# 无需重启 nginx（静态文件）
```

### 同步更新两个站点

如果需要同步更新内容（除了备案号），可以：

```bash
# 1. 修改 westwetlandtech.com 的文件
vi /var/www/westwetlandtech/index.html

# 2. 复制到 executor.life（会覆盖，注意备案号）
# 建议手动复制内容，而不是直接 cp，以保留备案号差异
```

## 📌 注意事项

### 1. 备案号差异

- **executor.life**: 仅 ICP 备案号（浙ICP备2025212705号-3）
- **westwetlandtech.com**: 公安备案 + ICP 备案

### 2. 文件独立性

- 两个域名现在使用独立的文件
- 修改一个不会影响另一个
- 需要同步更新时，注意保留备案号差异

### 3. assets 目录

- 目前是复制的，两个站点各有一份
- 如果需要共享，可以使用软链接：
  ```bash
  rm -rf /var/www/executor.life/assets
  ln -s /var/www/westwetlandtech/assets /var/www/executor.life/assets
  ```

### 4. SSL 证书

- 两个域名使用各自的 Let's Encrypt 证书
- 证书自动续期，无需手动操作

## 🎯 完成状态

- ✅ 创建 executor.life 独立目录
- ✅ 删除 executor.life 的公安备案号
- ✅ 保留 westwetlandtech.com 的完整备案信息
- ✅ 更新 nginx 配置，分离两个域名
- ✅ 验证两个域名显示正确的备案信息
- ✅ 创建操作记录文档

---

**配置完成！** 🎉

- **executor.life** 现在只显示 ICP 备案号
- **westwetlandtech.com** 保留完整的备案信息（公安备案 + ICP 备案）
- 两个域名完全独立，互不影响
