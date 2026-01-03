# 故障排除指南

## 依赖安装问题

### 错误：Preparing metadata (pyproject.toml) failed / meson setup error

**症状：**
```
error: subprocess-exited-with-error
× Preparing metadata (pyproject.toml) did not run successfully.
│ exit code: 1
╰─> [many lines of output]
    + meson setup
```

**原因：** 这通常是因为numpy或pandas需要从源码编译，但缺少必要的构建工具。

**解决方案：**

#### 方案1：使用修复版安装脚本（推荐）

```bash
cd backend
./install-deps-fixed.sh
```

#### 方案2：使用预编译的wheel包

```bash
# 强制使用预编译包
pip install --only-binary :all: numpy pandas

# 如果失败，尝试不缓存
pip install --no-cache-dir numpy pandas
```

#### 方案3：使用conda（如果已安装）

```bash
# 使用conda安装numpy和pandas（推荐）
conda install numpy pandas

# 然后安装其他依赖
pip install -r requirements-no-compile.txt
```

#### 方案4：跳过numpy/pandas（如果不需要数据分析）

```bash
# 安装不包含numpy/pandas的依赖
pip install -r requirements-no-compile.txt

# 系统仍然可以运行，只是某些数据分析功能不可用
```

#### 方案5：安装构建工具（macOS）

```bash
# 确保Xcode Command Line Tools已安装
xcode-select --install

# 安装meson（如果缺失）
pip install meson ninja

# 然后重试
pip install numpy pandas
```

#### 方案6：使用Homebrew（macOS）

```bash
# 如果使用Homebrew Python
brew install python@3.11
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 错误：metadata-generation-failed

**症状：**
```
error: metadata-generation-failed
× Encountered error while generating package metadata.
```

**解决方案：**

#### 1. 升级pip和构建工具（最常用）

```bash
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

#### 2. 使用安装脚本

```bash
cd backend
./install-deps.sh
```

#### 3. macOS系统检查Xcode工具

```bash
# 检查是否已安装
xcode-select -p

# 如果未安装，运行：
xcode-select --install
```

#### 4. 使用更新后的依赖文件

如果使用Python 3.13或更高版本：

```bash
pip install -r requirements-fixed.txt
```

#### 5. 逐个安装定位问题

```bash
# 先安装核心包
pip install fastapi uvicorn[standard] sqlalchemy pydantic pydantic-settings

# 再安装其他包
pip install python-dotenv openai httpx python-dateutil
pip install pandas numpy alembic
pip install pytest pytest-asyncio pytest-cov
```

#### 6. 使用虚拟环境

```bash
# 创建新的虚拟环境
python3 -m venv venv
source venv/bin/activate

# 升级pip
pip install --upgrade pip setuptools wheel

# 安装依赖
pip install -r requirements.txt
```

#### 7. 使用国内镜像源

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 错误：No module named 'xxx'

**解决方案：**

```bash
# 确保在正确的虚拟环境中
source venv/bin/activate  # macOS/Linux

# 重新安装依赖
pip install -r requirements.txt
```

### 错误：Python版本不兼容

**检查Python版本：**
```bash
python3 --version
```

**要求：** Python 3.9+

**如果版本过低，升级Python：**
- macOS: `brew install python@3.11`
- Linux: 使用系统包管理器
- Windows: 从python.org下载

## 数据库问题

### 错误：无法创建数据库

**解决方案：**

```bash
# 检查文件权限
chmod 666 backend/health.db  # 如果文件已存在

# 或删除旧数据库重新创建
rm backend/health.db
# 重新启动服务
```

### 错误：数据库锁定

**解决方案：**

```bash
# 关闭所有使用数据库的进程
# 删除锁文件（SQLite）
rm backend/health.db-journal
```

## 端口占用问题

### 错误：Address already in use

**查找占用端口的进程：**

```bash
# macOS/Linux
lsof -i :8000  # 后端端口
lsof -i :3000  # 前端端口

# 杀死进程
kill -9 <PID>
```

**或使用其他端口：**

```bash
# 后端
uvicorn main:app --reload --port 8001

# 前端
npm run dev -- -p 3001
```

## API连接问题

### 错误：CORS错误

**检查：**
1. 后端CORS配置（`backend/main.py`）
2. 前端API地址（`frontend/src/services/api.ts`）
3. 确保后端服务已启动

### 错误：Connection refused

**检查：**
1. 后端服务是否运行：`curl http://localhost:8000/health`
2. 防火墙设置
3. API地址是否正确

## OpenAI API问题

### 错误：OpenAI API未配置

**症状：** 健康分析功能返回错误信息

**解决方案：**

1. 创建 `.env` 文件：
```bash
cd backend
cp .env.example .env
```

2. 添加API密钥：
```env
OPENAI_API_KEY=your_api_key_here
```

3. 重启服务

### 错误：API调用失败

**检查：**
1. API密钥是否正确
2. 账户余额是否充足
3. 网络连接是否正常

## 测试问题

### 错误：测试失败

**解决方案：**

```bash
# 确保在backend目录
cd backend

# 安装测试依赖
pip install -r requirements.txt

# 运行测试
pytest -v

# 查看详细错误
pytest -vv -s
```

### 错误：导入错误

**检查：**
1. 是否在正确的目录运行测试
2. Python路径是否正确
3. 虚拟环境是否激活

## 前端问题

### 错误：npm install失败

**解决方案：**

```bash
# 清除缓存
npm cache clean --force

# 删除node_modules重新安装
rm -rf node_modules package-lock.json
npm install
```

### 错误：模块未找到

**解决方案：**

```bash
# 重新安装依赖
npm install

# 检查package.json中的依赖是否正确
```

### 错误：multiprocessing/process.py Traceback (Python 3.13)

**症状：**
```
Process SpawnProcess-1:
Traceback (most recent call last):
  File ".../multiprocessing/process.py", line 313, in _bootstrap
```

**原因：** Python 3.13与uvicorn的reloader在某些情况下存在兼容性问题。

**解决方案：**

#### 方案1：使用简化版启动脚本（推荐）

```bash
cd backend
./start-simple.sh
```

这个脚本不使用`--reload`选项，避免multiprocessing问题。

#### 方案2：手动启动（不使用reload）

```bash
cd backend
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

#### 方案3：更新uvicorn到最新版本

```bash
pip install --upgrade uvicorn[standard]>=0.32.0
```

#### 方案4：使用修复版启动脚本

```bash
cd backend
./start-fixed.sh
```

#### 方案5：设置环境变量

```bash
export PYTHONUNBUFFERED=1
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

#### 方案6：使用watchfiles替代（如果已安装）

```bash
pip install watchfiles
uvicorn main:app --host 0.0.0.0 --port 8000 --reload --reload-engine watchfiles
```

## 常见问题快速检查清单

- [ ] Python版本 >= 3.9
- [ ] pip已升级到最新版本
- [ ] 虚拟环境已创建并激活
- [ ] 所有依赖已安装
- [ ] .env文件已配置
- [ ] 数据库文件有写入权限
- [ ] 端口8000和3000未被占用
- [ ] 后端服务已启动
- [ ] 前端服务已启动

## 获取帮助

如果以上方法都无法解决问题：

1. 查看错误日志的完整输出
2. 检查Python和pip版本
3. 尝试在全新的虚拟环境中安装
4. 查看项目的GitHub Issues（如果有）

## 日志位置

- 后端日志：控制台输出
- 前端日志：浏览器控制台（F12）
- 数据库：`backend/health.db`

