# =============================================================================
# AbstrHActor — containerized test runner (Windows / PowerShell 5.1+)
#
# Builds the Dockerfile.test image, then runs:
#   1. pytest    (unit tests + coverage, output -> .\test-results\)
#   2. ruff+mypy (static checks, profile "lint")
#
# Usage:
#   .\scripts\run_tests.ps1                 # build + pytest + lint
#   .\scripts\run_tests.ps1 -LintOnly       # build + lint only
#   .\scripts\run_tests.ps1 -SkipBuild      # skip the image build step
#   .\scripts\run_tests.ps1 -TestArgs "-k test_filters"
#                                           # extra pytest args (passed via
#                                           # the PYTEST_ARGS env hook)
#
# Requirements: Docker Desktop with the 'docker compose' (v2) plugin, or the
# legacy docker-compose binary.
# =============================================================================

[CmdletBinding()]
param(
    [switch]$LintOnly,
    [switch]$SkipBuild,
    [string]$TestArgs = ""
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $ProjectRoot

$ComposeFile = 'docker-compose.test.yml'
$ResultDir = Join-Path $ProjectRoot 'test-results'

# -----------------------------------------------------------------------------
# Colored output helpers
# -----------------------------------------------------------------------------
function Write-Section { param([string]$Text) Write-Host "`n==> $Text" -ForegroundColor Cyan -Bold }
function Write-Ok      { param([string]$Text) Write-Host "[ ok ] $Text" -ForegroundColor Green }
function Write-Fail    { param([string]$Text) Write-Host "[FAIL] $Text" -ForegroundColor Red }

# -----------------------------------------------------------------------------
# Compose command + Docker availability
# -----------------------------------------------------------------------------
$UseV2 = $false
if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker compose version *> $null
    if ($LASTEXITCODE -eq 0) { $UseV2 = $true }
}
if (-not $UseV2 -and -not (Get-Command docker-compose -ErrorAction SilentlyContinue)) {
    Write-Fail "Docker with 'docker compose' (v2) or 'docker-compose' is required."
    exit 1
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Docker daemon is not running. Start Docker Desktop first."
    exit 1
}

function Invoke-Compose {
    param([string[]]$ComposeArgs)
    if ($UseV2) { & docker compose @ComposeArgs } else { & docker-compose @ComposeArgs }
    return $LASTEXITCODE
}

# -----------------------------------------------------------------------------
# 1. Build
# -----------------------------------------------------------------------------
if (-not $SkipBuild) {
    Write-Section "Building test image (profiles: default + lint)"
    $code = Invoke-Compose @('--profile', 'lint', '-f', $ComposeFile, 'build')
    if ($code -ne 0) {
        Write-Fail "Image build failed."
        exit 1
    }
    Write-Ok "Image build"
}

$exitCode = 0

# -----------------------------------------------------------------------------
# 2. pytest (unit tests + coverage)
# -----------------------------------------------------------------------------
if (-not $LintOnly) {
    Write-Section "Running pytest (unit tests + coverage)"
    New-Item -ItemType Directory -Force -Path $ResultDir | Out-Null

    # Extra pytest args ride on the PYTEST_ARGS env hook (compose interpolates
    # it into the service environment; keeps quoting intact).
    $env:PYTEST_ARGS = $TestArgs

    $code = Invoke-Compose @('-f', $ComposeFile, 'run', '--rm', 'test')
    Remove-Item Env:\PYTEST_ARGS -ErrorAction SilentlyContinue
    if ($code -ne 0) {
        Write-Fail "pytest failed (see output above)"
        $exitCode = 1
    } else {
        Write-Ok "pytest passed"
        Write-Section "Reports"
        Write-Host "  - coverage xml : test-results\coverage.xml"
    }
}

# -----------------------------------------------------------------------------
# 3. Lint (ruff + mypy)
# -----------------------------------------------------------------------------
Write-Section "Running static checks (ruff + mypy)"
$code = Invoke-Compose @('--profile', 'lint', '-f', $ComposeFile, 'run', '--rm', 'lint')
if ($code -ne 0) {
    Write-Fail "lint failed (see output above)"
    $exitCode = 1
} else {
    Write-Ok "ruff + mypy passed"
}

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "All checks passed." -ForegroundColor Green -Bold
} else {
    Write-Host "Some checks failed." -ForegroundColor Red -Bold
}
exit $exitCode
