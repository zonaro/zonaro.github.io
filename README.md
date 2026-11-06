# Zonaro · Beatbox & Code

Portfólio público de Gabriel Forti Zonaro, dividido em duas áreas: desenvolvimento de software e música/beatbox.

## Site

- Desenvolvimento: https://zonaro.github.io/
- Beatbox: https://zonaro.github.io/beatbox/

## Hospedagem

HTML, CSS e JavaScript estáticos para GitHub Pages. Publicar a branch `main`, pasta `/ (root)`, em **Settings → Pages → Build and deployment → Deploy from a branch**.

## SEO e acessibilidade

Contém metadados Open Graph, dados estruturados schema.org, `sitemap.xml`, `robots.txt`, `llms.txt` e `profile.json`. Tem navegação sem JavaScript e respeita preferência de redução de movimento.

## Curadoria automática via GitHub CLI

O conteúdo dos projetos é gerado **localmente**, com `gh` autenticado e Python 3, sem tokens no GitHub Pages. Os dados vêm das configurações nativas do GitHub; não é necessária uma pasta de metadados em cada repositório.

Um projeto só aparece no site se tiver **exatamente uma** das seguintes *repository topics*:

| Topic | Exibição |
| --- | --- |
| `portfolio-primary` | Destaque principal |
| `portfolio-secondary` | Destaque secundário |
| `portfolio-catalog` | Somente no catálogo |

Sem essas topics, o repositório fica **oculto por padrão**. Com duas ou três ao mesmo tempo, ele é ignorado e aparece um aviso de conflito. Não é necessário `portfolio-private-ok` nem `portfolio-hidden`.

**Regra obrigatória de privacidade:** quando um repositório é privado, o gerador consulta somente o nome e a descrição para conteúdo do site. Lê as topics e a visibilidade apenas para decidir se entra no catálogo. **Nunca lê README, código, Social Preview, homepage, linguagens ou outras informações de repositórios privados.** Uma das três topics funciona como autorização explícita para publicar o **nome e a descrição** daquele projeto, e nada mais. Não gera link para o repositório privado.

Para repositórios **públicos**, utiliza nome, descrição, README renderizado (página de detalhe), Social Preview personalizada quando disponível, linguagem e links públicos. Links e imagens relativas do README são ajustados, e o HTML é filtrado antes de entrar no site.

### Uso no Fedora

Requer `git`, `gh` e `python3`. Após clonar este repositório:

```bash
gh auth login
gh auth setup-git
./scripts/update-portfolio.sh --dry-run
./scripts/update-portfolio.sh
git diff
./scripts/update-portfolio.sh --publish
```

- `--dry-run`: lista os elegíveis e conflitos, sem ler READMEs nem escrever arquivos.
- Sem argumentos: gera o site estaticamente no disco e mostra os projetos; **não publica**.
- `--no-images`: não baixa Social Previews (usa arte de fallback).
- `--publish`: exige branch `main` sem alterações **fora dos arquivos gerados**, mostra o diff resumido, confirma e faz commit/push.
- `--publish --yes`: dispensa a confirmação; somente para automação local consciente.

O GitHub Pages permanece configurado para publicar a `main` pela raiz. A versão pública atual não é substituída até uma execução de `--publish`. Execute `--dry-run` e confira especialmente os privados antes da primeira publicação. **Uma topic em um projeto privado significa que nome e descrição serão públicos.**

### Arquivos gerados

- `index.html`: regiões de destaques e catálogo identificadas por comentários `PORTFOLIO`.
- `projects/<nome>/index.html`: páginas individuais estáticas; para privados, apenas título e descrição.
- `assets/generated/projects.json` e `assets/generated/covers/`: dados e imagens aprovados para publicação.
- `sitemap.xml`, `llms.txt` e `profile.json`: atualizados com os projetos incluídos.

O gerador remove páginas e imagens geradas de projetos que deixaram de ser elegíveis. O código-fonte do portfólio, a página de beatbox e os demais assets existentes são preservados.

### Testes

```bash
python3 -m unittest discover -s tests -v
```

Os testes verificam seleção por topic, conflitos, isolamento de repositórios privados, filtragem de HTML e idempotência da geração, usando dados simulados e sem exigir autenticação.

Para detalhes de manutenção, consulte [`.agents/PORTFOLIO.md`](.agents/PORTFOLIO.md).
