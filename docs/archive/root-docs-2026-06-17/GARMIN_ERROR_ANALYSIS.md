# Garmin 错误分析报告

**更新时间**: 2026-01-23 08:00 UTC+8

## 🔍 错误概览

根据日志分析，Garmin 集成存在**两个主要问题**：

### 问题 1: 密码解密失败 ❌
```
2026-01-23 07:51:20 [ERROR] app.services.auth: 解密Garmin密码失败:
2026-01-23 07:50:40 [ERROR] app.api.data_collection: 解密用户 3 的 Garmin 凭据失败:
```

### 问题 2: Garmin 登录 401 错误 ❌
```
2026-01-23 07:51:47 [ERROR] garminconnect: Login failed: Error in request: 
401 Client Error: Unauthorized for url: https://sso.garmin.com/sso/signin
```

## 📊 详细分析

### 1. 密码解密失败

#### 错误位置
- **文件**: `backend/app/services/auth.py`
- **函数**: `GarminCredentialService.get_decrypted_credentials()`
- **行号**: 195-208

#### 相关代码
```python
@staticmethod
def get_decrypted_credentials(db: Session, user_id: int) -> Optional[dict]:
    """获取解密后的Garmin凭证"""
    credential = GarminCredentialService.get_credentials(db, user_id)
    if not credential:
        return None
    
    try:
        decrypted_password = GarminCredentialService.decrypt_password(credential.encrypted_password)
        return {
            "email": credential.garmin_email,
            "password": decrypted_password,
            "is_cn": getattr(credential, 'is_cn', False),
            ...
        }
    except Exception as e:
        logger.error(f"解密Garmin密码失败: {e}")  # ← 这里报错
        return None
```

#### 可能原因

##### 原因 A: 加密密钥不一致 ⭐⭐⭐⭐⭐ (最可能)
**症状**: 数据库中的密码是用旧密钥加密的，但现在用新密钥解密

**加密密钥生成逻辑**:
```python
# backend/app/services/auth.py (行 22-30)
GARMIN_ENCRYPTION_KEY = settings.garmin_encryption_key
if not GARMIN_ENCRYPTION_KEY:
    # 使用SECRET_KEY派生加密密钥
    key_bytes = hashlib.sha256(SECRET_KEY.encode()).digest()
    GARMIN_ENCRYPTION_KEY = base64.urlsafe_b64encode(key_bytes)
else:
    GARMIN_ENCRYPTION_KEY = GARMIN_ENCRYPTION_KEY.encode()

fernet = Fernet(GARMIN_ENCRYPTION_KEY)
```

**检查方法**:
```bash
# 1. 查看当前环境变量
ssh root@39.98.206.178 "cd /opt/health-app/backend && grep -E 'SECRET_KEY|GARMIN_ENCRYPTION_KEY' .env"

# 2. 检查数据库中的加密密码格式
ssh root@39.98.206.178 "cd /opt/health-app/backend && source venv/bin/activate && python3 -c \"
from app.database import SessionLocal
from app.models.user import GarminCredential
db = SessionLocal()
cred = db.query(GarminCredential).filter_by(user_id=3).first()
if cred:
    print(f'加密密码长度: {len(cred.encrypted_password)}')
    print(f'加密密码前20字符: {cred.encrypted_password[:20]}')
db.close()
\""
```

##### 原因 B: 数据库中的密码格式错误 ⭐⭐⭐
**症状**: 密码字段为空或格式不正确

**检查方法**:
```sql
SELECT 
    user_id, 
    garmin_email, 
    LENGTH(encrypted_password) as pwd_length,
    LEFT(encrypted_password, 20) as pwd_preview,
    last_sync_at,
    credentials_valid
FROM garmin_credentials 
WHERE user_id = 3;
```

##### 原因 C: Fernet 密钥格式错误 ⭐⭐
**症状**: `GARMIN_ENCRYPTION_KEY` 不是有效的 Fernet 密钥格式

**Fernet 密钥要求**:
- 必须是 32 字节的 URL-safe base64 编码字符串
- 总长度应该是 44 字符（32 字节 base64 编码后）

### 2. Garmin 登录 401 错误

#### 错误堆栈
```
File "/opt/health-app/backend/venv/lib/python3.12/site-packages/garth/sso.py", line 115, in login
    client.post(...)
requests.exceptions.HTTPError: 401 Client Error: Unauthorized for url: 
https://sso.garmin.com/sso/signin
```

#### 可能原因

##### 原因 A: 密码错误 ⭐⭐⭐⭐⭐
- Garmin 账号密码已更改
- 密码从未正确保存
- 密码解密后不正确（与问题1相关）

##### 原因 B: 账号被锁定 ⭐⭐⭐
- 多次登录失败导致账号被临时锁定
- 需要在 Garmin 网站上重置密码或解锁

##### 原因 C: Garmin API 变更 ⭐⭐
- Garmin SSO 认证流程发生变化
- 需要更新 `garminconnect` 库

##### 原因 D: 网络问题 ⭐
- 服务器无法访问 Garmin SSO 服务
- 需要检查防火墙或代理设置

## 🔧 解决方案

### 方案 1: 重新保存 Garmin 凭证 (推荐) ⭐⭐⭐⭐⭐

这是最简单、最安全的解决方案，可以同时解决问题1和问题2。

#### 步骤 1: 在 Web 界面重新保存凭证
1. 访问 `https://health.westwetlandtech.com/settings`
2. 找到 "Garmin 连接" 部分
3. 重新输入 Garmin 邮箱和密码
4. 点击 "保存" 或 "测试连接"

#### 步骤 2: 验证保存成功
```bash
# 查看日志
ssh root@39.98.206.178 "journalctl -u health-backend -f | grep -i garmin"

# 应该看到类似的成功日志:
# [INFO] app.api.auth: 保存Garmin凭证成功 - user_id=3
```

#### 步骤 3: 测试同步
1. 在 Web 界面点击 "同步 Garmin 数据"
2. 或访问 `https://health.westwetlandtech.com/garmin`
3. 点击 "立即同步"

### 方案 2: 检查并修复加密密钥

如果方案1不可行，可以尝试修复加密密钥。

#### 步骤 1: 检查当前环境变量
```bash
ssh root@39.98.206.178 "cd /opt/health-app/backend && cat .env | grep -E 'SECRET_KEY|GARMIN_ENCRYPTION_KEY'"
```

#### 步骤 2: 确认密钥一致性
```bash
# 生成测试脚本
cat > /tmp/test_encryption.py << 'EOF'
import os
import sys
sys.path.insert(0, '/opt/health-app/backend')

from app.database import SessionLocal
from app.models.user import GarminCredential
from app.services.auth import GarminCredentialService

db = SessionLocal()
try:
    # 获取用户3的凭证
    cred = db.query(GarminCredential).filter_by(user_id=3).first()
    if not cred:
        print("❌ 未找到用户3的Garmin凭证")
        sys.exit(1)
    
    print(f"✅ 找到凭证:")
    print(f"   邮箱: {cred.garmin_email}")
    print(f"   加密密码长度: {len(cred.encrypted_password)}")
    print(f"   加密密码前20字符: {cred.encrypted_password[:20]}")
    
    # 尝试解密
    try:
        decrypted = GarminCredentialService.decrypt_password(cred.encrypted_password)
        print(f"✅ 解密成功")
        print(f"   解密后密码长度: {len(decrypted)}")
    except Exception as e:
        print(f"❌ 解密失败: {e}")
        print(f"   错误类型: {type(e).__name__}")
        
        # 检查加密密钥
        from app.services.auth import GARMIN_ENCRYPTION_KEY
        print(f"\n当前加密密钥:")
        print(f"   长度: {len(GARMIN_ENCRYPTION_KEY)}")
        print(f"   前20字符: {GARMIN_ENCRYPTION_KEY[:20]}")
        
finally:
    db.close()
EOF

# 运行测试
ssh root@39.98.206.178 "cd /opt/health-app/backend && source venv/bin/activate && python3 /tmp/test_encryption.py"
```

#### 步骤 3: 如果密钥不一致，有两个选择

**选择 A: 使用旧密钥解密，用新密钥重新加密**
```python
# 这需要知道旧密钥，通常不可行
```

**选择 B: 删除旧凭证，重新保存**（推荐）
```sql
-- 删除旧凭证
DELETE FROM garmin_credentials WHERE user_id = 3;
```
然后按照方案1重新保存。

### 方案 3: 更新 Garmin 库

如果 Garmin API 发生变化，可能需要更新库。

```bash
ssh root@39.98.206.178 "
cd /opt/health-app/backend
source venv/bin/activate
pip install --upgrade garminconnect garth
systemctl restart health-backend
"
```

### 方案 4: 检查 Garmin 账号状态

1. 手动登录 Garmin 网站: https://connect.garmin.com
2. 检查账号是否正常
3. 如果需要，重置密码
4. 确认没有安全警告或锁定提示

## 🧪 诊断脚本

### 完整诊断脚本
```bash
#!/bin/bash
echo "========== Garmin 诊断脚本 =========="
echo ""

echo "1. 检查环境变量..."
cd /opt/health-app/backend
if grep -q "GARMIN_ENCRYPTION_KEY" .env; then
    echo "✅ GARMIN_ENCRYPTION_KEY 已设置"
else
    echo "⚠️  GARMIN_ENCRYPTION_KEY 未设置（将使用 SECRET_KEY 派生）"
fi

echo ""
echo "2. 检查数据库凭证..."
source venv/bin/activate
python3 << 'PYTHON'
from app.database import SessionLocal
from app.models.user import GarminCredential

db = SessionLocal()
cred = db.query(GarminCredential).filter_by(user_id=3).first()
if cred:
    print(f"✅ 找到凭证")
    print(f"   邮箱: {cred.garmin_email}")
    print(f"   加密密码长度: {len(cred.encrypted_password)}")
    print(f"   最后同步: {cred.last_sync_at}")
    print(f"   凭证有效: {getattr(cred, 'credentials_valid', 'N/A')}")
else:
    print("❌ 未找到凭证")
db.close()
PYTHON

echo ""
echo "3. 测试解密..."
python3 << 'PYTHON'
from app.database import SessionLocal
from app.services.auth import GarminCredentialService

db = SessionLocal()
try:
    result = GarminCredentialService.get_decrypted_credentials(db, 3)
    if result:
        print("✅ 解密成功")
        print(f"   邮箱: {result['email']}")
        print(f"   密码长度: {len(result['password'])}")
    else:
        print("❌ 解密失败（返回 None）")
except Exception as e:
    print(f"❌ 解密异常: {e}")
finally:
    db.close()
PYTHON

echo ""
echo "4. 检查最近的错误日志..."
journalctl -u health-backend -n 50 --no-pager | grep -i "garmin.*error\|解密.*失败" | tail -5

echo ""
echo "========== 诊断完成 =========="
```

保存为 `/tmp/diagnose_garmin.sh` 并运行：
```bash
ssh root@39.98.206.178 "bash /tmp/diagnose_garmin.sh"
```

## 📋 快速修复检查清单

- [ ] **步骤 1**: 在 Web 界面重新保存 Garmin 凭证
- [ ] **步骤 2**: 测试连接是否成功
- [ ] **步骤 3**: 尝试同步数据
- [ ] **步骤 4**: 检查后端日志确认无错误
- [ ] **步骤 5**: 验证数据是否成功同步

## 🎯 预期结果

修复成功后，应该看到：

### 日志中应该有
```
[INFO] app.services.data_collection.garmin_connect: [用户 3] Garmin登录成功
[INFO] app.services.data_collection.garmin_connect: [用户 3] 开始同步日期范围: 2026-01-22 到 2026-01-23
[INFO] app.services.data_collection.garmin_connect: [用户 3] 同步完成，成功 1 天
```

### 日志中不应该有
```
❌ [ERROR] app.services.auth: 解密Garmin密码失败
❌ [ERROR] garminconnect: Login failed: 401 Unauthorized
❌ [ERROR] app.services.data_collection.garmin_connect: Garmin登录失败
```

## 📞 需要帮助？

如果以上方案都不起作用，请提供以下信息：

1. 诊断脚本的完整输出
2. 环境变量配置（隐藏敏感信息）
3. 最近 100 行的 Garmin 相关日志
4. Garmin 账号是否能在网页上正常登录

---

**建议**: 优先尝试**方案1（重新保存凭证）**，这是最简单且最有效的解决方案。
