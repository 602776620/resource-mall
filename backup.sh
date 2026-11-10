#!/usr/bin/env bash
# 06 §6：PG 全量备份 pg_dump -Fc → backups/pg/，保留最近 14 份。
# 建议：每日 02:00 计划任务调用本脚本。
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || { echo "缺少 .env" >&2; exit 1; }
DEST=backups/pg
mkdir -p "$DEST"
STAMP=$(date +%Y%m%d-%H%M%S)

# -Fc 自定义格式（压缩、可并行恢复）；-T 透传二进制流到宿主机文件
docker compose exec -T db pg_dump -U mall -d mall -Fc > "$DEST/mall-$STAMP.dump"

# 保留最近 14 份
ls -1t "$DEST"/mall-*.dump 2>/dev/null | tail -n +15 | xargs -r rm -f
echo "backup ok: $DEST/mall-$STAMP.dump"
