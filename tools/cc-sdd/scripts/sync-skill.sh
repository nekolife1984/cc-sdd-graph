#!/bin/bash
# sync-skill.sh — スキルを codex-skills（基準）から全エージェントに同期する
#
# Usage:
#   # 全スキルを同期
#   bash tools/cc-sdd/scripts/sync-skill.sh --all
#
#   # 特定のスキルのみ同期
#   bash tools/cc-sdd/scripts/sync-skill.sh kiro-trace
#   bash tools/cc-sdd/scripts/sync-skill.sh kiro-trace kiro-impact
#
#   # dry-run（何がコピーされるか確認）
#   bash tools/cc-sdd/scripts/sync-skill.sh --dry-run kiro-trace
#
# 動作:
#   codex-skills/skills/<skill>/ を基準として、全 *-skills エージェントの
#   該当スキルディレクトリを上書きコピーする。
#   claude-code-skills はスキップする（内容が微妙に異なるため手動管理）。

set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")/../templates/agents" && pwd)"
SOURCE_AGENT="codex-skills"

# 全 *-skills エージェント（claude-code-skills は除外）
TARGET_AGENTS=()
for agent in "$BASE_DIR"/*-skills; do
  name=$(basename "$agent")
  [ "$name" != "$SOURCE_AGENT" ] || continue
  TARGET_AGENTS+=("$name")
done

DRY_RUN=false
SKILLS=()

# Parse args
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --all) SKILLS=($(ls "$BASE_DIR/$SOURCE_AGENT/skills/")) ;;
    *) SKILLS+=("$arg") ;;
  esac
done

if [ ${#SKILLS[@]} -eq 0 ]; then
  echo "Usage: $0 [--dry-run] <skill-name> [...] | --all"
  echo ""
  echo "Available skills:"
  for s in "$BASE_DIR/$SOURCE_AGENT/skills/"*/; do
    echo "  $(basename "$s")"
  done
  exit 1
fi

echo "=== Sync skills from $SOURCE_AGENT to ${#TARGET_AGENTS[@]} agents ==="
echo ""

for skill in "${SKILLS[@]}"; do
  SRC="$BASE_DIR/$SOURCE_AGENT/skills/$skill"
  if [ ! -d "$SRC" ]; then
    echo "❌ Skill '$skill' not found in $SOURCE_AGENT"
    continue
  fi

  for agent in "${TARGET_AGENTS[@]}"; do
    DST="$BASE_DIR/$agent/skills/$skill"
    if $DRY_RUN; then
      echo "  [DRY] cp -r $SRC → $DST"
    else
      rm -rf "$DST"
      cp -r "$SRC" "$DST"
      echo "  ✅ $agent/skills/$skill"
    fi
  done
done

echo ""
if $DRY_RUN; then
  echo "Dry-run complete. Run without --dry-run to apply."
else
  echo "Done! ${#SKILLS[@]} skill(s) synced to ${#TARGET_AGENTS[@]} agent(s)."
fi
