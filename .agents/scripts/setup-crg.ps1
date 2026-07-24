<#
.SYNOPSIS
    code-review-graph のインストール・セットアップ (Windows PowerShell版)
.DESCRIPTION
    このスクリプトは以下を行います:
    1. code-review-graph が未インストールなら pip でインストール
    2. code-review-graph install で MCP 設定を自動構成
    3. code-review-graph build でコードグラフを構築
.PARAMETER Yes
    自動モード（確認をスキップ）
.PARAMETER Platform
    エージェントプラットフォーム指定
.PARAMETER SkipBuild
    グラフビルドをスキップ
.EXAMPLE
    .\.agents\scripts\setup-crg.ps1
    .\.agents\scripts\setup-crg.ps1 -Yes -Platform claude-code
    .\.agents\scripts\setup-crg.ps1 -Yes -SkipBuild
#>

param(
    [switch]$Yes = $false,
    [string]$Platform = "",
    [switch]$SkipBuild = $false
)

function Write-Info  { Write-Host "ℹ️  $args" -ForegroundColor Cyan }
function Write-Ok    { Write-Host "✅ $args" -ForegroundColor Green }
function Write-Warn  { Write-Host "⚠️  $args" -ForegroundColor Yellow }
function Write-Err   { Write-Host "❌ $args" -ForegroundColor Red }

function Test-Command($cmd) {
    try { Get-Command $cmd -ErrorAction Stop | Out-Null; return $true }
    catch { return $false }
}

$PROJECT_ROOT = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

Write-Host ""
Write-Host "═══════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  code-review-graph セットアップ" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Python/pip 確認 ──
Write-Info "Step 1/4: Python/pip 環境を確認中..."

$pythonCmd = ""
foreach ($c in @("python3", "python")) {
    if (Test-Command $c) { $pythonCmd = $c; break }
}
if ([string]::IsNullOrEmpty($pythonCmd)) {
    Write-Err "Python が見つかりません。https://python.org からインストールしてください。"
    exit 1
}

# pip 確認
$pipVersion = & $pythonCmd -m pip --version 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {
    Write-Err "pip が見つかりません。$pythonCmd -m ensurepip を実行してください。"
    exit 1
}

$pyVer = & $pythonCmd --version 2>&1 | Out-String
Write-Ok "$($pyVer.Trim()), pip 利用可能"

# ── Step 2: CRG インストール ──
Write-Info "Step 2/4: code-review-graph を確認中..."

if (Test-Command "code-review-graph") {
    $crgVer = & code-review-graph --version 2>&1 | Out-String
    Write-Ok "code-review-graph は既にインストール済み: $($crgVer.Trim())"
} else {
    if ($Yes) {
        Write-Info "pip install code-review-graph を実行します..."
        & $pythonCmd -m pip install code-review-graph
        if ($LASTEXITCODE -ne 0) {
            Write-Err "code-review-graph のインストールに失敗しました"
            exit 1
        }
        Write-Ok "code-review-graph をインストールしました"
    } else {
        Write-Host ""
        Write-Host "  code-review-graph がインストールされていません。"
        $choice = Read-Host "  インストールしますか？ (y/N)"
        if ($choice -eq "y" -or $choice -eq "Y") {
            & $pythonCmd -m pip install code-review-graph
            if ($LASTEXITCODE -ne 0) {
                Write-Err "code-review-graph のインストールに失敗しました"
                exit 1
            }
            Write-Ok "code-review-graph をインストールしました"
        } else {
            Write-Warn "スキップしました。後で再実行できます。"
            exit 0
        }
    }
}

# PATH 再読み込み（pip user install の場合）
$userBase = & $pythonCmd -m site --user-base 2>&1 | Out-String
$userScripts = "$($userBase.Trim())\Scripts"
if (Test-Path $userScripts -and ($env:Path -notlike "*$userScripts*")) {
    $env:Path = "$userScripts;$env:Path"
}

if (-not (Test-Command "code-review-graph")) {
    Write-Err "code-review-graph が見つかりません。シェルを再起動するか、PATH を確認してください。"
    exit 1
}

# ── Step 3: MCP 設定 ──
Write-Info "Step 3/4: code-review-graph install で MCP 設定..."

$installArgs = @()
if (-not [string]::IsNullOrEmpty($Platform)) {
    $installArgs += "--platform", $Platform
}
if ($Yes) {
    $installArgs += "--yes"
}

Write-Info "実行: code-review-graph install $($installArgs -join ' ')"
& code-review-graph install $installArgs
if ($LASTEXITCODE -ne 0) {
    Write-Warn "code-review-graph install が警告を返しました（既に設定済みの場合があります）"
} else {
    Write-Ok "MCP 設定が完了しました"
}

# ── Step 4: グラフビルド ──
if (-not $SkipBuild) {
    Write-Info "Step 4/4: code-review-graph build でコードグラフを構築..."
    Write-Info "実行: code-review-graph build"
    & code-review-graph build
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "グラフビルドに失敗しました（コードがまだない可能性があります）"
    } else {
        Write-Ok "コードグラフを構築しました"
    }
} else {
    Write-Info "Step 4/4: スキップ（-SkipBuild）"
}

# ── 完了 ──
Write-Host ""
Write-Host "═══════════════════════════════════════" -ForegroundColor Green
Write-Host "  セットアップ完了！" -ForegroundColor Green
Write-Host "═══════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "  次にできること:"
Write-Host "    • kiro-trace 1.1     — 仕様→コード影響トレース"
Write-Host "    • kiro-impact        — コード→仕様影響トレース"
Write-Host "    • kiro-validate-boundary — 境界検証"
Write-Host "    • code-review-graph build   — グラフを再構築"
Write-Host "    • code-review-graph serve   — MCP サーバー起動確認"
Write-Host ""
