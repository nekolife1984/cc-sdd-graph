#!/bin/sh
# pre-commit hook: コード変更時のトレーサビリティチェック
#
# 有効化: ln -sf ../../.agents/scripts/pre-commit.sh .git/hooks/pre-commit
#
# 以下のチェックを実行する:
#   1. .trace-mapping.yaml とコードの @impl タグを突き合わせ
#   2. コード変更のスナップショットを更新

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo '.')"
SCRIPT_DIR="$PROJECT_ROOT/.agents/scripts"
EXIT_CODE=0

echo "🔍 [pre-commit] Running traceability checks..."

# ── 1. @impl タグの完全性チェック ──
if [ -f "$SCRIPT_DIR/check-impl-completeness.py" ] && [ -f "$PROJECT_ROOT/.trace-mapping.yaml" ]; then
    echo "  → Checking @impl tag completeness..."
    python3 "$SCRIPT_DIR/check-impl-completeness.py" --project-dir "$PROJECT_ROOT"
    if [ $? -ne 0 ]; then
        echo "  ❌ @impl tag check FAILED"
        EXIT_CODE=1
    else
        echo "  ✅ @impl tags OK"
    fi
elif [ -f "$SCRIPT_DIR/extract_tags.py" ]; then
    # フォールバック: extract_tags.py で基本チェック
    python3 "$SCRIPT_DIR/extract_tags.py" --check-missing --dir "$PROJECT_ROOT/strands-chat" 2>/dev/null && \
        echo "  ✅ @impl tags OK (legacy check)" || true
fi

# ── 2. スナップショット更新（コード変更を記録） ──
if [ -f "$SCRIPT_DIR/check_drift.py" ] && [ -f "$PROJECT_ROOT/.trace-mapping.yaml" ]; then
    echo "  → Updating traceability snapshot..."
    python3 "$SCRIPT_DIR/check_drift.py" --snapshot 2>/dev/null || true
fi

# ── 終了 ──
if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "❌ [pre-commit] Traceability gate BLOCKED the commit."
    echo "   Fix the @impl tag issues above, or use --no-verify to bypass."
fi

exit $EXIT_CODE
