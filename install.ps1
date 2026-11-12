#Requires -Version 5.1
<#
.SYNOPSIS
    One-click Windows PowerShell installer and interactive setup wizard for garmin-coach-mcp.
.DESCRIPTION
    Automates the 5-stage setup workflow for garmin-coach-mcp on Windows (PowerShell 5.1+ and PowerShell 7+):
      [1/5] Verify Minimum System Requirements (Python >= 3.11 or uv)
      [2/5] Create Virtual Environment (.venv) & Install Dependencies
      [3/5] Run Initial Garmin Connect Authentication (MFA/2FA supported)
      [4/5] Verify OAuth Token Creation
      [5/5] Live Garmin Account Read Verification (Optional)
#>
[CmdletBinding()]
param(
    [Parameter(HelpMessage = "Directory to store Garmin OAuth tokens (defaults to `$env:GARMIN_TOKEN_DIR or ~\.garminconnect)")]
    [string]$TokenDir = "",

    [Parameter(HelpMessage = "Skip interactive Garmin Connect authentication (Step 3 & 4)")]
    [switch]$SkipAuth,

    [Parameter(HelpMessage = "Skip live Garmin account read verification (Step 5)")]
    [switch]$SkipVerify,

    [Parameter(HelpMessage = "Run non-interactively without [Y/n] confirmation prompts")]
    [Alias("y")]
    [switch]$Yes,

    [Parameter(HelpMessage = "Show this help message and exit")]
    [Alias("h")]
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoDir = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location -LiteralPath $RepoDir

function Write-StepBanner {
    param(
        [Parameter(Mandatory = $true)][string]$Step,
        [Parameter(Mandatory = $true)][string]$Title
    )
    Write-Host ""
    Write-Host "==============================================================================" -ForegroundColor Cyan
    Write-Host "[$Step] $Title" -ForegroundColor Cyan
    Write-Host "==============================================================================" -ForegroundColor Cyan
}

function Write-Info {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "[INFO] " -ForegroundColor Green -NoNewline
    Write-Host $Message
}

function Write-Warn {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "[WARN] " -ForegroundColor Yellow -NoNewline
    Write-Host $Message
}

function Write-Err {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "[ERROR] " -ForegroundColor Red -NoNewline
    Write-Host $Message
}

function Show-Usage {
    @"
Usage: .\install.ps1 [OPTIONS]

One-click Windows PowerShell installer and interactive setup wizard for garmin-coach-mcp.

Options:
  -TokenDir <dir>     Directory to store Garmin OAuth tokens
                      (default: `$env:GARMIN_TOKEN_DIR or `$HOME\.garminconnect)
  -SkipAuth           Skip interactive Garmin Connect authentication (Step 3 & 4)
  -SkipVerify         Skip live Garmin account read verification (Step 5)
  -Yes, -y            Run non-interactively without [Y/n] confirmation prompts
  -Help, -h           Show this help message and exit

Examples:
  .\install.ps1
  .\install.ps1 -Yes
  .\install.ps1 -TokenDir "$HOME\.garminconnect" -SkipVerify
  .\install.ps1 -SkipAuth -SkipVerify
"@ | Write-Host
}

if ($Help) {
    Show-Usage
    exit 0
}

# Resolve default TokenDir
if ([string]::IsNullOrWhiteSpace($TokenDir)) {
    if (-not [string]::IsNullOrWhiteSpace($env:GARMIN_TOKEN_DIR)) {
        $TokenDir = $env:GARMIN_TOKEN_DIR
    } else {
        $TokenDir = Join-Path $HOME ".garminconnect"
    }
}

# Expand leading ~ if passed literally
if ($TokenDir.StartsWith("~")) {
    $TokenDir = Join-Path $HOME $TokenDir.Substring(1).TrimStart('\', '/')
}

Write-Host "Garmin Coach MCP Server (garmin-coach-mcp) — One-Click Windows Installer" -ForegroundColor White
Write-Host "Repository : $RepoDir"
Write-Host "Token Dir  : $TokenDir"

# ==============================================================================
# [1/5] Verify Minimum System Requirements
# ==============================================================================
Write-StepBanner -Step "1/5" -Title "Verify Minimum System Requirements"

$hasUv = $false
$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
if ($null -ne $uvCmd) {
    $hasUv = $true
    try {
        $uvVersion = (& uv --version 2>$null) -join " "
    } catch {
        $uvVersion = "uv"
    }
    Write-Info "Detected uv package manager: $uvVersion"
}

$pythonOk = $false
$pythonCmd = $null
$pythonArgs = @()
$pythonVersionStr = ""

# Check 'python' then 'py -3'
$candidates = @(
    @{ Exe = "python"; PrefixArgs = @() },
    @{ Exe = "py";     PrefixArgs = @("-3") },
    @{ Exe = "python3"; PrefixArgs = @() }
)

foreach ($cand in $candidates) {
    if ($pythonOk) { break }
    $exeCmd = Get-Command $cand.Exe -ErrorAction SilentlyContinue
    if ($null -ne $exeCmd) {
        try {
            $checkArgs = @($cand.PrefixArgs) + @("-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'); raise SystemExit(0 if sys.version_info >= (3, 11) else 1)")
            $verOut = & $cand.Exe @checkArgs 2>$null
            if ($LASTEXITCODE -eq 0 -and $verOut) {
                $pythonOk = $true
                $pythonCmd = $cand.Exe
                $pythonArgs = $cand.PrefixArgs
                $pythonVersionStr = ($verOut | Select-Object -First 1).ToString().Trim()
                $displayCmd = (@($cand.Exe) + $cand.PrefixArgs) -join " "
                Write-Info "Detected Python $pythonVersionStr via '$displayCmd' (>= 3.11 required)"
            } elseif ($verOut) {
                $pythonVersionStr = ($verOut | Select-Object -First 1).ToString().Trim()
                Write-Warn "Found Python $pythonVersionStr via '$($cand.Exe)' (< 3.11)."
            }
        } catch {
            # Ignore Windows Store alias or broken interpreter
        }
    }
}

if (-not $pythonOk -and $hasUv) {
    try {
        & uv python find ">=3.11" *> $null
        if ($LASTEXITCODE -eq 0) {
            $pythonOk = $true
            Write-Info "Found Python >= 3.11 managed via uv."
        }
    } catch {
        # uv python find failed
    }
}

if (-not $pythonOk) {
    $foundMsg = if ($pythonVersionStr) { $pythonVersionStr } else { "none" }
    Write-Err "Python 3.11 or newer is required (found: $foundMsg)."
    Write-Host "Please install Python 3.11+ (https://www.python.org/downloads/) or install uv:" -ForegroundColor Yellow
    Write-Host '  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"' -ForegroundColor Yellow
    exit 1
}

# ==============================================================================
# [2/5] Create Virtual Environment & Install Dependencies
# ==============================================================================
Write-StepBanner -Step "2/5" -Title "Create Virtual Environment & Install Dependencies"

$venvDir = Join-Path $RepoDir ".venv"
$venvExe = Join-Path $RepoDir ".venv\Scripts\garmin-coach-mcp.exe"
$venvPip = Join-Path $RepoDir ".venv\Scripts\pip.exe"

if ($hasUv) {
    if (-not (Test-Path -LiteralPath $venvDir)) {
        Write-Info "Creating virtual environment (.venv) with uv..."
        & uv venv .venv
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Failed to create .venv with uv."
            exit 1
        }
    } else {
        Write-Info "Existing virtual environment (.venv) detected."
    }

    Write-Info "Installing garmin-coach-mcp and dev dependencies via uv..."
    & uv pip install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) {
        if (Test-Path -LiteralPath $venvExe) {
            Write-Warn "Offline environment detected; reusing existing .venv installation."
        } else {
            Write-Err "Failed to install dependencies with uv."
            exit 1
        }
    }
} else {
    if (-not (Test-Path -LiteralPath $venvDir)) {
        Write-Info "Creating virtual environment (.venv) with $pythonCmd -m venv..."
        $venvCreateArgs = @($pythonArgs) + @("-m", "venv", ".venv")
        & $pythonCmd @venvCreateArgs
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Failed to create virtual environment (.venv)."
            exit 1
        }
    } else {
        Write-Info "Existing virtual environment (.venv) detected."
    }

    $existingOk = $false
    if (Test-Path -LiteralPath $venvExe) {
        try {
            & ".venv\Scripts\garmin-coach-mcp.exe" --help *> $null
            if ($LASTEXITCODE -eq 0) {
                $existingOk = $true
            }
        } catch {
            $existingOk = $false
        }
    }

    if ($existingOk) {
        Write-Info "Existing editable installation in .venv verified."
    } else {
        Write-Info "Upgrading pip and installing garmin-coach-mcp in editable mode..."
        & ".venv\Scripts\pip.exe" install --upgrade pip
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Failed to upgrade pip in .venv."
            exit 1
        }
        & ".venv\Scripts\pip.exe" install -e ".[dev]"
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Failed to install garmin-coach-mcp in .venv."
            exit 1
        }
    }
}

try {
    & ".venv\Scripts\garmin-coach-mcp.exe" --help *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Non-zero exit code ($LASTEXITCODE)"
    }
    Write-Info "CLI entrypoint verified: .venv\Scripts\garmin-coach-mcp.exe --help (OK)"
} catch {
    Write-Err "CLI entrypoint check failed: .venv\Scripts\garmin-coach-mcp.exe --help did not succeed."
    exit 1
}

function Test-ValidTokens {
    param([Parameter(Mandatory = $true)][string]$Dir)
    $singleBundle = Join-Path $Dir "garmin_tokens.json"
    if ((Test-Path -LiteralPath $singleBundle) -and ((Get-Item -LiteralPath $singleBundle).Length -gt 0)) {
        return $true
    }
    $oauth1 = Join-Path $Dir "oauth1_token.json"
    $oauth2 = Join-Path $Dir "oauth2_token.json"
    if ((Test-Path -LiteralPath $oauth1) -and ((Get-Item -LiteralPath $oauth1).Length -gt 0) -and
        (Test-Path -LiteralPath $oauth2) -and ((Get-Item -LiteralPath $oauth2).Length -gt 0)) {
        return $true
    }
    return $false
}

# ==============================================================================
# [3/5] Run Initial Garmin Connect Authentication
# ==============================================================================
Write-StepBanner -Step "3/5" -Title "Run Initial Garmin Connect Authentication"

if ($SkipAuth) {
    Write-Info "Skipping interactive Garmin authentication (-SkipAuth passed)."
} else {
    $runAuth = $true
    if (Test-ValidTokens -Dir $TokenDir) {
        if ($Yes) {
            Write-Info "Existing Garmin tokens found in $TokenDir. Keeping existing tokens (-Yes mode)."
            $runAuth = $false
        } else {
            $reply = Read-Host "Existing Garmin tokens found in $TokenDir. Re-authenticate? [y/N]"
            if ($reply -match "^(y|yes)$") {
                $runAuth = $true
            } else {
                Write-Info "Keeping existing tokens in $TokenDir."
                $runAuth = $false
            }
        }
    }

    if ($runAuth) {
        Write-Info "Starting interactive Garmin Connect login (supports 2FA/MFA)..."
        & ".venv\Scripts\garmin-coach-mcp.exe" auth --token-dir "$TokenDir"
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Garmin Connect authentication failed."
            exit 1
        }
    }
}

# ==============================================================================
# [4/5] Verify OAuth Token Creation
# ==============================================================================
Write-StepBanner -Step "4/5" -Title "Verify OAuth Token Creation"

if ($SkipAuth) {
    Write-Info "Skipping OAuth token file check (-SkipAuth passed)."
} else {
    if (-not (Test-ValidTokens -Dir $TokenDir)) {
        Write-Err "Garmin OAuth token files were not found or are empty in $TokenDir."
        Write-Err "Expected $TokenDir\garmin_tokens.json or both oauth1_token.json and oauth2_token.json."
        Write-Err "Run '.venv\Scripts\garmin-coach-mcp.exe auth --token-dir `"$TokenDir`"' to authenticate."
        exit 1
    }

    foreach ($tokenFileName in @("garmin_tokens.json", "oauth1_token.json", "oauth2_token.json")) {
        $tfPath = Join-Path $TokenDir $tokenFileName
        if (Test-Path -LiteralPath $tfPath) {
            $item = Get-Item -LiteralPath $tfPath
            if ($item.Length -gt 0) {
                Write-Info "Verified token file: $tfPath ($($item.Length) bytes)"
            }
        }
    }
    Write-Info "Verified token directory: $TokenDir"
}

# ==============================================================================
# [5/5] [Optional] Live Garmin Account Read Verification
# ==============================================================================
Write-StepBanner -Step "5/5" -Title "Live Garmin Account Read Verification (Optional)"

if ($SkipAuth -or $SkipVerify) {
    Write-Info "Skipping live Garmin account verification (-SkipAuth or -SkipVerify passed)."
} else {
    $doVerify = $true
    if (-not $Yes) {
        $verifyReply = Read-Host "Would you like to fetch your Garmin athlete profile now to verify account access? [Y/n]"
        if ($verifyReply -match "^(n|no)$") {
            $doVerify = $false
        } else {
            $doVerify = $true
        }
    }

    if ($doVerify) {
        Write-Info "Fetching Garmin athlete profile via 'garmin-coach-mcp verify'..."
        & ".venv\Scripts\garmin-coach-mcp.exe" verify --token-dir "$TokenDir"
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Live Garmin profile verification failed."
            exit 1
        }
    } else {
        Write-Info "Skipped live profile verification. You can run it anytime with:"
        Write-Host "  `"$venvExe`" verify --token-dir `"$TokenDir`""
    }
}

# ==============================================================================
# Final Summary Banner — Ready-to-Copy MCP Registration Commands
# ==============================================================================
$binaryPath = Join-Path $RepoDir ".venv\Scripts\garmin-coach-mcp.exe"
$cacheDir = if (-not [string]::IsNullOrWhiteSpace($env:GARMIN_CACHE_DIR)) {
    $env:GARMIN_CACHE_DIR
} else {
    Join-Path $HOME ".cache\garmin-coach-mcp"
}

$binaryPathJson = $binaryPath.Replace('\', '\\')
$tokenDirJson = $TokenDir.Replace('\', '\\')
$cacheDirJson = $cacheDir.Replace('\', '\\')

Write-Host ""
Write-Host "==============================================================================" -ForegroundColor Green
Write-Host "Setup Complete! garmin-coach-mcp is ready." -ForegroundColor Green
Write-Host "==============================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "1. Register in Claude Desktop / Cursor / Antigravity (~/.gemini/config/mcp_config.json):" -ForegroundColor White
@"
{
  "mcpServers": {
    "garmin-coach": {
      "command": "$binaryPathJson",
      "args": [],
      "env": {
        "GARMIN_TOKEN_DIR": "$tokenDirJson",
        "GARMIN_CACHE_DIR": "$cacheDirJson",
        "GARMIN_CACHE_TTL": "900",
        "GARMIN_UNITS": "metric"
      }
    }
  }
}
"@ | Write-Host
Write-Host ""
Write-Host "2. Register in Gemini CLI:" -ForegroundColor White
Write-Host "  gemini mcp add garmin-coach `"$binaryPath`" ``"
Write-Host "    -e GARMIN_TOKEN_DIR=`"$TokenDir`" ``"
Write-Host "    -e GARMIN_CACHE_DIR=`"$cacheDir`" ``"
Write-Host "    -e GARMIN_CACHE_TTL=900 ``"
Write-Host "    -e GARMIN_UNITS=metric"
Write-Host ""
Write-Host "3. Verify your Garmin connection anytime:" -ForegroundColor White
Write-Host "  `"$binaryPath`" verify --token-dir `"$TokenDir`""
Write-Host ""
