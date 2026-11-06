#!/usr/bin/env bash
# sync_to_install.sh — 把本技能目录同步到 WorkBuddy 已安装副本，并留一份带时间戳的备份
#
# 为什么需要：技能实际加载的是 ~/.workbuddy/skills/qilan-iges-partition，
# 而本目录（E:/work/skill/气帘iges分区skill）是**唯一权威源**。改完本目录必须同步，否则加载的还是老版本。
#
# 用法:
#   bash scripts/sync_to_install.sh            # 同步 + 备份
#   bash scripts/sync_to_install.sh --dry      # 只看差异（不写）
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
DST="${INSTALL_DIR:-C:/Users/hekie/.workbuddy/skills/qilan-iges-partition}"
DRY=0
[ "${1:-}" = "--dry" ] && DRY=1
TS="$(date +%Y%m%d-%H%M%S)"

echo "[sync] SRC=$SRC"
echo "[sync] DST=$DST"

if [ ! -d "$DST" ]; then
  echo "[sync] 目标不存在，直接创建（首次安装）"
  [ $DRY -eq 1 ] && { echo "[dry] mkdir -p $DST"; exit 0; }
  mkdir -p "$DST"
fi

echo "[sync] 差异清单（仅名称，按源为准）:"
diff -rq "$SRC" "$DST" 2>/dev/null | sed 's/^/       /' | head -40 || true

if [ $DRY -eq 1 ]; then
  echo "[dry] 未写入。去掉 --dry 执行同步。"
  exit 0
fi

BAK="$DST.bak-$TS"
cp -r "$DST" "$BAK"
echo "[sync] 备份 -> $BAK"

# 保留已安装副本的 _user_meta.json（安装元数据，源里没有）
cp -rf "$SRC"/. "$DST"/

echo "[sync] 完成。校验关键文件 md5："
for f in SKILL.md scripts/tree_model_v2.json; do
  a=$(md5sum "$SRC/$f" | cut -d' ' -f1)
  b=$(md5sum "$DST/$f" | cut -d' ' -f1)
  [ "$a" = "$b" ] && echo "       OK   $f  $a" || { echo "       FAIL $f  $a != $b"; exit 1; }
done
echo "[sync] 目标体积: $(du -sh "$DST" | cut -f1)"
