# 张展晖课程上传指南

## 📦 准备工作

### 1. 确保后端服务运行

```bash
cd backend
source venv/bin/activate
./start-server.sh
```

服务应该运行在 `http://localhost:8000`

### 2. 获取管理员 Token

**方法 1: 通过 API 文档**

1. 访问 http://localhost:8000/docs
2. 找到 `/auth/login` 接口
3. 点击 "Try it out"
4. 输入管理员邮箱和密码
5. 点击 "Execute"
6. 复制返回的 `access_token`

**方法 2: 使用 curl**

```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "your_password"
  }'
```

复制返回的 `access_token`

---

## 📤 上传课程

### 方法 1: 使用 Python 脚本（推荐）

#### 上传单个文件

```bash
cd backend

python scripts/upload_zhang_zhanhui_course.py \
  --file /path/to/01_心肺功能是一切基础.md \
  --token "YOUR_ACCESS_TOKEN_HERE"
```

#### 批量上传目录

```bash
python scripts/upload_zhang_zhanhui_course.py \
  --dir /path/to/zhang_zhanhui_courses \
  --source zhang_zhanhui \
  --token "YOUR_ACCESS_TOKEN_HERE"
```

---

### 方法 2: 使用 curl 直接上传

```bash
# 读取文件内容
CONTENT=$(cat /path/to/01_心肺功能是一切基础.md)

# 上传
curl -X POST "http://localhost:8000/knowledge/documents/course" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"content\": \"$(echo "$CONTENT" | sed 's/"/\\"/g' | sed ':a;N;$!ba;s/\n/\\n/g')\",
    \"title\": \"心肺功能是一切基础\",
    \"author\": \"张展晖\",
    \"source\": \"zhang_zhanhui_01\",
    \"difficulty\": \"intermediate\",
    \"target_audience\": [\"运动爱好者\", \"健康管理者\"],
    \"course_metadata\": {
      \"platform\": \"得到\",
      \"course_type\": \"运动科学\"
    }
  }"
```

---

### 方法 3: 使用 Python 代码

```python
import requests

API_URL = "http://localhost:8000/knowledge/documents/course"
TOKEN = "your_access_token_here"

# 读取课程文件
with open("01_心肺功能是一切基础.md", "r", encoding="utf-8") as f:
    content = f.read()

# 准备数据
data = {
    "content": content,
    "title": "心肺功能是一切基础",
    "author": "张展晖",
    "source": "zhang_zhanhui_01",
    "difficulty": "intermediate",
    "target_audience": ["运动爱好者", "健康管理者"],
    "course_metadata": {
        "platform": "得到",
        "course_type": "运动科学"
    }
}

# 发送请求
response = requests.post(
    API_URL,
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    },
    json=data,
    timeout=120
)

if response.status_code == 200:
    result = response.json()
    print(f"✅ 上传成功!")
    print(f"   文档块数: {result.get('documents_added', 0)}")
    print(f"   向量数: {result.get('embeddings_added', 0)}")
else:
    print(f"❌ 上传失败: {response.status_code}")
    print(f"   错误: {response.text}")
```

---

## 🔍 验证上传

### 1. 查看知识库统计

```bash
curl -X GET "http://localhost:8000/knowledge/stats" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**预期输出：**
```json
{
  "total_documents": 45,
  "sources": {
    "zhang_zhanhui": 45
  },
  "categories": {
    "cardio_training": 15,
    "strength_training": 10,
    "nutrition": 8,
    "recovery": 7,
    "exercise_physiology": 5
  }
}
```

### 2. 测试搜索

```bash
curl -X POST "http://localhost:8000/knowledge/search" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "如何根据心率进行有氧训练",
    "n_results": 3,
    "source": "zhang_zhanhui"
  }'
```

### 3. 测试 RAG 问答

```bash
curl -X POST "http://localhost:8000/knowledge/ask" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "我35岁，静息心率60，想减脂，应该在什么心率区间训练？",
    "category": "cardio_training",
    "include_health_data": false
  }'
```

---

## 📊 上传结果示例

成功上传后，你会看到类似的输出：

```json
{
  "success": true,
  "documents_added": 12,
  "embeddings_added": 12,
  "course_title": "心肺功能是一切基础",
  "author": "张展晖",
  "difficulty": "intermediate",
  "target_audience": ["运动爱好者", "健康管理者"]
}
```

**文档结构示例：**

```json
{
  "content": "# 心率区间训练法\n\n## 一、心率训练基础\n\n...",
  "title": "心率训练基础",
  "category": "cardio_training",
  "metadata": {
    "source": "zhang_zhanhui_01",
    "author": "张展晖",
    "difficulty": "intermediate",
    "target_audience": ["运动爱好者"],
    "breadcrumb": "心率区间训练法 > 一、心率训练基础",
    "section_level": 2,
    "parent_titles": ["心率区间训练法"],
    "key_concepts": ["心率", "训练", "基础"],
    "chunk_index": 0,
    "total_chunks": 1
  }
}
```

---

## ❓ 常见问题

### Q1: 上传时提示 "只有管理员可以添加知识库内容"

**解决方案：**
- 确保使用的是管理员账号登录获取的 token
- 检查 token 是否过期（默认24小时）
- 重新登录获取新 token

### Q2: 上传超时

**可能原因：**
- 文件太大（>100KB）
- 网络问题
- OpenAI API 调用慢

**解决方案：**
```bash
# 增加超时时间
python scripts/upload_zhang_zhanhui_course.py \
  --file your_file.md \
  --token YOUR_TOKEN \
  --timeout 300  # 5分钟
```

### Q3: 搜索不到刚上传的内容

**解决方案：**
- 等待几秒让向量化完成
- 检查 source 参数是否匹配
- 查看知识库统计确认上传成功

### Q4: 文档被分成太多块

**解决方案：**
- 检查 Markdown 结构，减少不必要的小标题
- 合并相关内容到同一节
- 调整 chunk_size（在代码中修改）

---

## 🎯 下一步

上传完成后，可以开始实现：

1. **目标设定智能引导** - 创建目标时基于课程内容生成训练计划
2. **运动前实时指导** - 推送当天的训练建议和心率区间
3. **运动后个性化分析** - 结合课程知识深度分析运动数据
4. **定期进度报告** - 评估目标完成情况并调整计划

详见项目的 `EXECUTOR_V2_ROADMAP.md`

---

## 📚 相关文档

- [增强版知识库详细说明](./KNOWLEDGE_BASE_ENHANCED.md)
- [API 文档](http://localhost:8000/docs)
- [项目路线图](../EXECUTOR_V2_ROADMAP.md)
