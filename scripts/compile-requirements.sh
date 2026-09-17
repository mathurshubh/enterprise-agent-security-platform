#!/usr/bin/env bash
# Generate or verify requirements.txt from requirements.in with the pinned pip-tools
# toolchain in requirements-tools.txt. Compile options live in pyproject.toml under
# [tool.pip-tools], where Dependabot reads them too.
#
# Usage (from any directory):
#   scripts/compile-requirements.sh                            regenerate requirements.txt
#   scripts/compile-requirements.sh --upgrade-package <name>   intentionally upgrade one package
#   scripts/compile-requirements.sh --check                    fail if requirements.txt is not
#                                                              reproducible from requirements.in
#
# Existing pins in requirements.txt are kept unless an upgrade is requested.
#
# Environment:
#   PYTHON          Python 3.13 interpreter used to build the toolchain
#                   (default: .venv/bin/python if present, otherwise python3)
#   PIP_TOOLS_VENV  toolchain virtualenv (default: .venv-tools)
set -euo pipefail

REQUIRED_PYTHON="3.13"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -z "${PYTHON:-}" ]]; then
  if [[ -x .venv/bin/python ]]; then PYTHON=.venv/bin/python; else PYTHON=python3; fi
fi
TOOLS_VENV="${PIP_TOOLS_VENV:-$ROOT/.venv-tools}"

python_version() {
  "$1" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
}

# The Python minor version is recorded in the requirements.txt header and determines
# environment markers, so every compilation must use the same one.
if [[ "$(python_version "$PYTHON")" != "$REQUIRED_PYTHON" ]]; then
  echo "error: requirements.txt is compiled with Python $REQUIRED_PYTHON, but $PYTHON is Python $(python_version "$PYTHON")." >&2
  echo "Set PYTHON to a Python $REQUIRED_PYTHON interpreter." >&2
  exit 2
fi

# The toolchain lives in its own virtualenv, so it is never installed from the
# lockfile it generates.
if [[ -x "$TOOLS_VENV/bin/python" && "$(python_version "$TOOLS_VENV/bin/python")" != "$REQUIRED_PYTHON" ]]; then
  echo "error: $TOOLS_VENV uses Python $(python_version "$TOOLS_VENV/bin/python"). Remove it and rerun." >&2
  exit 2
fi
if [[ ! -x "$TOOLS_VENV/bin/python" ]]; then
  "$PYTHON" -m venv "$TOOLS_VENV"
fi
"$TOOLS_VENV/bin/python" -m pip install --quiet --disable-pip-version-check -r requirements-tools.txt

# Record the regeneration command in the header instead of the raw pip-compile call.
export CUSTOM_COMPILE_COMMAND="scripts/compile-requirements.sh"

compile_in() {
  local dir="$1"
  shift
  (cd "$dir" && "$TOOLS_VENV/bin/pip-compile" --quiet --config=pyproject.toml \
    --output-file=requirements.txt "$@" requirements.in)
}

if [[ "${1:-}" == "--check" ]]; then
  # Regenerate from copies in a temporary directory; never modify the working tree.
  # The committed requirements.txt seeds existing pins, so the check verifies that it
  # is exactly what pip-compile produces from requirements.in, not that it is current.
  workdir="$(mktemp -d)"
  trap 'rm -rf "$workdir"' EXIT
  cp requirements.in requirements.txt pyproject.toml "$workdir/"

  compile_in "$workdir"

  if ! diff -u requirements.txt "$workdir/requirements.txt"; then
    echo "error: requirements.txt is not reproducible from requirements.in." >&2
    echo "Run scripts/compile-requirements.sh, review the diff, and commit both files." >&2
    exit 1
  fi
  echo "requirements.txt is reproducible from requirements.in."
else
  compile_in "$ROOT" "$@"
fi
