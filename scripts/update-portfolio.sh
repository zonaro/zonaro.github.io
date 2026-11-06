#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

publish=false
yes=false
options=()

for arg in "$@"; do
  case "$arg" in
    --publish) publish=true ;;
    --yes) yes=true ;;
    --dry-run|--no-images) options+=("$arg") ;;
    -h|--help)
      printf '%s\n' 'Uso: scripts/update-portfolio.sh [--dry-run] [--no-images] [--publish] [--yes]' \
        '  --dry-run    Lista os projetos elegíveis sem gerar arquivos.' \
        '  --publish    Gera, confirma e envia para main.' \
        '  --yes        Dispensa a confirmação interativa (use com cuidado).'
      exit 0 ;;
    *) printf 'Opção desconhecida: %s\n' "$arg" >&2; exit 1 ;;
  esac
done

command -v gh >/dev/null || { printf 'Instale o GitHub CLI (gh) primeiro.\n' >&2; exit 1; }
command -v python3 >/dev/null || { printf 'Python 3 não encontrado.\n' >&2; exit 1; }
gh auth status --active --hostname github.com >/dev/null || {
  printf 'Faça login primeiro: gh auth login\n' >&2; exit 1;
}

if $publish; then
  if [[ "$(git branch --show-current)" != "main" ]]; then
    printf 'Publicação permitida apenas na branch main.\n' >&2
    exit 1
  fi
  # A prior preview may have changed generated files. Never stage unrelated edits.
  while IFS= read -r changed; do
    file="${changed:3}"
    case "$file" in
      index.html|profile.json|llms.txt|sitemap.xml|projects/*|assets/generated/*) ;;
      *) printf 'Alteração não gerada detectada: %s. Revise antes de publicar.\n' "$file" >&2; exit 1 ;;
    esac
  done < <(git status --porcelain --untracked-files=all)
  if [[ " ${options[*]} " == *" --dry-run "* ]]; then
    printf 'Não combine --publish com --dry-run.\n' >&2
    exit 1
  fi
fi

python3 scripts/generate_portfolio.py "${options[@]}"

if ! $publish; then
  printf '\nPrévia concluída. Para publicar, revise git diff e execute com --publish.\n'
  exit 0
fi

git add -A -- index.html profile.json llms.txt sitemap.xml assets/generated
if [[ -d projects ]] || git ls-files --error-unmatch 'projects/*' >/dev/null 2>&1; then
  git add -A -- projects
fi
if git diff --cached --quiet; then
  printf 'Nenhuma alteração para publicar.\n'
  exit 0
fi

printf '\nArquivos alterados:\n'
git diff --cached --stat
if ! $yes; then
  printf '\nATENÇÃO: projetos privados classificados serão publicados com nome e descrição.\n'
  read -r -p 'Confirmar commit e push na main? [s/N] ' answer
  if [[ "$answer" != "s" && "$answer" != "S" ]]; then
    git restore --staged -- index.html profile.json llms.txt sitemap.xml assets/generated
    if [[ -d projects ]]; then git restore --staged -- projects; fi
    printf 'Publicação cancelada. Arquivos gerados mantidos para revisão.\n'
    exit 0
  fi
fi

git commit -m "build(portfolio): regenerate curated project pages"
git push origin main
printf 'Publicação enviada à main; acompanhe o deploy do GitHub Pages.\n'
