(() => {
  "use strict";

  const sectors = [
    { value: "Jardim", label: "Jardim", icon: "🌿", theme: "garden" },
    { value: "area jardim", label: "Área Jardim", icon: "🌱", theme: "leaf" },
    { value: "Hall de Entrada", label: "Hall de Entrada", icon: "🚪", theme: "entry" },
    { value: "Hall do auditorio/Bloco A", label: "Hall do Auditório / Bloco A", icon: "🏛️", theme: "hall" },
    { value: "Refeitorio", label: "Refeitório", icon: "🍽️", theme: "dining" },
    { value: "biblioteca", label: "Biblioteca", icon: "📚", theme: "library" },
    { value: "area externa", label: "Área Externa", icon: "☀️", theme: "outside" },
    { value: "porta sala de aula", label: "Porta da Sala de Aula", icon: "🚪", theme: "classroom" }
  ];

  const sectorByValue = new Map(sectors.map((sector) => [sector.value, sector]));
  const statusOrder = ["pendente", "andamento", "concluida"];
  const statusDetails = {
    pendente: { label: "Pendente", mark: "○" },
    andamento: { label: "Em andamento", mark: "◌" },
    concluida: { label: "Concluída", mark: "✓" }
  };

  const grid = document.getElementById("sectors-grid");
  const boardMessage = document.getElementById("board-message");
  const searchInput = document.getElementById("search-input");
  const progressText = document.getElementById("progress-text");
  const progressBar = document.getElementById("progress-bar");
  const progressTrack = document.getElementById("progress-track");
  const ideaDialog = document.getElementById("idea-dialog");
  const ideaForm = document.getElementById("idea-form");
  const wordCloudDialog = document.getElementById("word-cloud-dialog");
  const wordCloud = document.getElementById("word-cloud");
  const wordForm = document.getElementById("word-form");
  const wordInput = document.getElementById("word-input");
  const toast = document.getElementById("toast");
  const activityDialog = document.getElementById("activity-dialog");
  const activityList = document.getElementById("activity-list");
  const activityMessage = document.getElementById("activity-message");

  let ideas = [];
  let currentFilter = "all";
  let toastTimer = null;
  let previewWords = ["Paz", "União", "Alegria", "Esperança", "Amor", "Luz", "Boas Festas", "Gratidão", "Magia", "Família"];

  function normalize(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase("pt-BR");
  }

  function element(tagName, className, text) {
    const node = document.createElement(tagName);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function setBoardMessage(message, visible) {
    boardMessage.textContent = message;
    boardMessage.classList.toggle("is-visible", visible);
  }

  function showToast(message) {
    window.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.hidden = false;
    toast.classList.add("is-visible");
    toastTimer = window.setTimeout(() => {
      toast.classList.remove("is-visible");
      window.setTimeout(() => {
        toast.hidden = true;
      }, 190);
    }, 2800);
  }

  async function requestJson(url, options) {
    const requestOptions = { ...options };
    const method = (requestOptions.method || "GET").toUpperCase();
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      const headers = new Headers(requestOptions.headers || {});
      headers.set("X-CSRFToken", document.querySelector('meta[name="csrf-token"]').content);
      requestOptions.headers = headers;
    }
    const response = await fetch(url, requestOptions);
    if (!response.ok) {
      throw new Error("A solicitação falhou (" + response.status + ").");
    }
    if (response.status === 204) return null;
    return response.json();
  }

  function createIdeaRow(idea) {
    const row = element("li", "idea-row");
    const details = statusDetails[idea.status] || statusDetails.pendente;

    const statusButton = element("button", "idea-status idea-status--" + (statusDetails[idea.status] ? idea.status : "pendente"));
    statusButton.type = "button";
    statusButton.dataset.action = "cycle-status";
    statusButton.dataset.ideaId = String(idea.id);
    statusButton.setAttribute("aria-label", "Alterar status de " + idea.idea + ". Status atual: " + details.label + ".");
    statusButton.title = "Avançar status: " + details.label;

    const mark = element("span", "idea-status__mark", details.mark);
    mark.setAttribute("aria-hidden", "true");
    statusButton.append(mark);

    const text = element("span", "idea-text", idea.idea);
    if (idea.status === "concluida") text.classList.add("is-complete");

    const completionButton = element(
      "button",
      "complete-action" + (idea.status === "concluida" ? " complete-action--reopen" : ""),
      idea.status === "concluida" ? "Reabrir" : "Concluir"
    );
    completionButton.type = "button";
    completionButton.dataset.action = "toggle-complete";
    completionButton.dataset.ideaId = String(idea.id);
    completionButton.setAttribute(
      "aria-label",
      (idea.status === "concluida" ? "Reabrir ideia: " : "Marcar como concluída: ") + idea.idea
    );

    const deleteButton = element("button", "delete-idea", "×");
    deleteButton.type = "button";
    deleteButton.dataset.action = "delete-idea";
    deleteButton.dataset.ideaId = String(idea.id);
    deleteButton.setAttribute("aria-label", "Excluir ideia: " + idea.idea);
    deleteButton.title = "Excluir ideia";

    row.append(statusButton, text, completionButton, deleteButton);
    return row;
  }

  function createSectorCard(sectorName, sectorIdeas, visibleIdeas) {
    const config = sectorByValue.get(sectorName);
    const label = config ? config.label : sectorName;
    const card = element("article", "sector-card" + (config ? " sector-card--" + config.theme : ""));
    const pin = element("span", "sector-pin");
    pin.setAttribute("aria-hidden", "true");

    const heading = element("header", "sector-heading");
    const title = element("h2");
    const icon = element("span", "sector-heading__icon", config ? config.icon : "📌");
    icon.setAttribute("aria-hidden", "true");
    const titleText = element("span", "", label);
    title.append(icon, titleText);

    const completed = sectorIdeas.filter((idea) => idea.status === "concluida").length;
    const count = element("span", "sector-count", completed + "/" + sectorIdeas.length + " feitas");
    count.setAttribute("aria-label", completed + " de " + sectorIdeas.length + " ideias concluídas");
    heading.append(title, count);

    const list = element("ul", "idea-list");
    visibleIdeas.forEach((idea) => list.append(createIdeaRow(idea)));

    const footer = element("footer", "sector-footer");
    footer.append(element("span", "", "Clique no círculo para avançar o status"));
    if (sectorName === "Refeitorio") {
      const previewButton = element("button", "", "Prévia da nuvem");
      previewButton.type = "button";
      previewButton.dataset.action = "word-cloud";
      previewButton.setAttribute("aria-haspopup", "dialog");
      footer.append(previewButton);
    }

    card.append(pin, heading, list, footer);
    return card;
  }

  function updateProgress() {
    const total = ideas.length;
    const completed = ideas.filter((idea) => idea.status === "concluida").length;
    const percent = total ? Math.round((completed / total) * 100) : 0;
    progressText.textContent = percent + "% · " + completed + "/" + total + " concluídas";
    progressBar.style.width = percent + "%";
    progressTrack.setAttribute("aria-valuenow", String(percent));
  }

  function renderDashboard() {
    grid.replaceChildren();
    updateProgress();

    const groups = new Map();
    ideas.forEach((idea) => {
      const key = idea.sector || "Outros";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(idea);
    });

    const orderedSectors = sectors
      .map((sector) => sector.value)
      .filter((sectorName) => groups.has(sectorName));
    groups.forEach((_items, sectorName) => {
      if (!sectorByValue.has(sectorName)) orderedSectors.push(sectorName);
    });

    const query = normalize(searchInput.value.trim());
    let visibleCardCount = 0;

    orderedSectors.forEach((sectorName) => {
      const sectorIdeas = groups.get(sectorName) || [];
      const visibleIdeas = sectorIdeas.filter((idea) => {
        const matchesStatus = currentFilter === "all" || idea.status === currentFilter;
        const matchesText = !query ||
          normalize(sectorName).includes(query) ||
          normalize(idea.idea).includes(query);
        return matchesStatus && matchesText;
      });

      if (!visibleIdeas.length) return;
      grid.append(createSectorCard(sectorName, sectorIdeas, visibleIdeas));
      visibleCardCount += 1;
    });

    grid.setAttribute("aria-busy", "false");
    if (visibleCardCount) {
      setBoardMessage("", false);
    } else if (!ideas.length) {
      setBoardMessage("A lousa ainda está vazia. Adicione a primeira ideia usando o botão acima.", true);
    } else {
      setBoardMessage("Nenhuma ideia corresponde à busca ou ao filtro escolhido.", true);
    }
  }

  async function loadIdeas() {
    grid.setAttribute("aria-busy", "true");
    setBoardMessage("Carregando ideias…", true);
    try {
      const data = await requestJson("/api/ideas");
      ideas = Array.isArray(data) ? data : [];
      renderDashboard();
    } catch (error) {
      console.error("Erro ao carregar ideias:", error);
      setBoardMessage("Não consegui carregar as ideias. Confira se o servidor da aplicação está rodando e tente novamente.", true);
      const retry = element("button", "button button--quiet", "Tentar novamente");
      retry.type = "button";
      retry.addEventListener("click", loadIdeas);
      boardMessage.append(" ", retry);
    } finally {
      grid.setAttribute("aria-busy", "false");
    }
  }

  async function updateStatus(ideaId) {
    const idea = ideas.find((item) => Number(item.id) === Number(ideaId));
    if (!idea) return;
    const currentIndex = statusOrder.indexOf(idea.status);
    const nextStatus = statusOrder[(currentIndex + 1 + statusOrder.length) % statusOrder.length];

    try {
      await requestJson("/api/ideas/" + encodeURIComponent(ideaId), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus })
      });
      await loadIdeas();
      const nextLabel = statusDetails[nextStatus].label.toLocaleLowerCase("pt-BR");
      showToast("Ideia marcada como " + nextLabel + ".");
    } catch (error) {
      console.error("Erro ao atualizar ideia:", error);
      showToast("Não foi possível atualizar o status.");
    }
  }

  async function toggleCompletion(ideaId) {
    const idea = ideas.find((item) => Number(item.id) === Number(ideaId));
    if (!idea) return;
    const nextStatus = idea.status === "concluida" ? "pendente" : "concluida";

    try {
      await requestJson("/api/ideas/" + encodeURIComponent(ideaId), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus })
      });
      await loadIdeas();
      showToast(nextStatus === "concluida" ? "Ideia concluída." : "Ideia reaberta como pendente.");
    } catch (error) {
      console.error("Erro ao alterar conclusão da ideia:", error);
      showToast("Não foi possível alterar a conclusão.");
    }
  }

  function describeActivity(entry) {
    if (entry.action === "created") return "adicionou a ideia";
    if (entry.action === "deleted") return "removeu a ideia";
    if (entry.action === "status_changed") {
      const from = statusDetails[entry.from_status]?.label || entry.from_status || "sem status";
      const to = statusDetails[entry.to_status]?.label || entry.to_status || "sem status";
      return "alterou o status de " + from + " para " + to;
    }
    return "alterou a ideia";
  }

  function formatActivityTime(timestamp) {
    const date = new Date(Number(timestamp) * 1000);
    if (Number.isNaN(date.getTime())) return "Horário indisponível";
    return new Intl.DateTimeFormat("pt-BR", {
      dateStyle: "short",
      timeStyle: "short"
    }).format(date);
  }

  async function loadActivity() {
    if (!activityList || !activityMessage) return;
    activityList.replaceChildren();
    activityMessage.textContent = "Carregando histórico…";
    activityMessage.hidden = false;
    try {
      const entries = await requestJson("/api/activity");
      if (!Array.isArray(entries) || entries.length === 0) {
        activityMessage.textContent = "Ainda não há ações registradas.";
        return;
      }
      entries.forEach((entry) => {
        const item = element("li", "activity-entry");
        const heading = element("div", "activity-entry__heading");
        heading.append(
          element("strong", "activity-entry__actor", entry.actor_email),
          element("span", "activity-entry__action", describeActivity(entry))
        );
        const subject = element("p", "activity-entry__subject", entry.idea);
        const context = element("div", "activity-entry__context");
        context.append(
          element("span", "", entry.sector),
          element("span", "activity-entry__ip", entry.client_ip || "IP não registrado"),
          element("time", "", formatActivityTime(entry.created_at))
        );
        item.append(heading, subject, context);
        activityList.append(item);
      });
      activityMessage.hidden = true;
    } catch (error) {
      console.error("Erro ao carregar histórico:", error);
      activityMessage.textContent = "Não foi possível carregar o histórico.";
      const retryButton = element("button", "button button--quiet", "Tentar novamente");
      retryButton.type = "button";
      retryButton.addEventListener("click", loadActivity, { once: true });
      activityMessage.append(" ", retryButton);
    }
  }

  async function deleteIdea(ideaId) {
    const idea = ideas.find((item) => Number(item.id) === Number(ideaId));
    if (!idea || !window.confirm("Remover esta ideia da lousa?")) return;

    try {
      await requestJson("/api/ideas/" + encodeURIComponent(ideaId), { method: "DELETE" });
      await loadIdeas();
      showToast("Ideia removida da lousa.");
    } catch (error) {
      console.error("Erro ao excluir ideia:", error);
      showToast("Não foi possível remover a ideia.");
    }
  }

  function openIdeaDialog() {
    if (!ideaDialog.open) ideaDialog.showModal();
    document.getElementById("new-sector").focus();
  }

  function renderWordCloud() {
    wordCloud.replaceChildren();
    previewWords.forEach((word) => {
      const span = element("span", "word-cloud__word", word);
      wordCloud.append(span);
    });
  }

  function openWordCloudDialog() {
    renderWordCloud();
    if (!wordCloudDialog.open) wordCloudDialog.showModal();
    wordInput.focus();
  }

  document.getElementById("add-idea-button").addEventListener("click", openIdeaDialog);

  const activityButton = document.getElementById("activity-button");
  if (activityButton && activityDialog) {
    activityButton.addEventListener("click", () => {
      if (!activityDialog.open) activityDialog.showModal();
      loadActivity();
    });
  }

  document.querySelectorAll("[data-close-dialog]").forEach((button) => {
    button.addEventListener("click", () => {
      const dialog = document.getElementById(button.dataset.closeDialog);
      if (dialog && dialog.open) dialog.close();
    });
  });

  [ideaDialog, wordCloudDialog, activityDialog].filter(Boolean).forEach((dialog) => {
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
  });

  document.querySelectorAll(".filter-button").forEach((button) => {
    button.addEventListener("click", () => {
      currentFilter = button.dataset.filter || "all";
      document.querySelectorAll(".filter-button").forEach((filterButton) => {
        const active = filterButton === button;
        filterButton.classList.toggle("is-active", active);
        filterButton.setAttribute("aria-pressed", String(active));
      });
      renderDashboard();
    });
  });

  searchInput.addEventListener("input", renderDashboard);
  window.addEventListener("keydown", (event) => {
    const tagName = event.target && event.target.tagName;
    const isTyping = ["INPUT", "TEXTAREA", "SELECT"].includes(tagName) ||
      (event.target && event.target.isContentEditable);
    if (event.key === "/" && !isTyping && !ideaDialog.open && !wordCloudDialog.open &&
        !(activityDialog && activityDialog.open)) {
      event.preventDefault();
      searchInput.focus();
    }
  });

  grid.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const action = button.dataset.action;
    if (action === "cycle-status") updateStatus(button.dataset.ideaId);
    if (action === "toggle-complete") toggleCompletion(button.dataset.ideaId);
    if (action === "delete-idea") deleteIdea(button.dataset.ideaId);
    if (action === "word-cloud") openWordCloudDialog();
  });

  ideaForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const sector = document.getElementById("new-sector").value;
    const idea = document.getElementById("new-idea").value.trim();
    if (!sector || !idea) return;

    try {
      await requestJson("/api/ideas", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sector, idea })
      });
      ideaForm.reset();
      ideaDialog.close();
      await loadIdeas();
      showToast("Nova ideia fixada na lousa.");
    } catch (error) {
      console.error("Erro ao adicionar ideia:", error);
      showToast("Não foi possível salvar a ideia.");
    }
  });

  wordForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const word = wordInput.value.trim();
    if (!word) return;
    previewWords.push(word);
    wordInput.value = "";
    renderWordCloud();
    wordInput.focus();
    showToast("Palavra adicionada à prévia local.");
  });

  loadIdeas();
})();
