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

# 执行备份（压缩）。
# 必须以 postgres superuser 身份 dump：genetic_raw_files / genetic_raw_audit 开了
# FORCE ROW LEVEL SECURITY（对表 owner 也生效）。app 角色 health_user 是 owner 但被刻意
# 设为「非 superuser / 非 BYPASSRLS」(基因数据租户隔离的 DB 层保证)，用它跑 pg_dump 会在
# 第一张 force-RLS 表上整体失败、exit 1、不产文件。superuser 经本地 socket peer auth 绕过
# RLS(含 FORCE)，不改任何角色权限，app 隔离不受影响。
# ⚠️ 绝不能给 health_user 加 BYPASSRLS 来「修」备份 —— 会静默拆掉运行时租户隔离。
# ⚠️ 也不要用 --enable-row-security(会按策略静默过滤行 → 残缺备份)。
# cd /tmp 消除 postgres 用户无法 cd 进 /root 的 "could not change directory" 噪声。
# set -o pipefail 已开:pg_dump 非零退出会让整条管道失败,if 诚实捕获,不被 gzip 的 0 掩盖。
cd /tmp
if sudo -u postgres pg_dump "$DB_NAME" | gzip > "$BACKUP_FILE"; then
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "[$(date)] ✅ 备份成功: ${BACKUP_FILE} (${SIZE})"
else
    echo "[$(date)] ❌ 备份失败!"
    rm -f "$BACKUP_FILE"
    exit 1
fi

# 完整性校验(不假装成功)：force-RLS 基因表最容易被错误的备份方式整体丢失/被静默过滤。
# 动态枚举所有 FORCE RLS 表(relforcerowsecurity)，断言每张表的数据段(COPY)都出现在备份里。
# - 枚举失败 → 无法验证 → 保留备份文件(可能是好的)但 exit 1，让调用方知道这份未经校验。
# - 某表 COPY 段缺失 → 备份确定不完整 → 删文件 exit 1。
# - 枚举为空(pre-migration / 无 RLS 的库)→ 无需校验，正常通过。
if ! FORCE_RLS_TABLES=$(sudo -u postgres psql "$DB_NAME" -tAc \
    "SELECT n.nspname || '.' || c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relforcerowsecurity AND c.relkind = 'r'"); then
    echo "[$(date)] ❌ 完整性校验无法执行(枚举 force-RLS 表失败) —— 备份保留但标记为未校验"
    exit 1
fi
# 逐行读(while read 而非 `for t in $list`)——后者依赖 IFS 含换行的词分割,在 zsh 等
# 不默认词分割的 shell 下会把整张列表当成一个 token、令多表 zgrep 退化为 OR 匹配而静默放过。
# herestring(<<<)让循环跑在当前 shell,rm/exit 能真正中断脚本(管道会起子 shell 失效)。
while IFS= read -r t; do
    [ -z "$t" ] && continue
    if zgrep -q "^COPY ${t} " "$BACKUP_FILE"; then
        echo "[$(date)] 🔐 完整性校验通过: force-RLS 表 ${t} 数据段在备份内"
    else
        echo "[$(date)] ❌ 完整性校验失败: 备份缺少 force-RLS 表 ${t} 的数据段(COPY) —— 删除残缺备份"
        rm -f "$BACKUP_FILE"
        exit 1
    fi
done <<< "$FORCE_RLS_TABLES"

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
