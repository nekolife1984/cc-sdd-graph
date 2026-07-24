#!/bin/sh
# pre-commit hook: コード変更時のトレーサビリティスナップショット自動更新
#
# 有効化: ln -sf ../../.agents/scripts/pre-commit.sh .git/hooks/pre-commit

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo '.')"
SCRIPT_DIR="$PROJECT_ROOT/.agents/scripts"

# スナップショット更新（コード変更を記録）
if [ -f "$SCRIPT_DIR/check_drift.py" ] && [ -f "$PROJECT_ROOT/.trace-mapping.yaml" ]; then
    python3 "$SCRIPT_DIR/check_drift.py" --snapshot 2>/dev/null
fi

# extract_tags.py でタグチェック（@impl タグが消えてないか）
if [ -f "$SCRIPT_DIR/extract_tags.py" ]; then
    python3 "$SCRIPT_DIR/extract_tags.py" --check-missing --dir "$PROJECT_ROOT/strands-chat" 2>/dev/null
fi
