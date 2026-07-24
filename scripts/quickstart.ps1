<#
.SYNOPSIS
    One-command cc-sdd-graph + CRG setup (Windows PowerShell)
.DESCRIPTION
Installs cc-sdd-graph skills/templates, code-review-graph,
and optionally copies CI/CD templates.
.PARAMETER Yes
    Auto mode (skip prompts)
.EXAMPLE
    .\quickstart.ps1
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

# ── Step 0: Prerequisites ──
Write-Host ""
Write-Host "═══════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  cc-sdd-graph + CRG Setup" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

Write-Info "Step 0/4: Checking prerequisites..."

$hasNode = Test-Command node
$hasNpx = Test-Command npx
$hasPython = Test-Command python3 -or (Test-Command python)
$pythonCmd = if (Test-Command python3) { "python3" } else { "python" }

if (-not $hasNode) { Write-Err "Node.js not found. Install from https://nodejs.org"; exit 1 }
if (-not $hasNpx) { Write-Err "npx not found. Run: npm install -g npx"; exit 1 }
if (-not $hasPython) { Write-Err "Python not found. Install from https://python.org"; exit 1 }

Write-Ok "Node.js, npx, Python available"

# ── Step 1: Agent selection ──
Write-Info "Step 1/4: Installing cc-sdd-graph..."

$agentMap = @{
    "1" = ""; "2" = "--codex-skills"; "3" = "--cursor-skills"
    "4" = "--github-copilot-skills"; "5" = "--gemini-cli-skills"
    "6" = "--windsurf-skills"; "7" = "--opencode-skills"; "8" = "--antigravity-skills"
}
$crgPlatformMap = @{
    "1" = "claude-code"; "2" = "codex"; "3" = "cursor"
    "4" = "copilot"; "5" = "gemini-cli"; "6" = "windsurf"
    "7" = "opencode"; "8" = ""
}
$prefixMap = @{ "1" = "/"; "2" = "`$"; "3" = "/"; "4" = "/"; "5" = "/"; "6" = "@"; "7" = "/"; "8" = "/" }

if (-not $Yes) {
    Write-Host "  Select your AI coding agent:"
    Write-Host "  [1] Claude Code (default)"
    Write-Host "  [2] Codex"; Write-Host "  [3] Cursor"; Write-Host "  [4] GitHub Copilot"
    Write-Host "  [5] Gemini CLI"; Write-Host "  [6] Windsurf"; Write-Host "  [7] OpenCode"; Write-Host "  [8] Antigravity"
    $agentChoice = Read-Host "  Choice (1-8, Enter=1)"
    if ([string]::IsNullOrEmpty($agentChoice)) { $agentChoice = "1" }

    Write-Host ""
    Write-Host "  Select template language:"
    Write-Host "  [1] English (default)"; Write-Host "  [2] Japanese"
    $langChoice = Read-Host "  Choice (1-2, Enter=1)"
    if ([string]::IsNullOrEmpty($langChoice)) { $langChoice = "1" }
} else {
    $agentChoice = "1"; $langChoice = "1"
}

$agentFlag = $agentMap[$agentChoice]
$langFlag = if ($langChoice -eq "2") { "--lang ja" } else { "" }
$crgPlatform = $crgPlatformMap[$agentChoice]
$prefix = $prefixMap[$agentChoice]

# Kiro directory prompt
$kiroFlag = ""
Write-Host ""
Write-Host "  Kiro directory (where specs and settings are stored):"
$kiroInput = Read-Host "  Path (Enter=.kiro)"
if (-not [string]::IsNullOrEmpty($kiroInput)) {
    $kiroFlag = "--kiro-dir $kiroInput"
}

try {
    Write-Info "Running: npx github:$GITHUB_REPO $agentFlag $langFlag $kiroFlag"
    npx "github:$GITHUB_REPO" $agentFlag $langFlag $kiroFlag
} catch {
    Write-Warn "npx github: failed. Falling back to git clone..."
    $tmpDir = "$env:TEMP\cc-sdd-graph-$(Get-Random)"
    git clone --depth 1 "https://github.com/$GITHUB_REPO.git" $tmpDir
    Push-Location "$tmpDir\tools\cc-sdd"
    npm install; npm run build
    node dist\cli.js $agentFlag $langFlag
    Pop-Location
    Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
}
Write-Ok "cc-sdd-graph installation complete"

# ── Step 2: CRG setup ──
Write-Info "Step 2/4: Setting up code-review-graph..."

$setupCrgPath = ".agents\scripts\setup-crg.ps1"
if (-not (Test-Path $setupCrgPath)) {
    New-Item -ItemType Directory -Force -Path ".agents\scripts" | Out-Null
    Write-Info "Downloading setup-crg.ps1..."
    try {
        Invoke-WebRequest -Uri "$RAW_BASE/.agents/scripts/setup-crg.ps1" -OutFile $setupCrgPath
        Write-Ok "setup-crg.ps1 downloaded"
    } catch {
        Write-Warn "Failed to download setup-crg.ps1. Skipping CRG setup."
    }
}

if (Test-Path $setupCrgPath) {
    & $setupCrgPath -Yes -Platform $crgPlatform
    Write-Ok "code-review-graph setup complete"
} else {
    Write-Warn "CRG setup skipped"
}

# ── Step 3: .trace-mapping.yaml ──
Write-Info "Step 3/4: Checking .trace-mapping.yaml..."
if (Test-Path ".trace-mapping.yaml") {
    Write-Ok ".trace-mapping.yaml already exists"
} elseif (Test-Path ".trace-mapping.example.yaml") {
    Copy-Item ".trace-mapping.example.yaml" ".trace-mapping.yaml"
    Write-Ok "Created .trace-mapping.yaml from .trace-mapping.example.yaml"
} else {
    Write-Warn ".trace-mapping.yaml not found. Create one manually later."
}

# ── Step 4: Initial snapshot ──
Write-Info "Step 4/4: Saving initial snapshot..."
if (Test-Path ".agents/scripts/check_drift.py") {
    try {
        & $pythonCmd .agents/scripts/check_drift.py --snapshot
        Write-Ok "Initial snapshot saved"
    } catch { Write-Warn "Snapshot failed" }
} else { Write-Warn "check_drift.py not found" }

# ── Step 5: CI/CD Templates (opt-in) ──
Write-Host ""
Write-Info "Step 5/5: CI/CD Templates (optional)..."
Write-Host ""
Write-Host "  cc-sdd-graph includes CI/CD templates for GitHub Actions:"
Write-Host "    * traceability-check.yml — 3-stage gate (PR blocking)"
Write-Host "    * ci-check.sh — local equivalent for pre-push"
Write-Host ""
if (-not $Yes) {
    $ciChoice = Read-Host "  Copy CI/CD templates to this project? (y/N)"
} else {
    $ciChoice = "n"
}
if ($ciChoice -eq "y" -or $ciChoice -eq "Y") {
    $templateSrc = ""
    if (Test-Path "tools/cc-sdd/templates/shared/.github/workflows/traceability-check.yml") {
        $templateSrc = "tools/cc-sdd/templates/shared"
    }
    if ($templateSrc -ne "") {
        # GitHub Actions workflow
        New-Item -ItemType Directory -Force -Path ".github/workflows" | Out-Null
        try {
            Copy-Item "$templateSrc/.github/workflows/traceability-check.yml" ".github/workflows/traceability-check.yml"
            Write-Ok "Copied .github/workflows/traceability-check.yml"
        } catch { Write-Warn "Failed to copy GitHub Actions workflow" }

        # ci-check.sh
        if (Test-Path "$templateSrc/scripts/ci-check.sh") {
            try {
                Copy-Item "$templateSrc/scripts/ci-check.sh" ".agents/scripts/ci-check.sh"
                Write-Ok "Copied .agents/scripts/ci-check.sh"
            } catch { Write-Warn "Failed to copy ci-check.sh" }
        }
    } else {
        Write-Warn "Template files not found locally."
        Write-Host "  Install manually from the cc-sdd-graph repo:"
        Write-Host "    Copy-Item tools/cc-sdd/templates/shared/.github/workflows/traceability-check.yml .github/workflows/"
        Write-Host "    Copy-Item tools/cc-sdd/templates/shared/scripts/ci-check.sh .agents/scripts/"
    }
} else {
    Write-Info "Skipping CI/CD templates. Install later with:"
    Write-Host "    Copy-Item tools/cc-sdd/templates/shared/.github/workflows/traceability-check.yml .github/workflows/"
    Write-Host "    Copy-Item tools/cc-sdd/templates/shared/scripts/ci-check.sh .agents/scripts/"
}

# ── Completion ──
Write-Host ""
Write-Host "═══════════════════════════════════════" -ForegroundColor Green
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "═══════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "  Get started with:"
Write-Host "    ${prefix}kiro-discovery ""your idea"""
Write-Host "    ${prefix}kiro-spec-init my-feature"
Write-Host "    ${prefix}kiro-spec-requirements my-feature"
Write-Host "    ${prefix}kiro-spec-design my-feature"
Write-Host "    ${prefix}kiro-spec-tasks my-feature"
Write-Host "    ${prefix}kiro-impl my-feature"
Write-Host ""
Write-Host "  CRG Traceability:"
Write-Host "    ${prefix}kiro-trace 1.1"
Write-Host "    ${prefix}kiro-impact src/my-file.py"
Write-Host "    ${prefix}kiro-validate-boundary"
Write-Host ""
Write-Host "  Rebuild code graph:"
Write-Host "    code-review-graph build"
Write-Host ""
