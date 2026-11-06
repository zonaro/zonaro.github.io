#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"
command -v gh >/dev/null || { printf 'GitHub CLI (gh) não encontrado.\n' >&2; exit 1; }
command -v python3 >/dev/null || { printf 'Python 3 não encontrado.\n' >&2; exit 1; }
gh auth status --active --hostname github.com >/dev/null || { printf 'Faça login usando gh auth login.\n' >&2; exit 1; }
exec python3 scripts/portfolio_dashboard.py "$@"
