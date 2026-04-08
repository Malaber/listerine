#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

find_shared_venv() {
  git -C "$ROOT" worktree list --porcelain | while read -r line; do
    [[ "$line" == worktree\ * ]] || continue
    worktree_path="${line#worktree }"
    [[ "$worktree_path" == "$ROOT" ]] && continue
    if [[ -x "$worktree_path/.venv/bin/inv" ]]; then
      printf '%s\n' "$worktree_path/.venv"
      return 0
    fi
  done
}

if [[ -x "$ROOT/.venv/bin/inv" ]]; then
  "$ROOT/.venv/bin/python" --version
  exit 0
fi

if [[ -L "$ROOT/.venv" && ! -e "$ROOT/.venv" ]]; then
  rm "$ROOT/.venv"
fi

if [[ ! -e "$ROOT/.venv" ]]; then
  if shared_venv="$(find_shared_venv)"; then
    ln -s "$shared_venv" "$ROOT/.venv"
    echo "Linked worktree .venv -> $shared_venv"
    "$ROOT/.venv/bin/python" --version
    exit 0
  fi
fi

./scripts/setup_env.sh
