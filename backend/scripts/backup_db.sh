#!/bin/bash
# ============================================
# PostgreSQL 数据库自动备份脚本
#
# 使用方法：
#   chmod +x /opt/health-app/backend/scripts/backup_db.sh
#   # 添加到 crontab（每天凌晨 3 点执行）：
#   crontab -e
#   0 3 * * * /opt/health-app/backend/scripts/backup_db.sh >> /opt/health-app/backups/backup.log 2>&1
#
# 恢复数据库：
#   gunzip -c /opt/health-app/backups/health_db_2026-03-26_03-00.sql.gz | psql -U health_user health_db
# ============================================

set -euo pipefail

# 配置（从 .env 读取或使用默认值）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"

if [ -f "$ENV_FILE" ]; then
    DATABASE_URL=$(grep "^DATABASE_URL=" "$ENV_FILE" | cut -d= -f2-)
fi
DATABASE_URL="${DATABASE_URL:-postgresql://health_user:health2026@localhost:5432/health_db}"

BACKUP_DIR="/opt/health-app/backups"
TIMESTAMP=$(date +%Y-%m-%d_%H-%M)
DB_NAME=$(echo "$DATABASE_URL" | sed 's|.*/||')
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.sql.gz"

# 确保备份目录存在
mkdir -p "$BACKUP_DIR"

echo "[$(date)] 开始备份 ${DB_NAME}..."

# 执行备份（压缩，使用 DATABASE_URL 连接）
if pg_dump "$DATABASE_URL" | gzip > "$BACKUP_FILE"; then
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "[$(date)] ✅ 备份成功: ${BACKUP_FILE} (${SIZE})"
else
    echo "[$(date)] ❌ 备份失败!"
    rm -f "$BACKUP_FILE"
    exit 1
fi

# 只保留最新 1 份（避免备份堆积吃硬盘）—— 删除除最新外的所有旧备份
DELETED=$(ls -t "${BACKUP_DIR}/${DB_NAME}_"*.sql.gz 2>/dev/null | tail -n +2 | xargs -r rm -fv | wc -l)
if [ "$DELETED" -gt 0 ]; then
    echo "[$(date)] 🗑️ 删除了 ${DELETED} 份旧备份（仅保留最新 1 份）"
fi

# 打印容量信息（防硬盘不足）
COUNT=$(ls -1 "${BACKUP_DIR}/${DB_NAME}_"*.sql.gz 2>/dev/null | wc -l)
DB_SIZE=$(psql "$DATABASE_URL" -tAc "SELECT pg_size_pretty(pg_database_size(current_database()))" 2>/dev/null | tr -d ' ')
DISK=$(df -h "$BACKUP_DIR" 2>/dev/null | awk 'NR==2{print $4" 可用 / "$2" 总 ("$5" 已用)"}')
echo "[$(date)] 📦 当前共有 ${COUNT} 个备份 | 数据库实际大小: ${DB_SIZE:-未知} | 磁盘: ${DISK}"
