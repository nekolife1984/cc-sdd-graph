#!/bin/bash
# setup-crg.sh — code-review-graph のインストール・セットアップ
#
# Usage:
#   bash .agents/scripts/setup-crg.sh                          # 対話モード
#   bash .agents/scripts/setup-crg.sh --yes                     # 自動モード
#   bash .agents/scripts/setup-crg.sh --platform claude-code    # 特定エージェント
#   bash .agents/scripts/setup-crg.sh --skip-build              # ビルドをスキップ
#
# このスクリプトは以下を行います:
#   1. code-review-graph が未インストールなら pip/pipx でインストール
#   2. code-review-graph install で MCP 設定を自動構成
#   3. code-review-graph build でコードグラフを構築
#   4. .trace-mapping.example.yaml があれば .trace-mapping.yaml としてコピー

set -euo pipefail

# ── 設定 ──────────────────────────────────────────────
YES=false
PLATFORM=""
SKIP_BUILD=false
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd 2>/dev/null || echo "$SCRIPT_DIR")"
TRACE_EXAMPLE="$PROJECT_ROOT/.trace-mapping.example.yaml"
TRACE_TARGET="$PROJECT_ROOT/.trace-mapping.yaml"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${CYAN}ℹ️  $1${NC}"; }
ok()    { echo -e "${GREEN}✅ $1${NC}"; }
warn()  { echo -e "${YELLOW}⚠️  $1${NC}"; }
err()   { echo -e "${RED}❌ $1${NC}"; }

# ── 引数パース ────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes|-y) YES=true; shift ;;
    --platform) PLATFORM="$2"; shift 2 ;;
    --skip-build) SKIP_BUILD=true; shift ;;
    --help|-h)
      echo "Usage: $0 [--yes] [--platform <agent>] [--skip-build]"
      echo ""
      echo "  --yes             自動モード（確認なし）"
      echo "  --platform        エージェント指定（例: claude-code, codex, cursor）"
      echo "  --skip-build      グラフビルドをスキップ"
      exit 0 ;;
    *) err "Unknown option: $1"; exit 1 ;;
  esac
done

echo ""
echo -e "${CYAN}═══════════════════════════════════════${NC}"
echo -e "${CYAN}  code-review-graph セットアップ${NC}"
echo -e "${CYAN}═══════════════════════════════════════${NC}"
echo ""

# ── Step 1: Python / pip 確認 ─────────────────────────
info "Step 1/4: Python/pip 環境を確認中..."

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

# pip 確認
PIP="$PYTHON -m pip"
if ! $PIP --version &>/dev/null; then
  err "pip が見つかりません。$PYTHON -m ensurepip を実行してください。"
  exit 1
fi

PY_VERSION=$($PYTHON --version 2>&1)
ok "$PY_VERSION, pip 利用可能"

# ── Step 2: CRG インストール ──────────────────────────
info "Step 2/4: code-review-graph を確認中..."

if command -v code-review-graph &>/dev/null; then
  CRG_VER=$(code-review-graph --version 2>/dev/null || echo "（不明）")
  ok "code-review-graph は既にインストール済み: $CRG_VER"
else
  if [ "$YES" = true ]; then
    info "pipx install code-review-graph を実行します..."
    if command -v pipx &>/dev/null; then
      pipx install code-review-graph
    else
      $PIP install code-review-graph
    fi
    ok "code-review-graph をインストールしました"
  else
    echo ""
    echo -e "  code-review-graph がインストールされていません。"
    echo -e "  インストールしますか？"
    echo -e "  [1] pipx install code-review-graph（隔離環境、推奨）"
    echo -e "  [2] pip install code-review-graph（ユーザー環境）"
    echo -e "  [3] スキップ"
    echo -n "  選択 (1/2/3): "
    read -r CHOICE
    case "$CHOICE" in
      1)
        if command -v pipx &>/dev/null; then
          pipx install code-review-graph
        else
          warn "pipx がありません。pip でインストールします。"
          $PIP install code-review-graph
        fi
        ;;
      2)
        $PIP install code-review-graph
        ;;
      3|*)
        warn "スキップしました。後で bash $0 で再実行できます。"
        exit 0
        ;;
    esac
    ok "code-review-graph をインストールしました"
  fi
fi

# PATH 再読み込み（pipx の場合）
if command -v pipx &>/dev/null; then
  export PATH="$HOME/.local/bin:$PATH"
fi

if ! command -v code-review-graph &>/dev/null; then
  err "code-review-graph が見つかりません。PATH を確認するか、シェルを再起動してください。"
  exit 1
fi

# ── Step 3: MCP 設定 ───────────────────────────────────
info "Step 3/4: code-review-graph install で MCP 設定..."

INSTALL_ARGS=()
if [ -n "$PLATFORM" ]; then
  INSTALL_ARGS+=(--platform "$PLATFORM")
fi
if [ "$YES" = true ]; then
  INSTALL_ARGS+=(--yes)
fi

echo ""
info "実行: code-review-graph install ${INSTALL_ARGS[*]}"
code-review-graph install "${INSTALL_ARGS[@]}"
ok "MCP 設定が完了しました"

# ── Step 4: グラフビルド ──────────────────────────────
if [ "$SKIP_BUILD" = false ]; then
  info "Step 4/4: code-review-graph build でコードグラフを構築..."
  echo ""
  info "実行: code-review-graph build"
  code-review-graph build
  ok "コードグラフを構築しました"
else
  info "Step 4/4: スキップ（--skip-build）"
fi

# ── .trace-mapping.yaml がなければ例からコピー ────────
if [ -f "$TRACE_EXAMPLE" ] && [ ! -f "$TRACE_TARGET" ]; then
  cp "$TRACE_EXAMPLE" "$TRACE_TARGET"
  ok ".trace-mapping.example.yaml を .trace-mapping.yaml としてコピーしました"
fi

# ── 完了 ──────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo -e "${GREEN}  セットアップ完了！${NC}"
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo ""
echo "  次にできること:"
echo "    • /kiro-trace 1.1     — 仕様→コード影響トレース"
echo "    • /kiro-impact        — コード→仕様影響トレース"
echo "    • /kiro-validate-boundary — 境界検証"
echo "    • code-review-graph build   — グラフを再構築"
echo "    • code-review-graph serve   — MCP サーバー起動確認"
echo ""
