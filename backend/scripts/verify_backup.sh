#!/bin/bash
# ============================================
# 数据库备份持久性自检 + 自愈
#
# 与 Claude / 任何外部进程无关, 由服务器 cron 每天 09:xx 跑:
#   7 9 * * * /opt/health-app/backend/scripts/verify_backup.sh >> /opt/health-app/backups/backup_verify.log 2>&1
#
# 背景: 2026-06-16 发现 03:00 的 cron 备份会神秘消失(原因未锁定)。本脚本在备份生成
# 几小时后复查: 当天备份不存在 → 立即补一份(自愈), 保证任何时刻都有当天的可回滚备份。
# ============================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="/opt/health-app/backups"
TODAY=$(date +%Y-%m-%d)

ENV_FILE="$SCRIPT_DIR/../.env"
if [ -f "$ENV_FILE" ]; then
    DATABASE_URL=$(grep "^DATABASE_URL=" "$ENV_FILE" | cut -d= -f2-)
fi
DATABASE_URL="${DATABASE_URL:-}"
if [ -z "$DATABASE_URL" ]; then
    echo "[$(date)] 🚨 DATABASE_URL 未配置，无法验证或补建备份"
    exit 1
fi
DB_NAME=$(echo "$DATABASE_URL" | sed 's|.*/||')

DISK=$(df -h "$BACKUP_DIR" 2>/dev/null | awk 'NR==2{print $4" 可用 ("$5" 已用)"}')

# 找当天的有效备份(完整 gzip 且非空)
FOUND=""
for f in "$BACKUP_DIR/${DB_NAME}_${TODAY}_"*.sql.gz; do
    [ -f "$f" ] || continue
    if gzip -t "$f" 2>/dev/null && [ "$(wc -c < "$f")" -gt 500 ]; then
        FOUND="$f"
        break
    fi
done

if [ -n "$FOUND" ]; then
    SIZE=$(du -h "$FOUND" | cut -f1)
    echo "[$(date)] ✅ PASS 当天备份存在: $(basename "$FOUND") ($SIZE) | 磁盘: $DISK"
else
    echo "[$(date)] ❌ FAIL 当天($TODAY)无有效备份! 触发自愈补份..."
    if bash "$SCRIPT_DIR/backup_db.sh"; then
        echo "[$(date)] 🔧 自愈成功: 已补当天备份(详见 backup.log)"
    else
        echo "[$(date)] 🚨 自愈失败: pg_dump 不可用, 需人工介入 | 磁盘: $DISK"
    fi
fi
