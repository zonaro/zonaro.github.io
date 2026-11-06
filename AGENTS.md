# Orientações para agentes — zonaro.github.io

- Este repositório é público e publica em `https://zonaro.github.io/` pela branch `main`.
- Preserve a identidade RedClaw, o conteúdo da área `/beatbox/` e os metadados de SEO.
- A curadoria de projetos vem exclusivamente das repository topics `portfolio-primary`, `portfolio-secondary`, `portfolio-catalog`.
- Nunca inclua repositórios sem exatamente uma dessas topics. Não reaproveite a lista antiga de 45 itens como fallback.
- Para repositórios privados, o gerador só pode ler e publicar **nome e descrição**. `isPrivate` e topics são consultados apenas para decidir a inclusão. **Jamais chamar endpoints de README, conteúdo, código, Social Preview ou informações extras para privados.**
- As tags de apresentação (`portfolio-label-<slug>`) são atribuídas via topics somente aos públicos. `scripts/portfolio_labels.json` deve conter apenas nome/cor das tags, sem associações com repositórios privados/ocultos. Nunca publicar tags de repositórios privados.
- O link `homepage` pode ser consultado e editado somente para repositórios confirmados públicos; priorizá-lo como link externo no portfólio, com GitHub como fallback e sem eliminar páginas de detalhe.
- Mantenha arquivos gerados em `projects/` e `assets/generated/`; o script nunca deve precisar de credenciais no browser ou no GitHub Pages.
- Mudanças no gerador exigem testes offline: `python3 -m unittest discover -s tests -v`.
- Nunca execute `--publish` sem revisar os projetos selecionados e os dados privados. Não publique automaticamente a primeira migração.
- `scripts/portfolio_dashboard.py` é uma API **exclusivamente local**. Não altere o bind de `127.0.0.1`, a validação de origem/token ou a política de não ler README de privados.
- Ao editar topics pelo painel, preserve todas as topics que não pertençam ao conjunto de classificação, e recuse alterações concorrentes em vez de sobrescrever sem aviso.
- A exclusão de repositórios no painel é destrutiva: exigir confirmação exata `zonaro/<repo>`, nova verificação de permissões/identidade e proteger `zonaro.github.io`. Nunca executar exclusão real durante os testes.
- Capas SVG enviadas ou editadas precisam passar pelo sanitizador. Não permitir scripts, CSS, recursos externos ou links em SVG. Capas privadas são arte local criada apenas com o nome do projeto, nunca imagens obtidas do GitHub privado.
- Leia `.agents/PORTFOLIO.md` antes de modificar o gerador ou o formato das páginas.
