# 运行指南

## 前置要求

- Python 3.9 或更高版本
- Node.js 18 或更高版本
- npm 或 yarn

## 快速启动

### 方式一：使用启动脚本（推荐）

#### 后端启动

```bash
cd backend
./start.sh
```

或者手动启动：

```bash
cd backend
python3 -m venv venv  # 首次运行需要创建虚拟环境
source venv/bin/activate  # macOS/Linux
# 或 venv\Scripts\activate  # Windows
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

#### 前端启动

在另一个终端窗口：

```bash
cd frontend
./start.sh
```

或者手动启动：

```bash
cd frontend
npm install  # 首次运行需要安装依赖
npm run dev
```

### 方式二：使用Docker（待实现）

## 验证运行

### 1. 检查后端服务

打开浏览器访问：
- API文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health
- API根路径：http://localhost:8000/

### 2. 检查前端服务

打开浏览器访问：
- 前端应用：http://localhost:3000

## 环境配置

### 后端环境变量

在 `backend` 目录下创建 `.env` 文件：

```bash
cd backend
cp .env.example .env  # 如果存在示例文件
```

编辑 `.env` 文件：

```env
# OpenAI API配置（用于健康分析）
OPENAI_API_KEY=your_openai_api_key_here

# Garmin API配置（可选）
GARMIN_API_KEY=your_garmin_api_key_here
GARMIN_API_SECRET=your_garmin_api_secret_here

# 数据库配置
DATABASE_URL=sqlite:///./health.db

# 应用配置
APP_ENV=development
DEBUG=True
```

**注意**：
- `OPENAI_API_KEY` 是必需的，用于健康分析功能
- `GARMIN_API_KEY` 是可选的，用于Garmin数据同步
- 如果没有配置OpenAI API，健康分析功能会返回提示信息

### 前端环境变量（可选）

在 `frontend` 目录下创建 `.env.local` 文件（如果需要自定义API地址）：

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

## 数据库初始化

数据库会在首次启动时自动创建。如果需要重置数据库：

```bash
cd backend
rm health.db  # 删除现有数据库
# 重新启动服务，数据库会自动创建
```

## 常见问题

### 1. 端口被占用

**后端端口8000被占用：**
```bash
# 查找占用8000端口的进程
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows

# 修改启动命令使用其他端口
uvicorn main:app --reload --port 8001
```

**前端端口3000被占用：**
```bash
# 修改package.json中的dev脚本，或使用：
npm run dev -- -p 3001
```

### 2. 依赖安装失败

**Python依赖安装错误（metadata-generation-failed）：**

这是常见问题，通常由以下原因引起：

1. **升级pip和构建工具：**
```bash
# 升级pip、setuptools和wheel
pip install --upgrade pip setuptools wheel

# 然后重新安装依赖
pip install -r requirements.txt
```

2. **使用安装脚本（推荐）：**
```bash
cd backend
./install-deps.sh
```

3. **使用更新后的依赖文件：**
```bash
# 如果原始requirements.txt有问题，使用更新版本
pip install -r requirements-fixed.txt
```

4. **macOS系统需要Xcode Command Line Tools：**
```bash
# 检查是否已安装
xcode-select -p

# 如果未安装，运行：
xcode-select --install
```

5. **使用国内镜像源（可选，加速下载）：**
```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

6. **逐个安装定位问题包：**
```bash
# 先安装基础包
pip install fastapi uvicorn[standard] sqlalchemy pydantic

# 再安装其他包
pip install openai httpx python-dateutil
pip install pandas numpy alembic
pip install pytest pytest-asyncio pytest-cov
```

7. **如果使用Python 3.13，某些包可能需要更新版本：**
```bash
# 使用更新后的依赖文件（已兼容Python 3.13）
pip install -r requirements-fixed.txt
```

8. **使用虚拟环境（推荐）：**
```bash
# 创建新的虚拟环境
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# 或 venv\Scripts\activate  # Windows

# 在虚拟环境中安装
pip install --upgrade pip
pip install -r requirements.txt
```

**Node依赖：**
```bash
# 清除缓存
npm cache clean --force

# 删除node_modules重新安装
rm -rf node_modules package-lock.json
npm install
```

### 3. 数据库连接错误

确保数据库文件有写入权限：
```bash
chmod 666 backend/health.db  # 如果使用SQLite
```

### 4. CORS错误

如果前端无法访问后端API，检查：
- 后端CORS配置（`backend/main.py`）
- 前端API地址配置（`frontend/src/services/api.ts`）

## 开发模式

### 后端热重载

使用 `--reload` 参数启动，代码修改后自动重启：

```bash
uvicorn main:app --reload
```

### 前端热重载

Next.js默认支持热重载，修改代码后自动刷新。

## 生产部署

### 后端

```bash
# 使用生产模式启动
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

# 或使用gunicorn
pip install gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### 前端

```bash
# 构建生产版本
npm run build

# 启动生产服务器
npm start
```

## 运行测试

### 后端测试

```bash
cd backend
pytest
```

运行特定测试文件：
```bash
pytest tests/test_users.py
```

运行并查看覆盖率：
```bash
pytest --cov=app --cov-report=html
```

### 前端测试

```bash
cd frontend
npm test
```

## 下一步

1. 查看 [QUICKSTART.md](./QUICKSTART.md) 了解基本使用
2. 查看 [README.md](./README.md) 了解系统功能
3. 运行测试用例验证功能

