#!/usr/bin/env bash
# =============================================================================
# AbstrHActor — containerized test runner (Linux / macOS)
#
# Builds the Dockerfile.test image, then runs:
#   1. pytest    (unit tests + coverage, output -> ./test-results/)
#   2. ruff+mypy (static checks, profile "lint")
#
# Usage:
#   ./scripts/run_tests.sh                    # build + pytest + lint
#   ./scripts/run_tests.sh --lint-only        # build + lint only
#   ./scripts/run_tests.sh --no-build         # skip the image build step
#   ./scripts/run_tests.sh -- -k test_filters # extra pytest args
#
# Environment:
#   PYTEST_ARGS   overrides the pytest invocation entirely (compose passthrough)
#   NO_COLOR=1    disables ANSI colors
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

COMPOSE_FILE="docker-compose.test.yml"
RESULT_DIR="${PROJECT_ROOT}/test-results"

# -----------------------------------------------------------------------------
# Compose command + Docker availability
# -----------------------------------------------------------------------------
COMPOSE=()
if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo "ERROR: 'docker compose' (v2) or 'docker-compose' is required." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon is not running. Start Docker Desktop / the daemon." >&2
  exit 1
fi

# -----------------------------------------------------------------------------
# Colors (respect NO_COLOR and non-TTY output)
# -----------------------------------------------------------------------------
if [[ -t 1 && "${NO_COLOR:-}" != "1" ]]; then
  C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'
  C_GREEN=$'\033[0;32m'; C_YELLOW=$'\033[0;33m'; C_RED=$'\033[0;31m'
  C_CYAN=$'\033[0;36m'
else
  C_RESET=""; C_BOLD=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_CYAN=""
fi

section() { printf "\n${C_BOLD}${C_CYAN}==> %s${C_RESET}\n" "$*"; }
ok()      { printf "${C_GREEN}[ ok ] %s${C_RESET}\n" "$*"; }
warn()    { printf "${C_YELLOW}[warn] %s${C_RESET}\n" "$*"; }
fail()    { printf "${C_RED}[FAIL] %s${C_RESET}\n" "$*"; }

# -----------------------------------------------------------------------------
# Flags
# -----------------------------------------------------------------------------
LINT_ONLY=0
SKIP_BUILD=0
EXTRA_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --lint-only) LINT_ONLY=1 ;;
    --no-build)  SKIP_BUILD=1 ;;
    --) shift; EXTRA_ARGS+=("$@"); break ;;
    *) EXTRA_ARGS+=("$1") ;;
  esac
  shift
done

exit_code=0

# -----------------------------------------------------------------------------
# 1. Build
# -----------------------------------------------------------------------------
if [[ "${SKIP_BUILD}" -eq 0 ]]; then
  section "Building test image (profiles: default + lint)"
  if ! "${COMPOSE[@]}" --profile lint -f "${COMPOSE_FILE}" build; then
    fail "image build failed"
    exit 1
  fi
  ok "image build"
fi

# -----------------------------------------------------------------------------
# 2. pytest (unit tests + coverage)
# -----------------------------------------------------------------------------
if [[ "${LINT_ONLY}" -eq 0 ]]; then
  section "Running pytest (unit tests + coverage)"
  mkdir -p "${RESULT_DIR}"
  # Container user (uid 1000) must be able to write the mounted report dir.
  chmod -R a+rwX "${RESULT_DIR}" 2>/dev/null || warn "could not chmod ${RESULT_DIR}"

  # shellcheck disable=SC2068
  if ! "${COMPOSE[@]}" -f "${COMPOSE_FILE}" run --rm test ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}; then
    fail "pytest failed (see output above)"
    exit_code=1
  else
    ok "pytest passed"
    section "Reports"
    printf "  - coverage xml : %s\n" "test-results/coverage.xml"
  fi
fi

# -----------------------------------------------------------------------------
# 3. Lint (ruff + mypy)
# -----------------------------------------------------------------------------
section "Running static checks (ruff + mypy)"
if ! "${COMPOSE[@]}" --profile lint -f "${COMPOSE_FILE}" run --rm lint; then
  fail "lint failed (see output above)"
  exit_code=1
else
  ok "ruff + mypy passed"
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
printf "\n"
if [[ "${exit_code}" -eq 0 ]]; then
  printf "${C_GREEN}${C_BOLD}All checks passed.${C_RESET}\n"
else
  printf "${C_RED}${C_BOLD}Some checks failed.${C_RESET}\n"
fi
exit "${exit_code}"
