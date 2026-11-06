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
./scripts/portfolio-dashboard.sh
./scripts/update-portfolio.sh --dry-run
./scripts/update-portfolio.sh
git diff
./scripts/update-portfolio.sh --publish
```

- `--dry-run`: lista os elegíveis e conflitos, sem ler READMEs nem escrever arquivos.
- Sem argumentos: gera o site estaticamente no disco e mostra os projetos; **não publica**.
- `--no-images`: não baixa Social Previews (mantém o fallback SVG).
- `--publish`: exige branch `main` sem alterações **fora dos arquivos gerados e capas SVG personalizadas**, mostra o diff resumido, confirma e faz commit/push.
- `--publish --yes`: dispensa a confirmação; somente para automação local consciente.

O GitHub Pages permanece configurado para publicar a `main` pela raiz. A versão pública atual não é substituída até uma execução de `--publish`. Execute `--dry-run` e confira especialmente os privados antes da primeira publicação. **Uma topic em um projeto privado significa que nome e descrição serão públicos.**

### Dashboard local de repositórios

Execute `./scripts/portfolio-dashboard.sh` no checkout deste repositório. O painel abre `http://127.0.0.1:8765/` e mostra todos os repositórios acessíveis à conta `zonaro`, públicos e privados. Opcionalmente, use `--port 8766` ou `--no-browser`.

- Busca e filtros por visibilidade e categoria; contadores de destaques e catálogo.
- Classificação entre **Oculto**, **Principal**, **Secundário** e **Catálogo**, salva automaticamente ao trocar o select. Não existe botão Salvar.
- Descrição curta editável e salva automaticamente ao sair do campo; o painel verifica se outro usuário não alterou o conteúdo entretanto.
- **Tags coloridas:** em projetos públicos, o botão **Tags** permite criar, aplicar e desmarcar tags como *Em desenvolvimento* e *Comercial*, além de editar seu nome e sua cor. Cada associação é armazenada como topic `portfolio-label-<slug>` no GitHub; cores e nomes ficam em `scripts/portfolio_labels.json`. Tudo salva automaticamente, sem botão Salvar. O arquivo não contém associações a repositórios ocultos.
- **Site do projeto:** o botão **Site do projeto** edita o campo *Website* nativo do GitHub, com salvamento ao sair do campo. Quando presente, é o link externo principal no portfólio; caso contrário, o link externo aponta ao repositório. Páginas internas de detalhes continuam disponíveis. Por privacidade, tags e site são editáveis apenas para repositórios públicos.
- O painel preserva as topics não relacionadas às funções editadas e recusa sobrescrever alterações concorrentes.
- **Capa SVG:** editor local com três estilos, 20 símbolos vetoriais monocromáticos (além da inicial), cores, visualização, upload `.svg` (até 100 KB) e edição direta do SVG. Mudanças são gravadas em `assets/portfolio-covers/<slug>.svg` automaticamente; o upload rejeita scripts, imagens externas e recursos ativos. Caso não haja capa personalizada, o gerador cria um SVG determinístico em `assets/generated/covers/`.
- Capas criadas para projetos **ocultos** permanecem locais e não são adicionadas ao Git na publicação. Quando um projeto já publicado for ocultado, a capa deixa de fazer parte da versão atual do site (embora commits antigos possam continuar acessíveis no histórico do Git).
- **Prioridade de imagem:** Social Preview personalizada de repositórios públicos → capa SVG personalizada no portfólio → SVG automático. Para privados, o gerador nunca consulta imagem no GitHub; a arte local é gerada apenas a partir do nome autorizado.
- **Social Preview do GitHub:** o botão de edição abre as configurações do repositório em uma nova aba. O GitHub não oferece API pública de upload dessa imagem; o upload da Social Preview é manual no GitHub.
- **Excluir repositório:** botão vermelho e diálogo separado que exige digitar `zonaro/nome-exato`. O backend confere novamente identidade, privacidade, topics e permissão administrativa antes de executar `gh repo delete zonaro/nome --yes`. O repositório `zonaro.github.io` é protegido e nenhum repositório é excluído sem confirmação.
- **Gerar prévia local** executa o gerador, mostra os arquivos modificados e não publica nada. Depois da prévia, **Publicar no GitHub Pages** exige a confirmação `PUBLICAR` e executa o mesmo fluxo de commit/push do shell.
- O servidor escuta exclusivamente em `127.0.0.1`, exige token de sessão e valida origem para escritas; não publica API nem credenciais no Pages. Feche com Ctrl+C.

**Importante:** o código da interface faz parte do repositório público, mas os dados privados e a API de administração são servidos somente pelo processo local. Nunca abra a porta para a rede nem implante `portfolio_dashboard.py` em um servidor público.

Para habilitar a exclusão no GitHub CLI, pode ser necessário executar `gh auth refresh -s delete_repo`. **Excluir é diferente de ocultar no portfólio:** a exclusão remove o repositório do GitHub, pode afetar forks, issues e permissões e sua restauração não é garantida. Após excluir, gere e publique uma nova versão do portfólio para remover os cartões estáticos antigos. Nenhum repositório real é apagado por instalar ou iniciar a dashboard.

### Arquivos gerados

- `index.html`: regiões de destaques e catálogo identificadas por comentários `PORTFOLIO`.
- `projects/<nome>/index.html`: páginas individuais estáticas; para privados, apenas título e descrição.
- `assets/generated/projects.json`, `assets/generated/covers/` e `assets/portfolio-covers/`: dados, imagens geradas e SVGs personalizados versionados.
- `scripts/portfolio_labels.json`: definições públicas de tags (nome e cor, sem dados de repositórios); alterações entram no commit ao publicar.
- `sitemap.xml`, `llms.txt` e `profile.json`: atualizados com os projetos incluídos.

O gerador remove páginas e imagens geradas de projetos que deixaram de ser elegíveis. O código-fonte do portfólio, a página de beatbox e os demais assets existentes são preservados.

### Testes

```bash
python3 -m unittest discover -s tests -v
```

Os testes verificam seleção por topic, conflitos, isolamento de repositórios privados, filtragem de HTML e idempotência da geração, usando dados simulados e sem exigir autenticação.

Para detalhes de manutenção, consulte [`.agents/PORTFOLIO.md`](.agents/PORTFOLIO.md).
