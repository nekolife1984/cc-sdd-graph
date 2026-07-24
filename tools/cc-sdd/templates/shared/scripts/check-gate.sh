#!/bin/bash
# check-gate.sh — False-green verifier gate & matrix updater
#
# Usage:
#   bash check-gate.sh                    # 全 P0 チェック実行 + matrix 更新
#   bash check-gate.sh --matrix-only      # matrix のみ再生成
#   bash check-gate.sh --ci               # CI モード（PRコメント用出力）
#
# Exit code: 0 = all green, 1 = any amber+ issue

set -euo pipefail
PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo '.')"
cd "$PROJECT_ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}ℹ️  $1${NC}"; }
ok()    { echo -e "${GREEN}✅ $1${NC}"; }
warn()  { echo -e "${YELLOW}⚠️  $1${NC}"; }
err()   { echo -e "${RED}❌ $1${NC}"; }

MATRIX_FILE=".kiro/quality/false_green_matrix.md"
RESULTS_FILE=".kiro/quality/.gate-results.json"

mkdir -p "$(dirname "$MATRIX_FILE")" "$(dirname "$RESULTS_FILE")"

echo ""
echo -e "${CYAN}═══════════════════════════════════════${NC}"
echo -e "${CYAN}  False-Green Verifier Gate${NC}"
echo -e "${CYAN}═══════════════════════════════════════${NC}"
echo ""

# ── P0 チェック実行 ──
info "Running P0 vector checks..."

declare -A CHECK_RESULTS
ALL_PASSED=true

run_p0_check() {
    local name="$1"
    local label="$2"
    echo ""
    info "P0: $label"
    if python3 .agents/scripts/check-trace-completeness.py --check "$name" 2>&1; then
        ok "$label: PASS"
        CHECK_RESULTS["$name"]="caught_amber"
    else
        warn "$label: ISSUES FOUND"
        CHECK_RESULTS["$name"]="missed_green"
        ALL_PASSED=false
    fi
}

run_p0_check "coverage"   "P0-1: @impl coverage orphan"
run_p0_check "assertions" "P0-2: @verifies empty assertion"
run_p0_check "stale"      "P0-3: stale mapping entry"

echo ""
info "P0-4: CI gate bypass..."
if python3 .agents/scripts/check-ci-bypass.py 2>&1; then
    ok "P0-4: PASS"
    CHECK_RESULTS["ci_bypass"]="caught_amber"
else
    warn "P0-4: ISSUES FOUND"
    CHECK_RESULTS["ci_bypass"]="missed_green"
    ALL_PASSED=false
fi

echo ""

# ── Matrix 更新 ──
if [ ! -f "$MATRIX_FILE" ]; then
    warn "Matrix file not found at $MATRIX_FILE"
    info "Run: cp tools/cc-sdd/templates/shared/quality/false_green_matrix.md .kiro/quality/"
    exit 1
fi

MATRIX_DATE=$(date "+%Y-%m-%d")
sed -i '' "s/最終測定:.*/最終測定: $MATRIX_DATE/" "$MATRIX_FILE" 2>/dev/null || true

# ── 結果出力 ──
echo "---"
echo ""

if $ALL_PASSED; then
    ok "All P0 checks passed"
    echo ""
    echo "Detection matrix:"
    printf "  %-25s %s\n" "P0-1 (coverage)"     "${CHECK_RESULTS[coverage]}"
    printf "  %-25s %s\n" "P0-2 (assertions)"   "${CHECK_RESULTS[assertions]}"
    printf "  %-25s %s\n" "P0-3 (stale)"        "${CHECK_RESULTS[stale]}"

    echo ""
    echo "Run without --matrix-only to update matrix file."
    exit 0
else
    err "Some P0 checks failed — see issues above"
    exit 1
fi
