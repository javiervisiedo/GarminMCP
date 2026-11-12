#!/usr/bin/env bash
# ==============================================================================
# garmin-coach-mcp — One-Click Installer & Interactive Setup Script
# ==============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

# ANSI color codes (disabled automatically when NO_COLOR is set or stdout is not a TTY)
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    BOLD="\033[1m"
    GREEN="\033[1;32m"
    CYAN="\033[1;36m"
    YELLOW="\033[1;33m"
    RED="\033[1;31m"
    RESET="\033[0m"
else
    BOLD=""
    GREEN=""
    CYAN=""
    YELLOW=""
    RED=""
    RESET=""
fi

step_banner() {
    local step="$1"
    local title="$2"
    echo ""
    echo -e "${CYAN}${BOLD}==============================================================================${RESET}"
    echo -e "${CYAN}${BOLD}[${step}] ${title}${RESET}"
    echo -e "${CYAN}${BOLD}==============================================================================${RESET}"
}

info() {
    echo -e "${GREEN}[INFO]${RESET} $*"
}

warn() {
    echo -e "${YELLOW}[WARN]${RESET} $*"
}

error() {
    echo -e "${RED}[ERROR]${RESET} $*" >&2
}

usage() {
    cat <<EOF
Usage: ./install.sh [OPTIONS]

One-click installer and interactive setup wizard for garmin-coach-mcp.

Options:
  --token-dir <dir>   Directory to store Garmin OAuth tokens
                      (default: \${GARMIN_TOKEN_DIR:-\$HOME/.garminconnect})
  --skip-auth         Skip interactive Garmin Connect authentication (Step 3 & 4)
  --skip-verify       Skip live Garmin account read verification (Step 5)
  -y, --yes           Run non-interactively without [Y/n] confirmation prompts
  -h, --help          Show this help message and exit

Examples:
  ./install.sh
  ./install.sh --yes
  ./install.sh --token-dir ~/.garminconnect --skip-verify
  ./install.sh --skip-auth --skip-verify
EOF
}

# Default option values
TOKEN_DIR="${GARMIN_TOKEN_DIR:-$HOME/.garminconnect}"
SKIP_AUTH=false
SKIP_VERIFY=false
ASSUME_YES=false

# Parse CLI flags
while [[ $# -gt 0 ]]; do
    case "$1" in
        --token-dir)
            if [[ $# -lt 2 ]]; then
                error "--token-dir requires a directory path argument."
                exit 1
            fi
            TOKEN_DIR="$2"
            shift 2
            ;;
        --token-dir=*)
            TOKEN_DIR="${1#*=}"
            shift
            ;;
        --skip-auth)
            SKIP_AUTH=true
            shift
            ;;
        --skip-verify)
            SKIP_VERIFY=true
            shift
            ;;
        -y|--yes)
            ASSUME_YES=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Expand leading tilde if passed literally
TOKEN_DIR="${TOKEN_DIR/#\~/$HOME}"

echo -e "${BOLD}Garmin Coach MCP Server (garmin-coach-mcp) — One-Click Installer${RESET}"
echo -e "Repository : ${REPO_DIR}"
echo -e "Token Dir  : ${TOKEN_DIR}"

# ==============================================================================
# Step 1 — Verify Minimum System Requirements
# ==============================================================================
step_banner "1/5" "Verify Minimum System Requirements"

OS_NAME="$(uname -s)"
case "$OS_NAME" in
    Linux|Darwin)
        info "Operating System: ${OS_NAME} (supported)"
        ;;
    *)
        error "Unsupported operating system for install.sh: ${OS_NAME}. On Windows, please run .\install.ps1 in PowerShell (or run ./install.sh inside WSL)."
        exit 1
        ;;
esac

HAS_UV=false
if command -v uv >/dev/null 2>&1; then
    HAS_UV=true
    UV_VERSION="$(uv --version 2>/dev/null || echo 'uv')"
    info "Detected uv package manager: ${UV_VERSION}"
fi

PYTHON_OK=false
PYTHON_VERSION_STR=""

if command -v python3 >/dev/null 2>&1; then
    if python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
        PYTHON_OK=true
        PYTHON_VERSION_STR="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
        info "Detected Python ${PYTHON_VERSION_STR} (>= 3.11 required)"
    else
        PYTHON_VERSION_STR="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")' 2>/dev/null || echo 'unknown')"
        warn "System python3 is version ${PYTHON_VERSION_STR} (< 3.11)."
    fi
fi

if [[ "$PYTHON_OK" == false && "$HAS_UV" == true ]]; then
    if uv python find '>=3.11' >/dev/null 2>&1; then
        PYTHON_OK=true
        info "Found Python >= 3.11 managed via uv."
    fi
fi

if [[ "$PYTHON_OK" == false ]]; then
    error "Python 3.11 or newer is required (found: ${PYTHON_VERSION_STR:-none})."
    echo -e "Please install Python 3.11+ or install ${BOLD}uv${RESET}:" >&2
    echo -e "  curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 1
fi

# ==============================================================================
# Step 2 — Create Virtual Environment & Install Dependencies
# ==============================================================================
step_banner "2/5" "Create Virtual Environment & Install Dependencies"

if [[ "$HAS_UV" == true ]]; then
    if [[ ! -d ".venv" ]]; then
        info "Creating virtual environment (.venv) with uv..."
        uv venv .venv
    else
        info "Existing virtual environment (.venv) detected."
    fi
    info "Installing garmin-coach-mcp and dev dependencies via uv..."
    if ! uv pip install -e ".[dev]"; then
        if [[ -x ".venv/bin/garmin-coach-mcp" ]]; then
            warn "Offline environment detected; reusing existing .venv installation."
        else
            error "Failed to install dependencies with uv."
            exit 1
        fi
    fi
else
    if [[ ! -d ".venv" ]]; then
        info "Creating virtual environment (.venv) with python3 -m venv..."
        python3 -m venv .venv
    else
        info "Existing virtual environment (.venv) detected."
    fi
    if [[ -x ".venv/bin/garmin-coach-mcp" ]] && .venv/bin/garmin-coach-mcp --help >/dev/null 2>&1; then
        info "Existing editable installation in .venv verified."
    else
        info "Upgrading pip and installing garmin-coach-mcp in editable mode..."
        .venv/bin/pip install --upgrade pip
        .venv/bin/pip install -e ".[dev]"
    fi
fi

if .venv/bin/garmin-coach-mcp --help >/dev/null 2>&1; then
    info "CLI entrypoint verified: .venv/bin/garmin-coach-mcp --help (OK)"
else
    error "CLI entrypoint check failed: .venv/bin/garmin-coach-mcp --help did not succeed."
    exit 1
fi

# Helper to check if valid non-empty Garmin token files exist
has_valid_tokens() {
    local dir="$1"
    if [[ -s "${dir}/garmin_tokens.json" ]]; then
        return 0
    fi
    if [[ -s "${dir}/oauth1_token.json" && -s "${dir}/oauth2_token.json" ]]; then
        return 0
    fi
    return 1
}

# ==============================================================================
# Step 3 — Run Initial Garmin Connect Authentication
# ==============================================================================
step_banner "3/5" "Run Initial Garmin Connect Authentication"

if [[ "$SKIP_AUTH" == true ]]; then
    info "Skipping interactive Garmin authentication (--skip-auth passed)."
else
    RUN_AUTH=true
    if has_valid_tokens "$TOKEN_DIR"; then
        if [[ "$ASSUME_YES" == true ]]; then
            info "Existing Garmin tokens found in ${TOKEN_DIR}. Keeping existing tokens (--yes mode)."
            RUN_AUTH=false
        else
            read -r -p "Existing Garmin tokens found in ${TOKEN_DIR}. Re-authenticate? [y/N] " REPLY || REPLY="N"
            case "$REPLY" in
                [yY]|[yY][eE][sS])
                    RUN_AUTH=true
                    ;;
                *)
                    info "Keeping existing tokens in ${TOKEN_DIR}."
                    RUN_AUTH=false
                    ;;
            esac
        fi
    fi

    if [[ "$RUN_AUTH" == true ]]; then
        info "Starting interactive Garmin Connect login (supports 2FA/MFA)..."
        .venv/bin/garmin-coach-mcp auth --token-dir "$TOKEN_DIR"
    fi
fi

# ==============================================================================
# Step 4 — Verify OAuth Token Creation & Permissions
# ==============================================================================
step_banner "4/5" "Verify OAuth Token Creation & Permissions"

if [[ "$SKIP_AUTH" == true ]]; then
    info "Skipping OAuth token file check (--skip-auth passed)."
else
    if ! has_valid_tokens "$TOKEN_DIR"; then
        error "Garmin OAuth token files were not found or are empty in ${TOKEN_DIR}."
        error "Expected ${TOKEN_DIR}/garmin_tokens.json or both oauth1_token.json and oauth2_token.json."
        error "Run '.venv/bin/garmin-coach-mcp auth --token-dir \"${TOKEN_DIR}\"' to authenticate."
        exit 1
    fi

    chmod 700 "$TOKEN_DIR" 2>/dev/null || true
    for tf in "${TOKEN_DIR}/garmin_tokens.json" "${TOKEN_DIR}/oauth1_token.json" "${TOKEN_DIR}/oauth2_token.json"; do
        if [[ -f "$tf" ]]; then
            chmod 600 "$tf" 2>/dev/null || true
            info "Verified token file: ${tf} (non-empty, mode 0600)"
        fi
    done
    info "Verified token directory: ${TOKEN_DIR} (mode 0700)"
fi

# ==============================================================================
# Step 5 — [Optional] Live Garmin Account Read Verification
# ==============================================================================
step_banner "5/5" "Live Garmin Account Read Verification (Optional)"

if [[ "$SKIP_AUTH" == true || "$SKIP_VERIFY" == true ]]; then
    info "Skipping live Garmin account verification (--skip-auth or --skip-verify passed)."
else
    DO_VERIFY=true
    if [[ "$ASSUME_YES" == false ]]; then
        read -r -p "Would you like to fetch your Garmin athlete profile now to verify account access? [Y/n] " VERIFY_REPLY || VERIFY_REPLY="Y"
        case "$VERIFY_REPLY" in
            [nN]|[nN][oO])
                DO_VERIFY=false
                ;;
            *)
                DO_VERIFY=true
                ;;
        esac
    fi

    if [[ "$DO_VERIFY" == true ]]; then
        info "Fetching Garmin athlete profile via 'garmin-coach-mcp verify'..."
        .venv/bin/garmin-coach-mcp verify --token-dir "$TOKEN_DIR"
    else
        info "Skipped live profile verification. You can run it anytime with:"
        echo "  ${REPO_DIR}/.venv/bin/garmin-coach-mcp verify --token-dir \"${TOKEN_DIR}\""
    fi
fi

# ==============================================================================
# Final Summary Banner — Ready-to-Copy MCP Registration Commands
# ==============================================================================
BINARY_PATH="${REPO_DIR}/.venv/bin/garmin-coach-mcp"
CACHE_DIR="${GARMIN_CACHE_DIR:-$HOME/.cache/garmin-coach-mcp}"

echo ""
echo -e "${GREEN}${BOLD}==============================================================================${RESET}"
echo -e "${GREEN}${BOLD}Setup Complete! garmin-coach-mcp is ready.${RESET}"
echo -e "${GREEN}${BOLD}==============================================================================${RESET}"
echo ""
echo -e "${BOLD}1. Register in Claude Desktop / Cursor / Antigravity (~/.gemini/config/mcp_config.json):${RESET}"
cat <<EOF
{
  "mcpServers": {
    "garmin-coach": {
      "command": "${BINARY_PATH}",
      "args": [],
      "env": {
        "GARMIN_TOKEN_DIR": "${TOKEN_DIR}",
        "GARMIN_CACHE_DIR": "${CACHE_DIR}",
        "GARMIN_CACHE_TTL": "900",
        "GARMIN_UNITS": "metric"
      }
    }
  }
}
EOF
echo ""
echo -e "${BOLD}2. Register in Gemini CLI:${RESET}"
echo "  gemini mcp add garmin-coach \"${BINARY_PATH}\" \\"
echo "    -e GARMIN_TOKEN_DIR=\"${TOKEN_DIR}\" \\"
echo "    -e GARMIN_CACHE_DIR=\"${CACHE_DIR}\" \\"
echo "    -e GARMIN_CACHE_TTL=900 \\"
echo "    -e GARMIN_UNITS=metric"
echo ""
echo -e "${BOLD}3. Verify your Garmin connection anytime:${RESET}"
echo "  \"${BINARY_PATH}\" verify --token-dir \"${TOKEN_DIR}\""
echo ""
