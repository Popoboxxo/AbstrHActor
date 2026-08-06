#!/bin/sh
# =============================================================================
# Abstractor test-container entrypoint
#
# Dispatch table (first argument decides):
#   (no args) / <pytest args>  -> pytest tests/ -v <args>
#                                 ($PYTEST_ARGS, when set, is prepended and wins)
#   lint                       -> ruff check + mypy
#   shell | bash               -> interactive /bin/sh
#
# PYTEST_ARGS is the environment-variable hook used by docker-compose.test.yml
# and the runner scripts to pass arbitrary pytest flags without touching CMD.
# =============================================================================
set -e

# -----------------------------------------------------------------------------
# Static checks
# -----------------------------------------------------------------------------
if [ "$#" -ge 1 ] && { [ "$1" = "lint" ] || [ "$1" = "check" ]; }; then
    shift
    echo "==> ruff check custom_components tests"
    ruff check custom_components tests "$@"
    echo "==> mypy custom_components"
    mypy --cache-dir=/tmp/.mypy_cache --ignore-missing-imports custom_components
    exit 0
fi

# -----------------------------------------------------------------------------
# Interactive shell escape hatch:  docker compose run --rm test shell
# -----------------------------------------------------------------------------
if [ "$#" -ge 1 ] && { [ "$1" = "shell" ] || [ "$1" = "bash" ]; }; then
    shift
    exec /bin/sh "$@"
fi

# -----------------------------------------------------------------------------
# pytest (default)
# -----------------------------------------------------------------------------
if [ -n "${PYTEST_ARGS:-}" ]; then
    # PYTEST_ARGS wins; positional args are appended (e.g. `run --rm test -k x`).
    # shellcheck disable=SC2086
    set -- $PYTEST_ARGS "$@"
elif [ "$#" -eq 0 ]; then
    set -- tests/ -v
fi

echo "==> pytest $*"
exec pytest "$@"
