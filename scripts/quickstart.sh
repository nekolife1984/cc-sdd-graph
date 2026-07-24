#!/bin/bash
# quickstart.sh — One-command cc-sdd-graph + CRG setup
#
# Usage:
#   # Run directly from GitHub (recommended)
#   bash <(curl -s https://raw.githubusercontent.com/nekolife1984/cc-sdd-graph/main/scripts/quickstart.sh)
#
#   # Or clone first
#   git clone https://github.com/nekolife1984/cc-sdd-graph.git
#   bash cc-sdd-graph/scripts/quickstart.sh
#
# This script:
#   1. Installs cc-sdd-graph skills and templates
#   2. Installs and configures code-review-graph
#   3. Initializes .trace-mapping.yaml

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}ℹ️  $1${NC}"; }
ok()    { echo -e "${GREEN}✅ $1${NC}"; }
warn()  { echo -e "${YELLOW}⚠️  $1${NC}"; }
err()   { echo -e "${RED}❌ $1${NC}"; }

# ── Config ─────────────────────────────────────────────
GITHUB_REPO="nekolife1984/cc-sdd-graph"
RAW_BASE="https://raw.githubusercontent.com/$GITHUB_REPO/main"
REPO_URL="https://github.com/$GITHUB_REPO.git"
TMP_DIR=""

cleanup() {
  [ -n "$TMP_DIR" ] && rm -rf "$TMP_DIR" 2>/dev/null || true
}
trap cleanup EXIT

echo ""
echo -e "${CYAN}═══════════════════════════════════════${NC}"
echo -e "${CYAN}  cc-sdd-graph + CRG Setup${NC}"
echo -e "${CYAN}═══════════════════════════════════════${NC}"
echo ""

# ── Step 0: Prerequisites ──────────────────────────────
info "Step 0/4: Checking prerequisites..."

if ! command -v node &>/dev/null; then
  err "Node.js not found. Install from https://nodejs.org"
  exit 1
fi

PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then
    PYTHON="$cmd"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  err "Python not found. Install from https://python.org"
  exit 1
fi

if ! command -v npx &>/dev/null; then
  err "npx not found. Run: npm install -g npx"
  exit 1
fi

ok "Node.js, Python ($($PYTHON --version 2>&1 || true)), npx available"

# ── Step 1: Install cc-sdd-graph ────────────────────────
info "Step 1/4: Installing cc-sdd-graph..."

echo ""
echo "  Select your AI coding agent:"
echo "  [1] Claude Code (default)"
echo "  [2] Codex"
echo "  [3] Cursor"
echo "  [4] GitHub Copilot"
echo "  [5] Gemini CLI"
echo "  [6] Windsurf"
echo "  [7] OpenCode"
echo "  [8] Antigravity"
echo -n "  Choice (1-8, Enter=1): "
read -r AGENT_CHOICE

case "${AGENT_CHOICE:-1}" in
  1) AGENT_FLAG="";;
  2) AGENT_FLAG="--codex-skills";;
  3) AGENT_FLAG="--cursor-skills";;
  4) AGENT_FLAG="--github-copilot-skills";;
  5) AGENT_FLAG="--gemini-cli-skills";;
  6) AGENT_FLAG="--windsurf-skills";;
  7) AGENT_FLAG="--opencode-skills";;
  8) AGENT_FLAG="--antigravity-skills";;
  *) AGENT_FLAG="";;
esac

echo ""
echo "  Select template language:"
echo "  [1] English (default)"
echo "  [2] Japanese"
echo -n "  Choice (1-2, Enter=1): "
read -r LANG_CHOICE

case "${LANG_CHOICE:-1}" in
  1) LANG_FLAG="";;
  2) LANG_FLAG="--lang ja";;
  *) LANG_FLAG="";;
esac

echo ""
info "Running: npx github:$GITHUB_REPO $AGENT_FLAG $LANG_FLAG"
npx "github:$GITHUB_REPO" $AGENT_FLAG $LANG_FLAG
ok "cc-sdd-graph installation complete"

# ── Step 2: CRG Setup ──────────────────────────────────
info "Step 2/4: Setting up code-review-graph..."

SETUP_CRG=".agents/scripts/setup-crg.sh"
if [ -f "$SETUP_CRG" ]; then
  info "setup-crg.sh already exists"
else
  mkdir -p .agents/scripts
  info "Downloading setup-crg.sh..."
  curl -sSL "$RAW_BASE/.agents/scripts/setup-crg.sh" -o "$SETUP_CRG"
  chmod +x "$SETUP_CRG"
  ok "setup-crg.sh downloaded"
fi

echo ""
info "Running: bash $SETUP_CRG --yes"
if [ -n "$AGENT_FLAG" ]; then
  case "$AGENT_FLAG" in
    *claude-code*)    CRG_PLATFORM="claude-code" ;;
    *codex*)          CRG_PLATFORM="codex" ;;
    *cursor*)         CRG_PLATFORM="cursor" ;;
    *copilot*)        CRG_PLATFORM="copilot" ;;
    *gemini*)         CRG_PLATFORM="gemini-cli" ;;
    *windsurf*)       CRG_PLATFORM="windsurf" ;;
    *opencode*)       CRG_PLATFORM="opencode" ;;
    *)                CRG_PLATFORM="" ;;
  esac
  bash "$SETUP_CRG" --yes --platform "$CRG_PLATFORM"
else
  bash "$SETUP_CRG" --yes
fi

ok "code-review-graph setup complete"

# ── Step 3: Initialize .trace-mapping.yaml ─────────────
info "Step 3/4: Checking .trace-mapping.yaml..."

if [ -f ".trace-mapping.yaml" ]; then
  ok ".trace-mapping.yaml already exists"
elif [ -f ".trace-mapping.example.yaml" ]; then
  cp ".trace-mapping.example.yaml" ".trace-mapping.yaml"
  ok "Created .trace-mapping.yaml from .trace-mapping.example.yaml"
else
  warn ".trace-mapping.yaml not found. Create one manually later."
fi

# ── Step 4: Initial Snapshot ───────────────────────────
info "Step 4/4: Saving initial snapshot..."

if [ -f ".agents/scripts/check_drift.py" ]; then
  $PYTHON .agents/scripts/check_drift.py --snapshot 2>/dev/null && \
    ok "Initial snapshot saved" || \
    warn "Snapshot failed (rerun later when code exists)"
else
  warn "check_drift.py not found"
fi

# ── Completion ─────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo -e "${GREEN}  Setup Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo ""
echo "  Get started with:"
echo ""

case "${AGENT_CHOICE:-1}" in
  2) PREFIX='$';;
  *) PREFIX='/';;
esac

echo "    ${PREFIX}kiro-discovery \"your idea\""
echo "    ${PREFIX}kiro-spec-init my-feature"
echo "    ${PREFIX}kiro-spec-requirements my-feature"
echo "    ${PREFIX}kiro-spec-design my-feature"
echo "    ${PREFIX}kiro-spec-tasks my-feature"
echo "    ${PREFIX}kiro-impl my-feature"
echo ""
echo "  CRG Traceability:"
echo "    ${PREFIX}kiro-trace 1.1"
echo "    ${PREFIX}kiro-impact src/my-file.py"
echo "    ${PREFIX}kiro-validate-boundary"
echo ""
echo "  Rebuild code graph:"
echo "    code-review-graph build"
echo ""
