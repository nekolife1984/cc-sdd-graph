<#
.SYNOPSIS
    cc-sdd-graph + CRG 一括セットアップ (Windows PowerShell版)
.DESCRIPTION
    このスクリプトは以下を行います:
    1. cc-sdd-graph のインストール（スキル + テンプレート）
    2. code-review-graph のインストールとセットアップ
    3. .trace-mapping.yaml の初期化
.PARAMETER Yes
    自動モード（確認をスキップ）
.EXAMPLE
    # インタラクティブ実行
    .\quickstart.ps1

    # 自動モード
    .\quickstart.ps1 -Yes
#>

param(
    [switch]$Yes = $false
)

$GITHUB_REPO = "nekolife1984/cc-sdd-graph"
$RAW_BASE = "https://raw.githubusercontent.com/$GITHUB_REPO/main"

function Write-Info  { Write-Host "ℹ️  $args" -ForegroundColor Cyan }
function Write-Ok    { Write-Host "✅ $args" -ForegroundColor Green }
function Write-Warn  { Write-Host "⚠️  $args" -ForegroundColor Yellow }
function Write-Err   { Write-Host "❌ $args" -ForegroundColor Red }

function Test-Command($cmd) {
    try { Get-Command $cmd -ErrorAction Stop | Out-Null; return $true }
    catch { return $false }
}

# ── Step 0: 前提確認 ──
Write-Host ""
Write-Host "═══════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  cc-sdd-graph + CRG セットアップ" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

Write-Info "Step 0/4: 前提環境を確認中..."

$hasNode = Test-Command node
$hasNpx = Test-Command npx
$hasPython = Test-Command python3 -or (Test-Command python)
$pythonCmd = if (Test-Command python3) { "python3" } else { "python" }

if (-not $hasNode) { Write-Err "Node.js が見つかりません。https://nodejs.org からインストールしてください。"; exit 1 }
if (-not $hasNpx) { Write-Err "npx が見つかりません。npm install -g npx を実行してください。"; exit 1 }
if (-not $hasPython) { Write-Err "Python が見つかりません。https://python.org からインストールしてください。"; exit 1 }

Write-Ok "Node.js, npx, Python 利用可能"

# ── Step 1: エージェント選択 ──
Write-Info "Step 1/4: cc-sdd-graph をインストール中..."
Write-Host ""

$agentMap = @{
    "1" = "";               # Claude Code
    "2" = "--codex-skills"
    "3" = "--cursor-skills"
    "4" = "--github-copilot-skills"
    "5" = "--gemini-cli-skills"
    "6" = "--windsurf-skills"
    "7" = "--opencode-skills"
    "8" = "--antigravity-skills"
}
$crgPlatformMap = @{
    "1" = "claude-code"
    "2" = "codex"
    "3" = "cursor"
    "4" = "copilot"
    "5" = "gemini-cli"
    "6" = "windsurf"
    "7" = "opencode"
    "8" = ""
}

$prefixMap = @{
    "1" = "/"; "2" = "`$"; "3" = "/"; "4" = "/"
    "5" = "/"; "6" = "@"; "7" = "/"; "8" = "/"
}

if (-not $Yes) {
    Write-Host "  エージェントを選択:"
    Write-Host "  [1] Claude Code（デフォルト）"
    Write-Host "  [2] Codex"
    Write-Host "  [3] Cursor"
    Write-Host "  [4] GitHub Copilot"
    Write-Host "  [5] Gemini CLI"
    Write-Host "  [6] Windsurf"
    Write-Host "  [7] OpenCode"
    Write-Host "  [8] Antigravity"
    $agentChoice = Read-Host "  選択 (1-8, Enter=1)"
    if ([string]::IsNullOrEmpty($agentChoice)) { $agentChoice = "1" }

    Write-Host ""
    Write-Host "  言語を選択:"
    Write-Host "  [1] English（デフォルト）"
    Write-Host "  [2] 日本語"
    $langChoice = Read-Host "  選択 (1-2, Enter=1)"
    if ([string]::IsNullOrEmpty($langChoice)) { $langChoice = "1" }
} else {
    $agentChoice = "1"
    $langChoice = "1"
}

$agentFlag = $agentMap[$agentChoice]
$langFlag = if ($langChoice -eq "2") { "--lang ja" } else { "" }
$crgPlatform = $crgPlatformMap[$agentChoice]
$prefix = $prefixMap[$agentChoice]

# cc-sdd-graph を実行（npmがgithub: をサポートしていない場合は別の方法で）
try {
    Write-Info "実行: npx github:$GITHUB_REPO $agentFlag $langFlag"
    if ($IsWindows -or $env:OS -match "Windows") {
        # Windows: npx が github: プレフィックスを処理できるか確認
        $npxCmd = "npx github:$GITHUB_REPO $agentFlag $langFlag"
        Invoke-Expression $npxCmd
    } else {
        npx "github:$GITHUB_REPO" $agentFlag $langFlag
    }
} catch {
    Write-Warn "npx github: が失敗しました。代替方法でインストールします..."
    # フォールバック: gh コマンドまたは git clone
    $tmpDir = "$env:TEMP\cc-sdd-graph-$(Get-Random)"
    Write-Info "テンポラリディレクトリ: $tmpDir"
    git clone --depth 1 "https://github.com/$GITHUB_REPO.git" $tmpDir
    Push-Location $tmpDir\tools\cc-sdd
    npm install
    npm run build
    node dist\cli.js $agentFlag $langFlag
    Pop-Location
    Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
}
Write-Ok "cc-sdd-graph のインストールが完了しました"

# ── Step 2: setup-crg.ps1 をダウンロードして実行 ──
Write-Info "Step 2/4: code-review-graph をセットアップ中..."

$setupCrgPath = ".agents\scripts\setup-crg.ps1"
if (-not (Test-Path $setupCrgPath)) {
    New-Item -ItemType Directory -Force -Path ".agents\scripts" | Out-Null
    Write-Info "setup-crg.ps1 をダウンロード中..."
    try {
        Invoke-WebRequest -Uri "$RAW_BASE/.agents/scripts/setup-crg.ps1" -OutFile $setupCrgPath
        Write-Ok "setup-crg.ps1 をダウンロードしました"
    } catch {
        Write-Warn "setup-crg.ps1 のダウンロードに失敗しました。CRG セットアップをスキップします。"
        Write-Warn "手動で bash setup-crg.sh --yes を実行してください（Git Bash が必要）"
    }
}

# ここで setup-crg.ps1 を呼ぶ（別ファイルとして作成するのでまだ存在しない）
if (Test-Path $setupCrgPath) {
    & $setupCrgPath -Yes -Platform $crgPlatform
    Write-Ok "code-review-graph のセットアップが完了しました"
} else {
    Write-Warn "CRG セットアップをスキップしました"
}

# ── Step 3: .trace-mapping.yaml 初期化 ──
Write-Info "Step 3/4: .trace-mapping.yaml を確認中..."

if (Test-Path ".trace-mapping.yaml") {
    Write-Ok ".trace-mapping.yaml は既に存在します"
} elseif (Test-Path ".trace-mapping.example.yaml") {
    Copy-Item ".trace-mapping.example.yaml" ".trace-mapping.yaml"
    Write-Ok ".trace-mapping.example.yaml を .trace-mapping.yaml としてコピーしました"
} else {
    Write-Warn ".trace-mapping.yaml がありません。後で手動で作成してください。"
}

# ── Step 4: 初回スナップショット ──
Write-Info "Step 4/4: 初回スナップショットを保存中..."

if (Test-Path ".agents/scripts/check_drift.py") {
    try {
        & $pythonCmd .agents/scripts/check_drift.py --snapshot
        Write-Ok "初回スナップショットを保存しました"
    } catch {
        Write-Warn "スナップショット保存に失敗しました"
    }
} else {
    Write-Warn "check_drift.py が見つかりません"
}

# ── 完了 ──
Write-Host ""
Write-Host "═══════════════════════════════════════" -ForegroundColor Green
Write-Host "  セットアップ完了！" -ForegroundColor Green
Write-Host "═══════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "  次のコマンドで使い始められます:"
Write-Host "    ${prefix}kiro-discovery ""アイデア"""
Write-Host "    ${prefix}kiro-spec-init my-feature"
Write-Host "    ${prefix}kiro-spec-requirements my-feature"
Write-Host "    ${prefix}kiro-spec-design my-feature"
Write-Host "    ${prefix}kiro-spec-tasks my-feature"
Write-Host "    ${prefix}kiro-impl my-feature"
Write-Host ""
Write-Host "  CRG トレーサビリティ:"
Write-Host "    ${prefix}kiro-trace 1.1"
Write-Host "    ${prefix}kiro-impact src/my-file.py"
Write-Host "    ${prefix}kiro-validate-boundary"
Write-Host ""
Write-Host "  コードグラフの再構築:"
Write-Host "    code-review-graph build"
Write-Host ""
