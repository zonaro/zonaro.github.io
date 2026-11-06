# Orientações para agentes — zonaro.github.io

- Este repositório é público e publica em `https://zonaro.github.io/` pela branch `main`.
- Preserve a identidade RedClaw, o conteúdo da área `/beatbox/` e os metadados de SEO.
- A curadoria de projetos vem exclusivamente das repository topics `portfolio-primary`, `portfolio-secondary`, `portfolio-catalog`.
- Nunca inclua repositórios sem exatamente uma dessas topics. Não reaproveite a lista antiga de 45 itens como fallback.
- Para repositórios privados, o gerador só pode ler e publicar **nome e descrição**. `isPrivate` e topics são consultados apenas para decidir a inclusão. **Jamais chamar endpoints de README, conteúdo, código, Social Preview ou informações extras para privados.**
- Mantenha arquivos gerados em `projects/` e `assets/generated/`; o script nunca deve precisar de credenciais no browser ou no GitHub Pages.
- Mudanças no gerador exigem testes offline: `python3 -m unittest discover -s tests -v`.
- Nunca execute `--publish` sem revisar os projetos selecionados e os dados privados. Não publique automaticamente a primeira migração.
- Leia `.agents/PORTFOLIO.md` antes de modificar o gerador ou o formato das páginas.
