#!/bin/bash
# ci-check.sh — CIと同じトレーサビリティチェックをローカルで実行
#
# 使い方:
#   bash .agents/scripts/ci-check.sh
#
# 以下の3段階チェックを順に実行:
#   1. Trace Completeness Gate  — @impl/@spec/@verifies の網羅性
#   2. Drift Check              — コードと仕様書の乖離
#   3. Impact Summary           — 変更の影響範囲（参考）
#
# 全て通過で exit 0, いずれか失敗で exit 1

set -e
PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo '.')"
cd "$PROJECT_ROOT"

echo "=========================================="
echo "  ci-check.sh — Traceability CI (local)"
echo "=========================================="
echo ""

# ── Stage 1 ──
echo "=== Stage 1/3: Trace Completeness Gate ==="
if python3 .agents/scripts/check-trace-completeness.py 2>/dev/null; then
    echo "  ✅ Trace completeness: PASS"
else
    echo "  ❌ Trace completeness: FAIL"
    echo "     Fix the issues above and re-run."
    exit 1
fi
echo ""

# ── Stage 2 ──
echo "=== Stage 2/3: Drift Check ==="
if python3 .agents/scripts/check_drift.py --diff --gate 2>/dev/null; then
    echo "  ✅ Drift check: PASS"
else
    echo "  ❌ Drift check: FAIL"
    echo "     Spec changed but code/tests didn't follow."
    exit 1
fi
echo ""

# ── Stage 3 ──
echo "=== Stage 3/3: Impact Summary ==="
python3 .agents/scripts/impact.py --quick --diff 2>/dev/null || true
echo ""

echo "=========================================="
echo "  ✅ All checks passed"
echo "=========================================="
