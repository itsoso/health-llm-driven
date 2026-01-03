# Python 3.13 快速修复指南

## 问题
Python 3.13 与 uvicorn 的默认 reloader 存在兼容性问题，导致 multiprocessing 错误。

## 解决方案（按推荐顺序）

### ✅ 方案1：不使用自动重载（最简单，推荐）

```bash
cd backend
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

**优点：** 立即工作，无错误  
**缺点：** 修改代码后需要手动重启（Ctrl+C 然后重新运行）

### ✅ 方案2：使用 watchfiles（推荐，支持自动重载）

```bash
cd backend
source venv/bin/activate

# 安装watchfiles
pip install watchfiles

# 使用watchfiles启动
uvicorn main:app --host 0.0.0.0 --port 8000 --reload --reload-engine watchfiles
```

或使用脚本：
```bash
./start-with-watchfiles.sh
```

**优点：** 支持自动重载，兼容Python 3.13  
**缺点：** 需要额外安装watchfiles

### ✅ 方案3：更新到最新uvicorn

```bash
cd backend
source venv/bin/activate

# 更新uvicorn到最新版本
pip install --upgrade "uvicorn[standard]>=0.32.0"

# 尝试启动
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**优点：** 可能已修复兼容性问题  
**缺点：** 不一定能解决问题

### ✅ 方案4：使用修复后的启动脚本

```bash
cd backend
./start.sh
```

脚本会自动检测Python版本，Python 3.13+会使用兼容模式。

## 立即执行（推荐）

**最简单的方法：**

```bash
cd backend
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

服务会正常启动，访问 http://localhost:8000/docs 查看API文档。

## 验证服务

启动后，在浏览器访问：
- http://localhost:8000/health - 应该返回 `{"status":"healthy"}`
- http://localhost:8000/docs - API文档界面

## 如果需要自动重载

使用方案2（watchfiles），这是目前最可靠的Python 3.13兼容方案。

