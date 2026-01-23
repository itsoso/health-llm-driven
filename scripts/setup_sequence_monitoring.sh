#!/bin/bash
# 设置数据库序列监控
# 用于在生产服务器上部署序列检查和修复脚本

set -e

echo "=========================================="
echo "设置数据库序列监控"
echo "=========================================="
echo ""

# 检查是否在服务器上运行
if [ ! -d "/opt/health-app" ]; then
    echo "❌ 错误: 未找到 /opt/health-app 目录"
    echo "   请在生产服务器上运行此脚本"
    exit 1
fi

# 切换到项目目录
cd /opt/health-app/backend

# 确保脚本目录存在
mkdir -p scripts
mkdir -p /var/log/health-app

# 设置脚本权限
chmod +x scripts/check_sequences.py
chmod +x scripts/fix_sequences.py

echo "✅ 脚本权限已设置"
echo ""

# 测试检查脚本
echo "测试检查脚本..."
source venv/bin/activate
python3 scripts/check_sequences.py
CHECK_EXIT_CODE=$?

if [ $CHECK_EXIT_CODE -eq 0 ]; then
    echo "✅ 检查脚本运行正常"
elif [ $CHECK_EXIT_CODE -eq 1 ]; then
    echo "⚠️  发现序列问题"
    echo ""
    echo "是否立即修复? (y/n)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        python3 scripts/fix_sequences.py
        echo "✅ 序列已修复"
    fi
else
    echo "❌ 检查脚本运行失败"
    exit 1
fi

echo ""
echo "=========================================="
echo "设置定时任务"
echo "=========================================="
echo ""

# 创建 crontab 条目
CRON_JOB="0 2 * * * cd /opt/health-app/backend && source venv/bin/activate && python3 scripts/check_sequences.py >> /var/log/health-app/sequence-check.log 2>&1"

# 检查是否已存在
if crontab -l 2>/dev/null | grep -q "check_sequences.py"; then
    echo "⚠️  定时任务已存在，跳过"
else
    # 添加到 crontab
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "✅ 已添加定时任务（每天凌晨 2 点执行）"
fi

echo ""
echo "=========================================="
echo "设置完成"
echo "=========================================="
echo ""
echo "📋 已配置的功能:"
echo "   ✅ 序列检查脚本: /opt/health-app/backend/scripts/check_sequences.py"
echo "   ✅ 序列修复脚本: /opt/health-app/backend/scripts/fix_sequences.py"
echo "   ✅ 定时任务: 每天凌晨 2 点自动检查"
echo "   ✅ 日志文件: /var/log/health-app/sequence-check.log"
echo ""
echo "📝 使用方法:"
echo "   检查序列: cd /opt/health-app/backend && source venv/bin/activate && python3 scripts/check_sequences.py"
echo "   修复序列: cd /opt/health-app/backend && source venv/bin/activate && python3 scripts/fix_sequences.py"
echo "   查看日志: tail -f /var/log/health-app/sequence-check.log"
echo ""
echo "🎉 设置完成！"
