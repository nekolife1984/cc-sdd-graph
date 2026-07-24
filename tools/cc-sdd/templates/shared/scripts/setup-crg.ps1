<#
.SYNOPSIS
    Install and configure code-review-graph (Windows PowerShell)
.DESCRIPTION
    Installs code-review-graph, configures MCP, and builds the code graph.
.PARAMETER Yes
    Auto mode (skip prompts)
.PARAMETER Platform
    Agent platform (e.g. claude-code, codex, cursor)
.PARAMETER SkipBuild
    Skip graph build
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
Write-Host "  code-review-graph Setup" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Python/pip ──
Write-Info "Step 1/4: Checking Python/pip environment..."
$pythonCmd = ""
foreach ($c in @("python3", "python")) {
    if (Test-Command $c) { $pythonCmd = $c; break }
}
if ([string]::IsNullOrEmpty($pythonCmd)) {
    Write-Err "Python not found. Install from https://python.org"; exit 1
}

$pipVersion = & $pythonCmd -m pip --version 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {
    Write-Err "pip not found. Run: $pythonCmd -m ensurepip"; exit 1
}

$pyVer = & $pythonCmd --version 2>&1
Write-Ok "$($pyVer.Trim()), pip available"

# ── Step 2: Install CRG ──
Write-Info "Step 2/4: Checking code-review-graph..."
if (Test-Command "code-review-graph") {
    $crgVer = & code-review-graph --version 2>&1 | Out-String
    Write-Ok "code-review-graph already installed: $($crgVer.Trim())"
} else {
    if ($Yes) {
        Write-Info "Installing code-review-graph..."
        & $pythonCmd -m pip install code-review-graph
        if ($LASTEXITCODE -ne 0) { Write-Err "Installation failed"; exit 1 }
        Write-Ok "code-review-graph installed"
    } else {
        Write-Host ""
        $choice = Read-Host "  code-review-graph not found. Install it? (y/N)"
        if ($choice -eq "y" -or $choice -eq "Y") {
            & $pythonCmd -m pip install code-review-graph
            if ($LASTEXITCODE -ne 0) { Write-Err "Installation failed"; exit 1 }
            Write-Ok "code-review-graph installed"
        } else { Write-Warn "Skipped."; exit 0 }
    }
}

$userBase = & $pythonCmd -m site --user-base 2>&1 | Out-String
$userScripts = "$($userBase.Trim())\Scripts"
if (Test-Path $userScripts -and ($env:Path -notlike "*$userScripts*")) {
    $env:Path = "$userScripts;$env:Path"
}

if (-not (Test-Command "code-review-graph")) {
    Write-Err "code-review-graph not found. Check PATH or restart your shell."
    exit 1
}

# ── Step 3: MCP config ──
Write-Info "Step 3/4: Configuring MCP via code-review-graph install..."
$installArgs = @()
if (-not [string]::IsNullOrEmpty($Platform)) { $installArgs += "--platform", $Platform }
if ($Yes) { $installArgs += "--yes" }

Write-Info "Running: code-review-graph install $($installArgs -join ' ')"
& code-review-graph install $installArgs
if ($LASTEXITCODE -ne 0) {
    Write-Warn "code-review-graph install returned warnings (may already be configured)"
} else { Write-Ok "MCP configuration complete" }

# ── Step 4: Build graph ──
if (-not $SkipBuild) {
    Write-Info "Step 4/4: Building code graph..."
    & code-review-graph build
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Graph build failed (code may not exist yet)"
    } else { Write-Ok "Code graph built" }
} else { Write-Info "Step 4/4: Skipped (-SkipBuild)" }

# ── Step 5: Pre-commit hook ──
Write-Info "Step 5/5: Setting up pre-commit hook..."
$hookSrc = "$PSScriptRoot\pre-commit.sh"
$hookDir = "$PROJECT_ROOT\.git\hooks"
$hookDst = "$hookDir\pre-commit"
if (Test-Path $hookDst) {
    Write-Ok "pre-commit hook already exists"
} elseif ((Test-Path $hookSrc) -and (Test-Path $hookDir)) {
    if ($Yes) {
        & cmd /c "mklink $hookDst $hookSrc" | Out-Null
        Write-Ok "pre-commit hook linked (auto-mode)"
    } else {
        $choice = Read-Host "  Link pre-commit hook for auto snapshot updates? (Y/n)"
        if ([string]::IsNullOrEmpty($choice) -or $choice -eq "y" -or $choice -eq "Y") {
            & cmd /c "mklink $hookDst $hookSrc" | Out-Null
            Write-Ok "pre-commit hook linked"
        } else { Write-Info "Skipped." }
    }
} else {
    Write-Warn "pre-commit.sh or .git/hooks/ not found. Skipping."
}

Write-Host ""
Write-Host "═══════════════════════════════════════" -ForegroundColor Green
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "═══════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "  Next steps:"
Write-Host "    • kiro-trace 1.1        — Trace spec→code impact"
Write-Host "    • kiro-impact           — Trace code→spec impact"
Write-Host "    • kiro-validate-boundary — Verify task boundaries"
Write-Host "    • code-review-graph build   — Rebuild the code graph"
Write-Host "    • code-review-graph serve   — Check MCP server status"
Write-Host ""
