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

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof data.detail === "string" ? data.detail : "Passkey request failed.";
    throw new Error(message);
  }

  return data;
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
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

function renderItems(root, items) {
  const container = root.querySelector("[data-item-list]");
  const emptyState = root.querySelector("[data-item-empty]");
  if (!container || !emptyState) {
    return;
  }

  const sortedItems = [...items].sort((left, right) => {
    if (left.checked !== right.checked) {
      return Number(left.checked) - Number(right.checked);
    }
    return left.sort_order - right.sort_order;
  });

  container.innerHTML = "";
  emptyState.hidden = sortedItems.length > 0;

  sortedItems.forEach((item) => {
    const article = document.createElement("article");
    article.className = `item-card${item.checked ? " is-checked" : ""}`;
    const quantity = item.quantity_text ? `<p class="item-meta">Qty: ${item.quantity_text}</p>` : "";
    const note = item.note ? `<p class="item-meta">${item.note}</p>` : "";

    article.innerHTML = `
      <div>
        <h3>${item.name}</h3>
        ${quantity}
        ${note}
      </div>
      <div class="item-actions">
        <button type="button" data-item-toggle="${item.id}">
          ${item.checked ? "Uncheck" : "Check"}
        </button>
        <button type="button" data-item-delete="${item.id}">Delete</button>
      </div>
    `;
    container.appendChild(article);
  });
}

async function loadListDetail(root) {
  const listId = root.dataset.listId;
  const [groceryList, items] = await Promise.all([
    fetchJson(`/api/v1/lists/${listId}`),
    fetchJson(`/api/v1/lists/${listId}/items`),
  ]);

  const title = root.querySelector("[data-list-title]");
  if (title) {
    title.textContent = groceryList.name;
  }

  renderItems(root, items);
}

async function initListDetail() {
  const root = document.querySelector("[data-list-detail]");
  if (!root) {
    return;
  }

  const itemForm = root.querySelector("[data-item-form]");
  const listId = root.dataset.listId;

  const refresh = async () => {
    setListMessage(root, "", "");
    await loadListDetail(root);
  };

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
      await postJson(`/api/v1/lists/${listId}/items`, payload);
      itemForm.reset();
      await refresh();
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

    if (!toggleId && !deleteId) {
      return;
    }

    try {
      if (toggleId) {
        const action = target.textContent?.includes("Uncheck") ? "uncheck" : "check";
        await postJson(`/api/v1/items/${toggleId}/${action}`, {});
        await refresh();
        return;
      }

      const response = await fetch(`/api/v1/items/${deleteId}`, { method: "DELETE" });
      if (!response.ok) {
        throw new Error("Could not delete item.");
      }
      await refresh();
      setListMessage(root, "success", "Item deleted.");
    } catch (error) {
      setListMessage(root, "error", error instanceof Error ? error.message : "List action failed.");
    }
  });

  try {
    await refresh();
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
