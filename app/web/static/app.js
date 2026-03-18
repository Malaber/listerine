function base64UrlToBytes(value) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
  const decoded = atob(padded);
  return Uint8Array.from(decoded, (char) => char.charCodeAt(0));
}

function bytesToBase64Url(value) {
  const bytes = value instanceof Uint8Array ? value : new Uint8Array(value);
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function publicKeyFromJSON(publicKey) {
  const parsed = { ...publicKey, challenge: base64UrlToBytes(publicKey.challenge) };

  if (parsed.user?.id) {
    parsed.user = { ...parsed.user, id: base64UrlToBytes(parsed.user.id) };
  }

  if (Array.isArray(parsed.excludeCredentials)) {
    parsed.excludeCredentials = parsed.excludeCredentials.map((credential) => ({
      ...credential,
      id: base64UrlToBytes(credential.id),
    }));
  }

  if (Array.isArray(parsed.allowCredentials)) {
    parsed.allowCredentials = parsed.allowCredentials.map((credential) => ({
      ...credential,
      id: base64UrlToBytes(credential.id),
    }));
  }

  return parsed;
}

function credentialToJSON(value) {
  if (value instanceof ArrayBuffer) {
    return bytesToBase64Url(value);
  }

  if (ArrayBuffer.isView(value)) {
    return bytesToBase64Url(value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength));
  }

  if (Array.isArray(value)) {
    return value.map(credentialToJSON);
  }

  if (value && typeof value.toJSON === "function") {
    return credentialToJSON(value.toJSON());
  }

  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, inner]) => [key, credentialToJSON(inner)]));
  }

  return value;
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (response.status === 401) {
    window.location.assign("/login");
    throw new Error("Unauthorized");
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof data.detail === "string" ? data.detail : "Passkey request failed.";
    throw new Error(message);
  }

  return data;
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (response.status === 401) {
    window.location.assign("/login");
    throw new Error("Unauthorized");
  }
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const message = typeof data.detail === "string" ? data.detail : "Request failed.";
    throw new Error(message);
  }

  return data;
}

function setMessage(root, type, message) {
  const errorNode = root.querySelector("[data-auth-error]");
  const successNode = root.querySelector("[data-auth-success]");

  errorNode.hidden = true;
  successNode.hidden = true;
  errorNode.textContent = "";
  successNode.textContent = "";

  if (type === "error") {
    errorNode.hidden = false;
    errorNode.textContent = message;
    return;
  }

  successNode.hidden = false;
  successNode.textContent = message;
}

function toggleButtons(root, disabled) {
  root.querySelectorAll("button").forEach((button) => {
    button.disabled = disabled;
  });
}

function setDashboardMessage(root, type, message) {
  const errorNode = root.querySelector("[data-dashboard-error]");
  const successNode = root.querySelector("[data-dashboard-success]");

  if (!errorNode || !successNode) {
    return;
  }

  errorNode.hidden = true;
  successNode.hidden = true;
  errorNode.textContent = "";
  successNode.textContent = "";

  if (!message) {
    return;
  }

  if (type === "error") {
    errorNode.hidden = false;
    errorNode.textContent = message;
    return;
  }

  successNode.hidden = false;
  successNode.textContent = message;
}

function toggleDashboardForms(root, disabled) {
  root
    .querySelectorAll("[data-dashboard] button, [data-dashboard] input, [data-dashboard] select")
    .forEach((node) => {
      node.disabled = disabled;
    });
}

function updateHouseholdOptions(root, households) {
  const select = root.querySelector("[data-household-select]");
  if (!select) {
    return;
  }

  const currentValue = select.value;
  select.innerHTML = "";

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = households.length ? "Select a household" : "Create a household first";
  select.appendChild(placeholder);

  households.forEach((household) => {
    const option = document.createElement("option");
    option.value = household.id;
    option.textContent = household.name;
    select.appendChild(option);
  });

  if (households.some((household) => household.id === currentValue)) {
    select.value = currentValue;
  } else if (households.length === 1) {
    select.value = households[0].id;
  }
}

function renderHouseholds(root, households, listsByHousehold) {
  const container = root.querySelector("[data-household-list]");
  const emptyState = root.querySelector("[data-dashboard-empty]");
  if (!container || !emptyState) {
    return;
  }

  container.innerHTML = "";
  const hasHouseholds = households.length > 0;
  emptyState.hidden = hasHouseholds;

  households.forEach((household) => {
    const lists = listsByHousehold.get(household.id) || [];
    const card = document.createElement("article");
    card.className = "household-card";
    card.innerHTML = `
      <h3>${household.name}</h3>
      <p class="household-meta">${lists.length} ${lists.length === 1 ? "list" : "lists"}</p>
    `;

    const listGrid = document.createElement("ul");
    listGrid.className = "list-grid";

    if (lists.length === 0) {
      const emptyListState = document.createElement("p");
      emptyListState.className = "dashboard-helper";
      emptyListState.textContent = "No lists yet. Use the form above to create the first one.";
      card.appendChild(emptyListState);
    } else {
      lists.forEach((list) => {
        const item = document.createElement("li");
        item.innerHTML = `
          <a href="/lists/${list.id}">
            <strong>${list.name}</strong>
            <small>Open list</small>
          </a>
        `;
        listGrid.appendChild(item);
      });
      card.appendChild(listGrid);
    }

    container.appendChild(card);
  });
}

async function loadDashboardData(root) {
  const households = await fetchJson("/api/v1/households");
  const listResponses = await Promise.all(
    households.map(async (household) => ({
      householdId: household.id,
      lists: await fetchJson(`/api/v1/households/${household.id}/lists`),
    }))
  );
  const listsByHousehold = new Map(
    listResponses.map((response) => [response.householdId, response.lists])
  );

  updateHouseholdOptions(root, households);
  renderHouseholds(root, households, listsByHousehold);
}

async function initDashboard() {
  const root = document.querySelector("[data-dashboard]");
  if (!root) {
    return;
  }

  const householdForm = root.querySelector("[data-household-form]");
  const listForm = root.querySelector("[data-list-form]");

  const refresh = async () => {
    setDashboardMessage(root, "", "");
    await loadDashboardData(root);
  };

  householdForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(householdForm);
    toggleDashboardForms(root, true);
    try {
      const name = String(formData.get("name") || "").trim();
      if (!name) {
        throw new Error("Please enter a household name.");
      }
      await postJson("/api/v1/households", { name });
      householdForm.reset();
      await refresh();
      setDashboardMessage(root, "success", "Household created. You can add a list now.");
    } catch (error) {
      setDashboardMessage(
        root,
        "error",
        error instanceof Error ? error.message : "Could not create the household."
      );
    } finally {
      toggleDashboardForms(root, false);
    }
  });

  listForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(listForm);
    toggleDashboardForms(root, true);
    try {
      const householdId = String(formData.get("household_id") || "");
      const name = String(formData.get("name") || "").trim();
      if (!householdId) {
        throw new Error("Create or choose a household before creating a list.");
      }
      if (!name) {
        throw new Error("Please enter a list name.");
      }
      const groceryList = await postJson(`/api/v1/households/${householdId}/lists`, { name });
      listForm.reset();
      await refresh();
      window.location.assign(`/lists/${groceryList.id}`);
    } catch (error) {
      setDashboardMessage(
        root,
        "error",
        error instanceof Error ? error.message : "Could not create the list."
      );
    } finally {
      toggleDashboardForms(root, false);
    }
  });

  try {
    await refresh();
  } catch (error) {
    setDashboardMessage(
      root,
      "error",
      error instanceof Error ? error.message : "Could not load your households."
    );
  }
}

function setListMessage(root, type, message) {
  const errorNode = root.querySelector("[data-list-error]");
  const successNode = root.querySelector("[data-list-success]");

  if (!errorNode || !successNode) {
    return;
  }

  errorNode.hidden = true;
  successNode.hidden = true;
  errorNode.textContent = "";
  successNode.textContent = "";

  if (!message) {
    return;
  }

  if (type === "error") {
    errorNode.hidden = false;
    errorNode.textContent = message;
    return;
  }

  successNode.hidden = false;
  successNode.textContent = message;
}

function setListSyncStatus(root, message) {
  const statusNode = root.querySelector("[data-list-sync-status]");
  if (statusNode) {
    statusNode.textContent = message;
  }
}

function hideUndoToast(root, state) {
  const toast = root.querySelector("[data-list-toast]");
  const message = root.querySelector("[data-list-toast-message]");
  const timer = root.querySelector("[data-list-toast-timer]");
  if (!toast || !message) {
    return;
  }

  if (state.undoTimerId) {
    window.clearTimeout(state.undoTimerId);
  }
  state.undoTimerId = null;
  state.undoAction = null;
  message.textContent = "";
  if (timer instanceof HTMLElement) {
    timer.style.animation = "none";
  }
  toast.classList.remove("is-active");
  toast.hidden = true;
}

function showUndoToast(root, state, messageText, undoAction) {
  const toast = root.querySelector("[data-list-toast]");
  const message = root.querySelector("[data-list-toast-message]");
  const timer = root.querySelector("[data-list-toast-timer]");
  if (!toast || !message) {
    return;
  }

  hideUndoToast(root, state);
  state.undoAction = undoAction;
  message.textContent = messageText;
  toast.hidden = false;
  if (timer instanceof HTMLElement) {
    timer.style.animation = "none";
    // Force a reflow so the countdown animation reliably restarts each time.
    void timer.offsetWidth;
    timer.style.animation = "";
  }
  toast.classList.add("is-active");
  state.undoTimerId = window.setTimeout(() => {
    hideUndoToast(root, state);
  }, 10000);
}

function normalizeItemName(value) {
  return value.trim().replace(/\s+/g, " ").toLowerCase();
}

function normalizeSearchText(value) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .replace(/\s+/g, " ")
    .toLowerCase();
}

function syncModalState(root) {
  const addOverlay = root.querySelector("[data-item-panel-overlay]");
  const editOverlay = root.querySelector("[data-item-edit-overlay]");
  const settingsOverlay = root.querySelector("[data-list-settings-overlay]");
  const hasModalOpen =
    (addOverlay instanceof HTMLElement && !addOverlay.hidden) ||
    (editOverlay instanceof HTMLElement && !editOverlay.hidden) ||
    (settingsOverlay instanceof HTMLElement && !settingsOverlay.hidden);

  root.classList.toggle("has-modal-open", hasModalOpen);
  document.body.classList.toggle("has-list-modal-open", hasModalOpen);
}

function setItemPanelOpen(root, isOpen) {
  const panel = root.querySelector("[data-item-panel]");
  const overlay = root.querySelector("[data-item-panel-overlay]");
  const toggle = root.querySelector("[data-item-form-toggle]");
  const nameInput = root.querySelector("[data-item-name-input]");
  const categorySearch = root.querySelector("[data-item-category-search]");
  const editPanel = root.querySelector("[data-item-edit-panel]");
  const editOverlay = root.querySelector("[data-item-edit-overlay]");
  const settingsPanel = root.querySelector("[data-list-settings-panel]");
  const settingsOverlay = root.querySelector("[data-list-settings-overlay]");

  if (!panel || !overlay || !toggle) {
    return;
  }

  overlay.hidden = !isOpen;
  panel.hidden = !isOpen;
  if (isOpen && editPanel instanceof HTMLElement && editOverlay instanceof HTMLElement) {
    editPanel.hidden = true;
    editOverlay.hidden = true;
  }
  if (isOpen && settingsPanel instanceof HTMLElement && settingsOverlay instanceof HTMLElement) {
    settingsPanel.hidden = true;
    settingsOverlay.hidden = true;
  }
  if (isOpen && categorySearch instanceof HTMLInputElement) {
    categorySearch.value = "";
  }
  toggle.setAttribute("aria-expanded", String(isOpen));
  syncModalState(root);

  if (isOpen && nameInput instanceof HTMLElement) {
    window.setTimeout(() => {
      nameInput.focus();
    }, 0);
  }
}

function formatSuggestionMeta(state, item) {
  const meta = [];
  const category = item.category_id ? state.categories.get(item.category_id)?.name || "" : "";
  if (category) {
    meta.push(category);
  }
  if (item.quantity_text) {
    meta.push(item.quantity_text);
  }
  if (item.note) {
    meta.push(item.note);
  }
  meta.push(item.checked ? "checked earlier" : "already on this list");
  return meta.join(" / ");
}

function categorySortKey(state, categoryId) {
  if (!categoryId) {
    return {
      color: "",
      name: "Uncategorized",
      isExplicit: false,
      sortOrder: Number.MAX_SAFE_INTEGER,
    };
  }

  const category = state.categories.get(categoryId);
  if (!category) {
    return {
      color: "",
      name: "Uncategorized",
      isExplicit: false,
      sortOrder: Number.MAX_SAFE_INTEGER,
    };
  }

  return {
    color: category.color || "",
    name: category.name,
    isExplicit: state.categoryOrder.has(categoryId),
    sortOrder: state.categoryOrder.get(categoryId) ?? Number.MAX_SAFE_INTEGER,
  };
}

function decorateItem(state, item) {
  const category = item.category_id ? state.categories.get(item.category_id) : null;
  return {
    ...item,
    _categoryColor: category?.color || "",
    _categoryName: category?.name || "",
  };
}

function setCategoryRadioValue(root, selector, categoryId) {
  root.querySelectorAll(selector).forEach((radio) => {
    if (!(radio instanceof HTMLInputElement)) {
      return;
    }

    radio.checked = radio.value === (categoryId || "");
  });
}

function categoryMatchesQuery(category, query) {
  if (!query) {
    return true;
  }

  const haystacks = [category.name, ...(category.aliases || [])].map((value) => normalizeSearchText(value));
  return haystacks.some((value) => value.includes(query));
}

function syncCategoryRadioGroup(container, groupName, currentValue, state, searchQuery) {
  if (!(container instanceof HTMLElement)) {
    return;
  }

  container.innerHTML = "";
  const categories = [...state.categories.values()].sort((left, right) => left.name.localeCompare(right.name));
  const options = [
    {
      color: "",
      id: "",
      name: "No category",
      hint: "Keep this item above the category sections.",
    },
    ...categories,
  ].filter(
    (category, index) =>
      index === 0 || category.id === (currentValue || "") || categoryMatchesQuery(category, searchQuery)
  );

  if (options.length === 0) {
    const emptyState = document.createElement("p");
    emptyState.className = "category-radio-empty";
    emptyState.textContent = "No category matches that search yet.";
    container.appendChild(emptyState);
    return;
  }

  options.forEach((category, index) => {
    const option = document.createElement("label");
    option.className = "category-radio-option";

    const input = document.createElement("input");
    input.type = "radio";
    input.name = groupName;
    input.value = category.id;
    input.checked = (currentValue || "") === category.id;
    option.appendChild(input);

    const card = document.createElement("span");
    card.className = "category-radio-card";

    const swatch = document.createElement("span");
    swatch.className = "category-radio-swatch";
    swatch.style.background = category.color || "#cbd5e1";
    card.appendChild(swatch);

    const copy = document.createElement("span");
    copy.className = "category-radio-copy";

    const title = document.createElement("strong");
    title.textContent = category.name;
    copy.appendChild(title);

    if (index === 0) {
      const hint = document.createElement("span");
      hint.textContent = category.hint;
      copy.appendChild(hint);
    }

    card.appendChild(copy);
    option.appendChild(card);
    container.appendChild(option);
  });
}

function syncCategoryRadioGroups(root, state) {
  const addContainer = root.querySelector("[data-item-category-radios]");
  const editContainer = root.querySelector("[data-item-edit-category-radios]");
  const addSearchInput = root.querySelector("[data-item-category-search]");
  const editSearchInput = root.querySelector("[data-item-edit-category-search]");
  const addSearch = addSearchInput instanceof HTMLInputElement ? addSearchInput.value : "";
  const editSearch = editSearchInput instanceof HTMLInputElement ? editSearchInput.value : "";
  const addCurrentValue =
    root.querySelector('input[name="category_id"]:checked') instanceof HTMLInputElement
      ? root.querySelector('input[name="category_id"]:checked').value
      : "";
  const editCurrentValue =
    root.querySelector('input[name="edit_category_id"]:checked') instanceof HTMLInputElement
      ? root.querySelector('input[name="edit_category_id"]:checked').value
      : "";

  syncCategoryRadioGroup(
    addContainer,
    "category_id",
    addCurrentValue,
    state,
    normalizeSearchText(addSearch)
  );
  syncCategoryRadioGroup(
    editContainer,
    "edit_category_id",
    editCurrentValue,
    state,
    normalizeSearchText(editSearch)
  );
}

function getManualCategoryIds(state) {
  return [...state.categories.values()]
    .filter((category) => state.categoryOrder.has(category.id))
    .sort((left, right) => state.categoryOrder.get(left.id) - state.categoryOrder.get(right.id))
    .map((category) => category.id);
}

function getAlphabeticalCategoryIds(state) {
  return [...state.categories.values()]
    .filter((category) => !state.categoryOrder.has(category.id))
    .sort((left, right) => left.name.localeCompare(right.name))
    .map((category) => category.id);
}

function getOrderedCategoryIds(state) {
  return [...getManualCategoryIds(state), ...getAlphabeticalCategoryIds(state)];
}

function getDisplayedCategoryIds(state) {
  const itemCategoryIds = new Set(
    [...state.items.values()]
      .filter((item) => !item.checked)
      .map((item) => item.category_id)
      .filter((categoryId) => categoryId && state.categories.has(categoryId))
  );

  return getOrderedCategoryIds(state).filter((categoryId) => itemCategoryIds.has(categoryId));
}

function deriveManualCategoryIds(state, orderedCategoryIds) {
  for (let prefixLength = 0; prefixLength <= orderedCategoryIds.length; prefixLength += 1) {
    const prefix = orderedCategoryIds.slice(0, prefixLength);
    const remainder = orderedCategoryIds.slice(prefixLength);
    const alphabeticalRemainder = [...remainder].sort((leftId, rightId) => {
      const leftName = state.categories.get(leftId)?.name || "";
      const rightName = state.categories.get(rightId)?.name || "";
      return leftName.localeCompare(rightName);
    });

    if (
      remainder.length === alphabeticalRemainder.length &&
      remainder.every((categoryId, index) => categoryId === alphabeticalRemainder[index])
    ) {
      return prefix;
    }
  }

  return orderedCategoryIds;
}

function setCategoryOrder(state, categoryIds) {
  state.categoryOrder = new Map(categoryIds.map((categoryId, index) => [categoryId, index]));
}

async function saveCategoryOrder(root, state) {
  const listId = root.dataset.listId;
  const categoryIds = getManualCategoryIds(state);
  const response = await fetchJson(`/api/v1/lists/${listId}/category-order`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ category_ids: categoryIds }),
  });
  state.categoryOrder = new Map(response.map((entry) => [entry.category_id, entry.sort_order]));
}

function setItemEditPanelOpen(root, state, itemId) {
  const panel = root.querySelector("[data-item-edit-panel]");
  const overlay = root.querySelector("[data-item-edit-overlay]");
  const form = root.querySelector("[data-item-edit-form]");
  const title = root.querySelector("[data-item-edit-title]");
  if (
    !(panel instanceof HTMLElement) ||
    !(overlay instanceof HTMLElement) ||
    !(form instanceof HTMLFormElement) ||
    !title
  ) {
    return;
  }

  state.editingItemId = itemId;
  if (!itemId) {
    overlay.hidden = true;
    panel.hidden = true;
    form.reset();
    const editSearch = root.querySelector("[data-item-edit-category-search]");
    if (editSearch instanceof HTMLInputElement) {
      editSearch.value = "";
    }
    syncModalState(root);
    return;
  }

  const item = state.items.get(itemId);
  if (!item) {
    overlay.hidden = true;
    panel.hidden = true;
    syncModalState(root);
    return;
  }

  setItemPanelOpen(root, false);
  overlay.hidden = false;
  panel.hidden = false;
  syncModalState(root);
  title.textContent = item.name;

  form.elements.namedItem("name").value = item.name;
  form.elements.namedItem("quantity_text").value = item.quantity_text || "";
  form.elements.namedItem("note").value = item.note || "";
  const editSearch = root.querySelector("[data-item-edit-category-search]");
  if (editSearch instanceof HTMLInputElement) {
    editSearch.value = "";
  }

  setCategoryRadioValue(root, 'input[name="edit_category_id"]', item.category_id || "");
  syncCategoryRadioGroups(root, state);
}

function renderCategoryOrderSettings(root, state) {
  const container = root.querySelector("[data-list-settings-category-list]");
  if (!(container instanceof HTMLElement)) {
    return;
  }

  container.innerHTML = "";
  const orderedCategories = getOrderedCategoryIds(state).map((categoryId) => state.categories.get(categoryId)).filter(Boolean);

  if (orderedCategories.length === 0) {
    const emptyState = document.createElement("p");
    emptyState.className = "dashboard-helper";
    emptyState.textContent = "Create categories in admin to customize the order for this list.";
    container.appendChild(emptyState);
    return;
  }

  orderedCategories.forEach((category, index) => {
    const row = document.createElement("div");
    row.className = "settings-category-row";

    const swatch = document.createElement("span");
    swatch.className = "item-category-swatch";
    swatch.style.background = category.color || "#cbd5e1";
    row.appendChild(swatch);

    const copy = document.createElement("div");
    copy.className = "settings-category-copy";

    const title = document.createElement("strong");
    title.textContent = category.name;
    copy.appendChild(title);

    const meta = document.createElement("span");
    meta.textContent = state.categoryOrder.has(category.id)
      ? "Pinned in this list order"
      : "Alphabetical until you move it";
    copy.appendChild(meta);
    row.appendChild(copy);

    const actions = document.createElement("div");
    actions.className = "settings-category-actions";

    const moveUp = document.createElement("button");
    moveUp.type = "button";
    moveUp.dataset.settingsCategoryMove = "up";
    moveUp.dataset.categoryId = category.id;
    moveUp.setAttribute("aria-label", `Move ${category.name} up`);
    moveUp.disabled = index === 0;
    moveUp.textContent = "↑";
    actions.appendChild(moveUp);

    const moveDown = document.createElement("button");
    moveDown.type = "button";
    moveDown.dataset.settingsCategoryMove = "down";
    moveDown.dataset.categoryId = category.id;
    moveDown.setAttribute("aria-label", `Move ${category.name} down`);
    moveDown.disabled = index === orderedCategories.length - 1;
    moveDown.textContent = "↓";
    actions.appendChild(moveDown);

    row.appendChild(actions);
    container.appendChild(row);
  });
}

function setListSettingsOpen(root, state, isOpen) {
  const overlay = root.querySelector("[data-list-settings-overlay]");
  const panel = root.querySelector("[data-list-settings-panel]");
  if (!(overlay instanceof HTMLElement) || !(panel instanceof HTMLElement)) {
    return;
  }

  overlay.hidden = !isOpen;
  panel.hidden = !isOpen;

  if (isOpen) {
    setItemPanelOpen(root, false);
    setItemEditPanelOpen(root, state, null);
    renderCategoryOrderSettings(root, state);
  }

  syncModalState(root);
}

function renderItemSuggestions(root, state) {
  const suggestionsNode = root.querySelector("[data-item-suggestions]");
  const suggestionsSlot = root.querySelector("[data-item-suggestions-slot]");
  const nameInput = root.querySelector("[data-item-name-input]");

  if (
    !(suggestionsNode instanceof HTMLElement) ||
    !(suggestionsSlot instanceof HTMLElement) ||
    !(nameInput instanceof HTMLInputElement)
  ) {
    return;
  }

  const query = normalizeItemName(nameInput.value);
  suggestionsNode.innerHTML = "";
  if (!query) {
    suggestionsSlot.classList.remove("is-active");
    return;
  }

  const matches = [...state.items.values()]
    .filter((item) => normalizeItemName(item.name).includes(query))
    .sort((left, right) => {
      const leftName = normalizeItemName(left.name);
      const rightName = normalizeItemName(right.name);
      const leftExact = Number(leftName === query);
      const rightExact = Number(rightName === query);
      if (leftExact !== rightExact) {
        return rightExact - leftExact;
      }
      const leftStarts = Number(leftName.startsWith(query));
      const rightStarts = Number(rightName.startsWith(query));
      if (leftStarts !== rightStarts) {
        return rightStarts - leftStarts;
      }
      if (left.checked !== right.checked) {
        return Number(left.checked) - Number(right.checked);
      }
      return left.name.localeCompare(right.name);
    })
    .slice(0, 4);

  if (matches.length === 0) {
    suggestionsSlot.classList.remove("is-active");
    return;
  }

  matches.forEach((item) => {
    const wrapper = document.createElement("article");
    wrapper.className = `item-suggestion${item.checked ? " is-checked" : ""}`;

    const main = document.createElement("div");
    main.className = "item-main";

    const checkmark = document.createElement("span");
    checkmark.className = `item-check item-suggestion-check${item.checked ? " is-checked" : ""}`;
    checkmark.setAttribute("aria-hidden", "true");
    main.appendChild(checkmark);

    const copy = document.createElement("div");
    copy.className = "item-copy item-suggestion-copy";

    const title = document.createElement("strong");
    title.className = "item-name";
    title.textContent = item.name;
    copy.appendChild(title);

    const meta = document.createElement("span");
    meta.textContent = formatSuggestionMeta(state, item);
    copy.appendChild(meta);

    main.appendChild(copy);
    wrapper.appendChild(main);

    const button = document.createElement("button");
    button.type = "button";
    button.dataset.itemReuse = item.id;
    button.setAttribute(
      "aria-label",
      item.checked ? `Add ${item.name} back to the list` : `Jump to ${item.name} in the list`
    );
    button.textContent = "+";

    wrapper.appendChild(button);
    suggestionsNode.appendChild(wrapper);
  });

  suggestionsSlot.classList.add("is-active");
}

function highlightItem(root, state, itemId) {
  const itemCard = root.querySelector(`[data-item-card="${itemId}"]`);
  if (!(itemCard instanceof HTMLElement)) {
    return;
  }

  const existingTimer = state.highlightTimers.get(itemId);
  if (existingTimer) {
    window.clearTimeout(existingTimer);
  }

  itemCard.classList.add("is-highlighted");
  itemCard.scrollIntoView({ behavior: "smooth", block: "center" });
  const timeoutId = window.setTimeout(() => {
    itemCard.classList.remove("is-highlighted");
    state.highlightTimers.delete(itemId);
  }, 1800);
  state.highlightTimers.set(itemId, timeoutId);
}

function compareActiveItems(state, left, right) {
  const leftIsUncategorized = !left.category_id;
  const rightIsUncategorized = !right.category_id;
  if (leftIsUncategorized !== rightIsUncategorized) {
    return Number(rightIsUncategorized) - Number(leftIsUncategorized);
  }

  if (!leftIsUncategorized && !rightIsUncategorized) {
    const leftCategory = categorySortKey(state, left.category_id);
    const rightCategory = categorySortKey(state, right.category_id);
    if (leftCategory.isExplicit !== rightCategory.isExplicit) {
      return Number(rightCategory.isExplicit) - Number(leftCategory.isExplicit);
    }
    if (leftCategory.sortOrder !== rightCategory.sortOrder) {
      return leftCategory.sortOrder - rightCategory.sortOrder;
    }
    if (leftCategory.name !== rightCategory.name) {
      return leftCategory.name.localeCompare(rightCategory.name);
    }
  }

  if (left.sort_order !== right.sort_order) {
    return left.sort_order - right.sort_order;
  }
  return left.name.localeCompare(right.name);
}

function compareCheckedItems(left, right) {
  const leftCheckedAt = left.checked_at ? Date.parse(left.checked_at) : 0;
  const rightCheckedAt = right.checked_at ? Date.parse(right.checked_at) : 0;
  if (leftCheckedAt !== rightCheckedAt) {
    return rightCheckedAt - leftCheckedAt;
  }
  return left.name.localeCompare(right.name);
}

function getActiveGroupOrder(state, items) {
  const groupKeys = new Set(
    items.map((item) => item.category_id || "uncategorized")
  );

  const orderedKeys = ["uncategorized"];
  getOrderedCategoryIds(state).forEach((categoryId) => {
    if (groupKeys.has(categoryId)) {
      orderedKeys.push(categoryId);
    }
  });

  return orderedKeys.filter((groupKey) => groupKeys.has(groupKey));
}

function renderItems(root, state) {
  const container = root.querySelector("[data-item-list]");
  const emptyState = root.querySelector("[data-item-empty]");
  if (!container || !emptyState) {
    return;
  }

  const decoratedItems = [...state.items.values()].map((item) => decorateItem(state, item));
  const activeItems = decoratedItems
    .filter((item) => !item.checked)
    .sort((left, right) => compareActiveItems(state, left, right));
  const checkedItems = decoratedItems
    .filter((item) => item.checked)
    .sort(compareCheckedItems);

  container.innerHTML = "";
  emptyState.hidden = decoratedItems.length > 0;

  const groupedActiveItems = new Map();
  activeItems.forEach((item) => {
    const groupKey = item.category_id || "uncategorized";
    if (!groupedActiveItems.has(groupKey)) {
      groupedActiveItems.set(groupKey, []);
    }
    groupedActiveItems.get(groupKey).push(item);
  });

  getActiveGroupOrder(state, activeItems).forEach((groupKey) => {
    const items = groupedActiveItems.get(groupKey) || [];
    const section = document.createElement("section");
    section.className = "item-category-group";

    const category = groupKey === "uncategorized" ? null : state.categories.get(groupKey);
    const heading = document.createElement("div");
    heading.className = "item-category-header";

    const swatch = document.createElement("span");
    swatch.className = "item-category-swatch";
    swatch.style.background = category?.color || "#cbd5e1";
    heading.appendChild(swatch);

    const headingCopy = document.createElement("div");
    const headingTitle = document.createElement("h3");
    headingTitle.textContent = category?.name || "Uncategorized";
    headingCopy.appendChild(headingTitle);

    const headingMeta = document.createElement("p");
    headingMeta.textContent = `${items.length} ${items.length === 1 ? "item" : "items"}`;
    headingCopy.appendChild(headingMeta);
    heading.appendChild(headingCopy);

    section.appendChild(heading);

    items.forEach((item) => {
      const article = document.createElement("article");
      article.className = `item-card${item.checked ? " is-checked" : ""}`;
      article.dataset.itemCard = item.id;
      article.dataset.itemEdit = item.id;

      const main = document.createElement("div");
      main.className = "item-main";

      const checkButton = document.createElement("button");
      checkButton.className = `item-check${item.checked ? " is-checked" : ""}`;
      checkButton.type = "button";
      checkButton.dataset.itemToggle = item.id;
      checkButton.setAttribute(
        "aria-label",
        item.checked ? `Uncheck ${item.name}` : `Check ${item.name}`
      );
      main.appendChild(checkButton);

      const copy = document.createElement("div");
      copy.className = "item-copy";

      const title = document.createElement("h3");
      title.className = "item-name";
      title.textContent = item.name;
      copy.appendChild(title);

      if (item.quantity_text) {
        const quantity = document.createElement("p");
        quantity.className = "item-meta";
        quantity.textContent = `Qty: ${item.quantity_text}`;
        copy.appendChild(quantity);
      }

      if (item.note) {
        const note = document.createElement("p");
        note.className = "item-meta";
        note.textContent = item.note;
        copy.appendChild(note);
      }

      main.appendChild(copy);
      article.appendChild(main);

      const actions = document.createElement("div");
      actions.className = "item-actions";

      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.className = "danger-button";
      deleteButton.dataset.itemDelete = item.id;
      deleteButton.textContent = "Delete";
      actions.appendChild(deleteButton);

      article.appendChild(actions);
      section.appendChild(article);
    });

    container.appendChild(section);
  });

  if (checkedItems.length > 0) {
    const section = document.createElement("section");
    section.className = "item-category-group";

    const heading = document.createElement("div");
    heading.className = "item-category-header";

    const swatch = document.createElement("span");
    swatch.className = "item-category-swatch";
    swatch.style.background = "#94a3b8";
    heading.appendChild(swatch);

    const headingCopy = document.createElement("div");
    const headingTitle = document.createElement("h3");
    headingTitle.textContent = "Checked off";
    headingCopy.appendChild(headingTitle);

    const headingMeta = document.createElement("p");
    headingMeta.textContent = `${checkedItems.length} ${checkedItems.length === 1 ? "item" : "items"}`;
    headingCopy.appendChild(headingMeta);
    heading.appendChild(headingCopy);
    section.appendChild(heading);

    checkedItems.forEach((item) => {
      const article = document.createElement("article");
      article.className = "item-card is-checked";
      article.dataset.itemCard = item.id;
      article.dataset.itemEdit = item.id;

      const main = document.createElement("div");
      main.className = "item-main";

      const checkButton = document.createElement("button");
      checkButton.className = "item-check is-checked";
      checkButton.type = "button";
      checkButton.dataset.itemToggle = item.id;
      checkButton.setAttribute("aria-label", `Uncheck ${item.name}`);
      main.appendChild(checkButton);

      const copy = document.createElement("div");
      copy.className = "item-copy";

      const title = document.createElement("h3");
      title.className = "item-name";
      title.textContent = item.name;
      copy.appendChild(title);

      if (item.quantity_text) {
        const quantity = document.createElement("p");
        quantity.className = "item-meta";
        quantity.textContent = `Qty: ${item.quantity_text}`;
        copy.appendChild(quantity);
      }

      if (item.note) {
        const note = document.createElement("p");
        note.className = "item-meta";
        note.textContent = item.note;
        copy.appendChild(note);
      }

      main.appendChild(copy);
      article.appendChild(main);

      const actions = document.createElement("div");
      actions.className = "item-actions";

      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.className = "danger-button";
      deleteButton.dataset.itemDelete = item.id;
      deleteButton.textContent = "Delete";
      actions.appendChild(deleteButton);

      article.appendChild(actions);
      section.appendChild(article);
    });

    container.appendChild(section);
  }

  renderItemSuggestions(root, state);
  renderCategoryOrderSettings(root, state);
  if (state.editingItemId) {
    setItemEditPanelOpen(root, state, state.editingItemId);
  }
}

function replaceItems(state, items) {
  state.items = new Map(items.map((item) => [item.id, item]));
}

function upsertItem(state, item) {
  state.items.set(item.id, item);
}

function removeItem(state, itemId) {
  state.items.delete(itemId);
}

async function loadListDetail(root, state) {
  const listId = root.dataset.listId;
  const [groceryList, items, categories, categoryOrder] = await Promise.all([
    fetchJson(`/api/v1/lists/${listId}`),
    fetchJson(`/api/v1/lists/${listId}/items`),
    fetchJson("/api/v1/categories"),
    fetchJson(`/api/v1/lists/${listId}/category-order`),
  ]);

  const title = root.querySelector("[data-list-title]");
  if (title) {
    title.textContent = groceryList.name;
  }

  state.categories = new Map(categories.map((category) => [category.id, category]));
  state.categoryOrder = new Map(
    categoryOrder.map((entry) => [entry.category_id, entry.sort_order])
  );
  replaceItems(state, items);
  syncCategoryRadioGroups(root, state);
  renderItems(root, state);
}

function connectListSocket(root, state) {
  const listId = root.dataset.listId;
  const token = root.dataset.accessToken;
  if (!listId || !token) {
    setListSyncStatus(root, "Live updates unavailable.");
    return;
  }

  let isDisposed = false;

  const connect = () => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socketUrl = `${protocol}//${window.location.host}/api/v1/ws/lists/${listId}?token=${encodeURIComponent(token)}`;
    setListSyncStatus(root, "Connecting live updates...");
    state.socket = new WebSocket(socketUrl);

    state.socket.addEventListener("open", () => {
      setListSyncStatus(root, "Live updates on.");
    });

    state.socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.type === "list_snapshot") {
        replaceItems(state, message.payload.items || []);
        state.categoryOrder = new Map(
          (message.payload.category_order || []).map((entry) => [entry.category_id, entry.sort_order])
        );
        renderItems(root, state);
        return;
      }

      if (message.type === "category_order_updated") {
        state.categoryOrder = new Map(
          (message.payload?.category_order || []).map((entry) => [entry.category_id, entry.sort_order])
        );
        renderItems(root, state);
        return;
      }

      const item = message.payload?.item;
      if (message.type === "item_deleted") {
        if (item?.id) {
          removeItem(state, item.id);
          renderItems(root, state);
        }
        return;
      }

      if (!item) {
        return;
      }

      upsertItem(state, item);
      renderItems(root, state);
    });

    state.socket.addEventListener("close", () => {
      state.socket = null;
      if (isDisposed) {
        return;
      }
      setListSyncStatus(root, "Live updates paused. Reconnecting...");
      window.setTimeout(connect, 1500);
    });
  };

  connect();
  window.addEventListener("beforeunload", () => {
    isDisposed = true;
    state.socket?.close();
  });
}

async function initListDetail() {
  const root = document.querySelector("[data-list-detail]");
  if (!root) {
    return;
  }

  const itemForm = root.querySelector("[data-item-form]");
  const itemEditForm = root.querySelector("[data-item-edit-form]");
  const nameInput = root.querySelector("[data-item-name-input]");
  const listId = root.dataset.listId;
  const state = {
    categoryOrder: new Map(),
    categories: new Map(),
    editingItemId: null,
    highlightTimers: new Map(),
    items: new Map(),
    socket: null,
    undoAction: null,
    undoTimerId: null,
  };

  const refresh = async () => {
    setListMessage(root, "", "");
    await loadListDetail(root, state);
  };

  root.querySelector("[data-item-form-toggle]")?.addEventListener("click", () => {
    const panel = root.querySelector("[data-item-panel]");
    setItemPanelOpen(root, panel?.hidden ?? true);
    renderItemSuggestions(root, state);
  });

  root.querySelectorAll("[data-item-form-close]").forEach((node) => {
    node.addEventListener("click", () => {
      setItemPanelOpen(root, false);
    });
  });

  root.querySelectorAll("[data-item-edit-close]").forEach((node) => {
    node.addEventListener("click", () => {
      setItemEditPanelOpen(root, state, null);
    });
  });

  root.querySelector("[data-list-settings-toggle]")?.addEventListener("click", () => {
    const panel = root.querySelector("[data-list-settings-panel]");
    setListSettingsOpen(root, state, panel instanceof HTMLElement ? panel.hidden : true);
  });

  root.querySelectorAll("[data-list-settings-close]").forEach((node) => {
    node.addEventListener("click", () => {
      setListSettingsOpen(root, state, false);
    });
  });

  nameInput?.addEventListener("input", () => {
    renderItemSuggestions(root, state);
  });

  root.querySelector("[data-item-category-search]")?.addEventListener("input", () => {
    syncCategoryRadioGroups(root, state);
  });

  root.querySelector("[data-item-edit-category-search]")?.addEventListener("input", () => {
    syncCategoryRadioGroups(root, state);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }

    const settingsPanel = root.querySelector("[data-list-settings-panel]");
    if (settingsPanel instanceof HTMLElement && !settingsPanel.hidden) {
      setListSettingsOpen(root, state, false);
      return;
    }

    if (state.editingItemId) {
      setItemEditPanelOpen(root, state, null);
      return;
    }

    const panel = root.querySelector("[data-item-panel]");
    if (panel instanceof HTMLElement && !panel.hidden) {
      setItemPanelOpen(root, false);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.defaultPrevented) {
      return;
    }

    const activeElement = document.activeElement;
    const panel = root.querySelector("[data-item-panel]");
    const editOverlay = root.querySelector("[data-item-edit-overlay]");
    const isTypingContext =
      activeElement instanceof HTMLInputElement ||
      activeElement instanceof HTMLTextAreaElement ||
      activeElement instanceof HTMLSelectElement ||
      activeElement?.isContentEditable;

    if (
      isTypingContext ||
      !panel?.hidden ||
      (editOverlay instanceof HTMLElement && !editOverlay.hidden)
    ) {
      return;
    }

    event.preventDefault();
    setItemPanelOpen(root, true);
    renderItemSuggestions(root, state);
  });

  root.querySelector("[data-list-toast-undo]")?.addEventListener("click", async () => {
    if (!state.undoAction) {
      return;
    }

    const undoAction = state.undoAction;
    hideUndoToast(root, state);

    try {
      await undoAction();
    } catch (error) {
      setListMessage(root, "error", error instanceof Error ? error.message : "Could not undo action.");
    }
  });

  itemForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(itemForm);
    const name = String(formData.get("name") || "").trim();
    if (!name) {
      setListMessage(root, "error", "Please enter an item name.");
      return;
    }

    const payload = { name };
    const categoryId = String(formData.get("category_id") || "").trim();
    const quantityText = String(formData.get("quantity_text") || "").trim();
    const note = String(formData.get("note") || "").trim();
    if (categoryId) {
      payload.category_id = categoryId;
    }
    if (quantityText) {
      payload.quantity_text = quantityText;
    }
    if (note) {
      payload.note = note;
    }

    try {
      const createdItem = await postJson(`/api/v1/lists/${listId}/items`, payload);
      upsertItem(state, createdItem);
      itemForm.reset();
      const addSearch = root.querySelector("[data-item-category-search]");
      if (addSearch instanceof HTMLInputElement) {
        addSearch.value = "";
      }
      setCategoryRadioValue(root, 'input[name="category_id"]', "");
      syncCategoryRadioGroups(root, state);
      renderItems(root, state);
      setItemPanelOpen(root, false);
      hideUndoToast(root, state);
      setListMessage(root, "success", "Item added.");
    } catch (error) {
      setListMessage(root, "error", error instanceof Error ? error.message : "Could not add item.");
    }
  });

  itemEditForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.editingItemId) {
      return;
    }

    const formData = new FormData(itemEditForm);
    const payload = {
      name: String(formData.get("name") || "").trim(),
      quantity_text: String(formData.get("quantity_text") || "").trim() || null,
      note: String(formData.get("note") || "").trim() || null,
      category_id: String(formData.get("edit_category_id") || "").trim() || null,
    };

    if (!payload.name) {
      setListMessage(root, "error", "Please enter an item name.");
      return;
    }

    try {
      const updatedItem = await fetchJson(`/api/v1/items/${state.editingItemId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      upsertItem(state, updatedItem);
      renderItems(root, state);
      setItemEditPanelOpen(root, state, updatedItem.id);
      setListMessage(root, "success", "Item updated.");
    } catch (error) {
      setListMessage(root, "error", error instanceof Error ? error.message : "Could not save item.");
    }
  });

  root.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    const toggleId = target.dataset.itemToggle;
    const deleteId = target.dataset.itemDelete;
    const reuseItemId = target.dataset.itemReuse;
    const categoryMove = target.dataset.settingsCategoryMove;
    const categoryId = target.dataset.categoryId;
    const editCard = target.closest("[data-item-edit]");

    if (editCard && !target.closest("button")) {
      setItemEditPanelOpen(root, state, editCard.dataset.itemEdit || null);
      return;
    }

    if (!toggleId && !deleteId && !reuseItemId && !categoryMove) {
      return;
    }

    try {
      if (categoryMove && categoryId) {
        const orderedCategoryIds = getOrderedCategoryIds(state);
        const currentIndex = orderedCategoryIds.indexOf(categoryId);
        if (currentIndex === -1) {
          return;
        }

        const nextIndex = categoryMove === "up" ? currentIndex - 1 : currentIndex + 1;
        if (nextIndex < 0 || nextIndex >= orderedCategoryIds.length) {
          return;
        }

        const nextOrderedCategoryIds = [...orderedCategoryIds];
        [nextOrderedCategoryIds[currentIndex], nextOrderedCategoryIds[nextIndex]] = [
          nextOrderedCategoryIds[nextIndex],
          nextOrderedCategoryIds[currentIndex],
        ];

        setCategoryOrder(state, deriveManualCategoryIds(state, nextOrderedCategoryIds));
        await saveCategoryOrder(root, state);
        renderItems(root, state);
        return;
      }

      if (reuseItemId) {
        const existingItem = state.items.get(reuseItemId);
        if (!existingItem) {
          throw new Error("Could not find that item.");
        }
        if (existingItem.checked) {
          const updatedItem = await postJson(`/api/v1/items/${reuseItemId}/uncheck`, {});
          upsertItem(state, updatedItem);
          itemForm.reset();
          renderItems(root, state);
          setItemPanelOpen(root, false);
          highlightItem(root, state, reuseItemId);
          showUndoToast(root, state, `${existingItem.name} added back to the list.`, async () => {
            const revertedItem = await postJson(`/api/v1/items/${reuseItemId}/check`, {});
            upsertItem(state, revertedItem);
            renderItems(root, state);
          });
          setListMessage(root, "success", "Item added back to the list.");
          return;
        }

        setItemPanelOpen(root, false);
        highlightItem(root, state, reuseItemId);
        return;
      }

      if (toggleId) {
        const existingItem = state.items.get(toggleId);
        if (!existingItem) {
          throw new Error("Could not find that item.");
        }
        const action = existingItem.checked ? "uncheck" : "check";
        const updatedItem = await postJson(`/api/v1/items/${toggleId}/${action}`, {});
        upsertItem(state, updatedItem);
        renderItems(root, state);
        showUndoToast(root, state, `${existingItem.name} ${action === "check" ? "checked" : "unchecked"}.`, async () => {
          const revertedAction = action === "check" ? "uncheck" : "check";
          const revertedItem = await postJson(`/api/v1/items/${toggleId}/${revertedAction}`, {});
          upsertItem(state, revertedItem);
          renderItems(root, state);
        });
        return;
      }

      const deletedItem = state.items.get(deleteId);
      if (!deletedItem) {
        throw new Error("Could not find that item.");
      }
      const response = await fetch(`/api/v1/items/${deleteId}`, { method: "DELETE" });
      if (response.status === 401) {
        window.location.assign("/login");
        throw new Error("Unauthorized");
      }
      if (!response.ok) {
        throw new Error("Could not delete item.");
      }
      removeItem(state, deleteId);
      renderItems(root, state);
      showUndoToast(root, state, `${deletedItem.name} deleted.`, async () => {
        const restoredItem = await postJson(`/api/v1/lists/${listId}/items`, {
          name: deletedItem.name,
          quantity_text: deletedItem.quantity_text,
          note: deletedItem.note,
          category_id: deletedItem.category_id,
          sort_order: deletedItem.sort_order,
        });
        let nextItem = restoredItem;
        if (deletedItem.checked) {
          nextItem = await postJson(`/api/v1/items/${restoredItem.id}/check`, {});
        }
        upsertItem(state, nextItem);
        renderItems(root, state);
      });
      if (state.editingItemId === deleteId) {
        setItemEditPanelOpen(root, state, null);
      }
      setListMessage(root, "success", "Item deleted.");
    } catch (error) {
      setListMessage(root, "error", error instanceof Error ? error.message : "List action failed.");
    }
  });

  root.querySelector("[data-item-edit-delete]")?.addEventListener("click", async () => {
    if (!state.editingItemId) {
      return;
    }

    const deleteButton = root.querySelector(`[data-item-delete="${state.editingItemId}"]`);
    if (!(deleteButton instanceof HTMLElement)) {
      return;
    }
    deleteButton.click();
  });

  try {
    await refresh();
    connectListSocket(root, state);
  } catch (error) {
    setListMessage(root, "error", error instanceof Error ? error.message : "Could not load the list.");
  }
}

async function registerWithPasskey(root, form) {
  const formData = new FormData(form);
  const options = await postJson("/api/v1/auth/register/options", {
    email: formData.get("email"),
    display_name: formData.get("display_name"),
  });
  const credential = await navigator.credentials.create({
    publicKey: publicKeyFromJSON(options),
  });
  await postJson("/api/v1/auth/register/verify", {
    credential: credentialToJSON(credential),
  });
  setMessage(root, "success", "Passkey created. Redirecting to your dashboard...");
  window.location.assign("/");
}

async function loginWithPasskey(root, form) {
  const formData = new FormData(form);
  const options = await postJson("/api/v1/auth/login/options", {
    email: formData.get("email"),
  });
  const credential = await navigator.credentials.get({
    publicKey: publicKeyFromJSON(options),
  });
  await postJson("/api/v1/auth/login/verify", {
    credential: credentialToJSON(credential),
  });
  setMessage(root, "success", "Passkey accepted. Redirecting to your dashboard...");
  window.location.assign("/");
}

function initPasskeyAuth() {
  const root = document.querySelector("[data-passkey-auth]");
  if (!root) {
    return;
  }

  if (!window.PublicKeyCredential || !navigator.credentials) {
    setMessage(root, "error", "This browser does not support passkeys.");
    toggleButtons(root, true);
    return;
  }

  const registerForm = root.querySelector("[data-passkey-register]");
  const loginForm = root.querySelector("[data-passkey-login]");

  root.querySelector("[data-passkey-register-button]").addEventListener("click", async () => {
    toggleButtons(root, true);
    try {
      await registerWithPasskey(root, registerForm);
    } catch (error) {
      setMessage(root, "error", error instanceof Error ? error.message : "Passkey registration failed.");
    } finally {
      toggleButtons(root, false);
    }
  });

  root.querySelector("[data-passkey-login-button]").addEventListener("click", async () => {
    toggleButtons(root, true);
    try {
      await loginWithPasskey(root, loginForm);
    } catch (error) {
      setMessage(root, "error", error instanceof Error ? error.message : "Passkey login failed.");
    } finally {
      toggleButtons(root, false);
    }
  });
}

initPasskeyAuth();
initDashboard();
initListDetail();
