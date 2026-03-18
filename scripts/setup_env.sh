#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${PYTHON_BIN:-}" ]]; then
  PY="${PYTHON_BIN}"
elif python3.14 --version >/dev/null 2>&1; then
  PY="python3.14"
elif [[ -x /root/.pyenv/versions/3.14.0/bin/python ]]; then
  PY="/root/.pyenv/versions/3.14.0/bin/python"
else
  PY="python"
fi

"${PY}" --version
"${PY}" -m pip install --upgrade pip setuptools wheel
"${PY}" -m pip install -e .[dev]
