# Gerador de portfólio — decisões e manutenção

## Objetivo

Gerar `zonaro.github.io` estaticamente na máquina do Zonaro (Fedora) usando a sessão local do GitHub CLI. Não usar credenciais no build do Pages nem depender de uma pasta `.redclaw` nos repositórios.

## Política de inclusão

Topics mutuamente exclusivas: `portfolio-primary`, `portfolio-secondary`, `portfolio-catalog`. Uma delas autoriza a publicação; sem ela, projeto ignorado. Conflitos geram aviso e impedem a publicação até correção. `portfolio-hidden` e `portfolio-private-ok` não são necessários.

## Política de leitura

1. `gh repo list zonaro --limit 1000 --json name,nameWithOwner,description,isPrivate,repositoryTopics` lista os repositórios da conta, inclusive privados acessíveis.
2. O gerador seleciona apenas os repositórios com uma das três topics, e rejeita conflitos.
3. Para privados, interrompe a leitura nesse ponto. Nome e descrição tornam-se públicos; nada mais é coletado. Não consultar endpoints específicos de repositórios privados.
4. Para públicos, `gh repo view --json ...` obtém imagem Open Graph, linguagem, links e branch. `gh api repos/OWNER/REPO/readme` com Accept HTML obtém o README renderizado.
5. README HTML é filtrado por allowlist, links relativos ajustados. Social Preview só é copiada de hosts confiáveis e quando for personalizada. Sem Social Preview, uma capa SVG local é escolhida: `assets/portfolio-covers/<slug>.svg` quando personalizada, ou `assets/generated/covers/<slug>.svg` gerada a partir do nome.
6. Para privados, nenhum endpoint adicional é consultado. As capas SVG locais não são lidas do repositório privado e devem usar somente o nome público autorizado.

## Geração e publicação

- A página inicial contém marcadores `PORTFOLIO:SHOWCASE` e `PORTFOLIO:CATALOG`. Apenas o conteúdo entre esses marcadores é substituído.
- `projects/<slug>/index.html` cria páginas estáticas de detalhe. Privados têm somente nome e descrição, sem link para o repositório.
- `assets/generated/projects.json` contém somente informações autorizadas. `sitemap.xml`, `llms.txt`, `profile.json` seguem a mesma seleção.
- A geração remove páginas e capas automáticas obsoletas, sem apagar artes SVG personalizadas. Execuções sucessivas com os mesmos dados devem produzir arquivos idênticos.
- `scripts/update-portfolio.sh` controla prévia, confirmação e publicação. Para `--publish`, exige `main` sem modificações fora dos arquivos gerados e dos SVGs personalizados, adiciona somente capas de projetos listados no JSON gerado e faz um único commit. SVGs de ocultos são ignorados pelo Git e permanecem locais; SVGs previamente publicados deixam o índice ao ocultar o projeto, sem apagar o arquivo local.
- Recomendação: primeiro rodar `--dry-run`, depois geração local e revisão; só então publicar. Automação via `systemd --user` pode ser adicionada futuramente se solicitada.

## Dashboard local

- Inicialização: `./scripts/portfolio-dashboard.sh`, com sessão `gh` válida. Página servida apenas em `http://127.0.0.1:8765/`.
- Backend stdlib: `scripts/portfolio_dashboard.py`; frontend: `scripts/dashboard/`. Nenhum token é persistido em arquivos ou enviado ao site público.
- GET `/api/repos` consulta apenas nome, descrição, visibilidade e topics de cada repo (nunca README), com token de sessão. POST `/api/classify` exige token, Origin local, JSON e comparação das topics esperadas com as atuais; altera apenas `portfolio-*` de classificação e preserva as demais.
- POST `/api/description` salva a descrição curta usando `gh repo edit --description`, após verificar o valor original na API. Alteração de select e saída do campo de texto disparam salvamento automático; não há botões de salvar.
- GET/POST `/api/cover` lê/cria somente SVGs locais no repositório do portfólio. Estilos e upload usam `scripts/portfolio_art.py`, que rejeita scripts, CSS, referências externas e atributos não autorizados; a imagem não é enviada para Social Preview do GitHub. Para editar Social Preview, a UI oferece link para Settings, pois não há API pública de upload.
- POST `/api/delete` exige confirmação exata `zonaro/<repo>` e verifica nome, ownership, permissões administrativas, topics e visibilidade antes de chamar `gh repo delete <repo> --yes`. O próprio `zonaro.github.io` não pode ser excluído por essa ferramenta. A permissão `delete_repo` pode precisar ser habilitada com `gh auth refresh -s delete_repo`.
- POST `/api/preview` gera os arquivos localmente. POST `/api/publish` exige prévia na sessão e confirmação `PUBLICAR`, depois chama `update-portfolio.sh --publish --yes`.
- A UI tem busca, filtros, ações por repositório e modais para edição de SVG e exclusão. Nenhum repositório é excluído quando o servidor inicia.
- Segurança: bind `127.0.0.1`, Host allowlist, sem CORS, token anti-CSRF e CSP. Não disponibilizar o backend em hospedagem pública.

## Segurança e limitações

- A topic em um repo privado **é consentimento para tornar nome e descrição públicos**. O README privado nunca é lido, nem para resumir.
- O script não clona todos os repositórios, não lê segredos, não usa PAT no Pages e não chama APIs com credenciais no navegador do visitante.
- O HTML público pode conter trechos técnicos de README; a limpeza é deliberadamente restritiva e talvez não reproduza toda a formatação específica do GitHub.
- Conflitos de topic ou falhas importantes na consulta retornam erro e bloqueiam o push.
- A página de beatbox é editorial e permanece intacta.

## Testes

`python3 -m unittest discover -s tests -v` roda sem rede. Os testes usam um repositório público, um privado classificado, dois ocultos e um conflitante para garantir que privados nunca provoquem chamadas de README nem de imagens.
