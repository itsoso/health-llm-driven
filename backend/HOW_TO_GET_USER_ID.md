# 如何获取user_id

## 方法1：查看现有用户列表（推荐）

运行脚本查看所有用户：

```bash
cd backend
source venv/bin/activate
python scripts/list_users.py
```

输出示例：
```
============================================================
系统中的用户列表
============================================================
ID    姓名                  性别        出生日期        
------------------------------------------------------------
1     张三                  男           1990-01-01
2     李四                  女           1985-05-15
============================================================

共 2 个用户

使用user_id进行Garmin同步:
  python scripts/sync_garmin.py email password 1 30
```

## 方法2：通过API查看用户

### 使用curl

```bash
# 获取所有用户
curl "http://localhost:8000/api/v1/users"

# 获取特定用户
curl "http://localhost:8000/api/v1/users/1"
```

### 使用Python

```python
import requests

# 获取所有用户
response = requests.get("http://localhost:8000/api/v1/users")
users = response.json()
for user in users:
    print(f"ID: {user['id']}, 姓名: {user['name']}")
```

## 方法3：创建新用户

如果系统中还没有用户，需要先创建一个：

### 使用脚本创建

```bash
cd backend
source venv/bin/activate
python scripts/create_user.py "你的姓名" "1990-01-01" "男"
```

示例：
```bash
python scripts/create_user.py "张三" "1990-01-01" "男"
```

输出会显示创建的user_id：
```
✅ 用户创建成功!
==================================================
用户ID: 1
姓名: 张三
性别: 男
出生日期: 1990-01-01
==================================================

现在可以使用此user_id进行Garmin同步:
  python scripts/sync_garmin.py email password 1 30
```

### 通过API创建

```bash
curl -X POST "http://localhost:8000/api/v1/users" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "张三",
    "birth_date": "1990-01-01",
    "gender": "男"
  }'
```

响应会包含创建的user_id：
```json
{
  "id": 1,
  "name": "张三",
  "birth_date": "1990-01-01",
  "gender": "男"
}
```

## 方法4：在浏览器中查看

如果后端服务正在运行，访问：

- API文档: http://localhost:8000/docs
- 用户列表: http://localhost:8000/api/v1/users

在API文档中可以：
1. 查看所有用户
2. 创建新用户
3. 查看特定用户详情

## 快速开始流程

### 第一次使用

1. **创建用户**（如果还没有）：
```bash
cd backend
source venv/bin/activate
python scripts/create_user.py "你的姓名" "1990-01-01" "男"
```

2. **查看user_id**：
```bash
python scripts/list_users.py
```

3. **同步Garmin数据**：
```bash
python scripts/sync_garmin.py your_email@garmin.com your_password <user_id> 30
```

### 完整示例

```bash
# 1. 创建用户
python scripts/create_user.py "张三" "1990-01-01" "男"
# 输出: 用户ID: 1

# 2. 同步Garmin数据（使用user_id=1）
python scripts/sync_garmin.py itsoso@126.com Sisi1124 1 30
```

## 常见问题

### Q: 如何知道我的user_id是多少？

A: 运行 `python scripts/list_users.py` 查看所有用户及其ID。

### Q: 我忘记了user_id怎么办？

A: 使用 `list_users.py` 脚本查看，或者通过API查询。

### Q: 可以创建多个用户吗？

A: 可以，每个用户有独立的ID，可以分别同步各自的Garmin数据。

### Q: user_id是自动生成的吗？

A: 是的，创建用户时数据库会自动分配一个递增的ID。

## 提示

- user_id是整数，从1开始递增
- 每个用户的数据是独立的
- 建议记住或记录你的user_id，方便后续使用

