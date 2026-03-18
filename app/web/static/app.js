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
  if (!toast || !message) {
    return;
  }

  if (state.undoTimerId) {
    window.clearTimeout(state.undoTimerId);
  }
  state.undoTimerId = null;
  state.undoAction = null;
  message.textContent = "";
  toast.hidden = true;
}

function showUndoToast(root, state, messageText, undoAction) {
  const toast = root.querySelector("[data-list-toast]");
  const message = root.querySelector("[data-list-toast-message]");
  if (!toast || !message) {
    return;
  }

  hideUndoToast(root, state);
  state.undoAction = undoAction;
  message.textContent = messageText;
  toast.hidden = false;
  state.undoTimerId = window.setTimeout(() => {
    hideUndoToast(root, state);
  }, 5000);
}

function normalizeItemName(value) {
  return value.trim().replace(/\s+/g, " ").toLowerCase();
}

function setItemPanelOpen(root, isOpen) {
  const panel = root.querySelector("[data-item-panel]");
  const toggle = root.querySelector("[data-item-form-toggle]");
  const nameInput = root.querySelector("[data-item-name-input]");

  if (!panel || !toggle) {
    return;
  }

  panel.hidden = !isOpen;
  toggle.setAttribute("aria-expanded", String(isOpen));

  if (isOpen && nameInput instanceof HTMLElement) {
    window.setTimeout(() => {
      nameInput.focus();
    }, 0);
  }
}

function formatSuggestionMeta(item) {
  const meta = [];
  if (item.quantity_text) {
    meta.push(item.quantity_text);
  }
  if (item.note) {
    meta.push(item.note);
  }
  meta.push(item.checked ? "checked earlier" : "already on this list");
  return meta.join(" / ");
}

function renderItemSuggestions(root, state) {
  const suggestionsNode = root.querySelector("[data-item-suggestions]");
  const nameInput = root.querySelector("[data-item-name-input]");

  if (!suggestionsNode || !(nameInput instanceof HTMLInputElement)) {
    return;
  }

  const query = normalizeItemName(nameInput.value);
  suggestionsNode.innerHTML = "";
  if (!query) {
    suggestionsNode.hidden = true;
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
    suggestionsNode.hidden = true;
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
    meta.textContent = formatSuggestionMeta(item);
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

  suggestionsNode.hidden = false;
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

function renderItems(root, state) {
  const container = root.querySelector("[data-item-list]");
  const emptyState = root.querySelector("[data-item-empty]");
  if (!container || !emptyState) {
    return;
  }

  const sortedItems = [...state.items.values()].sort((left, right) => {
    if (left.checked !== right.checked) {
      return Number(left.checked) - Number(right.checked);
    }
    if (left.sort_order !== right.sort_order) {
      return left.sort_order - right.sort_order;
    }
    return left.name.localeCompare(right.name);
  });

  container.innerHTML = "";
  emptyState.hidden = sortedItems.length > 0;

  sortedItems.forEach((item) => {
    const article = document.createElement("article");
    article.className = `item-card${item.checked ? " is-checked" : ""}`;
    article.dataset.itemCard = item.id;

    const main = document.createElement("div");
    main.className = "item-main";

    const checkButton = document.createElement("button");
    checkButton.className = `item-check${item.checked ? " is-checked" : ""}`;
    checkButton.type = "button";
    checkButton.dataset.itemToggle = item.id;
    checkButton.setAttribute("aria-label", item.checked ? `Uncheck ${item.name}` : `Check ${item.name}`);
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
    deleteButton.dataset.itemDelete = item.id;
    deleteButton.textContent = "Delete";
    actions.appendChild(deleteButton);

    article.appendChild(actions);
    container.appendChild(article);
  });

  renderItemSuggestions(root, state);
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
  const [groceryList, items] = await Promise.all([
    fetchJson(`/api/v1/lists/${listId}`),
    fetchJson(`/api/v1/lists/${listId}/items`),
  ]);

  const title = root.querySelector("[data-list-title]");
  if (title) {
    title.textContent = groceryList.name;
  }

  replaceItems(state, items);
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
  const nameInput = root.querySelector("[data-item-name-input]");
  const listId = root.dataset.listId;
  const state = {
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

  root.querySelector("[data-item-form-close]")?.addEventListener("click", () => {
    setItemPanelOpen(root, false);
  });

  nameInput?.addEventListener("input", () => {
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
    const quantityText = String(formData.get("quantity_text") || "").trim();
    const note = String(formData.get("note") || "").trim();
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
      renderItems(root, state);
      setItemPanelOpen(root, false);
      hideUndoToast(root, state);
      setListMessage(root, "success", "Item added.");
    } catch (error) {
      setListMessage(root, "error", error instanceof Error ? error.message : "Could not add item.");
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

    if (!toggleId && !deleteId && !reuseItemId) {
      return;
    }

    try {
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
      setListMessage(root, "success", "Item deleted.");
    } catch (error) {
      setListMessage(root, "error", error instanceof Error ? error.message : "List action failed.");
    }
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
