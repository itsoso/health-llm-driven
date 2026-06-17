# Garmin Session 缓存问题修复方案

**问题发现时间**: 2026-01-23  
**影响用户**: 用户 18 (可能影响所有用户)  
**问题严重性**: 高（可能导致账号被锁定）

## 🐛 问题描述

用户 18 报告 Garmin 账号被锁定，经过分析发现是 session 缓存机制存在问题。

## 🔍 问题分析

### 1. 当前实现

系统使用两层过期时间检查：

1. **数据库层**: `session_expires_at` 字段（设置为 23 小时）
2. **Token 层**: OAuth2 token 的 `expires_at` 字段（Garmin 设置为 24 小时）

### 2. 发现的问题

#### 问题 1: 过期检查不一致

```python
# backend/app/services/data_collection/garmin_connect.py:366
if cred.session_expires_at and cred.session_expires_at < datetime.utcnow():
    logger.info(f"{prefix} 缓存的 garth session 已过期")
    return False
```

**问题**:
- 只检查数据库的 `session_expires_at`（23小时）
- 不检查 OAuth2 token 本身的 `expires_at`（24小时）
- 可能导致使用已过期的 token

#### 问题 2: Session 过期后未清理

当数据库的 `session_expires_at` 过期后：
- 函数返回 `False`
- 但**不清理**数据库中的过期 session
- 下次同步时可能再次尝试加载过期 session

#### 问题 3: Token 过期时间检查不准确

```python
# 当前实现
session_data = json.loads(cred.garth_session)
# 直接使用，不检查 token 是否真的有效
```

**问题**:
- 没有检查 `oauth2_token.json` 中的 `expires_at`
- 可能使用已过期的 token 尝试 API 调用
- 导致 API 调用失败，触发重新登录

#### 问题 4: 频繁重新登录

当 session 过期或无效时：
- 系统会尝试重新登录
- 如果多个用户同时过期，会导致短时间内大量登录请求
- **Garmin 可能将此视为异常行为并锁定账号**

### 3. 用户 18 的情况

#### Session 状态

```
Session 已缓存: 是
Session 数据大小: 2737 字节
OAuth2 Token 过期时间: 2026-01-20 10:02:28 (已过期)
数据库 session_expires_at: 2026-01-20 03:09:16 UTC (已过期 70.2 小时)
最后同步: 2026-01-22 00:02:12 (33.3 小时前)
```

#### 问题

1. **Session 已过期 70 小时**，但系统在 1月22日还在使用
2. **OAuth2 Token 已过期**，但没有被检测到
3. 系统可能在多次尝试使用过期 token 后才重新登录
4. **可能触发了 Garmin 的频率限制或安全机制**

## ✅ 修复方案

### 方案 1: 增强过期检查（推荐）

#### 1.1 检查 OAuth2 Token 过期时间

```python
def _load_session_from_db(self, db: Session) -> bool:
    """从数据库加载缓存的 garth session"""
    if not self.user_id:
        return False
    
    prefix = self._log_prefix()
    
    try:
        from app.models.user import GarminCredential
        
        cred = db.query(GarminCredential).filter(
            GarminCredential.user_id == self.user_id
        ).first()
        
        if not cred or not cred.garth_session:
            logger.debug(f"{prefix} 数据库中无缓存的 garth session")
            return False
        
        # 检查数据库层过期时间
        if cred.session_expires_at and cred.session_expires_at < datetime.utcnow():
            logger.info(f"{prefix} 缓存的 garth session 已过期（数据库层）")
            self._clear_session_from_db(db)  # 🔑 清理过期 session
            return False
        
        # 解析 session 数据
        session_data = json.loads(cred.garth_session)
        
        # 🔑 新增: 检查 OAuth2 Token 过期时间
        if 'oauth2_token.json' in session_data:
            oauth2_token = session_data['oauth2_token.json']
            if 'expires_at' in oauth2_token:
                token_expires_at = datetime.fromtimestamp(oauth2_token['expires_at'])
                now = datetime.now()
                
                if token_expires_at < now:
                    logger.info(f"{prefix} OAuth2 Token 已过期（Token 层）")
                    self._clear_session_from_db(db)  # 🔑 清理过期 session
                    return False
                
                # 如果 token 即将过期（< 1 小时），也视为过期
                if (token_expires_at - now).total_seconds() < 3600:
                    logger.info(f"{prefix} OAuth2 Token 即将过期（< 1 小时）")
                    self._clear_session_from_db(db)  # 🔑 清理过期 session
                    return False
        
        # 使用 garth 恢复 session
        with tempfile.TemporaryDirectory() as tmpdir:
            # 写入 token 文件
            for filename, data in session_data.items():
                filepath = os.path.join(tmpdir, filename)
                with open(filepath, 'w') as f:
                    json.dump(data, f)
            
            # 创建 Garmin 客户端并恢复 session
            self.client = Garmin(self.email, self.password, is_cn=self.is_cn)
            self.client.garth.load(tmpdir)
            
            # 验证 session 是否有效
            if self.client.garth.oauth2_token:
                # 尝试一个简单的 API 调用来验证 token
                try:
                    self.client.garth.connectapi("/userprofile-service/userprofile/profile")
                    self._ensure_display_name()
                    self._authenticated = True
                    logger.info(f"{prefix} ✅ 从数据库加载 garth session 成功，无需重新登录")
                    return True
                except Exception as e:
                    logger.warning(f"{prefix} 缓存的 session 无效，需要重新登录: {e}")
                    self._authenticated = False
                    self._clear_session_from_db(db)  # 🔑 清理无效 session
                    return False
                    
    except Exception as e:
        logger.warning(f"{prefix} 加载 garth session 失败: {e}")
        self._clear_session_from_db(db)  # 🔑 清理异常 session
    
    return False
```

#### 1.2 调整 Session 过期时间

```python
# 当前: 23 小时
TOKEN_CACHE_HOURS = 23

# 修改为: 20 小时（留出 4 小时缓冲）
TOKEN_CACHE_HOURS = 20
```

**理由**:
- Garmin OAuth2 Token 有效期为 24 小时
- 设置为 20 小时，留出 4 小时缓冲
- 避免在 token 即将过期时使用

### 方案 2: 添加重试机制和频率限制

#### 2.1 登录失败重试机制

```python
def _authenticate(self, db: Optional[Session] = None):
    """认证并获取Garmin客户端"""
    prefix = self._log_prefix()
    
    # 1. 优先尝试从数据库加载缓存的 session
    if db and self.user_id and not self._authenticated:
        if self._load_session_from_db(db):
            logger.info(f"{prefix} ✅ 使用缓存的 OAuth Token，避免重新登录")
            return
    
    # 2. 🔑 新增: 检查是否频繁登录
    if db and self.user_id:
        from app.models.user import GarminCredential
        
        cred = db.query(GarminCredential).filter(
            GarminCredential.user_id == self.user_id
        ).first()
        
        if cred and cred.last_sync_at:
            time_since_last_login = (datetime.now() - cred.last_sync_at).total_seconds()
            
            # 如果距离上次登录 < 5 分钟，拒绝登录
            if time_since_last_login < 300:
                logger.warning(f"{prefix} 登录过于频繁，距上次登录仅 {time_since_last_login:.0f} 秒")
                raise GarminAuthenticationError(
                    f"登录过于频繁，请等待 {300 - time_since_last_login:.0f} 秒后再试"
                )
    
    # 3. 重新登录
    # ... 原有登录逻辑 ...
```

#### 2.2 错误次数限制

```python
def _authenticate(self, db: Optional[Session] = None):
    """认证并获取Garmin客户端"""
    prefix = self._log_prefix()
    
    # 检查错误次数
    if db and self.user_id:
        from app.models.user import GarminCredential
        
        cred = db.query(GarminCredential).filter(
            GarminCredential.user_id == self.user_id
        ).first()
        
        # 🔑 新增: 如果错误次数 > 5，暂停同步 1 小时
        if cred and cred.error_count and cred.error_count > 5:
            if cred.updated_at:
                time_since_last_error = (datetime.now() - cred.updated_at).total_seconds()
                
                if time_since_last_error < 3600:  # 1 小时
                    logger.warning(f"{prefix} 错误次数过多 ({cred.error_count})，暂停同步")
                    raise GarminAuthenticationError(
                        f"登录失败次数过多，请等待 {(3600 - time_since_last_error) / 60:.0f} 分钟后再试"
                    )
                else:
                    # 超过 1 小时，重置错误计数
                    cred.error_count = 0
                    db.commit()
    
    # ... 原有登录逻辑 ...
```

### 方案 3: 监控和告警

#### 3.1 添加登录监控

```python
# backend/app/services/monitoring.py
class GarminLoginMonitor:
    """Garmin 登录监控"""
    
    @staticmethod
    def record_login_attempt(user_id: int, success: bool, error: str = None):
        """记录登录尝试"""
        # 记录到日志
        if success:
            logger.info(f"[监控] 用户 {user_id} Garmin 登录成功")
        else:
            logger.warning(f"[监控] 用户 {user_id} Garmin 登录失败: {error}")
        
        # 可以扩展为写入监控数据库或发送告警
    
    @staticmethod
    def check_login_frequency(user_id: int, db: Session) -> bool:
        """检查登录频率是否异常"""
        # 查询最近 1 小时的登录次数
        one_hour_ago = datetime.now() - timedelta(hours=1)
        
        # 从日志或数据库查询登录次数
        # 如果 > 10 次，返回 True（异常）
        
        return False
```

#### 3.2 告警机制

```python
def _authenticate(self, db: Optional[Session] = None):
    """认证并获取Garmin客户端"""
    try:
        # ... 登录逻辑 ...
        
        # 登录成功
        GarminLoginMonitor.record_login_attempt(self.user_id, success=True)
        
    except Exception as e:
        # 登录失败
        GarminLoginMonitor.record_login_attempt(
            self.user_id, 
            success=False, 
            error=str(e)
        )
        
        # 检查是否需要告警
        if GarminLoginMonitor.check_login_frequency(self.user_id, db):
            logger.error(f"{prefix} 登录频率异常，可能导致账号被锁定")
            # 发送告警邮件/短信
        
        raise
```

## 📝 实施步骤

### 阶段 1: 紧急修复（立即）

1. **修复 `_load_session_from_db`**
   - 添加 OAuth2 Token 过期检查
   - 过期时清理数据库 session
   - 调整 `TOKEN_CACHE_HOURS` 为 20

2. **清理用户 18 的过期 session**
   ```sql
   UPDATE garmin_credentials 
   SET garth_session = NULL, 
       session_expires_at = NULL,
       error_count = 0,
       last_error = NULL
   WHERE user_id = 18;
   ```

3. **等待 Garmin 解锁**
   - 通常需要 24 小时
   - 或联系 Garmin 客服

### 阶段 2: 增强保护（1-2 天）

1. **添加登录频率限制**
   - 5 分钟内不允许重复登录
   - 错误次数 > 5 时暂停 1 小时

2. **添加监控和告警**
   - 记录所有登录尝试
   - 异常频率时发送告警

### 阶段 3: 长期优化（1 周）

1. **优化 Session 管理**
   - 实现 Token 自动刷新
   - 添加 Session 健康检查

2. **改进错误处理**
   - 区分不同类型的登录错误
   - 针对性处理（密码错误、MFA、锁定等）

3. **用户通知**
   - 账号异常时通知用户
   - 提供自助解决方案

## 🎯 预期效果

### 修复前

- ❌ Session 过期检查不准确
- ❌ 过期 session 未清理
- ❌ 可能频繁重新登录
- ❌ 可能导致账号被锁定

### 修复后

- ✅ 准确检查 OAuth2 Token 过期时间
- ✅ 自动清理过期 session
- ✅ 避免频繁登录（频率限制）
- ✅ 降低账号被锁定风险

## 📊 监控指标

修复后需要监控以下指标：

1. **Session 命中率**
   - 目标: > 95%
   - 当前: 未知（需要添加监控）

2. **登录失败率**
   - 目标: < 1%
   - 当前: 未知

3. **账号锁定次数**
   - 目标: 0
   - 当前: 1 (用户 18)

4. **Session 过期率**
   - 目标: < 5%
   - 当前: 未知

## 🔗 相关文档

- `USER_18_GARMIN_ISSUE_ANALYSIS.md` - 用户 18 问题分析
- `AGENTS.md` - 开发规范（安全要求）
- Garmin Connect API 文档

---

**修复优先级**: 🔴 高  
**预计修复时间**: 2-4 小时  
**影响范围**: 所有 Garmin 用户
