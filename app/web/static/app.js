const LANGUAGE_COOKIE_NAME = "listerine_locale";
const SUPPORTED_LANGUAGE_OPTIONS = [
  { value: "", label: "Browser default" },
  { value: "en", label: "English" },
  { value: "de", label: "Deutsch" },
];

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

function normalizeLanguagePreference(value) {
  return SUPPORTED_LANGUAGE_OPTIONS.some((option) => option.value === value) ? value : "";
}

function getBrowserLanguage() {
  if (typeof navigator === "undefined") {
    return "en";
  }

  if (Array.isArray(navigator.languages) && navigator.languages.length > 0) {
    return navigator.languages[0];
  }

  return navigator.language || "en";
}

function getStoredLanguagePreference() {
  if (typeof document === "undefined") {
    return "";
  }

  const cookie = document.cookie
    .split(";")
    .map((entry) => entry.trim())
    .find((entry) => entry.startsWith(`${LANGUAGE_COOKIE_NAME}=`));
  if (!cookie) {
    return "";
  }

  return normalizeLanguagePreference(decodeURIComponent(cookie.split("=").slice(1).join("=")));
}

function storeLanguagePreference(value) {
  const normalized = normalizeLanguagePreference(value);
  if (typeof document === "undefined") {
    return normalized;
  }

  if (normalized) {
    document.cookie = `${LANGUAGE_COOKIE_NAME}=${encodeURIComponent(normalized)}; path=/; max-age=31536000; SameSite=Lax`;
  } else {
    document.cookie = `${LANGUAGE_COOKIE_NAME}=; path=/; max-age=0; SameSite=Lax`;
  }

  return normalized;
}

function getPreferredLocale() {
  return getStoredLanguagePreference() || getCurrentLocale();
}

function applyLanguagePreference(value = getStoredLanguagePreference()) {
  const normalized = normalizeLanguagePreference(value);
  if (typeof document !== "undefined") {
    document.documentElement.lang = normalized || getCurrentLocale();
  }
  return normalized;
}

function languagePreferenceLabel(value) {
  const normalized = normalizeLanguagePreference(value);
  const option = SUPPORTED_LANGUAGE_OPTIONS.find((entry) => entry.value === normalized);
  if (!option || !normalized) {
    return translate(
      "settings.language_browser_default_with_locale",
      { locale: getCurrentLocale() },
      "Browser default ({locale})"
    );
  }
  return option.label;
}

function syncLanguageSettings(root) {
  const preference = applyLanguagePreference();
  const select = root.querySelector("[data-language-settings-select]");
  const summary = root.querySelector("[data-language-settings-summary]");

  if (select instanceof HTMLSelectElement) {
    select.value = preference;
  }

  if (summary instanceof HTMLElement) {
    summary.textContent = languagePreferenceLabel(preference);
  }
}

function setLanguageSettingsOpen(root, isOpen) {
  const overlay = root.querySelector("[data-language-settings-overlay]");
  const panel = root.querySelector("[data-language-settings-panel]");
  if (!(overlay instanceof HTMLElement) || !(panel instanceof HTMLElement)) {
    return;
  }

  overlay.hidden = !isOpen;
  panel.hidden = !isOpen;
  if (isOpen) {
    syncLanguageSettings(root);
    root.querySelector("[data-language-settings-select]")?.focus();
  }
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

function getI18nState() {
  const state = globalThis.__appI18n;
  if (!state || typeof state !== "object") {
    return { locale: "en", catalog: {} };
  }
  if ((!state.catalog || typeof state.catalog !== "object") && typeof state.catalogBase64 === "string") {
    try {
      state.catalog = JSON.parse(atob(state.catalogBase64));
    } catch {
      state.catalog = {};
    }
  }
  return {
    locale: typeof state.locale === "string" ? state.locale : "en",
    catalog: state.catalog && typeof state.catalog === "object" ? state.catalog : {},
  };
}

function getCurrentLocale() {
  return getI18nState().locale || "en";
}

function resolveTranslation(key) {
  return key.split(".").reduce((current, part) => {
    if (!current || typeof current !== "object") {
      return undefined;
    }
    return current[part];
  }, getI18nState().catalog);
}

function interpolateTranslation(template, params = {}) {
  return template.replace(/\{(\w+)\}/g, (_, key) => String(params[key] ?? `{${key}}`));
}

function translate(key, params = {}, fallback = key) {
  const value = resolveTranslation(key);
  if (typeof value !== "string") {
    return interpolateTranslation(fallback, params);
  }
  return interpolateTranslation(value, params);
}

function translatePlural(key, count, params = {}, fallback = {}) {
  const locale = getCurrentLocale();
  const category = new Intl.PluralRules(locale).select(count);
  const entry = resolveTranslation(key);
  if (entry && typeof entry === "object") {
    const template = entry[category] || entry.other;
    if (typeof template === "string") {
      return interpolateTranslation(template, { count, ...params });
    }
  }
  const template = count === 1 ? fallback.one : fallback.other;
  return interpolateTranslation(template || "{count}", { count, ...params });
}

function navigateTo(url) {
  if (typeof globalThis.__appNavigateTo === "function") {
    globalThis.__appNavigateTo(url);
    return;
  }

  window.location.assign(url);
}

async function registerServiceWorker() {
  if (typeof window === "undefined" || typeof navigator === "undefined") {
    return null;
  }

  if (!("serviceWorker" in navigator)) {
    return null;
  }

  if (navigator.webdriver) {
    return null;
  }

  return navigator.serviceWorker.register("/service-worker.js");
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (response.status === 401) {
    navigateTo("/login");
    throw new Error(translate("common.errors.unauthorized", {}, "Unauthorized"));
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof data.detail === "string"
      ? data.detail
      : translate("common.errors.passkey_request_failed", {}, "Passkey request failed.");
    throw new Error(message);
  }

  return data;
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (response.status === 401) {
    navigateTo("/login");
    throw new Error(translate("common.errors.unauthorized", {}, "Unauthorized"));
  }
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const message = typeof data.detail === "string"
      ? data.detail
      : translate("common.errors.request_failed", {}, "Request failed.");
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

function setPasskeyManagementMessage(root, type, message) {
  const errorNode = root.querySelector("[data-passkey-error]");
  const successNode = root.querySelector("[data-passkey-success]");

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

function setInviteMessage(root, type, message) {
  const errorNode = root.querySelector("[data-invite-error]");
  const successNode = root.querySelector("[data-invite-success]");

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
      const locked = node.getAttribute("data-passkey-locked") === "true";
      node.disabled = disabled || locked;
    });
}

function syncDashboardModalState(root) {
  const overlays = [
    root.querySelector("[data-dashboard-add-overlay]"),
    root.querySelector("[data-dashboard-household-overlay]"),
    root.querySelector("[data-dashboard-list-overlay]"),
  ];
  const hasModalOpen = overlays.some((overlay) => overlay instanceof HTMLElement && !overlay.hidden);
  document.body.classList.toggle("has-list-modal-open", hasModalOpen);
}

function setDashboardPanelOpen(root, panelName, isOpen) {
  const panels = {
    add: {
      overlay: root.querySelector("[data-dashboard-add-overlay]"),
      panel: root.querySelector("[data-dashboard-add-panel]"),
    },
    household: {
      overlay: root.querySelector("[data-dashboard-household-overlay]"),
      panel: root.querySelector("[data-dashboard-household-panel]"),
      focus: root.querySelector("[data-household-name-input]"),
    },
    list: {
      overlay: root.querySelector("[data-dashboard-list-overlay]"),
      panel: root.querySelector("[data-dashboard-list-panel]"),
      focus: root.querySelector("[data-list-name-input]"),
    },
  };
  const toggle = root.querySelector("[data-dashboard-add-toggle]");

  Object.entries(panels).forEach(([name, nodes]) => {
    const shouldOpen = isOpen && name === panelName;
    if (nodes.overlay instanceof HTMLElement) {
      nodes.overlay.hidden = !shouldOpen;
    }
    if (nodes.panel instanceof HTMLElement) {
      nodes.panel.hidden = !shouldOpen;
    }
  });

  if (toggle instanceof HTMLElement) {
    toggle.setAttribute("aria-expanded", String(isOpen));
  }

  syncDashboardModalState(root);

  if (isOpen) {
    const activePanel = panels[panelName];
    if (activePanel?.focus instanceof HTMLElement) {
      window.setTimeout(() => {
        activePanel.focus.focus();
      }, 0);
    }
  }
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
  placeholder.textContent = households.length
    ? translate("dashboard.select_household", {}, "Select a household")
    : translate("dashboard.create_household_first", {}, "Create a household first");
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

function updateDashboardListOptions(root, households, listsByHousehold) {
  const group = root.querySelector("[data-dashboard-list-group]");
  const emptyState = root.querySelector("[data-dashboard-list-empty]");
  if (!group || !emptyState) {
    return;
  }

  const listOptions = households.flatMap((household) =>
    (listsByHousehold.get(household.id) || []).map((list) => ({
      householdName: household.name,
      id: list.id,
      name: list.name,
    }))
  );

  group.innerHTML = "";
  emptyState.hidden = listOptions.length > 0;
  if (!emptyState.hidden) {
    group.appendChild(emptyState);
    return;
  }

  listOptions.forEach((list) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "dashboard-add-list-button";
    button.setAttribute("data-dashboard-open-list", list.id);
    button.innerHTML = `
      <strong>${list.name}</strong>
      <small>${list.householdName}</small>
    `;
    group.appendChild(button);
  });
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
      <div class="household-card-header">
        <div>
          <h3>${household.name}</h3>
          <p class="household-meta">${translatePlural("dashboard.list_count", lists.length, {}, { one: "{count} list", other: "{count} lists" })}</p>
        </div>
        <button type="button" class="secondary-button" data-create-invite="${household.id}">
          ${translate("dashboard.create_invite_link", {}, "Create invite link")}
        </button>
      </div>
      <div class="household-invite-output" data-invite-output="${household.id}" hidden>
        <p class="dashboard-helper">${translate("dashboard.share_invite_hint", {}, "Share this link within 24 hours:")}</p>
        <div class="household-invite-row">
          <input type="text" readonly data-invite-link-input="${household.id}" />
          <button type="button" class="secondary-button" data-copy-invite="${household.id}">
            ${translate("common.copy", {}, "Copy")}
          </button>
        </div>
      </div>
    `;

    const listGrid = document.createElement("ul");
    listGrid.className = "list-grid";

    if (lists.length === 0) {
      const emptyListState = document.createElement("p");
      emptyListState.className = "dashboard-helper";
      emptyListState.textContent = translate(
        "dashboard.no_lists_yet",
        {},
        "No lists yet. Use the form above to create the first one."
      );
      card.appendChild(emptyListState);
    } else {
      lists.forEach((list) => {
        const item = document.createElement("li");
        item.innerHTML = `
          <a href="/lists/${list.id}">
            <strong>${list.name}</strong>
            <small>${translate("dashboard.open_list", {}, "Open list")}</small>
          </a>
        `;
        listGrid.appendChild(item);
      });
      card.appendChild(listGrid);
    }

    container.appendChild(card);
  });
}

function formatPasskeyDate(value) {
  if (!value) {
    return translate("settings.never_used", {}, "Never used yet");
  }

  return new Date(value).toLocaleString(getPreferredLocale(), {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function renderPasskeys(root, passkeys) {
  const container = root.querySelector("[data-passkey-list]");
  const emptyState = root.querySelector("[data-passkey-empty]");
  if (!container || !emptyState) {
    return;
  }

  container.innerHTML = "";
  emptyState.hidden = passkeys.length > 0;

  passkeys.forEach((passkey, index) => {
    const row = document.createElement("article");
    row.className = "passkey-row";
    row.innerHTML = `
      <div class="passkey-copy">
        <strong>${passkey.name}</strong>
        <span>${translate("settings.added_on", { date: formatPasskeyDate(passkey.created_at) }, "Added {date}")}</span>
        <span>${translate("settings.last_used", { date: formatPasskeyDate(passkey.last_used_at) }, "Last used {date}")}</span>
      </div>
      <div class="passkey-actions">
        <button
          type="button"
          class="secondary-button"
          data-passkey-rename="${passkey.id}"
          data-passkey-current-name="${passkey.name}"
        >
          ${translate("settings.rename", {}, "Rename")}
        </button>
        <button
          type="button"
          class="danger-button"
          data-passkey-delete="${passkey.id}"
          data-passkey-locked="${passkeys.length <= 1 ? "true" : "false"}"
          ${
            passkeys.length <= 1
              ? `title="${translate("settings.delete_disabled", {}, "Add another passkey before deleting this one.")}" aria-disabled="true"`
              : ""
          }
          ${passkeys.length <= 1 ? "disabled" : ""}
        >
          ${translate("common.delete", {}, "Delete")}
        </button>
      </div>
    `;
    container.appendChild(row);
  });
}

function suggestedPasskeyName(root) {
  return translate(
    "settings.suggested_name",
    { number: root.querySelectorAll(".passkey-row").length + 1 },
    "Passkey {number}"
  );
}

function setPasskeyNameFormState(root, state) {
  const form = root.querySelector("[data-passkey-name-form]");
  const input = root.querySelector("[data-passkey-name-input]");
  const addButton = root.querySelector("[data-passkey-add]");
  const title = root.querySelector("[data-passkey-name-title]");
  const submitButton = root.querySelector("[data-passkey-name-submit]");
  if (
    !(form instanceof HTMLFormElement)
    || !(input instanceof HTMLInputElement)
    || !(title instanceof HTMLElement)
    || !(submitButton instanceof HTMLButtonElement)
  ) {
    return;
  }

  const isOpen = Boolean(state);
  form.hidden = !isOpen;
  if (addButton instanceof HTMLButtonElement) {
    addButton.hidden = isOpen;
  }

  if (!isOpen) {
    form.dataset.mode = "";
    form.dataset.passkeyId = "";
    title.textContent = translate("settings.name_this_passkey", {}, "Name this passkey");
    submitButton.textContent = translate("common.continue", {}, "Continue");
    form.reset();
    return;
  }

  form.dataset.mode = state.mode;
  form.dataset.passkeyId = state.passkeyId || "";
  title.textContent = state.title;
  submitButton.textContent = state.submitLabel;
  input.value = state.name;
  window.setTimeout(() => {
    input.focus();
    input.select();
  }, 0);
}

async function copyText(value) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }

  const helper = document.createElement("textarea");
  helper.value = value;
  helper.setAttribute("readonly", "");
  helper.style.position = "absolute";
  helper.style.left = "-9999px";
  document.body.appendChild(helper);
  helper.select();
  document.execCommand("copy");
  document.body.removeChild(helper);
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
  updateDashboardListOptions(root, households, listsByHousehold);
  renderHouseholds(root, households, listsByHousehold);
}

async function loadPasskeyManagementData(root) {
  const passkeys = await fetchJson("/api/v1/auth/passkeys");
  renderPasskeys(root, passkeys);
}

function togglePasskeyManagementForms(root, disabled) {
  root
    .querySelectorAll("[data-passkey-management] button, [data-passkey-management] input")
    .forEach((node) => {
      const locked = node.getAttribute("data-passkey-locked") === "true";
      node.disabled = disabled || locked;
    });
}

function syncPasskeyManagementModalState(root) {
  const deleteOverlay = root.querySelector("[data-passkey-delete-overlay]");
  const hasModalOpen = deleteOverlay instanceof HTMLElement && !deleteOverlay.hidden;
  document.body.classList.toggle("has-list-modal-open", hasModalOpen);
}

function setPasskeyDeleteConfirmState(root, state) {
  const overlay = root.querySelector("[data-passkey-delete-overlay]");
  const panel = root.querySelector("[data-passkey-delete-panel]");
  const nameNode = root.querySelector("[data-passkey-delete-name]");
  const confirmButton = root.querySelector("[data-passkey-delete-confirm]");
  const copyNode = root.querySelector("[data-passkey-delete-copy]");
  if (
    !(overlay instanceof HTMLElement)
    || !(panel instanceof HTMLElement)
    || !(confirmButton instanceof HTMLButtonElement)
  ) {
    return;
  }

  const isOpen = Boolean(state);
  overlay.hidden = !isOpen;
  panel.hidden = !isOpen;
  if (nameNode instanceof HTMLElement) {
    nameNode.textContent = state?.name || translate("settings.delete_target_fallback", {}, "this passkey");
  }
  if (copyNode instanceof HTMLElement) {
    copyNode.childNodes[0].textContent = `${translate(
      "settings.delete_help_generic",
      {},
      "You must authenticate with another passkey to confirm you still have a working Passkey after deleting one."
    )} `;
  }
  confirmButton.dataset.passkeyId = state?.passkeyId || "";
  syncPasskeyManagementModalState(root);

  if (isOpen) {
    window.setTimeout(() => {
      confirmButton.focus();
    }, 0);
  }
}

function initPasskeyManagement(root, options = {}) {
  if (!root) {
    return;
  }

  const {
    setMessage = setPasskeyManagementMessage,
    toggleForms = togglePasskeyManagementForms,
    refreshData = () => loadPasskeyManagementData(root),
  } = options;

  const refresh = async () => {
    setMessage(root, "", "");
    await refreshData();
  };

  const passkeyNameForm = root.querySelector("[data-passkey-name-form]");

  root.addEventListener("click", async (event) => {
    const addPasskeyButton = event.target.closest("[data-passkey-add]");
    if (addPasskeyButton) {
      if (!window.PublicKeyCredential || !navigator.credentials) {
        setMessage(root, "error", translate("common.errors.unsupported_passkeys", {}, "This browser does not support passkeys."));
        return;
      }
      setMessage(root, "", "");
      setPasskeyNameFormState(root, {
        mode: "add",
        passkeyId: "",
        title: translate("settings.name_this_passkey", {}, "Name this passkey"),
        submitLabel: translate("common.continue", {}, "Continue"),
        name: suggestedPasskeyName(root),
      });
      return;
    }

    const cancelPasskeyNameButton = event.target.closest("[data-passkey-name-cancel]");
    if (cancelPasskeyNameButton) {
      setMessage(root, "", "");
      setPasskeyNameFormState(root, null);
      return;
    }

    const renamePasskeyButton = event.target.closest("[data-passkey-rename]");
    if (renamePasskeyButton) {
      if (!window.PublicKeyCredential || !navigator.credentials) {
        setMessage(root, "error", translate("common.errors.unsupported_passkeys", {}, "This browser does not support passkeys."));
        return;
      }

      const passkeyId = renamePasskeyButton.getAttribute("data-passkey-rename");
      const currentName = renamePasskeyButton.getAttribute("data-passkey-current-name") || "";
      setMessage(root, "", "");
      setPasskeyNameFormState(root, {
        mode: "rename",
        passkeyId,
        title: translate("settings.rename_this_passkey", {}, "Rename this passkey"),
        submitLabel: translate("settings.save_and_verify", {}, "Save and verify"),
        name: currentName,
      });
      return;
    }

    const deletePasskeyButton = event.target.closest("[data-passkey-delete]");
    if (deletePasskeyButton) {
      if (!window.PublicKeyCredential || !navigator.credentials) {
        setMessage(root, "error", translate("common.errors.unsupported_passkeys", {}, "This browser does not support passkeys."));
        return;
      }

      setMessage(root, "", "");
      setPasskeyDeleteConfirmState(root, {
        passkeyId: deletePasskeyButton.getAttribute("data-passkey-delete"),
        name:
          deletePasskeyButton.closest(".passkey-row")?.querySelector(".passkey-copy strong")
            ?.textContent?.trim() || translate("settings.delete_target_fallback", {}, "this passkey"),
      });
      return;
    }

    const closeDeletePasskeyButton = event.target.closest("[data-passkey-delete-close]");
    if (closeDeletePasskeyButton) {
      setPasskeyDeleteConfirmState(root, null);
      return;
    }

    const confirmDeletePasskeyButton = event.target.closest("[data-passkey-delete-confirm]");
    if (confirmDeletePasskeyButton) {
      const passkeyId = confirmDeletePasskeyButton.getAttribute("data-passkey-id");
      if (!passkeyId) {
        setPasskeyDeleteConfirmState(root, null);
        setMessage(root, "error", translate("settings.delete_choose_first", {}, "Choose a passkey to delete first."));
        return;
      }

      toggleForms(root, true);
      try {
        await deletePasskey(root, passkeyId);
        setPasskeyDeleteConfirmState(root, null);
        setPasskeyNameFormState(root, null);
        await refresh();
        setMessage(root, "success", translate("settings.deleted_success", {}, "Passkey deleted after confirming another one worked."));
      } catch (error) {
        setMessage(
          root,
          "error",
          error instanceof Error ? error.message : translate("settings.delete_failed", {}, "Could not delete that passkey.")
        );
      } finally {
        toggleForms(root, false);
      }
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }

    const overlay = root.querySelector("[data-passkey-delete-overlay]");
    if (overlay instanceof HTMLElement && !overlay.hidden) {
      setPasskeyDeleteConfirmState(root, null);
    }
  });

  if (passkeyNameForm instanceof HTMLFormElement) {
    passkeyNameForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const formData = new FormData(passkeyNameForm);
      const passkeyName = String(formData.get("name") || "").trim();
      const mode = passkeyNameForm.dataset.mode;
      const passkeyId = passkeyNameForm.dataset.passkeyId;
      if (!passkeyName) {
        setMessage(root, "error", translate("settings.name_required", {}, "Passkey name is required."));
        const input = root.querySelector("[data-passkey-name-input]");
        if (input instanceof HTMLInputElement) {
          input.focus();
        }
        return;
      }

      toggleForms(root, true);
      try {
        if (mode === "rename") {
          if (!passkeyId) {
            throw new Error(translate("settings.rename_choose_first", {}, "Choose a passkey to rename first."));
          }
          await renamePasskey(root, passkeyId, passkeyName);
        } else {
          await addPasskey(root, passkeyName);
        }
        setPasskeyNameFormState(root, null);
        await refresh();
        setMessage(
          root,
          "success",
          mode === "rename"
            ? translate("settings.renamed_success", {}, "Passkey renamed after confirming it still works.")
            : translate("settings.added_success", {}, "Another passkey is ready to use.")
        );
      } catch (error) {
        setMessage(
          root,
          "error",
          error instanceof Error
            ? error.message
            : mode === "rename"
              ? translate("settings.rename_failed", {}, "Could not rename that passkey.")
              : translate("settings.add_failed", {}, "Could not add another passkey.")
        );
      } finally {
        toggleForms(root, false);
      }
    });
  }

  return refresh();
}

async function addPasskey(root, name) {
  const options = await postJson("/api/v1/auth/passkeys/register/options", { name });
  const credential = await navigator.credentials.create({
    publicKey: publicKeyFromJSON(options),
  });
  await postJson("/api/v1/auth/passkeys/register/verify", {
    credential: credentialToJSON(credential),
  });
}

async function renamePasskey(root, passkeyId, name) {
  const options = await postJson(`/api/v1/auth/passkeys/${passkeyId}/rename/options`, { name });
  const credential = await navigator.credentials.get({
    publicKey: publicKeyFromJSON(options),
  });
  await postJson(`/api/v1/auth/passkeys/${passkeyId}/rename/verify`, {
    credential: credentialToJSON(credential),
  });
}

async function deletePasskey(root, passkeyId) {
  const options = await postJson(`/api/v1/auth/passkeys/${passkeyId}/delete/options`, {});
  const credential = await navigator.credentials.get({
    publicKey: publicKeyFromJSON(options),
  });
  await postJson(`/api/v1/auth/passkeys/${passkeyId}/delete/verify`, {
    credential: credentialToJSON(credential),
  });
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

  root.addEventListener("click", async (event) => {
    const inviteButton = event.target.closest("[data-create-invite]");
    if (inviteButton) {
      const householdId = inviteButton.getAttribute("data-create-invite");
      toggleDashboardForms(root, true);
      try {
        const invite = await postJson(`/api/v1/households/${householdId}/invites`, {});
        const output = root.querySelector(`[data-invite-output="${householdId}"]`);
        const input = root.querySelector(`[data-invite-link-input="${householdId}"]`);
        if (output && input) {
          input.value = invite.invite_url;
          output.hidden = false;
        }
        setDashboardMessage(root, "success", translate("dashboard.invite_link_created", {}, "Invite link created. It stays valid for 24 hours."));
      } catch (error) {
        setDashboardMessage(
          root,
          "error",
          error instanceof Error ? error.message : translate("dashboard.invite_link_create_failed", {}, "Could not create the invite link.")
        );
      } finally {
        toggleDashboardForms(root, false);
      }
      return;
    }

    const copyButton = event.target.closest("[data-copy-invite]");
    if (copyButton) {
      const householdId = copyButton.getAttribute("data-copy-invite");
      const input = root.querySelector(`[data-invite-link-input="${householdId}"]`);
      if (!(input instanceof HTMLInputElement) || !input.value) {
        return;
      }
      try {
        await copyText(input.value);
        setDashboardMessage(root, "success", translate("dashboard.invite_link_copied", {}, "Invite link copied."));
      } catch (error) {
        setDashboardMessage(
          root,
          "error",
          error instanceof Error ? error.message : translate("dashboard.invite_link_copy_failed", {}, "Could not copy the invite link.")
        );
      }
      return;
    }

    const openListButton = event.target.closest("[data-dashboard-open-list]");
    if (openListButton) {
      const listId = openListButton.getAttribute("data-dashboard-open-list");
      if (!listId) {
        setDashboardMessage(root, "error", translate("dashboard.choose_list_before_adding", {}, "Create or choose a list before adding an item."));
        return;
      }

      setDashboardPanelOpen(root, "add", false);
      navigateTo(`/lists/${listId}?addItem=1`);
      return;
    }
  });

  root.querySelector("[data-dashboard-add-toggle]")?.addEventListener("click", () => {
    const panel = root.querySelector("[data-dashboard-add-panel]");
    setDashboardPanelOpen(root, "add", panel?.hidden ?? true);
  });

  root.querySelectorAll("[data-dashboard-add-close]").forEach((node) => {
    node.addEventListener("click", () => {
      setDashboardPanelOpen(root, "add", false);
    });
  });

  root.querySelectorAll("[data-dashboard-household-close]").forEach((node) => {
    node.addEventListener("click", () => {
      setDashboardPanelOpen(root, "household", false);
    });
  });

  root.querySelectorAll("[data-dashboard-list-close]").forEach((node) => {
    node.addEventListener("click", () => {
      setDashboardPanelOpen(root, "list", false);
    });
  });

  root.querySelectorAll("[data-dashboard-panel-back]").forEach((node) => {
    node.addEventListener("click", () => {
      setDashboardPanelOpen(root, "add", true);
    });
  });

  root.querySelectorAll("[data-dashboard-add-option]").forEach((node) => {
    node.addEventListener("click", () => {
      const panelName = node.getAttribute("data-dashboard-add-option");
      if (panelName === "household" || panelName === "list") {
        setDashboardPanelOpen(root, panelName, true);
      }
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }

    const panelNames = ["household", "list", "add"];
    const openPanelName = panelNames.find((name) => {
      const panel = root.querySelector(`[data-dashboard-${name}-panel]`);
      return panel instanceof HTMLElement && !panel.hidden;
    });

    if (openPanelName) {
      setDashboardPanelOpen(root, openPanelName, false);
    }
  });

  householdForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(householdForm);
    toggleDashboardForms(root, true);
    try {
      const name = String(formData.get("name") || "").trim();
      if (!name) {
        throw new Error(translate("dashboard.household_name_required", {}, "Please enter a household name."));
      }
      await postJson("/api/v1/households", { name });
      householdForm.reset();
      await refresh();
      setDashboardPanelOpen(root, "household", false);
      setDashboardMessage(root, "success", translate("dashboard.household_created", {}, "Household created. You can add a list now."));
    } catch (error) {
      setDashboardMessage(
        root,
        "error",
        error instanceof Error ? error.message : translate("dashboard.household_create_failed", {}, "Could not create the household.")
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
        throw new Error(translate("dashboard.choose_household_before_list", {}, "Create or choose a household before creating a list."));
      }
      if (!name) {
        throw new Error(translate("dashboard.list_name_required", {}, "Please enter a list name."));
      }
      const groceryList = await postJson(`/api/v1/households/${householdId}/lists`, { name });
      listForm.reset();
      await refresh();
      setDashboardPanelOpen(root, "list", false);
      navigateTo(`/lists/${groceryList.id}`);
    } catch (error) {
      setDashboardMessage(
        root,
        "error",
        error instanceof Error ? error.message : translate("dashboard.list_create_failed", {}, "Could not create the list.")
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
      error instanceof Error ? error.message : translate("dashboard.load_failed", {}, "Could not load your households.")
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

async function runUndoAction(root, state, undoAction) {
  try {
    await undoAction();
  } catch (error) {
    setListMessage(root, "error", error instanceof Error ? error.message : translate("list_detail.undo_failed", {}, "Could not undo action."));
  }
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
  meta.push(item.checked
    ? translate("list_detail.checked_earlier", {}, "checked earlier")
    : translate("list_detail.already_on_list", {}, "already on this list"));
  return meta.join(" / ");
}

function categorySortKey(state, categoryId) {
  if (!categoryId) {
    return {
      color: "",
      name: translate("list_detail.uncategorized", {}, "Uncategorized"),
      isExplicit: false,
      sortOrder: Number.MAX_SAFE_INTEGER,
    };
  }

  const category = state.categories.get(categoryId);
  if (!category) {
    return {
      color: "",
      name: translate("list_detail.uncategorized", {}, "Uncategorized"),
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
      name: translate("list_detail.no_category", {}, "No category"),
      hint: translate("list_detail.no_category_hint", {}, "Keep this item above the category sections."),
    },
    ...categories,
  ].filter(
    (category, index) =>
      index === 0 || category.id === (currentValue || "") || categoryMatchesQuery(category, searchQuery)
  );

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
    emptyState.textContent = translate(
      "list_detail.create_categories_admin",
      {},
      "Create categories in admin to customize the order for this list."
    );
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
      ? translate("list_detail.pinned_in_order", {}, "Pinned in this list order")
      : translate("list_detail.alphabetical_until_moved", {}, "Alphabetical until you move it");
    copy.appendChild(meta);
    row.appendChild(copy);

    const actions = document.createElement("div");
    actions.className = "settings-category-actions";

    const moveUp = document.createElement("button");
    moveUp.type = "button";
    moveUp.dataset.settingsCategoryMove = "up";
    moveUp.dataset.categoryId = category.id;
    moveUp.setAttribute(
      "aria-label",
      translate("list_detail.move_category_up", { name: category.name }, "Move {name} up")
    );
    moveUp.disabled = index === 0;
    moveUp.textContent = "↑";
    actions.appendChild(moveUp);

    const moveDown = document.createElement("button");
    moveDown.type = "button";
    moveDown.dataset.settingsCategoryMove = "down";
    moveDown.dataset.categoryId = category.id;
    moveDown.setAttribute(
      "aria-label",
      translate("list_detail.move_category_down", { name: category.name }, "Move {name} down")
    );
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
      item.checked
        ? translate("list_detail.suggestion_add_back", { name: item.name }, "Add {name} back to the list")
        : translate("list_detail.suggestion_jump_to", { name: item.name }, "Jump to {name} in the list")
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

const CHECKED_ITEMS_INITIAL_LIMIT = 10;
const CHECKED_ITEMS_LOAD_MORE_COUNT = 100;

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
    headingCopy.className = "item-category-copy";
    const headingTitle = document.createElement("h3");
    headingTitle.textContent = category?.name || translate("list_detail.uncategorized", {}, "Uncategorized");
    headingCopy.appendChild(headingTitle);

    const headingMeta = document.createElement("p");
    headingMeta.className = "item-category-meta";
    headingMeta.textContent = translatePlural("list_detail.item_count", items.length, {}, { one: "{count} item", other: "{count} items" });
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
        item.checked
          ? translate("list_detail.uncheck_item", { name: item.name }, "Uncheck {name}")
          : translate("list_detail.check_item", { name: item.name }, "Check {name}")
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
        quantity.textContent = translate("list_detail.quantity_prefix", { quantity: item.quantity_text }, "Qty: {quantity}");
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
      section.appendChild(article);
    });

    container.appendChild(section);
  });

  if (checkedItems.length > 0) {
    const checkedTotalCount = checkedItems.length + (state.checkedRemainingCount || 0);
    const section = document.createElement("section");
    section.className = "item-category-group";

    const heading = document.createElement("div");
    heading.className = "item-category-header";

    const swatch = document.createElement("span");
    swatch.className = "item-category-swatch";
    swatch.style.background = "#94a3b8";
    heading.appendChild(swatch);

    const headingCopy = document.createElement("div");
    headingCopy.className = "item-category-copy";
    const headingTitle = document.createElement("h3");
    headingTitle.textContent = translate("list_detail.checked_off", {}, "Checked off");
    headingCopy.appendChild(headingTitle);

    const headingMeta = document.createElement("p");
    headingMeta.className = "item-category-meta";
    headingMeta.textContent = translatePlural("list_detail.item_count", checkedTotalCount, {}, { one: "{count} item", other: "{count} items" });
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
      checkButton.setAttribute(
        "aria-label",
        translate("list_detail.uncheck_item", { name: item.name }, "Uncheck {name}")
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
        quantity.textContent = translate("list_detail.quantity_prefix", { quantity: item.quantity_text }, "Qty: {quantity}");
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
      section.appendChild(article);
    });

    if (state.checkedRemainingCount > 0) {
      const remainingCount = state.checkedRemainingCount;
      const loadMoreWrapper = document.createElement("div");
      loadMoreWrapper.className = "checked-items-load-more";

      const loadMoreButton = document.createElement("button");
      loadMoreButton.type = "button";
      loadMoreButton.className = "secondary-button";
      loadMoreButton.textContent = `Load ${Math.min(CHECKED_ITEMS_LOAD_MORE_COUNT, remainingCount)} more`;
      loadMoreButton.addEventListener("click", async () => {
        loadMoreButton.disabled = true;
        try {
          await loadMoreCheckedItems(root, state);
        } finally {
          loadMoreButton.disabled = false;
        }
      });
      loadMoreWrapper.appendChild(loadMoreButton);

      const loadMoreMeta = document.createElement("p");
      loadMoreMeta.className = "item-category-meta";
      loadMoreMeta.textContent = `${remainingCount} older ${remainingCount === 1 ? "item" : "items"} not loaded`;
      loadMoreWrapper.appendChild(loadMoreMeta);

      section.appendChild(loadMoreWrapper);
    }

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

async function loadMoreCheckedItems(root, state) {
  const listId = root.dataset.listId;
  const checkedOffset = [...state.items.values()].filter((item) => item.checked).length;
  const olderItems = await fetchJson(
    `/api/v1/lists/${listId}/items/checked?offset=${checkedOffset}&limit=${CHECKED_ITEMS_LOAD_MORE_COUNT}`,
  );
  olderItems.forEach((item) => {
    state.items.set(item.id, item);
  });
  state.checkedRemainingCount = Math.max((state.checkedRemainingCount || 0) - olderItems.length, 0);
  renderItems(root, state);
  return olderItems;
}

async function restoreCheckedSuggestion(root, state, reuseItemId) {
  const revertedItem = await postJson(`/api/v1/items/${reuseItemId}/check`, {});
  upsertItem(state, revertedItem);
  renderItems(root, state);
}

async function restoreDeletedItem(root, state, listId, deletedItem) {
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
}

async function deleteItem(root, state, listId, itemId) {
  const deletedItem = state.items.get(itemId);
  if (!deletedItem) {
    throw new Error(translate("list_detail.item_not_found", {}, "Could not find that item."));
  }

  const response = await fetch(`/api/v1/items/${itemId}`, { method: "DELETE" });
  if (response.status === 401) {
    navigateTo("/login");
    throw new Error(translate("common.errors.unauthorized", {}, "Unauthorized"));
  }
  if (!response.ok) {
    throw new Error(translate("list_detail.item_delete_failed", {}, "Could not delete item."));
  }

  removeItem(state, itemId);
  renderItems(root, state);
  showUndoToast(
    root,
    state,
    translate("list_detail.item_deleted_named", { name: deletedItem.name }, "{name} deleted."),
    restoreDeletedItem.bind(null, root, state, listId, deletedItem),
  );
  if (state.editingItemId === itemId) {
    setItemEditPanelOpen(root, state, null);
  }
  setListMessage(root, "success", translate("list_detail.item_deleted", {}, "Item deleted."));
}

async function restoreToggledItem(root, state, toggleId, action) {
  const revertedAction = action === "check" ? "uncheck" : "check";
  const revertedItem = await postJson(`/api/v1/items/${toggleId}/${revertedAction}`, {});
  upsertItem(state, revertedItem);
  renderItems(root, state);
}

function handleSocketClose(root, state, reconnect, isDisposed) {
  state.socket = null;
  if (isDisposed()) {
    return;
  }
  setListSyncStatus(root, translate("list_detail.sync_paused", {}, "Live updates paused. Reconnecting..."));
  window.setTimeout(reconnect, 1500);
}

function disposeSocket(state, markDisposed) {
  markDisposed();
  if (typeof state.socket?.close === "function") {
    state.socket.close();
  }
}

async function loadListDetail(root, state) {
  const listId = root.dataset.listId;
  const [groceryList, itemWindow, categories, categoryOrder] = await Promise.all([
    fetchJson(`/api/v1/lists/${listId}`),
    fetchJson(`/api/v1/lists/${listId}/items/window`),
    fetchJson(`/api/v1/lists/${listId}/categories`),
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
  replaceItems(state, itemWindow.items || []);
  state.checkedRemainingCount = itemWindow.checked_remaining_count || 0;
  syncCategoryRadioGroups(root, state);
  renderItems(root, state);
}

function connectListSocket(root, state) {
  const listId = root.dataset.listId;
  if (!listId) {
    setListSyncStatus(root, translate("list_detail.sync_unavailable", {}, "Live updates unavailable."));
    return;
  }

  let isDisposed = false;

  const connect = () => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socketUrl = `${protocol}//${window.location.host}/api/v1/ws/lists/${listId}`;
    setListSyncStatus(root, translate("list_detail.sync_connecting", {}, "Connecting live updates..."));
    state.socket = new WebSocket(socketUrl);

    if (typeof state.socket?.addEventListener !== "function") {
      setListSyncStatus(root, translate("list_detail.sync_unavailable", {}, "Live updates unavailable."));
      return;
    }

    state.socket.addEventListener("open", () => {
      setListSyncStatus(root, translate("list_detail.sync_on", {}, "Live updates on."));
    });

    state.socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.type === "list_snapshot") {
        replaceItems(state, message.payload.items || []);
        state.checkedRemainingCount = message.payload.checked_remaining_count || 0;
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
      handleSocketClose(root, state, connect, () => isDisposed);
    });
  };

  connect();
  window.addEventListener("beforeunload", () => {
    disposeSocket(state, () => {
      isDisposed = true;
    });
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
    checkedRemainingCount: 0,
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

  const shouldOpenItemPanelFromQuery = () => {
    const params = new URLSearchParams(window.location.search);
    return params.get("addItem") === "1";
  };

  const clearItemPanelQuery = () => {
    const url = new URL(window.location.href);
    url.searchParams.delete("addItem");
    window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
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

    await runUndoAction(root, state, undoAction);
  });

  itemForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(itemForm);
    const name = String(formData.get("name") || "").trim();
    if (!name) {
      setListMessage(root, "error", translate("list_detail.item_name_required", {}, "Please enter an item name."));
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
      setListMessage(root, "success", translate("list_detail.item_added", {}, "Item added."));
    } catch (error) {
      setListMessage(root, "error", error instanceof Error ? error.message : translate("list_detail.item_add_failed", {}, "Could not add item."));
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
      setListMessage(root, "error", translate("list_detail.item_name_required", {}, "Please enter an item name."));
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
      setListMessage(root, "success", translate("list_detail.item_updated", {}, "Item updated."));
    } catch (error) {
      setListMessage(root, "error", error instanceof Error ? error.message : translate("list_detail.item_update_failed", {}, "Could not save item."));
    }
  });

  root.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    const toggleId = target.dataset.itemToggle;
    const reuseItemId = target.dataset.itemReuse;
    const categoryMove = target.dataset.settingsCategoryMove;
    const categoryId = target.dataset.categoryId;
    const editCard = target.closest("[data-item-edit]");

    if (editCard && !target.closest("button")) {
      setItemEditPanelOpen(root, state, editCard.dataset.itemEdit || null);
      return;
    }

    if (!toggleId && !reuseItemId && !categoryMove) {
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
          throw new Error(translate("list_detail.item_not_found", {}, "Could not find that item."));
        }
        if (existingItem.checked) {
          const updatedItem = await postJson(`/api/v1/items/${reuseItemId}/uncheck`, {});
          upsertItem(state, updatedItem);
          itemForm.reset();
          renderItems(root, state);
          setItemPanelOpen(root, false);
          highlightItem(root, state, reuseItemId);
          showUndoToast(
            root,
            state,
            translate("list_detail.item_added_back_named", { name: existingItem.name }, "{name} added back to the list."),
            restoreCheckedSuggestion.bind(null, root, state, reuseItemId),
          );
          setListMessage(root, "success", translate("list_detail.item_added_back", {}, "Item added back to the list."));
          return;
        }

        setItemPanelOpen(root, false);
        highlightItem(root, state, reuseItemId);
        return;
      }

      if (toggleId) {
        const existingItem = state.items.get(toggleId);
        if (!existingItem) {
          throw new Error(translate("list_detail.item_not_found", {}, "Could not find that item."));
        }
        const action = existingItem.checked ? "uncheck" : "check";
        const updatedItem = await postJson(`/api/v1/items/${toggleId}/${action}`, {});
        upsertItem(state, updatedItem);
        renderItems(root, state);
        showUndoToast(
          root,
          state,
          action === "check"
            ? translate("list_detail.item_checked_named", { name: existingItem.name }, "{name} checked.")
            : translate("list_detail.item_unchecked_named", { name: existingItem.name }, "{name} unchecked."),
          restoreToggledItem.bind(null, root, state, toggleId, action),
        );
        return;
      }
    } catch (error) {
      setListMessage(root, "error", error instanceof Error ? error.message : translate("list_detail.list_action_failed", {}, "List action failed."));
    }
  });

  root.querySelector("[data-item-edit-delete]")?.addEventListener("click", async () => {
    if (!state.editingItemId) {
      return;
    }

    try {
      await deleteItem(root, state, listId, state.editingItemId);
    } catch (error) {
      setListMessage(root, "error", error instanceof Error ? error.message : translate("list_detail.item_delete_failed", {}, "Could not delete item."));
    }
  });

  try {
    await refresh();
    if (shouldOpenItemPanelFromQuery()) {
      setItemPanelOpen(root, true);
      renderItemSuggestions(root, state);
      clearItemPanelQuery();
    }
    connectListSocket(root, state);
  } catch (error) {
    setListMessage(root, "error", error instanceof Error ? error.message : translate("list_detail.load_failed", {}, "Could not load the list."));
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
  setMessage(root, "success", translate("auth.login.created_redirect", {}, "Passkey created. Redirecting to your dashboard..."));
  navigateTo(root.getAttribute("data-next-url") || "/");
}

async function loginWithPasskey(root, form) {
  void form;
  const options = await postJson("/api/v1/auth/login/options", {});
  const credential = await navigator.credentials.get({
    publicKey: publicKeyFromJSON(options),
  });
  await postJson("/api/v1/auth/login/verify", {
    credential: credentialToJSON(credential),
  });
  setMessage(root, "success", translate("auth.login.accepted_redirect", {}, "Passkey accepted. Redirecting to your dashboard..."));
  navigateTo(root.getAttribute("data-next-url") || "/");
}

async function addPasskeyWithLink(root) {
  const token = root.getAttribute("data-passkey-add-token");
  if (!token) {
    throw new Error(translate("auth.passkey_add.missing_token", {}, "Passkey add link is missing."));
  }

  const options = await postJson(`/api/v1/auth/passkey-add/${token}/options`, {});
  const credential = await navigator.credentials.create({
    publicKey: publicKeyFromJSON(options),
  });
  await postJson(`/api/v1/auth/passkey-add/${token}/verify`, {
    credential: credentialToJSON(credential),
  });
  setMessage(root, "success", translate("auth.passkey_add.created_redirect", {}, "Additional passkey created. Redirecting to your dashboard..."));
  navigateTo("/");
}

async function handlePasskeyLoginClick(root, loginForm) {
  toggleButtons(root, true);
  try {
    await loginWithPasskey(root, loginForm);
  } catch (error) {
    setMessage(root, "error", error instanceof Error ? error.message : translate("auth.login.login_failed", {}, "Passkey login failed."));
  } finally {
    toggleButtons(root, false);
  }
}

function setAuthTab(root, tab) {
  const panels = root.querySelectorAll("[data-auth-tab-panel]");
  const triggers = root.querySelectorAll("[data-auth-tab-trigger]");
  if (!panels.length || !triggers.length) {
    return;
  }

  panels.forEach((panel) => {
    panel.hidden = panel.getAttribute("data-auth-tab-panel") !== tab;
  });
  triggers.forEach((trigger) => {
    trigger.setAttribute(
      "aria-selected",
      trigger.getAttribute("data-auth-tab-trigger") === tab ? "true" : "false"
    );
  });

  if (tab === "signup") {
    root.querySelector('[data-passkey-register] input[name="display_name"]')?.focus();
  }
}

function initPasskeyAuth() {
  const root = document.querySelector("[data-passkey-auth]");
  if (!root) {
    return;
  }

  if (!window.PublicKeyCredential || !navigator.credentials) {
    setMessage(root, "error", translate("common.errors.unsupported_passkeys", {}, "This browser does not support passkeys."));
    toggleButtons(root, true);
    return;
  }

  const registerForm = root.querySelector("[data-passkey-register]");
  const loginForm = root.querySelector("[data-passkey-login]");
  root.querySelectorAll("[data-auth-tab-trigger]").forEach((trigger) => {
    trigger.addEventListener("click", () => {
      setAuthTab(root, trigger.getAttribute("data-auth-tab-trigger"));
    });
  });

  root.querySelector("[data-passkey-register-button]")?.addEventListener("click", async () => {
    toggleButtons(root, true);
    try {
      await registerWithPasskey(root, registerForm);
    } catch (error) {
      setMessage(root, "error", error instanceof Error ? error.message : translate("auth.login.registration_failed", {}, "Passkey registration failed."));
    } finally {
      toggleButtons(root, false);
    }
  });

  root.querySelector("[data-passkey-login-button]")?.addEventListener(
    "click",
    handlePasskeyLoginClick.bind(null, root, loginForm)
  );
}

function initPasskeyAddLink() {
  const root = document.querySelector("[data-passkey-add-link]");
  if (!root) {
    return;
  }

  if (!window.PublicKeyCredential || !navigator.credentials) {
    setMessage(root, "error", translate("common.errors.unsupported_passkeys", {}, "This browser does not support passkeys."));
    toggleButtons(root, true);
    return;
  }

  root.querySelector("[data-passkey-add-link-button]")?.addEventListener("click", async () => {
    toggleButtons(root, true);
    try {
      await addPasskeyWithLink(root);
    } catch (error) {
      setMessage(root, "error", error instanceof Error ? error.message : translate("auth.passkey_add.failed", {}, "Passkey add failed."));
    } finally {
      toggleButtons(root, false);
    }
  });
}

function setSettingsMessage(root, type, message) {
  const errorNode = root.querySelector("[data-settings-error]");
  const successNode = root.querySelector("[data-settings-success]");
  if (!(errorNode instanceof HTMLElement) || !(successNode instanceof HTMLElement)) {
    return;
  }

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

function initUserSettings() {
  const root = document.querySelector("[data-user-settings]");
  if (!root) {
    return;
  }

  applyLanguagePreference();
  syncLanguageSettings(root);
  root.querySelector("[data-language-settings-open]")?.addEventListener("click", () => {
    setLanguageSettingsOpen(root, true);
  });
  root.querySelectorAll("[data-language-settings-close]").forEach((node) => {
    node.addEventListener("click", () => {
      setLanguageSettingsOpen(root, false);
    });
  });
  root.querySelector("[data-language-settings-form]")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const select = root.querySelector("[data-language-settings-select]");
    const preference = storeLanguagePreference(select instanceof HTMLSelectElement ? select.value : "");
    syncLanguageSettings(root);
    setLanguageSettingsOpen(root, false);
    setSettingsMessage(
      root,
      "success",
      translate(
        "settings.language_saved",
        { language: languagePreferenceLabel(preference) },
        "Language set to {language}."
      )
    );
    const url = new URL(window.location.href);
    if (preference) {
      url.searchParams.set("lang", preference);
    } else {
      url.searchParams.delete("lang");
    }
    navigateTo(`${url.pathname}${url.search}${url.hash}`);
  });

  if (!window.PublicKeyCredential || !navigator.credentials) {
    setPasskeyManagementMessage(root, "error", translate("common.errors.unsupported_passkeys", {}, "This browser does not support passkeys."));
    toggleButtons(root, true);
    return;
  }

  initPasskeyManagement(root, {
    setMessage: setPasskeyManagementMessage,
    toggleForms: togglePasskeyManagementForms,
    refreshData: () => loadPasskeyManagementData(root),
  }).catch((error) => {
    setPasskeyManagementMessage(
      root,
      "error",
      error instanceof Error ? error.message : translate("settings.load_failed", {}, "Could not load your passkeys.")
    );
  });
}

function formatInviteExpiry(value) {
  const date = new Date(value);
  return date.toLocaleString(getPreferredLocale(), {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

async function initHouseholdInvite() {
  const root = document.querySelector("[data-household-invite]");
  if (!root) {
    return;
  }

  const token = root.getAttribute("data-invite-token");
  const loadingNode = root.querySelector("[data-invite-loading]");
  const readyNode = root.querySelector("[data-invite-ready]");
  const householdNameNode = root.querySelector("[data-invite-household-name]");
  const expiryNode = root.querySelector("[data-invite-expiry]");
  const membershipNoteNode = root.querySelector("[data-invite-membership-note]");
  const acceptButton = root.querySelector("[data-invite-accept]");

  try {
    const invite = await fetchJson(`/api/v1/households/invites/${token}`);
    loadingNode.hidden = true;
    readyNode.hidden = false;
    householdNameNode.textContent = invite.household_name;
    expiryNode.textContent = translate("invite.expires_on", { date: formatInviteExpiry(invite.expires_at) }, "This link expires on {date}.");
    membershipNoteNode.hidden = !invite.already_member;
  } catch (error) {
    loadingNode.hidden = true;
    setInviteMessage(
      root,
      "error",
      error instanceof Error ? error.message : translate("invite.unavailable", {}, "This invite link is no longer available."),
    );
    return;
  }

  acceptButton.addEventListener("click", async () => {
    acceptButton.disabled = true;
    setInviteMessage(root, "", "");
    try {
      const household = await postJson(`/api/v1/households/invites/${token}/accept`, {});
      setInviteMessage(root, "success", translate("invite.accepted", { household: household.name }, "You joined {household}. Redirecting now..."));
      window.setTimeout(() => {
        navigateTo("/");
      }, 500);
    } catch (error) {
      setInviteMessage(
        root,
        "error",
        error instanceof Error ? error.message : translate("invite.accept_failed", {}, "Could not accept the invite."),
      );
      acceptButton.disabled = false;
    }
  });
}

function initApp() {
  applyLanguagePreference();
  registerServiceWorker().catch(() => undefined);
  initPasskeyAuth();
  initPasskeyAddLink();
  initUserSettings();
  initDashboard();
  initHouseholdInvite();
  initListDetail();
}

if (typeof document !== "undefined") {
  initApp();
}

export {
  base64UrlToBytes,
  bytesToBase64Url,
  getI18nState,
  getCurrentLocale,
  interpolateTranslation,
  translate,
  translatePlural,
  publicKeyFromJSON,
  credentialToJSON,
  normalizeLanguagePreference,
  getBrowserLanguage,
  getStoredLanguagePreference,
  storeLanguagePreference,
  getPreferredLocale,
  applyLanguagePreference,
  languagePreferenceLabel,
  syncLanguageSettings,
  setLanguageSettingsOpen,
  registerServiceWorker,
  navigateTo,
  postJson,
  fetchJson,
  setMessage,
  toggleButtons,
  setDashboardMessage,
  toggleDashboardForms,
  syncDashboardModalState,
  setDashboardPanelOpen,
  updateHouseholdOptions,
  updateDashboardListOptions,
  renderHouseholds,
  loadDashboardData,
  formatPasskeyDate,
  renderPasskeys,
  suggestedPasskeyName,
  setPasskeyNameFormState,
  setPasskeyDeleteConfirmState,
  addPasskey,
  renamePasskey,
  deletePasskey,
  initDashboard,
  setListMessage,
  setListSyncStatus,
  hideUndoToast,
  showUndoToast,
  normalizeItemName,
  normalizeSearchText,
  syncModalState,
  setItemPanelOpen,
  formatSuggestionMeta,
  categorySortKey,
  decorateItem,
  setCategoryRadioValue,
  categoryMatchesQuery,
  syncCategoryRadioGroup,
  syncCategoryRadioGroups,
  getManualCategoryIds,
  getAlphabeticalCategoryIds,
  getOrderedCategoryIds,
  getDisplayedCategoryIds,
  deriveManualCategoryIds,
  setCategoryOrder,
  saveCategoryOrder,
  setItemEditPanelOpen,
  renderCategoryOrderSettings,
  setListSettingsOpen,
  renderItemSuggestions,
  highlightItem,
  compareActiveItems,
  compareCheckedItems,
  getActiveGroupOrder,
  renderItems,
  replaceItems,
  upsertItem,
  removeItem,
  loadMoreCheckedItems,
  restoreToggledItem,
  restoreCheckedSuggestion,
  restoreDeletedItem,
  runUndoAction,
  handleSocketClose,
  disposeSocket,
  loadListDetail,
  connectListSocket,
  initListDetail,
  registerWithPasskey,
  loginWithPasskey,
  addPasskeyWithLink,
  handlePasskeyLoginClick,
  setSettingsMessage,
  initPasskeyAuth,
  initPasskeyAddLink,
  initUserSettings,
  formatInviteExpiry,
  initHouseholdInvite,
  initApp,
};
