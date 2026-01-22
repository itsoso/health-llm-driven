#!/bin/bash
# 微信小程序推送配置脚本
# 用于快速配置小程序订阅消息推送功能

set -e

echo "=========================================="
echo "  微信小程序推送配置向导"
echo "=========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 配置文件路径
ENV_FILE="/opt/health-app/backend/.env"
BACKUP_FILE="/opt/health-app/backend/.env.backup.$(date +%Y%m%d_%H%M%S)"

# 检查是否在服务器上运行
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}警告: 未找到 $ENV_FILE${NC}"
    echo "请确认是否在正确的服务器上运行此脚本"
    read -p "是否继续？(y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
    ENV_FILE=".env"
fi

echo -e "${GREEN}步骤 1/3: 配置微信小程序基础信息${NC}"
echo "----------------------------------------"
echo ""
echo "请登录微信公众平台获取以下信息："
echo "路径: 微信公众平台 -> 开发 -> 开发管理 -> 开发设置"
echo ""

read -p "请输入小程序 AppID: " WECHAT_APPID
read -p "请输入小程序 AppSecret: " WECHAT_SECRET

if [ -z "$WECHAT_APPID" ] || [ -z "$WECHAT_SECRET" ]; then
    echo -e "${RED}错误: AppID 和 AppSecret 不能为空${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}步骤 2/3: 配置订阅消息模板ID${NC}"
echo "----------------------------------------"
echo ""
echo "请登录微信公众平台获取模板ID："
echo "路径: 微信公众平台 -> 功能 -> 订阅消息"
echo ""
echo "如果还未申请模板，请先申请后再继续"
echo "详细说明请参考: MINI_PROGRAM_PUSH_SETUP_GUIDE.md"
echo ""

read -p "是否已申请所有模板？(y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}请先在微信公众平台申请模板，然后重新运行此脚本${NC}"
    exit 1
fi

echo ""
echo "请输入各类型的模板ID（留空则跳过）："
echo ""

read -p "1. 健康提醒模板ID (WECHAT_TEMPLATE_REMINDER): " TEMPLATE_REMINDER
read -p "2. 早间简报模板ID (WECHAT_TEMPLATE_BRIEFING): " TEMPLATE_BRIEFING
read -p "3. 健康预警模板ID (WECHAT_TEMPLATE_ALERT): " TEMPLATE_ALERT
read -p "4. 目标进度模板ID (WECHAT_TEMPLATE_GOAL): " TEMPLATE_GOAL
read -p "5. 周报模板ID (WECHAT_TEMPLATE_WEEKLY): " TEMPLATE_WEEKLY

echo ""
echo -e "${GREEN}步骤 3/3: 保存配置${NC}"
echo "----------------------------------------"
echo ""

# 备份原配置文件
if [ -f "$ENV_FILE" ]; then
    echo "备份原配置文件到: $BACKUP_FILE"
    cp "$ENV_FILE" "$BACKUP_FILE"
fi

# 生成配置内容
CONFIG_CONTENT="
# ========== 微信小程序推送配置 ==========
# 配置时间: $(date '+%Y-%m-%d %H:%M:%S')

# 微信小程序基础配置
WECHAT_APPID=$WECHAT_APPID
WECHAT_SECRET=$WECHAT_SECRET

# 兼容配置（两种命名方式）
WECHAT_MINI_APP_ID=$WECHAT_APPID
WECHAT_MINI_APP_SECRET=$WECHAT_SECRET
"

# 添加模板ID配置
if [ -n "$TEMPLATE_REMINDER" ]; then
    CONFIG_CONTENT="$CONFIG_CONTENT
# 健康提醒模板
WECHAT_TEMPLATE_REMINDER=$TEMPLATE_REMINDER"
fi

if [ -n "$TEMPLATE_BRIEFING" ]; then
    CONFIG_CONTENT="$CONFIG_CONTENT
# 早间简报模板
WECHAT_TEMPLATE_BRIEFING=$TEMPLATE_BRIEFING"
fi

if [ -n "$TEMPLATE_ALERT" ]; then
    CONFIG_CONTENT="$CONFIG_CONTENT
# 健康预警模板
WECHAT_TEMPLATE_ALERT=$TEMPLATE_ALERT"
fi

if [ -n "$TEMPLATE_GOAL" ]; then
    CONFIG_CONTENT="$CONFIG_CONTENT
# 目标进度模板
WECHAT_TEMPLATE_GOAL=$TEMPLATE_GOAL"
fi

if [ -n "$TEMPLATE_WEEKLY" ]; then
    CONFIG_CONTENT="$CONFIG_CONTENT
# 周报模板
WECHAT_TEMPLATE_WEEKLY=$TEMPLATE_WEEKLY"
fi

# 检查配置是否已存在
if grep -q "WECHAT_APPID" "$ENV_FILE" 2>/dev/null; then
    echo -e "${YELLOW}检测到已有微信配置，将更新现有配置${NC}"
    
    # 删除旧的微信配置
    sed -i '/^# ========== 微信小程序推送配置 ==========/,/^$/d' "$ENV_FILE" 2>/dev/null || true
    sed -i '/^WECHAT_APPID=/d' "$ENV_FILE" 2>/dev/null || true
    sed -i '/^WECHAT_SECRET=/d' "$ENV_FILE" 2>/dev/null || true
    sed -i '/^WECHAT_MINI_APP_ID=/d' "$ENV_FILE" 2>/dev/null || true
    sed -i '/^WECHAT_MINI_APP_SECRET=/d' "$ENV_FILE" 2>/dev/null || true
    sed -i '/^WECHAT_TEMPLATE_/d' "$ENV_FILE" 2>/dev/null || true
fi

# 追加新配置
echo "$CONFIG_CONTENT" >> "$ENV_FILE"

echo -e "${GREEN}✓ 配置已保存到 $ENV_FILE${NC}"
echo ""

# 显示配置摘要
echo "=========================================="
echo "  配置摘要"
echo "=========================================="
echo ""
echo "AppID: ${WECHAT_APPID:0:10}..."
echo "AppSecret: ${WECHAT_SECRET:0:10}..."
echo ""
echo "已配置的模板："
[ -n "$TEMPLATE_REMINDER" ] && echo "  ✓ 健康提醒"
[ -n "$TEMPLATE_BRIEFING" ] && echo "  ✓ 早间简报"
[ -n "$TEMPLATE_ALERT" ] && echo "  ✓ 健康预警"
[ -n "$TEMPLATE_GOAL" ] && echo "  ✓ 目标进度"
[ -n "$TEMPLATE_WEEKLY" ] && echo "  ✓ 周报"
echo ""

# 重启服务
echo "=========================================="
echo "  重启服务"
echo "=========================================="
echo ""

read -p "是否立即重启后端服务使配置生效？(y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "正在重启 health-backend 服务..."
    systemctl restart health-backend
    
    sleep 3
    
    if systemctl is-active --quiet health-backend; then
        echo -e "${GREEN}✓ 服务重启成功${NC}"
    else
        echo -e "${RED}✗ 服务重启失败，请检查日志${NC}"
        echo "查看日志: journalctl -u health-backend -n 50"
        exit 1
    fi
else
    echo -e "${YELLOW}请稍后手动重启服务: systemctl restart health-backend${NC}"
fi

echo ""
echo "=========================================="
echo "  后续步骤"
echo "=========================================="
echo ""
echo "1. 更新小程序前端配置"
echo "   文件: packages/mini-program/src/services/subscribe.ts"
echo "   将模板ID填入 TEMPLATE_IDS 对象"
echo ""
echo "2. 重新编译小程序"
echo "   命令: cd packages/mini-program && npm run build:weapp"
echo ""
echo "3. 上传小程序到微信公众平台"
echo "   使用微信开发者工具上传 dist 目录"
echo ""
echo "4. 测试推送功能"
echo "   在小程序中测试订阅授权和推送接收"
echo ""
echo "详细说明请参考: MINI_PROGRAM_PUSH_SETUP_GUIDE.md"
echo ""
echo -e "${GREEN}配置完成！${NC}"
