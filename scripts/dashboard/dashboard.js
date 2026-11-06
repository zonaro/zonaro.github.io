(() => {
  "use strict";

  const token = document.querySelector('meta[name="dashboard-token"]').content;
  const $ = (id) => document.getElementById(id);
  const labels = {hidden: "Oculto do site", primary: "Destaque principal", secondary: "Destaque secundário", catalog: "Somente no catálogo"};
  let repos = [];
  let busy = false;
  let previewReady = false;
  const pending = new Map();

  const normalize = (value) => String(value ?? "").normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("pt-BR");

  async function api(path, data) {
    const request = {headers: {"X-Dashboard-Token": token}};
    if (data !== undefined) {
      request.method = "POST";
      request.headers["Content-Type"] = "application/json";
      request.body = JSON.stringify(data);
    }
    const response = await fetch(path, request);
    let result;
    try { result = await response.json(); } catch { throw new Error("Resposta inválida do servidor local."); }
    if (!response.ok) throw new Error(result.error || `Erro HTTP ${response.status}`);
    return result;
  }

  function notice(message, error = false) {
    const el = $("notice");
    el.hidden = !message;
    el.classList.toggle("error", error);
    el.textContent = message || "";
  }

  function effectiveCategory(repo) { return pending.get(repo.name) ?? repo.category; }

  function counts() {
    $("count-total").textContent = String(repos.length);
    for (const category of ["primary", "secondary", "catalog"]) {
      $("count-" + category).textContent = String(repos.filter((r) => effectiveCategory(r) === category).length);
    }
    $("unsaved-count").textContent = `${pending.size} alterações pendentes`;
    $("unsaved-count").hidden = pending.size === 0;
    $("save-all-count").textContent = `(${pending.size})`;
    $("save-all-btn").disabled = pending.size === 0 || busy;
    $("refresh-btn").disabled = busy;
    $("preview-btn").disabled = busy || pending.size > 0 || repos.length === 0;
    $("publish-btn").disabled = busy || !previewReady || pending.size > 0;
  }

  function make(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function renderRow(repo) {
    const row = make("tr");
    const projectCell = make("td");
    const title = make("div", "repo-name");
    const link = make("a", null, repo.name);
    link.href = repo.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    title.append(link);
    projectCell.append(title, make("div", "repo-desc", repo.description || "Sem descrição"));

    const privacyCell = make("td");
    privacyCell.append(make("span", "visibility-tag" + (repo.private ? " private" : ""), repo.private ? "Privado" : "Público"));

    const categoryCell = make("td");
    const select = make("select", "category-select");
    select.setAttribute("aria-label", `Classificação de ${repo.name}`);
    if (repo.category === "conflict" && !pending.has(repo.name)) {
      const placeholder = make("option", null, "Corrigir conflito");
      placeholder.value = "";
      placeholder.disabled = true;
      select.append(placeholder);
    }
    for (const [value, label] of Object.entries(labels)) {
      const option = make("option", null, label);
      option.value = value;
      select.append(option);
    }
    select.value = pending.get(repo.name) ?? (repo.category === "conflict" ? "" : repo.category);
    select.disabled = busy;
    select.classList.toggle("dirty", pending.has(repo.name));
    categoryCell.append(select);
    if (repo.category === "conflict") categoryCell.append(make("span", "conflict-label", "Mais de uma topic de portfólio"));

    const actionCell = make("td");
    const save = make("button", "save-row", "Salvar");
    save.type = "button";
    save.disabled = busy || !pending.has(repo.name);
    save.classList.toggle("ready", pending.has(repo.name));
    actionCell.append(save);

    select.addEventListener("change", () => {
      if (select.value === repo.category) pending.delete(repo.name);
      else pending.set(repo.name, select.value);
      previewReady = false;
      $("publish-note").hidden = true;
      render();
    });
    save.addEventListener("click", () => saveRepo(repo));
    row.append(projectCell, privacyCell, categoryCell, actionCell);
    return row;
  }

  function render() {
    const query = normalize($("search").value.trim());
    const privacy = $("visibility-filter").value;
    const category = $("category-filter").value;
    const filtered = repos.filter((repo) =>
      (!query || normalize(repo.name + " " + repo.description).includes(query)) &&
      (privacy === "all" || (privacy === "private") === repo.private) &&
      (category === "all" || effectiveCategory(repo) === category));
    const body = $("repo-rows");
    body.replaceChildren(...filtered.map(renderRow));
    $("empty-state").hidden = filtered.length > 0;
    $("showing-count").textContent = `Exibindo ${filtered.length} de ${repos.length} repositórios`;
    counts();
  }

  async function loadRepos() {
    if (busy) return;
    if (pending.size && !confirm("Descartar alterações ainda não salvas e atualizar do GitHub?")) return;
    busy = true;
    notice("");
    $("loading").hidden = false;
    $("table-shell").hidden = true;
    counts();
    try {
      const data = await api("/api/repos");
      repos = data.repositories;
      pending.clear();
      previewReady = false;
      $("publish-note").hidden = true;
    } catch (error) { notice(error.message, true); }
    finally {
      busy = false;
      $("loading").hidden = true;
      $("table-shell").hidden = false;
      render();
    }
  }

  async function saveRepo(repo) {
    if (busy || !pending.has(repo.name)) return;
    busy = true;
    counts();
    try {
      const result = await api("/api/classify", {
        name: repo.name, category: pending.get(repo.name), expected_topics: repo.topics,
      });
      repo.category = result.category;
      repo.topics = result.topics;
      pending.delete(repo.name);
      previewReady = false;
      notice(`${repo.name}: classificação salva no GitHub.`);
    } catch (error) { notice(`${repo.name}: ${error.message}`, true); }
    finally { busy = false; render(); }
  }

  async function saveAll() {
    if (busy || !pending.size) return;
    const targets = repos.filter((repo) => pending.has(repo.name));
    let saved = 0;
    let failed = 0;
    const errors = [];
    for (const repo of targets) {
      if (!pending.has(repo.name)) continue;
      busy = true;
      counts();
      try {
        const result = await api("/api/classify", {
          name: repo.name, category: pending.get(repo.name), expected_topics: repo.topics,
        });
        repo.category = result.category;
        repo.topics = result.topics;
        pending.delete(repo.name);
        saved++;
      } catch (error) { failed++; errors.push(`${repo.name}: ${error.message}`); }
    }
    busy = false;
    previewReady = false;
    notice(`${saved} salvos no GitHub${failed ? `; ${failed} falharam: ${errors.join(" | ")}` : "."}`, failed > 0);
    render();
  }

  async function workflow(path, payload) {
    if (busy || pending.size) return;
    busy = true;
    counts();
    const log = $("publish-note");
    log.hidden = false;
    log.textContent = "Executando localmente...";
    try {
      const result = await api(path, payload);
      log.textContent = result.summary || result.message || "Operação concluída.";
      if (path === "/api/preview") previewReady = true;
      else previewReady = false;
      notice(path === "/api/preview" ? "Prévia local gerada; revise as alterações antes de publicar." : "Commit e push enviados ao GitHub.");
    } catch (error) {
      log.textContent = error.message;
      if (path === "/api/preview") previewReady = false;
      notice(error.message, true);
    } finally { busy = false; counts(); }
  }

  $("search").addEventListener("input", render);
  $("visibility-filter").addEventListener("change", render);
  $("category-filter").addEventListener("change", render);
  $("refresh-btn").addEventListener("click", loadRepos);
  $("save-all-btn").addEventListener("click", saveAll);
  $("preview-btn").addEventListener("click", () => workflow("/api/preview", {}));
  $("publish-btn").addEventListener("click", () => {
    if (prompt("Para publicar o resultado no site, digite PUBLICAR:") !== "PUBLICAR") return;
    workflow("/api/publish", {confirm: "PUBLICAR"});
  });
  loadRepos();
})();
