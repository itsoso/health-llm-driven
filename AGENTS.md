# AGENTS.md - AI Agent 开发规范

> executor.life 项目 AI Agent 必须遵循的开发规则和安全准则
>
> **本文件定位 = 硬规则裁判**(安全/日志/测试/性能/隐私/提交/部署/DB)。它是「编码 agent 操作工具架」的规则层 —— 工具架的整体设计(导航 / 验证闸门 / 经验沉淀)见 `docs/design-agent-operating-harness.md`;产品里健康 agent 的 LLM 方法论见 `docs/HARNESS.md`(与本文件互不重述);产品范围与需求演进约束见 `docs/specs/reva-product-governance-spec.md`。

## 1. 安全规范 🔒

> 📄 全文已拆到 [`docs/governance/security.md`](docs/governance/security.md)（Operating Harness Phase 2, 2026-05-31）。含:1.1 依赖安全 · 1.2 代码安全 · 1.3 服务器安全。**改本章请改那个文件,此处只留导航。**

## 2. 日志规范 📝

### 2.1 日志级别定义

| 级别 | 用途 | 线上默认 |
|------|------|----------|
| DEBUG | 详细调试信息，变量值、流程追踪 | 关闭 |
| INFO | 正常业务流程，关键操作记录 | 开启 |
| WARNING | 异常但可恢复的情况 | 开启 |
| ERROR | 错误，需要关注但不影响服务 | 开启 |
| CRITICAL | 严重错误，服务可能中断 | 开启 |

### 2.2 日志格式标准

```python
# backend/app/utils/logging_config.py
import logging
import sys
from datetime import datetime

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def setup_logging(level: str = "INFO"):
    """
    配置日志系统
    
    Args:
        level: DEBUG/INFO/WARNING/ERROR/CRITICAL
    """
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(f"logs/app_{datetime.now():%Y%m%d}.log")
        ]
    )
```

### 2.3 业务日志要求

```python
# 功能日志示例
logger.info(f"用户 {user_id} 开始同步 Garmin 数据")
logger.info(f"用户 {user_id} Garmin 同步完成，获取 {record_count} 条记录")

# 性能日志示例
import time

start_time = time.time()
result = await heavy_operation()
duration = time.time() - start_time
logger.info(f"heavy_operation 执行完成，耗时 {duration:.3f}s")

# 错误日志示例（包含上下文）
try:
    result = await api_call()
except Exception as e:
    logger.error(f"API 调用失败 - user_id={user_id}, endpoint={endpoint}, error={str(e)}")
    logger.debug(f"完整异常信息", exc_info=True)  # 仅 DEBUG 级别打印堆栈
```

### 2.4 动态日志级别

```python
# 通过 API 动态调整日志级别
@router.post("/admin/log-level")
async def set_log_level(
    level: str,
    current_user: User = Depends(get_admin_user)
):
    """动态设置日志级别（仅管理员）"""
    import logging
    
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if level.upper() not in valid_levels:
        raise HTTPException(400, f"无效的日志级别，可选: {valid_levels}")
    
    logging.getLogger().setLevel(getattr(logging, level.upper()))
    logger.info(f"日志级别已调整为 {level.upper()}，操作者: {current_user.email}")
    
    return {"message": f"日志级别已设置为 {level.upper()}"}
```

### 2.5 敏感信息脱敏

```python
def mask_sensitive(data: dict, fields: list) -> dict:
    """脱敏敏感字段"""
    masked = data.copy()
    for field in fields:
        if field in masked:
            value = str(masked[field])
            if len(value) > 4:
                masked[field] = value[:2] + "***" + value[-2:]
            else:
                masked[field] = "***"
    return masked

# 使用示例
logger.info(f"用户登录: {mask_sensitive(user_data, ['password', 'token', 'phone'])}")
```

---

## 3. 测试规范 🧪

> 📄 全文已拆到 [`docs/governance/testing.md`](docs/governance/testing.md)（Operating Harness Phase 2, 2026-05-31）。含:3.1 测试覆盖要求 · 3.2 测试文件结构 · 3.3 测试命名规范 · 3.4 测试示例 · 3.5 CI/CD 集成。**改本章请改那个文件,此处只留导航。**

## 4. 性能规范 ⚡

### 4.1 响应时间要求

| 操作类型 | 目标响应时间 | 最大响应时间 |
|---------|-------------|-------------|
| 简单查询 | < 100ms | 500ms |
| 复杂查询 | < 500ms | 2s |
| 列表接口 | < 300ms | 1s |
| AI 分析 | < 5s | 30s |
| 文件上传 | < 2s | 10s |

### 4.2 数据库优化

```python
# 必须为常用查询字段建立索引
class GarminData(Base):
    __tablename__ = "garmin_data"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)  # 索引
    record_date = Column(Date, index=True)  # 索引
    
    # 复合索引
    __table_args__ = (
        Index('idx_user_date', 'user_id', 'record_date'),
    )

# 查询优化 - 避免 N+1 问题
# ❌ 错误示例
users = db.query(User).all()
for user in users:
    profile = db.query(UserProfile).filter_by(user_id=user.id).first()  # N 次查询

# ✅ 正确示例
users = db.query(User).options(joinedload(User.profile)).all()  # 1 次查询
```

### 4.3 缓存策略

```python
from functools import lru_cache
from datetime import datetime, timedelta

# 内存缓存（适用于不常变化的数据）
@lru_cache(maxsize=100)
def get_cached_config(key: str) -> str:
    return db.query(Config).filter_by(key=key).first().value

# 带过期时间的缓存
class TTLCache:
    def __init__(self, ttl_seconds: int = 300):
        self._cache = {}
        self._ttl = timedelta(seconds=ttl_seconds)
    
    def get(self, key: str):
        if key in self._cache:
            value, timestamp = self._cache[key]
            if datetime.now() - timestamp < self._ttl:
                return value
            del self._cache[key]
        return None
    
    def set(self, key: str, value):
        self._cache[key] = (value, datetime.now())

# 使用示例
weather_cache = TTLCache(ttl_seconds=1800)  # 30分钟缓存
```

### 4.4 异步处理

```python
# 耗时操作使用异步
import asyncio

async def sync_all_users_garmin_data():
    """批量同步所有用户数据"""
    users = get_sync_enabled_users()
    
    # 并发但限制并发数
    semaphore = asyncio.Semaphore(5)  # 最多同时 5 个
    
    async def sync_with_limit(user):
        async with semaphore:
            await sync_user_data(user)
    
    await asyncio.gather(*[sync_with_limit(u) for u in users])
```

### 4.5 性能监控

```python
import time
from functools import wraps

def performance_log(threshold_ms: float = 1000):
    """性能日志装饰器，超过阈值记录警告"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.time()
            result = await func(*args, **kwargs)
            duration_ms = (time.time() - start) * 1000
            
            if duration_ms > threshold_ms:
                logger.warning(
                    f"慢操作警告: {func.__name__} 耗时 {duration_ms:.2f}ms "
                    f"(阈值: {threshold_ms}ms)"
                )
            else:
                logger.debug(f"{func.__name__} 执行耗时 {duration_ms:.2f}ms")
            
            return result
        return wrapper
    return decorator

# 使用示例
@performance_log(threshold_ms=500)
async def get_daily_recommendation(user_id: int):
    ...
```

---

## 5. 数据安全与隐私 🛡️

### 5.1 数据分类

| 级别 | 类型 | 处理要求 |
|------|------|---------|
| L1 - 公开 | 系统配置、静态内容 | 无特殊要求 |
| L2 - 内部 | 聚合统计数据 | 访问控制 |
| L3 - 机密 | 用户健康数据、行为数据 | 加密存储、访问审计 |
| L4 - 绝密 | 密码、Token、密钥 | 加密、不可逆、最小权限 |

### 5.2 用户数据隔离

```python
# 所有用户数据查询必须带 user_id 过滤
# ❌ 错误示例 - 可能泄露其他用户数据
@router.get("/health-data/{record_id}")
async def get_health_data(record_id: int):
    return db.query(HealthData).filter_by(id=record_id).first()

# ✅ 正确示例 - 强制用户隔离
@router.get("/health-data/{record_id}")
async def get_health_data(
    record_id: int,
    current_user: User = Depends(get_current_user_required)
):
    record = db.query(HealthData).filter(
        HealthData.id == record_id,
        HealthData.user_id == current_user.id  # 强制过滤
    ).first()
    
    if not record:
        raise HTTPException(404, "数据不存在")
    
    return record
```

### 5.3 敏感数据加密

```python
from cryptography.fernet import Fernet
import os

# 加密服务
class EncryptionService:
    def __init__(self):
        key = os.getenv("ENCRYPTION_KEY")
        if not key:
            raise ValueError("ENCRYPTION_KEY 环境变量未设置")
        self.cipher = Fernet(key.encode())
    
    def encrypt(self, data: str) -> str:
        return self.cipher.encrypt(data.encode()).decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        return self.cipher.decrypt(encrypted_data.encode()).decode()

# 存储敏感凭证时加密
def save_garmin_credentials(user_id: int, password: str):
    encryption = EncryptionService()
    encrypted_password = encryption.encrypt(password)
    
    credential = GarminCredential(
        user_id=user_id,
        encrypted_password=encrypted_password  # 加密存储
    )
    db.add(credential)
    db.commit()
```

### 5.4 API 安全

```python
# 请求频率限制
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/login")
@limiter.limit("5/minute")  # 每分钟最多 5 次
async def login(request: Request, credentials: LoginRequest):
    ...

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://executor.life", "https://health.executor.life"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=True,
)

# 请求大小限制
app.add_middleware(
    RequestSizeLimitMiddleware,
    max_size=10 * 1024 * 1024  # 10MB
)
```

### 5.5 审计日志

```python
# 敏感操作必须记录审计日志
class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String(100))  # login, logout, data_export, admin_action
    resource = Column(String(100))  # 操作的资源
    details = Column(JSON)  # 操作详情
    ip_address = Column(String(50))
    user_agent = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)

def log_audit(
    user_id: int,
    action: str,
    resource: str,
    details: dict,
    request: Request
):
    audit = AuditLog(
        user_id=user_id,
        action=action,
        resource=resource,
        details=details,
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent", "")[:500]
    )
    db.add(audit)
    db.commit()

# 使用示例
@router.get("/export/health-data")
async def export_health_data(
    request: Request,
    current_user: User = Depends(get_current_user_required)
):
    log_audit(
        user_id=current_user.id,
        action="data_export",
        resource="health_data",
        details={"format": "json", "date_range": "last_30_days"},
        request=request
    )
    ...
```

---

## 6. 代码提交规范 📋

### 6.1 Commit Message 格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type 类型：**
- `feat`: 新功能
- `fix`: 修复 bug
- `docs`: 文档更新
- `style`: 代码格式（不影响功能）
- `refactor`: 重构
- `perf`: 性能优化
- `test`: 测试相关
- `chore`: 构建/工具变更
- `security`: 安全修复

**示例：**
```
feat(ai-scheduler): 添加早间健康简报功能

- 新增 AIScheduler 服务类
- 支持个性化问候语和健康数据摘要
- 集成用户画像和 Garmin 数据

Closes #123
```

### 6.2 代码审查清单

在提交 PR 前检查：

- [ ] 无硬编码的密钥或敏感信息
- [ ] 新依赖已检查安全性
- [ ] 添加了必要的日志
- [ ] 编写了单元测试
- [ ] 用户数据查询有 user_id 过滤
- [ ] 敏感操作有权限检查
- [ ] 代码通过 lint 检查
- [ ] 更新了相关文档

---

## 7. 紧急响应流程 🚨

### 7.1 安全事件处理

```
1. 发现异常 → 2. 隔离受影响系统 → 3. 保留证据 → 4. 分析原因 → 5. 修复并加固 → 6. 复盘总结
```

### 7.2 紧急联系

- 发现安全问题立即上报
- 保留完整的日志和证据
- 不要删除或修改被入侵的文件（先备份）

### 7.3 常用安全检查命令

```bash
# 检查异常进程
ps aux | grep -E "(curl|wget|chmod|nc|bash -i)" | grep -v grep

# 检查异常网络连接
ss -tulpn | grep -v 127.0.0.1
netstat -an | grep ESTABLISHED

# 检查最近修改的文件
find /opt/health-app -mtime -1 -type f

# 检查 crontab
for user in $(cut -f1 -d: /etc/passwd); do crontab -u $user -l 2>/dev/null; done

# 检查异常用户
cat /etc/passwd | awk -F: '$3 == 0 {print}'
```

---

## 8. 部署规范 🚀

> 📄 全文已拆到 [`docs/governance/deploy.md`](docs/governance/deploy.md)（Operating Harness Phase 2, 2026-05-31）。含:8.1 部署方式 · 8.2 线上配置管理 · 8.3 服务器信息 · 8.4 部署流程 · 8.5 环境变量同步 · 8.6 注意事项。**改本章请改那个文件,此处只留导航。**

## 9. 数据库规范 🗄️

### 9.1 数据库类型

**生产环境数据库: PostgreSQL**

> ⚠️ **重要**: 项目统一使用 PostgreSQL 数据库，SQLite 仅用于历史兼容，**已废弃**。
> 所有新的数据库操作、迁移、查询都必须基于 PostgreSQL。

| 环境 | 数据库 | 备注 |
|------|--------|------|
| 生产 | PostgreSQL | **唯一正式数据库** |
| 开发 | PostgreSQL | 推荐使用 Docker 本地运行 |
| ~~测试~~ | ~~SQLite~~ | **已废弃，请勿使用** |

### 9.2 连接配置

```bash
# .env 配置
DATABASE_URL=postgresql://user:password@host:5432/health_db

# 示例（本地开发）
DATABASE_URL=postgresql://health:health123@localhost:5432/health_dev

# 示例（生产环境）
DATABASE_URL=postgresql://health_user:xxx@localhost:5432/health_prod
```

### 9.3 迁移规范

**迁移文件位置:** `backend/migrations/`

**命名规范:** `YYYYMMDD_HHMMSS_description.sql` 或 `description.sql`

**迁移文件示例 (PostgreSQL):**

```sql
-- 使用 PostgreSQL 语法
CREATE TABLE IF NOT EXISTS example_table (
    id SERIAL PRIMARY KEY,                          -- 自增主键
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_example_name ON example_table(name);
```

**执行迁移:**

```bash
# 通过 psql 执行迁移
psql $DATABASE_URL -f migrations/create_xxx_tables.sql

# 或在服务器上
cd /opt/health-app/backend
psql "$DATABASE_URL" -f migrations/create_xxx_tables.sql
```

### 9.4 PostgreSQL vs SQLite 语法差异

| 功能 | PostgreSQL | SQLite (已废弃) |
|------|------------|-----------------|
| 自增主键 | `SERIAL PRIMARY KEY` | `INTEGER PRIMARY KEY AUTOINCREMENT` |
| 时间戳默认值 | `DEFAULT NOW()` | `DEFAULT CURRENT_TIMESTAMP` |
| 带时区时间 | `TIMESTAMP WITH TIME ZONE` | `TIMESTAMP` |
| 布尔类型 | `BOOLEAN` | `BOOLEAN` (实际存储为 0/1) |
| JSON 类型 | `JSONB` (推荐) | `TEXT` |

### 9.5 ORM 使用

项目使用 SQLAlchemy ORM，模型定义兼容 PostgreSQL：

```python
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

class ExampleModel(Base):
    __tablename__ = "example_table"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    metadata = Column(JSONB, nullable=True)  # PostgreSQL JSONB
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
```

---

## 版本历史

| 版本 | 日期 | 更新内容 |
|------|------|---------|
| 1.2 | 2026-01-25 | 新增数据库规范章节，明确使用 PostgreSQL，废弃 SQLite |
| 1.1 | 2026-01-25 | 新增部署规范章节，明确 deploy.sh 和 .env 使用规范 |
| 1.0 | 2026-01-17 | 初始版本，包含安全、日志、测试、性能、数据安全规范 |

---

> **记住**: 安全不是可选项，而是必选项。每一行代码都可能是攻击入口。

## 10. Codex 工作流偏好

- 后续开发默认直接在 `main` 分支进行，除非用户明确要求隔离分支或 worktree。
- 完成代码修改后，默认执行必要验证、`git commit`、`git push`。
- 需要上线的改动，按项目规范通过根目录 `deploy.sh` 部署并验证。
- Mobile 端纯 JS/TS/UI 改动优先使用 `scripts/mobile-ota.sh production "<message>"` 热更新；涉及 native 配置、依赖、EAS profile、SDK 或 TestFlight 新包时再使用 EAS build / submit。

## 11. 产品治理 Spec

- 涉及产品定位、需求演进、新用户行为、跨端职责、Health OS 对象、安全边界或验证闭环的任务，必须先按 [`docs/specs/reva-product-governance-spec.md`](docs/specs/reva-product-governance-spec.md) 做需求准入判断。
- 本文件和 `docs/governance/*` 仍然裁决工程安全、测试、部署、隐私、DB、日志和提交规则；产品治理 Spec 只裁决“该不该做、落到哪个产品对象、在哪个 surface 做、如何验证”。
- 新增非平凡产品行为时，优先使用 [`docs/specs/templates/feature-spec-template.md`](docs/specs/templates/feature-spec-template.md) 创建或更新 Feature Spec。

## 12. 需求→上线 全流程契约(跨 agent 通用，Codex 必读)

把一句用户需求走完整个生命周期（需求 → PRD → 规划 → 需求分解 → 研发 → 测试 → 部署 → 上线验证），或用户说「立项 / 走一遍流程 / 从需求到上线」时，**所有 coding agent（含 Codex / Cursor）必须遵循** agent 中立的流程契约 [`docs/specs/product-pipeline-contract.md`](docs/specs/product-pipeline-contract.md)：

- **双环**：定义环（需求→PRD→规划，便宜可逆）+ 交付环（分解→实现→测试→部署→验证，昂贵有闸）。
- **6 道可失败 Gate**：G1 准入（§8）/ G2 可行性+安全压测 / G3 测试 / G4 安全 / G5 部署健康分 / G6 上线验证。**任何 Gate 失败必回上游，绝不带红或带安全 BLOCK 往下走。**
- **Dossier 脊柱**：每 feature 一份 `docs/dossiers/<date>-<slug>.md`，串起全链 + 每道 Gate 裁决（含 REJECT/BLOCK）+ 当前状态，**接手先读它从断点续**。
- **测试 Gate 硬约束**：跑测试**绝不 `| tail`**（吞退出码 → 带红上线）；部署前集成闸 CI 模式合跑 + 查主干真实色。
- 每个 agent 用自己的工具满足同一套 Gate。Claude Code 的具体编排在 `.claude/skills/product-pipeline/`；Codex/其他 agent 直接按契约走。

## 13. 系统透明化入口(跨 agent 通用)

- 涉及产品范围、系统架构、多端职责、能力规划、PRD/Plan 对齐、或从需求到实现的任务时，先读 `docs/system-map.json` 与 `docs/product-map.md`，再进入具体代码搜索。
- `docs/system-map.json` 是机器可读总地图：系统目标、产品能力、端、源码、测试、部署路径和安全级别必须能追溯；人类说明见 `docs/product-map.md`。
- 新增或实质改变产品能力时，同一分支更新 `docs/system-map.json`，并运行 `python scripts/check_system_map.py`；`scripts/validate.py` 已把它纳入 blocking 结构闸门。
- Claude Code 可用 `.claude/skills/system-transparency/` 编排读取与回写；Codex/其他 agent 直接按本节和地图执行。

<skills_system priority="1">

## Available Skills

<!-- SKILLS_TABLE_START -->
<usage>
When users ask you to perform tasks, check if any of the available skills below can help complete the task more effectively. Skills provide specialized capabilities and domain knowledge.

How to use skills:
- Invoke: `npx openskills read <skill-name>` (run in your shell)
  - For multiple: `npx openskills read skill-one,skill-two`
- The skill content will load with detailed instructions on how to complete the task
- Base directory provided in output for resolving bundled resources (references/, scripts/, assets/)

Usage notes:
- Only use skills listed in <available_skills> below
- Do not invoke a skill that is already loaded in your context
- Each skill invocation is stateless
</usage>

<available_skills>

<skill>
<name>brainstorming</name>
<description>"You MUST use this before any creative work - creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements and design before implementation."</description>
<location>global</location>
</skill>

<skill>
<name>dispatching-parallel-agents</name>
<description>Use when facing 2+ independent tasks that can be worked on without shared state or sequential dependencies</description>
<location>global</location>
</skill>

<skill>
<name>executing-plans</name>
<description>Use when you have a written implementation plan to execute in a separate session with review checkpoints</description>
<location>global</location>
</skill>

<skill>
<name>finishing-a-development-branch</name>
<description>Use when implementation is complete, all tests pass, and you need to decide how to integrate the work - guides completion of development work by presenting structured options for merge, PR, or cleanup</description>
<location>global</location>
</skill>

<skill>
<name>receiving-code-review</name>
<description>Use when receiving code review feedback, before implementing suggestions, especially if feedback seems unclear or technically questionable - requires technical rigor and verification, not performative agreement or blind implementation</description>
<location>global</location>
</skill>

<skill>
<name>requesting-code-review</name>
<description>Use when completing tasks, implementing major features, or before merging to verify work meets requirements</description>
<location>global</location>
</skill>

<skill>
<name>subagent-driven-development</name>
<description>Use when executing implementation plans with independent tasks in the current session</description>
<location>global</location>
</skill>

<skill>
<name>systematic-debugging</name>
<description>Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes</description>
<location>global</location>
</skill>

<skill>
<name>test-driven-development</name>
<description>Use when implementing any feature or bugfix, before writing implementation code</description>
<location>global</location>
</skill>

<skill>
<name>using-git-worktrees</name>
<description>Use when starting feature work that needs isolation from current workspace or before executing implementation plans - creates isolated git worktrees with smart directory selection and safety verification</description>
<location>global</location>
</skill>

<skill>
<name>using-superpowers</name>
<description>Use when starting any conversation - establishes how to find and use skills, requiring Skill tool invocation before ANY response including clarifying questions</description>
<location>global</location>
</skill>

<skill>
<name>verification-before-completion</name>
<description>Use when about to claim work is complete, fixed, or passing, before committing or creating PRs - requires running verification commands and confirming output before making any success claims; evidence before assertions always</description>
<location>global</location>
</skill>

<skill>
<name>writing-plans</name>
<description>Use when you have a spec or requirements for a multi-step task, before touching code</description>
<location>global</location>
</skill>

<skill>
<name>writing-skills</name>
<description>Use when creating new skills, editing existing skills, or verifying skills work before deployment</description>
<location>global</location>
</skill>

</available_skills>
<!-- SKILLS_TABLE_END -->

</skills_system>
