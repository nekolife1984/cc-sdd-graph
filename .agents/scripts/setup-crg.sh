#!/bin/bash
# setup-crg.sh — Install and configure code-review-graph
#
# Usage:
#   bash .agents/scripts/setup-crg.sh
#   bash .agents/scripts/setup-crg.sh --yes
#   bash .agents/scripts/setup-crg.sh --platform claude-code
#   bash .agents/scripts/setup-crg.sh --skip-build
#
# This script:
#   1. Installs code-review-graph via pip/pipx if missing
#   2. Runs code-review-graph install for MCP configuration
#   3. Runs code-review-graph build to create the code graph

set -euo pipefail

YES=false
PLATFORM=""
SKIP_BUILD=false
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd 2>/dev/null || echo "$SCRIPT_DIR")"
TRACE_EXAMPLE="$PROJECT_ROOT/.trace-mapping.example.yaml"
TRACE_TARGET="$PROJECT_ROOT/.trace-mapping.yaml"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}ℹ️  $1${NC}"; }
ok()    { echo -e "${GREEN}✅ $1${NC}"; }
warn()  { echo -e "${YELLOW}⚠️  $1${NC}"; }
err()   { echo -e "${RED}❌ $1${NC}"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes|-y) YES=true; shift ;;
    --platform) PLATFORM="$2"; shift 2 ;;
    --skip-build) SKIP_BUILD=true; shift ;;
    --help|-h)
      echo "Usage: $0 [--yes] [--platform <agent>] [--skip-build]"
      echo "  --yes             Non-interactive mode"
      echo "  --platform        Agent platform (e.g. claude-code, codex, cursor)"
      echo "  --skip-build      Skip graph build"; exit 0 ;;
    *) err "Unknown option: $1"; exit 1 ;;
  esac
done

echo ""
echo -e "${CYAN}═══════════════════════════════════════${NC}"
echo -e "${CYAN}  code-review-graph Setup${NC}"
echo -e "${CYAN}═══════════════════════════════════════${NC}"
echo ""

# ── Step 1: Python/pip check ──
info "Step 1/4: Checking Python/pip environment..."
PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then PYTHON="$cmd"; break; fi
done
if [ -z "$PYTHON" ]; then err "Python not found. Install from https://python.org"; exit 1; fi

PIP="$PYTHON -m pip"
if ! $PIP --version &>/dev/null; then err "pip not found. Run $PYTHON -m ensurepip"; exit 1; fi

PY_VERSION=$($PYTHON --version 2>&1)
ok "$PY_VERSION, pip available"

# ── Step 2: Install CRG ──
info "Step 2/4: Checking code-review-graph..."
if command -v code-review-graph &>/dev/null; then
  CRG_VER=$(code-review-graph --version 2>/dev/null || echo "unknown")
  ok "code-review-graph already installed: $CRG_VER"
else
  if [ "$YES" = true ]; then
    info "Installing code-review-graph..."
    if command -v pipx &>/dev/null; then pipx install code-review-graph
    else $PIP install code-review-graph; fi
    ok "code-review-graph installed"
  else
    echo ""
    echo "  code-review-graph is not installed."
    echo "  Install it now?"
    echo "  [1] pipx install code-review-graph (isolated, recommended)"
    echo "  [2] pip install code-review-graph (user environment)"
    echo "  [3] Skip"
    echo -n "  Choice (1/2/3): "
    read -r CHOICE
    case "$CHOICE" in
      1) if command -v pipx &>/dev/null; then pipx install code-review-graph
         else warn "pipx not found, using pip instead."; $PIP install code-review-graph; fi ;;
      2) $PIP install code-review-graph ;;
      3|*) warn "Skipped. Run bash $0 later to retry."; exit 0 ;;
    esac
    ok "code-review-graph installed"
  fi
fi

if command -v pipx &>/dev/null; then export PATH="$HOME/.local/bin:$PATH"; fi
if ! command -v code-review-graph &>/dev/null; then
  err "code-review-graph not found. Check PATH or restart your shell."
  exit 1
fi

# ── Step 3: MCP config ──
info "Step 3/4: Configuring MCP via code-review-graph install..."
INSTALL_ARGS=()
[ -n "$PLATFORM" ] && INSTALL_ARGS+=(--platform "$PLATFORM")
[ "$YES" = true ] && INSTALL_ARGS+=(--yes)
info "Running: code-review-graph install ${INSTALL_ARGS[*]}"
code-review-graph install "${INSTALL_ARGS[@]}"
ok "MCP configuration complete"

# ── Step 4: Graph build ──
if [ "$SKIP_BUILD" = false ]; then
  info "Step 4/4: Building code graph via code-review-graph build..."
  code-review-graph build
  ok "Code graph built"
else
  info "Step 4/4: Skipped (--skip-build)"
fi

# Copy example if target doesn't exist
if [ -f "$TRACE_EXAMPLE" ] && [ ! -f "$TRACE_TARGET" ]; then
  cp "$TRACE_EXAMPLE" "$TRACE_TARGET"
  ok "Created .trace-mapping.yaml from example"
fi

echo ""
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo -e "${GREEN}  Setup Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo ""
echo "  Next steps:"
echo "    • /kiro-trace 1.1        — Trace spec→code impact"
echo "    • /kiro-impact           — Trace code→spec impact"
echo "    • /kiro-validate-boundary — Verify task boundaries"
echo "    • code-review-graph build   — Rebuild the code graph"
echo "    • code-review-graph serve   — Check MCP server status"
echo ""
