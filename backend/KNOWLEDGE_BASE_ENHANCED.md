# 增强版知识库使用指南

> 专为运动科学课程（如张展晖课程）优化的知识库系统

## 🎯 优化内容

### 1. 增强版文档加载器

**主要改进：**

#### ✅ 保留 Markdown 标题层级和面包屑上下文
```
原始 Markdown:
# 心率区间训练法
## 一、心率训练基础
### 1.1 为什么要监测心率

处理后的文档:
{
  "title": "为什么要监测心率",
  "breadcrumb": "心率区间训练法 > 一、心率训练基础 > 1.1 为什么要监测心率",
  "parent_titles": ["心率区间训练法", "一、心率训练基础"],
  "key_concepts": ["心率", "监测", "训练"]
}
```

#### ✅ 更大的分块大小（1800-2000 字符）
- 普通内容：1800 字符
- 张展晖课程：2000 字符
- 适配完整的训练方法讲解，避免知识点被截断

#### ✅ 丰富的元数据
```json
{
  "metadata": {
    "source": "zhang_zhanhui_01",
    "author": "张展晖",
    "difficulty": "intermediate",
    "target_audience": ["跑步爱好者", "减脂人群"],
    "breadcrumb": "心率区间训练法 > 五区心率训练法 > Zone 2 - 有氧基础区",
    "section_level": 3,
    "parent_titles": ["心率区间训练法", "五区心率训练法"],
    "key_concepts": ["Zone 2", "有氧", "燃脂", "60-70%"],
    "chunk_index": 0,
    "total_chunks": 1
  }
}
```

#### ✅ 智能分类识别
- `cardio_training`: 心肺训练
- `strength_training`: 力量训练
- `exercise_physiology`: 运动生理学
- `nutrition`: 营养补给
- `recovery`: 恢复策略
- `weight_management`: 体重管理
- `goal_setting`: 目标设定
- `injury_prevention`: 损伤预防
- `performance`: 运动表现

---

## 📤 上传张展晖课程

### 方法 1: 使用 Python 脚本（推荐）

#### 步骤 1: 获取管理员 Token

```bash
# 访问 API 文档
open http://localhost:8000/docs

# 或使用 curl 登录
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "your_password"}'

# 复制返回的 access_token
```

#### 步骤 2: 上传单个文件

```bash
cd backend

python scripts/upload_zhang_zhanhui_course.py \
  --file /path/to/01_心肺功能是一切基础.md \
  --token YOUR_ADMIN_TOKEN
```

#### 步骤 3: 批量上传目录

```bash
python scripts/upload_zhang_zhanhui_course.py \
  --dir /path/to/zhang_zhanhui_courses \
  --token YOUR_ADMIN_TOKEN
```

#### 步骤 4: 测试搜索

```bash
python scripts/upload_zhang_zhanhui_course.py \
  --test \
  --token YOUR_ADMIN_TOKEN
```

---

### 方法 2: 使用 API 直接上传

#### API 端点
```
POST /knowledge/documents/course
```

#### 请求示例

```bash
curl -X POST "http://localhost:8000/knowledge/documents/course" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "# 心率区间训练法\n\n...",
    "title": "心率区间训练法",
    "author": "张展晖",
    "source": "zhang_zhanhui_01",
    "difficulty": "intermediate",
    "target_audience": ["跑步爱好者", "运动爱好者"],
    "course_metadata": {
      "platform": "得到",
      "course_type": "运动科学"
    }
  }'
```

#### Python 示例

```python
import requests

API_URL = "http://localhost:8000/knowledge/documents/course"
TOKEN = "your_admin_token"

# 读取课程文件
with open("01_心肺功能.md", "r", encoding="utf-8") as f:
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
    json=data
)

print(response.json())
```

---

### 方法 3: 使用前端界面上传

访问 `http://localhost:3000/knowledge` 页面，使用"上传课程"功能。

---

## 🔍 搜索和检索

### 基础搜索

```bash
curl -X POST "http://localhost:8000/knowledge/search" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "如何根据心率进行有氧训练",
    "n_results": 5,
    "source": "zhang_zhanhui"
  }'
```

### RAG 问答

```bash
curl -X POST "http://localhost:8000/knowledge/ask" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "我35岁，静息心率60，想减脂，应该在什么心率区间训练？",
    "category": "cardio_training",
    "include_health_data": true
  }'
```

---

## 📊 查看知识库统计

```bash
curl -X GET "http://localhost:8000/knowledge/stats" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**返回示例：**
```json
{
  "total_documents": 156,
  "sources": {
    "zhang_zhanhui": 45,
    "feng_xue": 28,
    "pipi_mama": 18,
    "exercise_science": 35
  },
  "categories": {
    "cardio_training": 32,
    "strength_training": 18,
    "nutrition": 24,
    "recovery": 15
  }
}
```

---

## 🗑️ 管理知识库

### 删除指定来源的文档

```bash
curl -X DELETE "http://localhost:8000/knowledge/documents/source" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source": "zhang_zhanhui_01"}'
```

### 清空整个知识库（谨慎！）

```bash
curl -X DELETE "http://localhost:8000/knowledge/documents/all?confirm=true" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 🎓 课程文件命名建议

为了更好地组织和识别课程内容，建议使用以下命名规范：

```
01_心肺功能是一切基础.md
02_如何科学有效地提升心肺能力.md
03_柔韧度不好真的要命.md
04_肌肉耐力让你更享受运动.md
05_怎样应对发胖这件事.md
06_发刊词_你需要从这门课中学到什么.md
```

**命名规则：**
- 使用数字前缀（01, 02, ...）表示顺序
- 使用下划线分隔
- 使用描述性标题
- 使用 `.md` 扩展名

---

## 🔧 高级配置

### 自定义分块参数

如果需要调整分块大小，可以修改 `document_loader_enhanced.py`:

```python
# 为特定类型的课程创建专用加载器
custom_loader = EnhancedDocumentLoader(
    chunk_size=2500,      # 更大的分块
    chunk_overlap=500,    # 更大的重叠
    preserve_hierarchy=True
)
```

### 自定义分类规则

在 `_infer_category_enhanced` 方法中添加自定义关键词：

```python
category_keywords = {
    "your_category": ["关键词1", "关键词2", "关键词3"],
    # ...
}
```

---

## 📝 最佳实践

### 1. 课程内容组织

**推荐结构：**
```markdown
# 主标题（课程名称）

> 简短描述或引言

## 一、第一部分

### 1.1 小节标题

内容...

### 1.2 小节标题

内容...

## 二、第二部分

...
```

### 2. 元数据设置

- **difficulty**:
  - `beginner`: 适合初学者
  - `intermediate`: 适合有一定基础的人
  - `advanced`: 适合进阶人群

- **target_audience**: 尽量具体
  - ✅ 好: `["跑步爱好者", "马拉松备赛者"]`
  - ❌ 差: `["运动的人"]`

### 3. 批量上传顺序

建议按课程顺序上传，source 使用数字后缀：
```
zhang_zhanhui_01
zhang_zhanhui_02
zhang_zhanhui_03
...
```

---

## 🐛 常见问题

### Q1: 上传失败，提示"课程内容解析失败"

**可能原因：**
- Markdown 格式不规范
- 文件编码不是 UTF-8
- 内容为空或只有空白字符

**解决方案：**
```bash
# 检查文件编码
file -I your_file.md

# 转换为 UTF-8
iconv -f GBK -t UTF-8 your_file.md > your_file_utf8.md
```

### Q2: 搜索不到刚上传的内容

**可能原因：**
- 向量化需要时间（通常几秒到几十秒）
- source 参数不匹配

**解决方案：**
```bash
# 等待几秒后重试
sleep 5

# 检查知识库统计
curl http://localhost:8000/knowledge/stats
```

### Q3: 文档被分成太多块

**解决方案：**
- 增大 `chunk_size` 参数
- 检查 Markdown 结构，确保标题层级合理
- 使用更少的小标题

---

## 📚 相关文档

- [知识库 RAG 系统架构](./KNOWLEDGE_BASE_RAG.md)
- [目标管理系统指南](./GOAL_MANAGEMENT_GUIDE.md)
- [API 文档](http://localhost:8000/docs)

---

## 🎉 下一步

上传完张展晖课程后，可以开始实现：

1. **目标设定时的智能引导** - 基于课程内容生成个性化训练计划
2. **运动前的实时指导** - 根据用户状态推送训练建议
3. **运动后的个性化分析** - 结合课程知识深度分析运动数据
4. **定期进度报告** - 评估目标完成情况并调整计划

详见 `EXECUTOR_V2_ROADMAP.md` 的 Phase 2 规划。
