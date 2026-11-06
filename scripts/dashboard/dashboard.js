(() => {
  "use strict";

  const token = document.querySelector('meta[name="dashboard-token"]').content;
  const $ = (id) => document.getElementById(id);
  const labels = {hidden: "Oculto do site", primary: "Destaque principal", secondary: "Destaque secundário", catalog: "Somente no catálogo"};
  let repos = [];
  let busy = false;
  let previewReady = false;
  let deleteTarget = null;
  let coverTarget = null;
  let tagsTarget = null;
  let homepageTarget = null;
  let palette = {};

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
    $("notice").hidden = !message;
    $("notice").classList.toggle("error", error);
    $("notice").textContent = message || "";
  }

  function invalidatePreview() {
    previewReady = false;
    $("publish-note").hidden = true;
  }

  function counts() {
    $("count-total").textContent = String(repos.length);
    for (const category of ["primary", "secondary", "catalog"]) {
      $("count-" + category).textContent = String(repos.filter((r) => r.category === category).length);
    }
    $("refresh-btn").disabled = busy;
    $("preview-btn").disabled = busy || repos.length === 0;
    $("publish-btn").disabled = busy || !previewReady;
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
    const desc = make("input", "repo-desc");
    desc.type = "text";
    desc.value = repo.description;
    desc.maxLength = 350;
    desc.placeholder = "Descrição curta do repositório...";
    desc.setAttribute("aria-label", `Descrição de ${repo.name}`);
    desc.disabled = busy;
    desc.addEventListener("change", () => saveDescription(repo, desc.value));
    projectCell.append(title, desc, make("small", "field-hint", "Descrição salva ao sair do campo"));
    if (repo.labels?.length) {
      const tags = make("div", "repo-tags");
      for (const slug of repo.labels) {
        if (!palette[slug]) continue;
        const chip = make("span", "repo-tag", palette[slug].name);
        chip.style.setProperty("--tag-color", palette[slug].color);
        tags.append(chip);
      }
      projectCell.append(tags);
    }

    const privacyCell = make("td");
    privacyCell.append(make("span", "visibility-tag" + (repo.private ? " private" : ""), repo.private ? "Privado" : "Público"));

    const categoryCell = make("td");
    const select = make("select", "category-select");
    select.setAttribute("aria-label", `Classificação de ${repo.name}`);
    if (repo.category === "conflict") {
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
    select.value = repo.category === "conflict" ? "" : repo.category;
    select.disabled = busy;
    select.addEventListener("change", () => saveCategory(repo, select.value));
    categoryCell.append(select);
    if (repo.category === "conflict") categoryCell.append(make("span", "conflict-label", "Mais de uma topic de portfólio"));

    const actionCell = make("td");
    const actions = make("div", "row-actions");
    const cover = make("button", "row-action", "Capa SVG");
    cover.type = "button";
    cover.disabled = busy;
    cover.addEventListener("click", () => openCover(repo));
    const social = make("a", "row-action", "Social Preview ↗");
    social.href = `${repo.url}/settings`;
    social.target = "_blank";
    social.rel = "noopener noreferrer";
    social.title = "O upload da Social Preview é feito nas configurações do GitHub";
    actions.append(cover, social);
    if (!repo.private) {
      const tagButton = make("button", "row-action", "Tags");
      tagButton.type = "button";
      tagButton.disabled = busy;
      tagButton.addEventListener("click", () => openTags(repo));
      const website = make("button", "row-action", "Site do projeto");
      website.type = "button";
      website.disabled = busy;
      website.addEventListener("click", () => openHomepage(repo));
      actions.prepend(tagButton, website);
    }
    if (repo.name.toLowerCase() === "zonaro.github.io") {
      actions.append(make("span", "protected-label", "Exclusão protegida"));
    } else {
      const remove = make("button", "row-action row-action-danger", "Excluir");
      remove.type = "button";
      remove.disabled = busy;
      remove.setAttribute("aria-label", `Excluir definitivamente ${repo.name}`);
      remove.addEventListener("click", () => openDelete(repo));
      actions.append(remove);
    }
    actionCell.append(actions);
    row.append(projectCell, privacyCell, categoryCell, actionCell);
    return row;
  }

  function render() {
    const query = normalize($("search").value.trim());
    const privacy = $("visibility-filter").value;
    const category = $("category-filter").value;
    const filtered = repos.filter((repo) =>
      (!query || normalize(repo.name + " " + repo.description + " " +
        (repo.labels || []).map((slug) => palette[slug]?.name || "").join(" ")).includes(query)) &&
      (privacy === "all" || (privacy === "private") === repo.private) &&
      (category === "all" || repo.category === category));
    $("repo-rows").replaceChildren(...filtered.map(renderRow));
    $("empty-state").hidden = filtered.length > 0;
    $("showing-count").textContent = `Exibindo ${filtered.length} de ${repos.length} repositórios`;
    counts();
  }

  async function loadRepos() {
    if (busy) return;
    busy = true;
    notice("");
    $("loading").hidden = false;
    $("table-shell").hidden = true;
    counts();
    try {
      const data = await api("/api/repos");
      repos = data.repositories;
      palette = data.labels || {};
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

  async function updateField(path, repo, payload, applyResult, success) {
    if (busy) return;
    busy = true;
    render();
    try {
      const result = await api(path, payload);
      applyResult(result);
      previewReady = false;
      $("publish-note").hidden = true;
      notice(`${repo.name}: ${success}`);
    } catch (error) { notice(`${repo.name}: ${error.message}`, true); }
    finally { busy = false; render(); }
  }

  function saveCategory(repo, category) {
    if (!category || category === repo.category) return;
    updateField("/api/classify", repo, {name: repo.name, category, expected_topics: repo.topics},
      (result) => { repo.category = result.category; repo.topics = result.topics; }, "classificação salva automaticamente no GitHub.");
  }

  function saveDescription(repo, description) {
    if (description === repo.description) return;
    updateField("/api/description", repo,
      {name: repo.name, description, expected_description: repo.description},
      (result) => { repo.description = result.description; }, "descrição salva automaticamente no GitHub.");
  }

  function tagsStatus(message, error = false) {
    $("tags-status").textContent = message;
    $("tags-status").classList.toggle("error", error);
  }

  function renderTags() {
    if (!tagsTarget) return;
    const box = $("tags-list");
    box.replaceChildren();
    for (const [slug, label] of Object.entries(palette).sort((a, b) => a[1].name.localeCompare(b[1].name, "pt-BR"))) {
      const item = make("div", "tag-editor-item");
      const check = make("input");
      check.type = "checkbox";
      check.checked = tagsTarget.labels.includes(slug);
      check.setAttribute("aria-label", `Aplicar ${label.name} em ${tagsTarget.name}`);
      check.addEventListener("change", () => assignTags(tagsTarget, slug, check.checked));
      const name = make("input", "tag-name-input");
      name.type = "text";
      name.maxLength = 48;
      name.value = label.name;
      name.setAttribute("aria-label", `Nome da tag ${label.name}`);
      name.addEventListener("change", () => editTag(slug, name.value, color.value));
      const color = make("input", "tag-color-input");
      color.type = "color";
      color.value = label.color;
      color.setAttribute("aria-label", `Cor da tag ${label.name}`);
      color.addEventListener("change", () => editTag(slug, name.value, color.value));
      item.append(check, name, color);
      box.append(item);
    }
    $("tags-empty").hidden = Object.keys(palette).length > 0;
  }

  function openTags(repo) {
    if (busy || repo.private) return;
    tagsTarget = repo;
    $("tags-title").textContent = `Tags · ${repo.name}`;
    tagsStatus("Marque para aplicar. Alterar nome ou cor atualiza a tag em todos os projetos.");
    renderTags();
    $("tags-dialog").showModal();
  }

  async function assignTags(repo, slug, enabled) {
    if (busy) return;
    const selected = new Set(repo.labels || []);
    if (enabled) selected.add(slug); else selected.delete(slug);
    busy = true;
    try {
      const result = await api("/api/assign-labels", {name: repo.name,
        labels: [...selected], expected_topics: repo.topics});
      repo.topics = result.topics;
      repo.labels = result.labels;
      invalidatePreview();
      tagsStatus("Tags salvas automaticamente nas topics do GitHub.");
    } catch (error) { tagsStatus(error.message, true); }
    finally { busy = false; render(); renderTags(); }
  }

  async function editTag(slug, name, color) {
    if (busy) return;
    busy = true;
    try {
      const result = await api("/api/labels", {slug, name, color, expected: palette[slug]});
      palette = result.labels;
      invalidatePreview();
      tagsStatus("Definição da tag salva localmente. Publique o portfólio para atualizar as cores no site.");
    } catch (error) { tagsStatus(error.message, true); }
    finally { busy = false; render(); renderTags(); }
  }

  async function createTag() {
    if (busy || !tagsTarget) return;
    const name = $("new-tag-name").value.trim();
    const color = $("new-tag-color").value;
    if (!name) return tagsStatus("Informe o nome da tag.", true);
    busy = true;
    try {
      const result = await api("/api/labels", {name, color});
      palette = result.labels;
      invalidatePreview();
      const repo = tagsTarget;
      const assigned = await api("/api/assign-labels", {name: repo.name,
        labels: [...repo.labels, result.slug], expected_topics: repo.topics});
      repo.topics = assigned.topics;
      repo.labels = assigned.labels;
      $("new-tag-name").value = "";
      tagsStatus(`Tag ${name} criada e aplicada. Alterações salvas automaticamente.`);
    } catch (error) { tagsStatus(error.message, true); }
    finally { busy = false; render(); renderTags(); }
  }

  function homepageStatus(message, error = false) {
    $("homepage-status").textContent = message;
    $("homepage-status").classList.toggle("error", error);
  }

  async function openHomepage(repo) {
    if (busy || repo.private) return;
    homepageTarget = repo;
    $("homepage-title").textContent = `Site do projeto · ${repo.name}`;
    $("homepage-input").value = "";
    $("homepage-input").disabled = true;
    homepageStatus("Consultando site atual no GitHub...");
    $("homepage-dialog").showModal();
    try {
      const data = await api(`/api/homepage?name=${encodeURIComponent(repo.name)}`);
      if (homepageTarget !== repo) return;
      repo.homepage = data.homepage;
      $("homepage-input").value = data.homepage;
      $("homepage-input").disabled = false;
      homepageStatus("Salva ao sair do campo. Vazio usa o link do repositório como alternativa.");
    } catch (error) { homepageStatus(error.message, true); }
  }

  async function saveHomepage() {
    if (busy || !homepageTarget) return;
    const repo = homepageTarget;
    const newValue = $("homepage-input").value.trim();
    if (newValue === repo.homepage) return;
    busy = true;
    $("homepage-input").disabled = true;
    try {
      const data = await api("/api/homepage", {name: repo.name,
        homepage: newValue, expected_homepage: repo.homepage});
      repo.homepage = data.homepage;
      invalidatePreview();
      homepageStatus("Link salvo automaticamente no GitHub. Gere uma prévia para atualizar o portfólio.");
    } catch (error) { homepageStatus(error.message, true); }
    finally { busy = false; $("homepage-input").disabled = false; render(); }
  }

  function openDelete(repo) {
    if (busy) return;
    deleteTarget = repo;
    const fullName = `zonaro/${repo.name}`;
    $("delete-target").textContent = fullName;
    $("delete-confirmation").value = "";
    $("delete-confirmation").placeholder = fullName;
    $("delete-confirm").disabled = true;
    $("delete-dialog").showModal();
    $("delete-confirmation").focus();
  }

  async function deleteRepo() {
    if (busy || !deleteTarget) return;
    const repo = deleteTarget;
    const confirmation = $("delete-confirmation").value;
    if (confirmation !== `zonaro/${repo.name}`) return;
    $("delete-dialog").close();
    deleteTarget = null;
    busy = true;
    render();
    try {
      await api("/api/delete", {name: repo.name, confirmation,
        expected_topics: repo.topics, expected_private: repo.private});
      repos = repos.filter((r) => r.name !== repo.name);
      previewReady = false;
      $("publish-note").hidden = true;
      notice(`${confirmation} foi excluído do GitHub. Gere uma prévia para removê-lo também do site estático.`);
    } catch (error) { notice(`${repo.name}: ${error.message}`, true); }
    finally { busy = false; render(); }
  }

  function coverStatus(message, error = false) {
    $("cover-status").textContent = message;
    $("cover-status").classList.toggle("error", error);
  }

  function setCover(data) {
    $("cover-source").value = data.svg;
    $("cover-preview").src = "data:image/svg+xml;charset=UTF-8," + encodeURIComponent(data.svg);
    coverStatus(data.custom ? "Capa SVG personalizada no checkout local." : "Capa automática disponível. Personalize se desejar.");
  }

  async function openCover(repo) {
    if (busy) return;
    coverTarget = repo;
    $("cover-title").textContent = `Capa SVG · ${repo.name}`;
    coverStatus("Carregando capa...");
    $("cover-dialog").showModal();
    try {
      const data = await api(`/api/cover?name=${encodeURIComponent(repo.name)}`);
      if (coverTarget !== repo) return;
      $("cover-background").value = data.default_background;
      $("cover-accent").value = data.default_accent;
      $("cover-style").value = "orbits";
      $("cover-icon").value = "auto";
      setCover(data);
    }
    catch (error) { coverStatus(error.message, true); }
  }

  async function saveCover(payload) {
    if (busy || !coverTarget) return;
    const repo = coverTarget;
    busy = true;
    render();
    coverStatus("Salvando capa SVG no checkout local...");
    try {
      const data = await api("/api/cover", {name: repo.name, ...payload});
      setCover(data);
      coverStatus("Capa SVG salva automaticamente. Gere e publique uma prévia para atualizar o site.");
      previewReady = false;
      $("publish-note").hidden = true;
    } catch (error) { coverStatus(error.message, true); }
    finally { busy = false; render(); }
  }

  function saveCoverPreset() {
    saveCover({mode: "preset", style: $("cover-style").value, icon: $("cover-icon").value,
      background: $("cover-background").value, accent: $("cover-accent").value});
  }

  async function workflow(path, payload) {
    if (busy) return;
    busy = true;
    render();
    const log = $("publish-note");
    log.hidden = false;
    log.textContent = "Executando localmente...";
    try {
      const result = await api(path, payload);
      log.textContent = result.summary || result.message || "Operação concluída.";
      previewReady = path === "/api/preview";
      notice(previewReady ? "Prévia local gerada; revise as alterações antes de publicar." : "Commit e push enviados ao GitHub.");
    } catch (error) {
      log.textContent = error.message;
      if (path === "/api/preview") previewReady = false;
      notice(error.message, true);
    } finally { busy = false; render(); }
  }

  $("search").addEventListener("input", render);
  $("visibility-filter").addEventListener("change", render);
  $("category-filter").addEventListener("change", render);
  $("refresh-btn").addEventListener("click", loadRepos);
  $("preview-btn").addEventListener("click", () => workflow("/api/preview", {}));
  $("publish-btn").addEventListener("click", () => {
    if (prompt("Para publicar o resultado no site, digite PUBLICAR:") !== "PUBLICAR") return;
    workflow("/api/publish", {confirm: "PUBLICAR"});
  });

  $("delete-confirmation").addEventListener("input", () => {
    $("delete-confirm").disabled = !deleteTarget || $("delete-confirmation").value !== `zonaro/${deleteTarget.name}`;
  });
  $("delete-cancel").addEventListener("click", () => $("delete-dialog").close());
  $("delete-dialog").addEventListener("close", () => { deleteTarget = null; });
  $("delete-confirm").addEventListener("click", deleteRepo);

  $("cover-close").addEventListener("click", () => $("cover-dialog").close());
  $("cover-dialog").addEventListener("close", () => { coverTarget = null; });
  for (const id of ["cover-style", "cover-icon", "cover-background", "cover-accent"]) {
    $(id).addEventListener("change", saveCoverPreset);
  }
  $("cover-source").addEventListener("change", () => saveCover({mode: "svg", svg: $("cover-source").value}));
  $("cover-source").addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      saveCover({mode: "svg", svg: $("cover-source").value});
    }
  });
  $("cover-upload").addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 100_000) coverStatus("O SVG deve ter no máximo 100 KB.", true);
    else saveCover({mode: "svg", svg: await file.text()});
    event.target.value = "";
  });
  $("tags-close").addEventListener("click", () => $("tags-dialog").close());
  $("tags-dialog").addEventListener("close", () => { tagsTarget = null; });
  $("create-tag").addEventListener("click", createTag);
  $("new-tag-name").addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); createTag(); }
  });
  $("homepage-close").addEventListener("click", () => $("homepage-dialog").close());
  $("homepage-dialog").addEventListener("close", () => { homepageTarget = null; });
  $("homepage-input").addEventListener("change", saveHomepage);
  loadRepos();
})();
