# Python版本选择指南

## Python版本说明

**Python版本号规则：**
- 版本号格式：`主版本.次版本.修订版本`（如 3.13.3）
- **3.13 比 3.9 更新**（3.13 > 3.12 > 3.11 > 3.10 > 3.9）
- 你不能"升级"从3.13到3.9，因为3.9是更旧的版本
- 你可以**降级**或**安装**Python 3.9

## 为什么可能需要Python 3.9？

虽然Python 3.13更新，但可能存在兼容性问题：
- 某些包可能还没有完全支持Python 3.13
- uvicorn的reloader在3.13上有问题（你刚遇到的）
- 更稳定的生态系统支持

## 安装Python 3.9（macOS）

### 方法1：使用Homebrew（推荐）

```bash
# 安装Python 3.9
brew install python@3.9

# 验证安装
python3.9 --version
```

### 方法2：使用pyenv（推荐，可以管理多个版本）

```bash
# 安装pyenv
brew install pyenv

# 安装Python 3.9
pyenv install 3.9.18

# 在项目目录设置Python版本
cd /Users/liqiuhua/work/personal/health-llm-driven/backend
pyenv local 3.9.18

# 验证
python --version  # 应该显示 3.9.18
```

### 方法3：从python.org下载

访问 https://www.python.org/downloads/release/python-3918/
下载macOS安装包。

## 使用Python 3.9创建虚拟环境

```bash
cd backend

# 删除旧的虚拟环境（如果存在）
rm -rf venv

# 使用Python 3.9创建新的虚拟环境
python3.9 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 验证Python版本
python --version  # 应该显示 3.9.x

# 安装依赖
pip install --upgrade pip
pip install -r requirements.txt

# 启动服务（现在可以使用--reload了）
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## 检查当前Python版本

```bash
# 查看系统默认Python版本
python3 --version

# 查看所有已安装的Python版本
ls -la /usr/local/bin/python*  # Homebrew安装位置
ls -la /opt/homebrew/bin/python*  # Apple Silicon Homebrew位置
which -a python3  # 查找所有python3
```

## 推荐方案

### 方案A：继续使用Python 3.13（当前）

**优点：**
- 最新特性
- 性能改进

**缺点：**
- 某些包兼容性问题
- uvicorn reloader问题（需要不使用--reload或使用watchfiles）

**使用方法：**
```bash
# 不使用reload
uvicorn main:app --host 0.0.0.0 --port 8000

# 或使用watchfiles
pip install watchfiles
uvicorn main:app --reload --reload-engine watchfiles --host 0.0.0.0 --port 8000
```

### 方案B：切换到Python 3.9（推荐，更稳定）

**优点：**
- 更好的包兼容性
- uvicorn reloader正常工作
- 更稳定的生态系统

**缺点：**
- 需要重新安装依赖
- 缺少一些新特性

**使用方法：**
```bash
# 安装Python 3.9（如果未安装）
brew install python@3.9

# 重新创建虚拟环境
cd backend
rm -rf venv
python3.9 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 现在可以正常使用reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 方案C：使用pyenv管理多个版本（最佳实践）

```bash
# 安装pyenv
brew install pyenv

# 添加到shell配置（~/.zshrc 或 ~/.bash_profile）
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.zshrc
echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.zshrc
echo 'eval "$(pyenv init -)"' >> ~/.zshrc

# 重新加载配置
source ~/.zshrc

# 安装Python 3.9和3.13
pyenv install 3.9.18
pyenv install 3.13.3

# 在项目目录设置使用3.9
cd backend
pyenv local 3.9.18

# 创建虚拟环境
python -m venv venv
source venv/bin/activate
```

## 快速检查脚本

创建 `check-python.sh`：

```bash
#!/bin/bash
echo "=== Python版本检查 ==="
echo "系统Python: $(python3 --version 2>&1)"
echo ""
echo "已安装的Python版本:"
ls -1 /usr/local/bin/python* 2>/dev/null | grep -E "python[0-9]" || \
ls -1 /opt/homebrew/bin/python* 2>/dev/null | grep -E "python[0-9]" || \
echo "未找到其他版本"
echo ""
echo "当前虚拟环境Python:"
if [ -d "venv" ]; then
    source venv/bin/activate
    python --version
    deactivate
else
    echo "未创建虚拟环境"
fi
```

## 建议

**对于这个项目，我建议：**

1. **如果只是想快速启动项目**：继续使用Python 3.13，不使用--reload选项
2. **如果需要开发（经常修改代码）**：切换到Python 3.9，可以使用--reload
3. **如果管理多个项目**：使用pyenv，可以为不同项目设置不同Python版本

## 总结

- ✅ Python 3.13 是更新的版本
- ❌ 不能"升级"到3.9（那是降级）
- ✅ 可以安装Python 3.9并使用它
- ✅ Python 3.9在这个项目上兼容性更好

