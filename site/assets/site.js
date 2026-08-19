(() => {
  document.documentElement.classList.add("js");

  const form = document.querySelector("#catalog-controls");
  const grid = document.querySelector("#tool-grid");
  const hostedSection = document.querySelector("#hosted-services");
  const hostedGrid = hostedSection?.querySelector(".tool-grid--hosted");
  const navDisclosure = document.querySelector(".site-nav__disclosure");
  const resultLabel = document.querySelector("#catalog-results");
  const mobileResultLabel = document.querySelector("#catalog-mobile-results");
  const filterCountLabel = document.querySelector("#catalog-filter-count");
  const filterToggle = document.querySelector("#catalog-filter-toggle");
  const filterPanel = document.querySelector("#catalog-filter-panel");
  const emptyState = document.querySelector("#catalog-empty");
  const editorPicks = document.querySelector("#editors-choice");
  const compareTray = document.querySelector("#compare-tray");
  const compareCount = document.querySelector("#compare-count");
  const compareSelection = document.querySelector("#compare-selection");
  const compareStatus = document.querySelector("#compare-status");
  const compareOpen = document.querySelector("#compare-open");
  const compareClear = document.querySelector("#compare-clear");
  const compareDialog = document.querySelector("#compare-dialog");
  const compareContent = document.querySelector("#compare-content");
  const deferredCatalog = document.querySelector("#catalog-card-template");
  const showMore = document.querySelector("#catalog-show-more");
  const deferredMemorial = document.querySelector("#memorial-card-template");

  if (!(form instanceof HTMLFormElement) || !(grid instanceof HTMLElement)) {
    return;
  }

  const search = form.elements.namedItem("q");
  const sort = form.elements.namedItem("sort");
  const facets = {
    category: form.elements.namedItem("category"),
    status: form.elements.namedItem("status"),
    use_case: form.elements.namedItem("use_case"),
    ecosystem: form.elements.namedItem("ecosystem"),
    artifact_type: form.elements.namedItem("artifact_type"),
    license: form.elements.namedItem("license"),
    capability: form.elements.namedItem("capability"),
  };
  let cards = Array.from(grid.querySelectorAll(".tool-card"));
  const hostedCards =
    hostedGrid instanceof HTMLElement
      ? Array.from(hostedGrid.querySelectorAll(".tool-card"))
      : [];
  const totalCatalogCount =
    cards.length +
    (deferredCatalog instanceof HTMLTemplateElement
      ? deferredCatalog.content.querySelectorAll(".tool-card").length
      : 0);
  const selectedForComparison = new Set();
  const mobileQuery = window.matchMedia("(max-width: 720px)");
  let pendingResetFrame = null;

  if (
    !(search instanceof HTMLInputElement) ||
    !(sort instanceof HTMLSelectElement) ||
    Object.values(facets).some((select) => !(select instanceof HTMLSelectElement))
  ) {
    return;
  }

  const normalized = (value) => value.trim().toLocaleLowerCase();
  const numberValue = (card, key) => Number(card.dataset[key] || 0);
  const dateValue = (card) => Date.parse(card.dataset.updated || "") || 0;
  const nameValue = (card) => card.dataset.name || "";
  const facetMatches = (card, datasetKey, selected) =>
    !selected || (card.dataset[datasetKey] || "").includes(`|${normalized(selected)}|`);
  const countLabel = (count, singular, plural) =>
    `${count} ${count === 1 ? singular : plural}`;

  const hydrateCatalog = () => {
    if (!(deferredCatalog instanceof HTMLTemplateElement) || !deferredCatalog.isConnected) {
      return false;
    }
    deferredCatalog.replaceWith(deferredCatalog.content);
    if (showMore instanceof HTMLElement) showMore.remove();
    cards = Array.from(grid.querySelectorAll(".tool-card"));
    return true;
  };

  const hydrateMemorial = () => {
    if (!(deferredMemorial instanceof HTMLTemplateElement) || !deferredMemorial.isConnected) {
      return false;
    }
    const details = deferredMemorial.closest("details");
    deferredMemorial.replaceWith(deferredMemorial.content);
    if (details instanceof HTMLDetailsElement) details.open = true;
    return true;
  };

  const hydrateCardTarget = (fragment) => {
    const id = fragment.startsWith("#") ? fragment.slice(1) : fragment;
    if (!id.startsWith("tool-")) return document.getElementById(id);

    let target = document.getElementById(id);
    if (target) return target;
    if (
      deferredCatalog instanceof HTMLTemplateElement &&
      deferredCatalog.content.getElementById(id)
    ) {
      hydrateCatalog();
    } else if (
      deferredMemorial instanceof HTMLTemplateElement &&
      deferredMemorial.content.getElementById(id)
    ) {
      hydrateMemorial();
    }
    target = document.getElementById(id);
    return target;
  };

  const revealHashTarget = (fragment = window.location.hash) => {
    if (!fragment.startsWith("#tool-")) return null;
    const target = hydrateCardTarget(fragment);
    if (!target) return null;

    applyFilters({ updateUrl: false });
    if (target.hidden) {
      form.reset();
      applyResetNow();
    }
    window.requestAnimationFrame(() => target.scrollIntoView({ block: "start" }));
    return target;
  };

  const comparators = {
    recommended: (left, right) => numberValue(left, "rank") - numberValue(right, "rank"),
    activity: (left, right) =>
      numberValue(left, "activityRank") - numberValue(right, "activityRank") ||
      numberValue(right, "stars") - numberValue(left, "stars") ||
      nameValue(left).localeCompare(nameValue(right)),
    stars: (left, right) =>
      numberValue(right, "stars") - numberValue(left, "stars") ||
      nameValue(left).localeCompare(nameValue(right)),
    updated: (left, right) =>
      dateValue(right) - dateValue(left) || nameValue(left).localeCompare(nameValue(right)),
    name: (left, right) => nameValue(left).localeCompare(nameValue(right)),
  };

  const selectedFacetCount = () =>
    Object.values(facets).filter((select) => select.value).length;

  const setPanelOpen = (open) => {
    if (!(filterPanel instanceof HTMLElement) || !(filterToggle instanceof HTMLButtonElement)) {
      return;
    }
    filterPanel.classList.toggle("is-open", open);
    filterToggle.setAttribute("aria-expanded", String(open));
  };

  const updateAddress = () => {
    const params = new URLSearchParams();
    if (search.value.trim()) params.set("q", search.value.trim());
    for (const [key, select] of Object.entries(facets)) {
      if (select.value) params.set(key, select.value);
    }
    if (sort.value !== "recommended") params.set("sort", sort.value);

    const url = new URL(window.location.href);
    url.search = params.toString();
    window.history.replaceState(null, "", url);
  };

  const applyFilters = ({ updateUrl = true } = {}) => {
    const query = normalized(search.value);
    const catalogIsComplete =
      !(deferredCatalog instanceof HTMLTemplateElement) || !deferredCatalog.isConnected;
    let visibleCount = 0;
    let visibleHostedCount = 0;

    for (const card of cards) {
      const matchesSearch = !query || (card.dataset.search || "").includes(query);
      const matchesCategory =
        !facets.category.value || card.dataset.category === facets.category.value;
      const matchesStatus = !facets.status.value || card.dataset.status === facets.status.value;
      const visible =
        matchesSearch &&
        matchesCategory &&
        matchesStatus &&
        facetMatches(card, "useCases", facets.use_case.value) &&
        facetMatches(card, "ecosystems", facets.ecosystem.value) &&
        facetMatches(card, "artifactTypes", facets.artifact_type.value) &&
        facetMatches(card, "licenses", facets.license.value) &&
        facetMatches(card, "capabilities", facets.capability.value);
      card.hidden = !visible;
      if (visible) visibleCount += 1;
    }

    for (const card of hostedCards) {
      const visible = !query || (card.dataset.search || "").includes(query);
      card.hidden = !visible;
      if (visible) visibleHostedCount += 1;
    }

    if (catalogIsComplete) {
      const comparator = comparators[sort.value] || comparators.recommended;
      for (const card of [...cards].sort(comparator)) {
        grid.append(card);
      }
    }

    const installableResultText = countLabel(
      visibleCount,
      "installable tool",
      "installable tools",
    );
    const hostedResultText = countLabel(
      visibleHostedCount,
      "hosted service",
      "hosted services",
    );
    const groupedResultText = `${installableResultText} · ${hostedResultText}`;
    const compactInstallableText = catalogIsComplete
      ? `${visibleCount} installable`
      : `${visibleCount}/${totalCatalogCount} installable`;
    const compactGroupedResultText = `${compactInstallableText} · ${visibleHostedCount} hosted`;
    if (resultLabel) {
      resultLabel.textContent = catalogIsComplete
        ? `Showing ${groupedResultText}`
        : `Showing ${visibleCount} of ${totalCatalogCount} installable tools · ${hostedResultText}`;
    }
    if (mobileResultLabel) {
      mobileResultLabel.textContent = compactGroupedResultText;
    }
    if (filterCountLabel) filterCountLabel.textContent = String(selectedFacetCount());
    if (emptyState) emptyState.hidden = visibleCount + visibleHostedCount !== 0;
    if (hostedSection instanceof HTMLElement) {
      hostedSection.hidden = Boolean(query && visibleHostedCount === 0);
    }
    if (editorPicks instanceof HTMLElement) {
      editorPicks.hidden = Boolean(query || selectedFacetCount());
    }
    if (updateUrl) updateAddress();
  };

  const selectHasValue = (select, value) =>
    Array.from(select.options).some((option) => option.value === value);

  const restoreFromAddress = () => {
    const params = new URLSearchParams(window.location.search);
    search.value = params.get("q") || "";
    for (const [key, select] of Object.entries(facets)) {
      const requested = params.get(key) || "";
      if (selectHasValue(select, requested)) select.value = requested;
    }
    const requestedSort = params.get("sort") || "recommended";
    if (selectHasValue(sort, requestedSort)) sort.value = requestedSort;
  };

  form.addEventListener("submit", (event) => event.preventDefault());
  form.addEventListener("input", () => {
    hydrateCatalog();
    applyFilters();
  });
  form.addEventListener("change", () => {
    hydrateCatalog();
    applyFilters();
  });

  if (showMore instanceof HTMLButtonElement) {
    showMore.addEventListener("click", () => {
      hydrateCatalog();
      applyFilters();
    });
  }

  const memorialDetails = deferredMemorial?.closest("details");
  if (memorialDetails instanceof HTMLDetailsElement) {
    memorialDetails.addEventListener("toggle", () => {
      if (memorialDetails.open) hydrateMemorial();
    });
  }

  const applyResetNow = () => {
    if (pendingResetFrame !== null) {
      window.cancelAnimationFrame(pendingResetFrame);
      pendingResetFrame = null;
    }
    applyFilters();
  };

  form.addEventListener("reset", () => {
    pendingResetFrame = window.requestAnimationFrame(() => {
      pendingResetFrame = null;
      applyFilters();
    });
  });

  document.querySelectorAll("[data-reset-catalog]").forEach((button) => {
    button.addEventListener("click", () => {
      form.reset();
      search.focus();
    });
  });

  const selectedCards = () =>
    cards.filter((card) => selectedForComparison.has(card.id));

  const updateComparisonTray = () => {
    const selected = selectedCards();
    if (compareTray instanceof HTMLElement) compareTray.hidden = selected.length === 0;
    if (compareCount) compareCount.textContent = String(selected.length);
    if (compareOpen instanceof HTMLButtonElement) compareOpen.disabled = selected.length < 2;

    for (const card of cards) {
      const button = card.querySelector("[data-compare-toggle]");
      if (!(button instanceof HTMLButtonElement)) continue;
      const isSelected = selectedForComparison.has(card.id);
      const name = card.dataset.displayName || "tool";
      button.setAttribute("aria-pressed", String(isSelected));
      button.setAttribute(
        "aria-label",
        `${isSelected ? "Remove" : "Add"} ${name} ${isSelected ? "from" : "to"} comparison`,
      );
      button.textContent = isSelected ? "Selected" : "Compare";
    }

    if (compareSelection) {
      compareSelection.replaceChildren();
      for (const card of selected) {
        const item = document.createElement("li");
        const button = document.createElement("button");
        const name = card.dataset.displayName || "Tool";
        button.type = "button";
        button.textContent = `${name} ×`;
        button.setAttribute("aria-label", `Remove ${name} from comparison`);
        button.addEventListener("click", () => {
          selectedForComparison.delete(card.id);
          updateComparisonTray();
          const cardButton = card.querySelector("[data-compare-toggle]");
          if (cardButton instanceof HTMLButtonElement) cardButton.focus();
        });
        item.append(button);
        compareSelection.append(item);
      }
    }
  };

  const toggleComparison = (card) => {
    if (selectedForComparison.has(card.id)) {
      selectedForComparison.delete(card.id);
      if (compareStatus) compareStatus.textContent = `${card.dataset.displayName || "Tool"} removed.`;
    } else if (selectedForComparison.size >= 4) {
      if (compareStatus) compareStatus.textContent = "You can compare up to four tools.";
      return;
    } else {
      selectedForComparison.add(card.id);
      if (compareStatus) compareStatus.textContent = `${card.dataset.displayName || "Tool"} selected.`;
    }
    updateComparisonTray();
  };

  const buildComparisonTable = () => {
    if (!(compareContent instanceof HTMLElement)) return;
    const selected = selectedCards();
    const fields = [
      ["Type", "artifactLabels"],
      ["Best for", "descriptionText"],
      ["Use cases", "useCaseLabels"],
      ["Ecosystems", "ecosystemLabels"],
      ["License", "licenseLabels"],
      ["Supported PHP", "supportedPhp"],
      ["Pro", "pro"],
      ["Con", "con"],
    ];
    const table = document.createElement("table");
    table.className = "comparison-table";
    const caption = document.createElement("caption");
    caption.className = "visually-hidden";
    caption.textContent = "Side-by-side comparison of selected PHP analysis tools";
    table.append(caption);

    const head = table.createTHead();
    const headRow = head.insertRow();
    const fieldHeading = document.createElement("th");
    fieldHeading.scope = "col";
    fieldHeading.textContent = "Field";
    headRow.append(fieldHeading);
    for (const card of selected) {
      const heading = document.createElement("th");
      const link = document.createElement("a");
      heading.scope = "col";
      link.href = card.dataset.primaryUrl || "#";
      link.textContent = card.dataset.displayName || "Tool";
      heading.append(link);
      headRow.append(heading);
    }

    const body = table.createTBody();
    for (const [label, key] of fields) {
      const row = body.insertRow();
      const heading = document.createElement("th");
      heading.scope = "row";
      heading.textContent = label;
      row.append(heading);
      for (const card of selected) {
        const cell = row.insertCell();
        cell.textContent = card.dataset[key] || "Not recorded";
      }
    }
    compareContent.replaceChildren(table);
  };

  grid.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const button = target.closest("[data-compare-toggle]");
    const card = button?.closest(".tool-card");
    if (button instanceof HTMLButtonElement && card instanceof HTMLElement) {
      toggleComparison(card);
    }
  });

  if (compareClear instanceof HTMLButtonElement) {
    compareClear.addEventListener("click", () => {
      selectedForComparison.clear();
      updateComparisonTray();
      if (
        compareDialog instanceof HTMLElement &&
        compareDialog.hasAttribute("open") &&
        typeof compareDialog.close === "function"
      ) {
        compareDialog.close();
      }
      search.focus();
    });
  }

  if (compareOpen instanceof HTMLButtonElement && compareDialog instanceof HTMLElement) {
    compareOpen.addEventListener("click", () => {
      if (selectedForComparison.size < 2) return;
      buildComparisonTable();
      if (typeof compareDialog.showModal === "function") {
        compareDialog.showModal();
      } else {
        compareDialog.setAttribute("open", "");
      }
    });
  }

  if (filterToggle instanceof HTMLButtonElement) {
    filterToggle.addEventListener("click", () => {
      const open = filterToggle.getAttribute("aria-expanded") !== "true";
      setPanelOpen(open);
      if (open) facets.category.focus();
    });
  }

  if (filterPanel instanceof HTMLElement) {
    filterPanel.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && mobileQuery.matches) {
        setPanelOpen(false);
        if (filterToggle instanceof HTMLButtonElement) filterToggle.focus();
      }
    });
  }

  const setNavigationForViewport = (mobile) => {
    if (navDisclosure instanceof HTMLDetailsElement) {
      navDisclosure.open = !mobile;
    }
  };

  mobileQuery.addEventListener("change", (event) => {
    setPanelOpen(!event.matches);
    setNavigationForViewport(event.matches);
  });

  if (navDisclosure instanceof HTMLDetailsElement) {
    navDisclosure.addEventListener("click", (event) => {
      if (mobileQuery.matches && event.target instanceof Element && event.target.closest("a")) {
        navDisclosure.open = false;
      }
    });
  }

  document.querySelectorAll('a[href^="#tool-"]').forEach((link) => {
    link.addEventListener("click", () => {
      const fragment = link.getAttribute("href");
      if (fragment) revealHashTarget(fragment);
    });
  });

  window.addEventListener("hashchange", () => revealHashTarget());

  restoreFromAddress();
  if (search.value.trim() || selectedFacetCount() || sort.value !== "recommended") {
    hydrateCatalog();
  }
  setPanelOpen(!mobileQuery.matches);
  setNavigationForViewport(mobileQuery.matches);
  applyFilters({ updateUrl: false });
  revealHashTarget();
})();
