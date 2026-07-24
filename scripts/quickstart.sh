#!/bin/bash
# quickstart.sh — cc-sdd-graph + CRG 一括セットアップ
#
# Usage:
#   # GitHub から直接実行（推奨）
#   bash <(curl -s https://raw.githubusercontent.com/nekolife1984/cc-sdd-graph/main/scripts/quickstart.sh)
#
#   # またはクローンしてから
#   git clone https://github.com/nekolife1984/cc-sdd-graph.git
#   bash cc-sdd-graph/scripts/quickstart.sh
#
# このスクリプトは以下を行います:
#   1. cc-sdd-graph のインストール（スキル + テンプレート）
#   2. code-review-graph のインストールとセットアップ
#   3. .trace-mapping.yaml の初期化

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

# ── 設定 ──────────────────────────────────────────────
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
echo -e "${CYAN}  cc-sdd-graph + CRG セットアップ${NC}"
echo -e "${CYAN}═══════════════════════════════════════${NC}"
echo ""

# ── Step 0: 前提確認 ──────────────────────────────────
info "Step 0/4: 前提環境を確認中..."

# Node.js
if ! command -v node &>/dev/null; then
  err "Node.js が見つかりません。https://nodejs.org からインストールしてください。"
  exit 1
fi

# Python
PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then
    PYTHON="$cmd"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  err "Python が見つかりません。https://python.org からインストールしてください。"
  exit 1
fi

# npx
if ! command -v npx &>/dev/null; then
  err "npx が見つかりません。npm install -g npx を実行してください。"
  exit 1
fi

ok "Node.js $($PYTHON --version 2>&1 || true), $($PYTHON --version 2>&1), npx 利用可能"

# ── Step 1: cc-sdd-graph インストール ─────────────────
info "Step 1/4: cc-sdd-graph をインストール中..."

echo ""
echo -e "  cc-sdd-graph がプロジェクトにスキルとテンプレートを"
echo -e "  インストールします。使用するエージェントと言語を"
echo -e "  選択してください。"
echo ""

# 対話的にエージェント選択
echo -e "  エージェントを選択:"
echo -e "  [1] Claude Code（デフォルト）"
echo -e "  [2] Codex"
echo -e "  [3] Cursor"
echo -e "  [4] GitHub Copilot"
echo -e "  [5] Gemini CLI"
echo -e "  [6] Windsurf"
echo -e "  [7] OpenCode"
echo -e "  [8] Antigravity"
echo -n "  選択 (1-8, Enter=1): "
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
echo -e "  言語を選択:"
echo -e "  [1] English（デフォルト）"
echo -e "  [2] 日本語"
echo -n "  選択 (1-2, Enter=1): "
read -r LANG_CHOICE

case "${LANG_CHOICE:-1}" in
  1) LANG_FLAG="";;
  2) LANG_FLAG="--lang ja";;
  *) LANG_FLAG="";;
esac

echo ""
info "実行: npx github:$GITHUB_REPO $AGENT_FLAG $LANG_FLAG"
npx "github:$GITHUB_REPO" $AGENT_FLAG $LANG_FLAG
ok "cc-sdd-graph のインストールが完了しました"

# ── Step 2: CRG セットアップ ──────────────────────────
info "Step 2/4: code-review-graph をセットアップ中..."

# setup-crg.sh をダウンロード
SETUP_CRG=".agents/scripts/setup-crg.sh"
if [ -f "$SETUP_CRG" ]; then
  info "setup-crg.sh が既に存在します"
else
  mkdir -p .agents/scripts
  info "setup-crg.sh をダウンロード中..."
  curl -sSL "$RAW_BASE/.agents/scripts/setup-crg.sh" -o "$SETUP_CRG"
  chmod +x "$SETUP_CRG"
  ok "setup-crg.sh をダウンロードしました"
fi

# CRG をインストール（自動モード）
echo ""
info "bash $SETUP_CRG --yes を実行します..."
if [ -n "$AGENT_FLAG" ]; then
  # エージェントフラグからプラットフォーム名を抽出
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

ok "code-review-graph のセットアップが完了しました"

# ── Step 3: .trace-mapping.yaml 初期化 ────────────────
info "Step 3/4: .trace-mapping.yaml を確認中..."

if [ -f ".trace-mapping.yaml" ]; then
  ok ".trace-mapping.yaml は既に存在します"
elif [ -f ".trace-mapping.example.yaml" ]; then
  cp ".trace-mapping.example.yaml" ".trace-mapping.yaml"
  ok ".trace-mapping.example.yaml を .trace-mapping.yaml としてコピーしました"
else
  warn ".trace-mapping.yaml がありません。後で手動で作成してください。"
fi

# ── Step 4: 初回スナップショット ─────────────────────
info "Step 4/4: 初回スナップショットを保存中..."

if [ -f ".agents/scripts/check_drift.py" ]; then
  $PYTHON .agents/scripts/check_drift.py --snapshot 2>/dev/null && \
    ok "初回スナップショットを保存しました" || \
    warn "スナップショット保存に失敗しました（コードがあれば後で実行）"
else
  warn "check_drift.py が見つかりません"
fi

# ── 完了 ──────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo -e "${GREEN}  セットアップ完了！${NC}"
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo ""
echo "  次のコマンドで使い始められます:"
echo ""

case "${AGENT_CHOICE:-1}" in
  2) PREFIX='$';;
  3) PREFIX='/';;
  4) PREFIX='/';;
  5) PREFIX='/';;
  6) PREFIX='@';;
  7) PREFIX='/';;
  8) PREFIX='/';;
  *) PREFIX='/';;
esac

echo "    ${PREFIX}kiro-discovery \"アイデア\""
echo "    ${PREFIX}kiro-spec-init my-feature"
echo "    ${PREFIX}kiro-spec-requirements my-feature"
echo "    ${PREFIX}kiro-spec-design my-feature"
echo "    ${PREFIX}kiro-spec-tasks my-feature"
echo "    ${PREFIX}kiro-impl my-feature"
echo ""
echo "  CRG トレーサビリティ:"
echo "    ${PREFIX}kiro-trace 1.1"
echo "    ${PREFIX}kiro-impact src/my-file.py"
echo "    ${PREFIX}kiro-validate-boundary"
echo ""
echo "  コードグラフの再構築:"
echo "    code-review-graph build"
echo ""
