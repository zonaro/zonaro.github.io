(() => {
  "use strict";

  const year = String(new Date().getFullYear());
  document.querySelectorAll("[data-year]").forEach((element) => {
    element.textContent = year;
  });

  const search = document.querySelector("#repo-search");
  const list = document.querySelector("#repo-list");
  const count = document.querySelector("#repo-count");

  if (search && list && count) {
    const items = [...list.querySelectorAll("li")];
    const normalize = (value) =>
      value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("pt-BR");

    search.addEventListener("input", () => {
      const query = normalize(search.value.trim());
      let visible = 0;
      for (const item of items) {
        const matches = normalize(item.textContent).includes(query);
        item.hidden = !matches;
        if (matches) visible++;
      }
      count.textContent = String(visible);
    });
  }
})();