import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

import {
  applyLanguagePreference,
  cloneDemoItem,
  createDemoItem,
  formatInviteExpiry,
  formatHiddenUntilLabel,
  formatPasskeyDate,
  getDemoPayload,
  getPreferredLocale,
  hideItemForLater,
  initUserSettings,
  isItemHidden,
  isDemoList,
  languagePreferenceLabel,
  loadListDetail,
  loadMoreCheckedItems,
  normalizeLanguagePreference,
  openItemPanelForCategory,
  registerServiceWorker,
  renderCategoryOrderSettings,
  renderHouseholds,
  renderPasskeys,
  renderItems,
  renderItemSuggestions,
  restoreCheckedSuggestion,
  restoreDeletedItem,
  restoreToggledItem,
  saveCategoryOrder,
  setCategoryOrder,
  setDemoItemChecked,
  setLanguageSettingsOpen,
  setListSyncStatus,
  storeLanguagePreference,
  syncLanguageSettings,
  updateDemoItem,
  connectListSocket,
  boundedEditDistance,
  fuzzyItemNameDistance,
  itemSuggestionMatch,
  offlineListStorageKey,
  loadOfflineListState,
  persistOfflineListState,
  applyOfflineListState,
  showOfflineSavedMessage,
  isBrowserOffline,
  isOfflineRequestError,
  shouldQueueItemMutation,
  createOfflineItem,
  applyLocalCheckedState,
  createItemWithOfflineFallback,
  updateItemWithOfflineFallback,
  setItemCheckedWithOfflineFallback,
  applyOfflineSyncResult,
  flushOfflineMutations,
  restoreHiddenItem,
  transitionAuthPanels,
  setAuthTab,
} from "./app.js";

function setGlobalProperty(name, value) {
  Object.defineProperty(globalThis, name, {
    configurable: true,
    writable: true,
    value,
  });
}

function setDomGlobals(dom) {
  setGlobalProperty("HTMLElement", dom.window.HTMLElement);
  setGlobalProperty("HTMLInputElement", dom.window.HTMLInputElement);
  setGlobalProperty("HTMLSelectElement", dom.window.HTMLSelectElement);
}

function restoreDomGlobals(originals) {
  setGlobalProperty("HTMLElement", originals.HTMLElement);
  setGlobalProperty("HTMLInputElement", originals.HTMLInputElement);
  setGlobalProperty("HTMLSelectElement", originals.HTMLSelectElement);
}

test("registerServiceWorker skips registration when service workers are unavailable", async () => {
  const originalWindow = globalThis.window;
  const originalNavigator = globalThis.navigator;

  setGlobalProperty("window", {});
  setGlobalProperty("navigator", {});

  try {
    const result = await registerServiceWorker();
    assert.equal(result, null);
  } finally {
    globalThis.window = originalWindow;
    globalThis.navigator = originalNavigator;
  }
});

test("registerServiceWorker skips registration during webdriver automation", async () => {
  const originalWindow = globalThis.window;
  const originalNavigator = globalThis.navigator;

  setGlobalProperty("window", {});
  setGlobalProperty("navigator", {
    webdriver: true,
    serviceWorker: {
      register: async () => {
        throw new Error("register should not be called during webdriver automation");
      },
    },
  });

  try {
    const result = await registerServiceWorker();
    assert.equal(result, null);
  } finally {
    setGlobalProperty("window", originalWindow);
    setGlobalProperty("navigator", originalNavigator);
  }
});

test("registerServiceWorker registers the root service worker when available", async () => {
  const originalWindow = globalThis.window;
  const originalNavigator = globalThis.navigator;
  const calls = [];
  const registration = { scope: "/" };

  setGlobalProperty("window", {});
  setGlobalProperty("navigator", {
    serviceWorker: {
      register: async (path) => {
        calls.push(path);
        return registration;
      },
    },
  });

  try {
    const result = await registerServiceWorker();
    assert.deepEqual(calls, ["/service-worker.js"]);
    assert.equal(result, registration);
  } finally {
    globalThis.window = originalWindow;
    globalThis.navigator = originalNavigator;
  }
});

test("transitionAuthPanels applies and clears height animation styles", () => {
  const dom = new JSDOM(`
    <section>
      <div data-auth-panels></div>
    </section>
  `);
  const originals = {
    HTMLElement: globalThis.HTMLElement,
    HTMLInputElement: globalThis.HTMLInputElement,
    HTMLSelectElement: globalThis.HTMLSelectElement,
  };
  const originalWindow = globalThis.window;
  const root = dom.window.document.querySelector("section");
  const panels = dom.window.document.querySelector("[data-auth-panels]");
  let didUpdate = false;

  setDomGlobals(dom);
  setGlobalProperty("window", dom.window);
  panels.getBoundingClientRect = () => ({ height: 120 });
  Object.defineProperty(panels, "scrollHeight", { configurable: true, value: 220 });

  try {
    transitionAuthPanels(root, () => {
      didUpdate = true;
    });
    assert.equal(didUpdate, true);
    assert.equal(panels.style.height, "220px");
    assert.equal(panels.style.overflow, "hidden");

    panels.dispatchEvent(new dom.window.Event("transitionend"));
    assert.equal(panels.style.height, "");
    assert.equal(panels.style.overflow, "");
  } finally {
    restoreDomGlobals(originals);
    setGlobalProperty("window", originalWindow);
    dom.window.close();
  }
});

test("transitionAuthPanels updates without animation when no wrapper exists", () => {
  const dom = new JSDOM("<section></section>");
  const originals = {
    HTMLElement: globalThis.HTMLElement,
    HTMLInputElement: globalThis.HTMLInputElement,
    HTMLSelectElement: globalThis.HTMLSelectElement,
  };
  let didUpdate = false;

  setDomGlobals(dom);

  try {
    transitionAuthPanels(dom.window.document.querySelector("section"), () => {
      didUpdate = true;
    });
    assert.equal(didUpdate, true);
  } finally {
    restoreDomGlobals(originals);
    dom.window.close();
  }
});

test("transitionAuthPanels skips styles when panel height is stable", () => {
  const dom = new JSDOM(`
    <section>
      <div data-auth-panels></div>
    </section>
  `);
  const originals = {
    HTMLElement: globalThis.HTMLElement,
    HTMLInputElement: globalThis.HTMLInputElement,
    HTMLSelectElement: globalThis.HTMLSelectElement,
  };
  const originalWindow = globalThis.window;
  const root = dom.window.document.querySelector("section");
  const panels = dom.window.document.querySelector("[data-auth-panels]");

  setDomGlobals(dom);
  setGlobalProperty("window", dom.window);
  panels.getBoundingClientRect = () => ({ height: 120 });
  Object.defineProperty(panels, "scrollHeight", { configurable: true, value: 120 });

  try {
    transitionAuthPanels(root, () => undefined);
    assert.equal(panels.style.height, "");
    assert.equal(panels.style.overflow, "");
  } finally {
    restoreDomGlobals(originals);
    setGlobalProperty("window", originalWindow);
    dom.window.close();
  }
});

test("setAuthTab toggles panels, selected state, focus, and panel height", () => {
  const dom = new JSDOM(`
    <section data-passkey-auth>
      <div data-auth-panels>
        <div data-auth-tab-panel="signin">
          <form data-passkey-login></form>
        </div>
        <div data-auth-tab-panel="signup" hidden>
          <form data-passkey-register>
            <input name="display_name" />
          </form>
        </div>
      </div>
      <button data-auth-tab-trigger="signin" aria-selected="true"></button>
      <button data-auth-tab-trigger="signup" aria-selected="false"></button>
    </section>
  `);
  const originals = {
    HTMLElement: globalThis.HTMLElement,
    HTMLInputElement: globalThis.HTMLInputElement,
    HTMLSelectElement: globalThis.HTMLSelectElement,
  };
  const originalWindow = globalThis.window;
  const root = dom.window.document.querySelector("[data-passkey-auth]");
  const panels = dom.window.document.querySelector("[data-auth-panels]");

  setDomGlobals(dom);
  setGlobalProperty("window", dom.window);
  panels.getBoundingClientRect = () => ({ height: 120 });
  Object.defineProperty(panels, "scrollHeight", { configurable: true, value: 220 });

  try {
    setAuthTab(root, "signup");
    assert.equal(root.querySelector('[data-auth-tab-panel="signin"]').hidden, true);
    assert.equal(root.querySelector('[data-auth-tab-panel="signup"]').hidden, false);
    assert.equal(root.querySelector('[data-auth-tab-trigger="signin"]').getAttribute("aria-selected"), "false");
    assert.equal(root.querySelector('[data-auth-tab-trigger="signup"]').getAttribute("aria-selected"), "true");
    assert.equal(dom.window.document.activeElement, root.querySelector('input[name="display_name"]'));
    assert.equal(panels.style.height, "220px");
    panels.dispatchEvent(new dom.window.Event("transitionend"));

    setAuthTab(root, "signin");
    assert.equal(root.querySelector('[data-auth-tab-panel="signin"]').hidden, false);
    assert.equal(root.querySelector('[data-auth-tab-panel="signup"]').hidden, true);
    assert.equal(root.querySelector('[data-auth-tab-trigger="signin"]').getAttribute("aria-selected"), "true");
  } finally {
    restoreDomGlobals(originals);
    setGlobalProperty("window", originalWindow);
    dom.window.close();
  }
});

test("setAuthTab ignores incomplete auth markup", () => {
  const dom = new JSDOM("<section></section>");
  assert.doesNotThrow(() => setAuthTab(dom.window.document.querySelector("section"), "signup"));
  dom.window.close();
});

function createListRoot() {
  const dom = new JSDOM(`
    <section data-list-detail data-list-id="list-1">
      <h1 data-list-title>Weekly</h1>
      <div data-list-error hidden></div>
      <div data-list-success hidden></div>
      <p data-list-sync-status></p>
      <div data-list-toast hidden>
        <p data-list-toast-message></p>
        <button type="button" data-list-toast-undo>Undo</button>
        <div data-list-toast-timer></div>
      </div>
      <input data-item-category-search value="" />
      <input data-item-edit-category-search value="" />
      <div data-item-suggestions-slot><div data-item-suggestions></div></div>
      <div data-item-category-radios></div>
      <div data-item-edit-category-radios></div>
      <div data-item-empty></div>
      <div data-item-list></div>
      <div data-list-settings-category-list></div>
    </section>
  `, { url: "https://example.test/lists/list-1" });
  return {
    document: dom.window.document,
    root: dom.window.document.querySelector("[data-list-detail]"),
    window: dom.window,
  };
}

function createQuickAddRoot() {
  const dom = new JSDOM(`
    <!doctype html>
    <html>
      <body>
        <section data-list-detail data-list-id="list-1">
          <button type="button" data-item-form-toggle aria-expanded="false">Add</button>
          <div data-list-error hidden></div>
          <div data-list-success hidden></div>
          <div data-item-panel-overlay hidden>
            <section data-item-panel hidden>
              <form data-item-form>
                <input data-item-name-input name="name" value="" />
                <input data-item-category-search value="produce" />
                <div data-item-category-radios></div>
                <input name="quantity_text" value="" />
                <input name="note" value="" />
              </form>
            </section>
          </div>
          <div data-item-edit-overlay hidden></div>
          <section data-item-edit-panel hidden></section>
          <div data-list-settings-overlay hidden></div>
          <section data-list-settings-panel hidden></section>
          <input data-item-edit-category-search value="" />
          <div data-item-edit-category-radios></div>
          <div data-item-suggestions-slot><div data-item-suggestions></div></div>
          <div data-item-empty></div>
          <div data-item-list></div>
          <div data-list-settings-category-list></div>
        </section>
      </body>
    </html>
  `, { url: "https://example.test/lists/list-1" });
  return {
    document: dom.window.document,
    root: dom.window.document.querySelector("[data-list-detail]"),
    window: dom.window,
  };
}

function createDashboardRoot() {
  const dom = new JSDOM(`
    <section data-dashboard>
      <div data-dashboard-empty></div>
      <div data-household-list></div>
    </section>
  `);
  return {
    document: dom.window.document,
    root: dom.window.document.querySelector("[data-dashboard]"),
  };
}

function createSuggestionRoot() {
  const dom = new JSDOM(`
    <section data-list-detail data-list-id="list-1">
      <input data-item-name-input value="m" />
      <div data-item-suggestions-slot>
        <div data-item-suggestions></div>
      </div>
    </section>
  `);
  return {
    document: dom.window.document,
    root: dom.window.document.querySelector("[data-list-detail]"),
    window: dom.window,
  };
}

function createDemoListRoot() {
  const demoPayload = {
    list: { id: "demo-list", name: "Saturday Groceries" },
    categories: [
      { id: "produce", name: "Produce", color: "#6bbf59" },
      { id: "pantry", name: "Pantry", color: "#f59e0b" },
    ],
    category_order: [
      { category_id: "produce", sort_order: 0 },
      { category_id: "pantry", sort_order: 1 },
    ],
    item_window: {
      checked_remaining_count: 0,
      items: [
        {
          id: "demo-item-1",
          name: "Bananas",
          category_id: "produce",
          quantity_text: "6",
          note: null,
          checked: false,
          checked_at: null,
          sort_order: 0,
        },
        {
          id: "demo-item-2",
          name: "Olive oil",
          category_id: "pantry",
          quantity_text: null,
          note: "Running low",
          checked: true,
          checked_at: "2026-04-08T09:00:00Z",
          sort_order: 1,
        },
      ],
    },
  };
  const dom = new JSDOM(`
    <!doctype html>
    <html>
      <body>
        <section
          data-list-detail
          data-list-id="demo-list"
          data-list-mode="demo"
          data-demo-sync-text="Interactive demo running locally."
          data-demo-payload='${JSON.stringify(demoPayload)}'
        >
          <h1 data-list-title></h1>
          <p data-list-sync-status></p>
          <input data-item-name-input value="" />
          <input data-item-category-search value="" />
          <input data-item-edit-category-search value="" />
          <div data-item-suggestions-slot><div data-item-suggestions></div></div>
          <div data-item-category-radios></div>
          <div data-item-edit-category-radios></div>
          <div data-item-empty></div>
          <div data-item-list></div>
        </section>
      </body>
    </html>
  `);
  return {
    document: dom.window.document,
    payload: demoPayload,
    root: dom.window.document.querySelector("[data-list-detail]"),
    window: dom.window,
  };
}

function createState(items) {
  return {
    categoryOrder: new Map(),
    categories: new Map(),
    checkedRemainingCount: 0,
    editingItemId: null,
    highlightedItemId: null,
    highlightTimers: new Map(),
    items: new Map(items.map((item) => [item.id, item])),
    offlineSyncInFlight: null,
    pendingMutations: [],
  };
}

function createCheckedItem(index) {
  const checkedAt = new Date(Date.UTC(2026, 0, 1, 12, 0, 0) - index * 1000).toISOString();
  return {
    id: `item-${index}`,
    name: `Checked item ${index}`,
    checked: true,
    checked_at: checkedAt,
    category_id: null,
    note: null,
    quantity_text: null,
    sort_order: index,
  };
}

test("renderItems only shows loaded checked items before loading more", () => {
  const { document, root } = createListRoot();
  const state = {
    ...createState(Array.from({ length: 10 }, (_, index) => createCheckedItem(index))),
    checkedRemainingCount: 110,
  };

  renderItems(root, state);

  const checkedCards = document.querySelectorAll(".item-card.is-checked");
  assert.equal(checkedCards.length, 10);
  assert.equal(checkedCards[0].querySelector(".item-name").textContent, "Checked item 0");
  assert.equal(checkedCards[9].querySelector(".item-name").textContent, "Checked item 9");
  assert.equal(document.querySelector(".item-category-header .item-category-meta").textContent, "120 items");
  assert.equal(document.querySelector(".checked-items-load-more button").textContent, "Load 100 more");
  assert.equal(document.querySelector(".checked-items-load-more .item-category-meta").textContent, "110 older items not loaded");
});

test("renderHouseholds shows open item counts on list links", () => {
  const { document, root } = createDashboardRoot();

  renderHouseholds(
    root,
    [{ id: "household-1", name: "Home" }],
    new Map([
      [
        "household-1",
        [
          { id: "list-1", name: "Weekly", open_item_count: 1 },
          { id: "list-2", name: "Hardware", open_item_count: 3 },
        ],
      ],
    ]),
  );

  assert.equal(document.querySelector('[href="/lists/list-1"] small').textContent, "1 open item");
  assert.equal(document.querySelector('[href="/lists/list-2"] small').textContent, "3 open items");
  assert.equal(document.body.textContent.includes("Open list"), false);
});

test("renderItems uses brown fallback swatches for uncategorized and checked groups", () => {
  const { document, root } = createListRoot();
  const activeItem = {
    id: "active-item",
    name: "Loose item",
    checked: false,
    checked_at: null,
    category_id: null,
    note: null,
    quantity_text: null,
    sort_order: 0,
  };
  const state = createState([activeItem, createCheckedItem(0)]);

  renderItems(root, state);

  const swatches = document.querySelectorAll(".item-category-swatch");
  assert.match(swatches[0].getAttribute("style") || "", /217, 197, 179|#d9c5b3/);
  assert.match(swatches[1].getAttribute("style") || "", /181, 150, 118|#b59676/);
});

test("renderItems hides active items until their hidden_until time", () => {
  const { document, root } = createListRoot();
  const originalDateNow = Date.now;
  const nowMs = Date.parse("2026-05-14T10:00:00.000Z");
  const visibleItem = {
    id: "visible-item",
    name: "Visible item",
    checked: false,
    checked_at: null,
    category_id: null,
    note: null,
    quantity_text: null,
    sort_order: 0,
  };
  const hiddenItem = {
    ...visibleItem,
    id: "hidden-item",
    name: "Hidden item",
    hidden_until: "2026-05-14T14:00:00.000Z",
    sort_order: 1,
  };
  const expiredHiddenItem = {
    ...visibleItem,
    id: "expired-hidden-item",
    name: "Expired hidden item",
    hidden_until: "2026-05-14T09:59:59.000Z",
    sort_order: 2,
  };

  Date.now = () => nowMs;
  try {
    assert.equal(isItemHidden(hiddenItem, nowMs), true);
    assert.equal(isItemHidden(expiredHiddenItem, nowMs), false);
    assert.equal(isItemHidden(visibleItem, nowMs), false);
    assert.equal(formatHiddenUntilLabel(hiddenItem, nowMs), "4h");
    assert.equal(
      formatHiddenUntilLabel({ ...hiddenItem, hidden_until: "2026-05-14T10:10:00.000Z" }, nowMs),
      "10m",
    );
    assert.equal(formatHiddenUntilLabel(visibleItem, nowMs), "");

    const state = createState([visibleItem, hiddenItem, expiredHiddenItem, createCheckedItem(0)]);
    state.openItemMenuId = "visible-item";
    renderItems(root, state);
  } finally {
    Date.now = originalDateNow;
  }

  const cardNames = [...document.querySelectorAll(".item-card .item-name")].map(
    (node) => node.textContent,
  );
  assert.deepEqual(cardNames, ["Visible item", "Expired hidden item", "Hidden item", "Checked item 0"]);
  assert.equal(document.querySelector(".item-hidden-group h3").textContent, "Hidden for 4h");
  assert.equal(document.querySelector('[data-item-unhide="hidden-item"]').textContent, "4h");
  assert.equal(document.querySelector('[data-item-menu-toggle="visible-item"]').textContent, "⋯");
  assert.equal(document.querySelector('[data-item-hide="visible-item"]').textContent, "Hide item for 4h");
  assert.equal(document.querySelector('[data-item-hide="visible-item"]').closest(".item-more-menu").hidden, false);
});

test("category quick add buttons open the add form with the category selected", () => {
  const { document, root, window } = createQuickAddRoot();
  const originals = {
    HTMLElement: globalThis.HTMLElement,
    HTMLInputElement: globalThis.HTMLInputElement,
    HTMLSelectElement: globalThis.HTMLSelectElement,
    document: globalThis.document,
    window: globalThis.window,
  };
  const state = createState([
    {
      id: "active-item",
      name: "Tomatoes",
      checked: false,
      checked_at: null,
      category_id: "cat-1",
      note: null,
      quantity_text: null,
      sort_order: 0,
    },
    {
      id: "loose-item",
      name: "Loose item",
      checked: false,
      checked_at: null,
      category_id: null,
      note: null,
      quantity_text: null,
      sort_order: 1,
    },
    createCheckedItem(0),
  ]);
  state.categories.set("cat-1", { id: "cat-1", name: "Produce", color: "#22c55e" });
  state.categoryOrder.set("cat-1", 0);
  setDomGlobals({ window });
  setGlobalProperty("document", document);
  setGlobalProperty("window", window);

  try {
    renderItems(root, state);

    const quickAddButtons = document.querySelectorAll(".item-category-quick-add");
    const checkedHeader = [...document.querySelectorAll(".item-category-header")]
      .find((header) => header.textContent.includes("Checked off"));
    assert.equal(quickAddButtons.length, 2);
    assert.equal(quickAddButtons[0].getAttribute("aria-label"), "Quick add uncategorized item");
    assert.equal(quickAddButtons[1].getAttribute("aria-label"), "Quick add to Produce");
    assert.equal(checkedHeader.querySelector(".item-category-quick-add"), null);

    openItemPanelForCategory(root, state, "cat-1");
    assert.equal(document.querySelector("[data-item-panel-overlay]").hidden, false);
    assert.equal(document.querySelector("[data-item-panel]").hidden, false);
    assert.equal(document.querySelector("[data-item-form-toggle]").getAttribute("aria-expanded"), "true");
    assert.equal(document.querySelector("[data-item-category-search]").value, "");
    assert.equal(document.querySelector('input[name="category_id"]:checked').value, "cat-1");

    openItemPanelForCategory(root, state, "missing-cat");
    assert.equal(document.querySelector('input[name="category_id"]:checked').value, "");
  } finally {
    restoreDomGlobals({
      HTMLElement: originals.HTMLElement,
      HTMLInputElement: originals.HTMLInputElement,
      HTMLSelectElement: originals.HTMLSelectElement,
    });
    setGlobalProperty("document", originals.document);
    setGlobalProperty("window", originals.window);
  }
});

test("category swatches preserve configured colors in list and settings views", () => {
  const { document, root } = createListRoot();
  const activeItem = {
    id: "active-item",
    name: "Paprika",
    checked: false,
    checked_at: null,
    category_id: "cat-1",
    note: null,
    quantity_text: null,
    sort_order: 0,
  };
  const state = createState([activeItem]);
  state.categories.set("cat-1", { id: "cat-1", name: "Gemuese", color: "#7ed957" });
  state.categoryOrder.set("cat-1", 0);

  renderItems(root, state);
  renderCategoryOrderSettings(root, state);

  const listSwatchStyle = document
    .querySelector(".item-category-group .item-category-swatch")
    .getAttribute("style") || "";
  const settingsSwatchStyle = document
    .querySelector(".settings-category-row .item-category-swatch")
    .getAttribute("style") || "";
  assert.match(listSwatchStyle, /126, 217, 87|#7ed957/);
  assert.match(settingsSwatchStyle, /126, 217, 87|#7ed957/);
});

test("loadMoreCheckedItems fetches one hundred older checked items per page", async () => {
  const { document, root } = createListRoot();
  const originalFetch = globalThis.fetch;
  const state = {
    ...createState(Array.from({ length: 10 }, (_, index) => createCheckedItem(index))),
    checkedRemainingCount: 110,
  };
  const calls = [];
  setGlobalProperty("fetch", async (url) => {
    calls.push(url);
    return {
      ok: true,
      status: 200,
      json: async () => Array.from({ length: 100 }, (_, index) => createCheckedItem(index + 10)),
    };
  });

  try {
    await loadMoreCheckedItems(root, state);
  } finally {
    setGlobalProperty("fetch", originalFetch);
  }

  const checkedCards = document.querySelectorAll(".item-card.is-checked");
  assert.deepEqual(calls, ["/api/v1/lists/list-1/items/checked?offset=10&limit=100"]);
  assert.equal(checkedCards.length, 110);
  assert.equal(checkedCards[109].querySelector(".item-name").textContent, "Checked item 109");
  assert.equal(document.querySelector(".item-category-header .item-category-meta").textContent, "120 items");
  assert.equal(document.querySelector(".checked-items-load-more button").textContent, "Load 10 more");
  assert.equal(document.querySelector(".checked-items-load-more .item-category-meta").textContent, "10 older items not loaded");
});

test("offline list cache helpers persist local state and merge sync results", () => {
  const { document, root, window } = createListRoot();
  const originals = {
    HTMLElement: globalThis.HTMLElement,
    HTMLInputElement: globalThis.HTMLInputElement,
    document: globalThis.document,
    window: globalThis.window,
  };
  const state = createState([
    {
      id: "local-item-1",
      list_id: "list-1",
      name: "Offline apples",
      checked: false,
      checked_at: null,
      category_id: "cat-1",
      note: null,
      quantity_text: "2",
      sort_order: 1,
    },
    {
      id: "delete-me",
      list_id: "list-1",
      name: "Delete me",
      checked: false,
      checked_at: null,
      category_id: null,
      note: null,
      quantity_text: null,
      sort_order: 2,
    },
  ]);
  state.categories.set("cat-1", { id: "cat-1", name: "Produce", color: "#22c55e" });
  state.categoryOrder.set("cat-1", 0);
  state.pendingMutations.push({ mutation_id: "m1", type: "create" });

  assert.equal(loadOfflineListState("no-window"), null);
  assert.equal(loadOfflineListState(""), null);
  setDomGlobals({ window });
  setGlobalProperty("document", document);
  setGlobalProperty("window", window);

  try {
    assert.equal(offlineListStorageKey("list-1"), "planini:list-offline:list-1");
    assert.equal(loadOfflineListState(""), null);
    assert.equal(loadOfflineListState("list-1"), null);
    window.localStorage.setItem(offlineListStorageKey("bad-json"), "{");
    assert.equal(loadOfflineListState("bad-json"), null);
    window.localStorage.setItem(offlineListStorageKey("not-object"), "false");
    assert.equal(loadOfflineListState("not-object"), null);

    persistOfflineListState(root, state);
    persistOfflineListState(document.createElement("section"), state);
    const cached = loadOfflineListState("list-1");
    assert.equal(cached.title, "Weekly");
    assert.equal(cached.items.length, 2);
    assert.equal(cached.categories[0].name, "Produce");
    assert.equal(cached.pendingMutations[0].mutation_id, "m1");

    const nextState = createState([]);
    applyOfflineListState(root, nextState, cached);
    assert.equal(nextState.items.get("local-item-1").name, "Offline apples");
    assert.equal(document.querySelectorAll(".item-card").length, 2);
    applyOfflineListState(root, nextState, { items: [], pendingMutations: [] });
    assert.equal(document.querySelector("[data-list-title]").textContent, "Weekly");

    const localItem = createOfflineItem(
      nextState,
      "list-1",
      "local-item-2",
      { name: "Offline pears", quantity_text: "3" },
      "2026-05-14T10:00:00.000Z",
    );
    assert.equal(localItem.sort_order, 0);
    assert.equal(localItem.checked_state_recorded_at, "2026-05-14T10:00:00.000Z");

    const checkedItem = applyLocalCheckedState(localItem, true, "2026-05-14T10:05:00.000Z");
    assert.equal(checkedItem.checked, true);
    assert.equal(checkedItem.checked_at, "2026-05-14T10:05:00.000Z");

    nextState.items.set("local-item-1", { ...checkedItem, id: "local-item-1" });
    applyOfflineSyncResult(nextState, {
      client_item_ids: { "local-item-1": "server-item-1" },
      deleted_item_ids: ["delete-me"],
      items: [{ ...checkedItem, id: "server-item-1", checked_at: "2026-05-14T10:05:00.000Z" }],
      applied_mutation_ids: ["m1"],
    });
    assert.equal(nextState.items.has("local-item-1"), false);
    assert.equal(nextState.items.has("delete-me"), false);
    assert.equal(nextState.items.get("server-item-1").checked, true);
    assert.equal(nextState.pendingMutations.length, 0);

    showOfflineSavedMessage(root);
    assert.equal(document.querySelector("[data-list-error]").textContent, "Offline. Changes saved locally and will sync when connection returns.");
    assert.equal(document.querySelector("[data-list-sync-status]").textContent, "Changes saved locally.");
  } finally {
    restoreDomGlobals(originals);
    setGlobalProperty("document", originals.document);
    setGlobalProperty("window", originals.window);
  }
});

test("offline item mutations save locally when browser or request is offline", async () => {
  const { document, root, window } = createListRoot();
  const originals = {
    HTMLElement: globalThis.HTMLElement,
    HTMLInputElement: globalThis.HTMLInputElement,
    document: globalThis.document,
    fetch: globalThis.fetch,
    navigator: globalThis.navigator,
    window: globalThis.window,
  };
  const state = createState([
    {
      id: "item-1",
      list_id: "list-1",
      name: "Milk",
      checked: false,
      checked_at: null,
      category_id: null,
      note: null,
      quantity_text: null,
      sort_order: 0,
    },
  ]);

  setDomGlobals({ window });
  setGlobalProperty("document", document);
  setGlobalProperty("window", window);
  setGlobalProperty("navigator", { onLine: false });
  setGlobalProperty("fetch", async () => {
    throw new Error("offline helpers should not fetch while navigator is offline");
  });

  try {
    assert.equal(isBrowserOffline(), true);
    assert.equal(isOfflineRequestError(new Error("regular")), true);
    assert.equal(shouldQueueItemMutation(state), true);

    const created = await createItemWithOfflineFallback(root, state, "list-1", { name: "Bananas" });
    assert.equal(created.id.startsWith("local-item-"), true);
    assert.equal(state.pendingMutations[0].type, "create");
    assert.equal(state.items.get(created.id).name, "Bananas");

    const updated = await updateItemWithOfflineFallback(root, state, created.id, { note: "ripe" });
    assert.equal(updated.note, "ripe");
    assert.equal(state.pendingMutations[1].type, "update");

    const checked = await setItemCheckedWithOfflineFallback(root, state, created.id, true);
    assert.equal(checked.checked, true);
    assert.equal(state.pendingMutations[2].checked, true);
    assert.equal(window.localStorage.getItem(offlineListStorageKey("list-1")).includes("Bananas"), true);
    assert.equal(document.querySelector("[data-list-error]").textContent, "Offline. Changes saved locally and will sync when connection returns.");
  } finally {
    restoreDomGlobals(originals);
    setGlobalProperty("document", originals.document);
    setGlobalProperty("fetch", originals.fetch);
    setGlobalProperty("navigator", originals.navigator);
    setGlobalProperty("window", originals.window);
  }
});

test("offline item helpers use network while online and fall back on fetch TypeError", async () => {
  const { root, window } = createListRoot();
  const originals = {
    HTMLElement: globalThis.HTMLElement,
    HTMLInputElement: globalThis.HTMLInputElement,
    document: globalThis.document,
    fetch: globalThis.fetch,
    navigator: globalThis.navigator,
    window: globalThis.window,
  };
  const state = createState([
    {
      id: "item-1",
      list_id: "list-1",
      name: "Milk",
      checked: false,
      checked_at: null,
      category_id: null,
      note: null,
      quantity_text: null,
      sort_order: 0,
    },
  ]);
  const calls = [];

  setDomGlobals({ window });
  setGlobalProperty("document", window.document);
  setGlobalProperty("window", window);
  setGlobalProperty("navigator", { onLine: true });
  setGlobalProperty("fetch", async (url, options) => {
    calls.push([url, options?.method || "GET"]);
    if (url === "/api/v1/lists/list-1/items") {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          id: "server-created",
          list_id: "list-1",
          name: "Eggs",
          checked: false,
          checked_at: null,
          category_id: null,
          note: null,
          quantity_text: null,
          sort_order: 1,
        }),
      };
    }
    if (url === "/api/v1/items/item-1" && options?.method === "PATCH") {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          ...state.items.get("item-1"),
          note: "organic",
        }),
      };
    }
    throw new TypeError("network down");
  });

  try {
    assert.equal(isBrowserOffline(), false);
    assert.equal(isOfflineRequestError(new TypeError("network down")), true);
    assert.equal(isOfflineRequestError(new Error("server rejected")), false);
    assert.equal(shouldQueueItemMutation(state, "item-1"), false);

    const created = await createItemWithOfflineFallback(root, state, "list-1", { name: "Eggs" });
    assert.equal(created.id, "server-created");
    assert.deepEqual(calls[0], ["/api/v1/lists/list-1/items", "POST"]);

    const updated = await updateItemWithOfflineFallback(root, state, "item-1", { note: "organic" });
    assert.equal(updated.note, "organic");
    assert.deepEqual(calls[1], ["/api/v1/items/item-1", "PATCH"]);

    const checked = await setItemCheckedWithOfflineFallback(root, state, "item-1", true);
    assert.equal(checked.id, "item-1");
    assert.equal(checked.checked, true);
    assert.equal(state.pendingMutations[0].type, "set_checked");

    state.pendingMutations = [];
    setGlobalProperty("fetch", async () => ({
      ok: false,
      status: 400,
      json: async () => ({ detail: "Bad item." }),
    }));
    await assert.rejects(
      () => createItemWithOfflineFallback(root, state, "list-1", { name: "Bad" }),
      /Bad item\./,
    );
    await assert.rejects(
      () => updateItemWithOfflineFallback(root, state, "item-1", { note: "bad" }),
      /Bad item\./,
    );
    await assert.rejects(
      () => setItemCheckedWithOfflineFallback(root, state, "item-1", true),
      /Bad item\./,
    );
  } finally {
    restoreDomGlobals(originals);
    setGlobalProperty("document", originals.document);
    setGlobalProperty("fetch", originals.fetch);
    setGlobalProperty("navigator", originals.navigator);
    setGlobalProperty("window", originals.window);
  }
});

test("hideItemForLater hides for four hours and restoreHiddenItem clears it", async () => {
  const { document, root, window } = createListRoot();
  const originals = {
    HTMLElement: globalThis.HTMLElement,
    HTMLInputElement: globalThis.HTMLInputElement,
    document: globalThis.document,
    fetch: globalThis.fetch,
    window: globalThis.window,
  };
  const state = createState([
    {
      id: "item-1",
      list_id: "list-1",
      name: "Milk",
      checked: false,
      checked_at: null,
      category_id: null,
      note: null,
      quantity_text: null,
      sort_order: 0,
    },
  ]);
  const calls = [];

  setDomGlobals({ window });
  setGlobalProperty("document", document);
  setGlobalProperty("window", window);
  setGlobalProperty("fetch", async (url, options) => {
    const payload = JSON.parse(options.body);
    calls.push([url, options.method, payload]);
    return {
      ok: true,
      status: 200,
      json: async () => ({ ...state.items.get("item-1"), hidden_until: payload.hidden_until }),
    };
  });

  try {
    const hidden = await hideItemForLater(root, state, "item-1", Date.parse("2026-05-14T10:00:00.000Z"));
    assert.equal(hidden.hidden_until, "2026-05-14T14:00:00.000Z");
    assert.equal(document.querySelectorAll(".item-card").length, 1);
    assert.equal(document.querySelector(".item-hidden-group h3").textContent, "Hidden for 4h");
    assert.equal(document.querySelector('[data-item-unhide="item-1"]').textContent, "4h");
    assert.equal(document.querySelector("[data-list-toast-message]").textContent, "Milk hidden for 4 hours.");

    const restored = await restoreHiddenItem(root, state, "item-1");
    assert.equal(restored.hidden_until, null);
    assert.equal(document.querySelector(".item-card .item-name").textContent, "Milk");
    assert.equal(document.querySelector(".item-hidden-group"), null);
  } finally {
    window.clearTimeout(state.undoTimerId);
    restoreDomGlobals(originals);
    setGlobalProperty("document", originals.document);
    setGlobalProperty("fetch", originals.fetch);
    setGlobalProperty("window", originals.window);
  }

  assert.deepEqual(calls, [
    ["/api/v1/items/item-1", "PATCH", { hidden_until: "2026-05-14T14:00:00.000Z" }],
    ["/api/v1/items/item-1", "PATCH", { hidden_until: null }],
  ]);
});

test("flushOfflineMutations clears applied mutations and reports sync failures", async () => {
  const { document, root, window } = createListRoot();
  const originals = {
    HTMLElement: globalThis.HTMLElement,
    HTMLInputElement: globalThis.HTMLInputElement,
    document: globalThis.document,
    fetch: globalThis.fetch,
    navigator: globalThis.navigator,
    window: globalThis.window,
  };
  const state = createState([
    {
      id: "local-item-1",
      list_id: "list-1",
      name: "Offline apples",
      checked: false,
      checked_at: null,
      category_id: null,
      note: null,
      quantity_text: null,
      sort_order: 0,
    },
  ]);
  state.pendingMutations = [{ mutation_id: "m1", type: "create" }];
  const calls = [];

  setDomGlobals({ window });
  setGlobalProperty("document", document);
  setGlobalProperty("window", window);
  setGlobalProperty("navigator", { onLine: true });
  setGlobalProperty("fetch", async (url, options) => {
    calls.push([url, JSON.parse(options.body).mutations.length]);
    return {
      ok: true,
      status: 200,
      json: async () => ({
        client_item_ids: { "local-item-1": "server-item-1" },
        deleted_item_ids: [],
        items: [{
          id: "server-item-1",
          list_id: "list-1",
          name: "Offline apples",
          checked: false,
          checked_at: null,
          category_id: null,
          note: null,
          quantity_text: null,
          sort_order: 0,
        }],
        applied_mutation_ids: ["m1"],
      }),
    };
  });

  try {
    const firstFlush = flushOfflineMutations(root, state);
    const inFlightFlush = flushOfflineMutations(root, state);
    assert.equal(firstFlush, inFlightFlush);
    await firstFlush;
    assert.deepEqual(calls, [["/api/v1/lists/list-1/items/sync", 1]]);
    assert.equal(state.pendingMutations.length, 0);
    assert.equal(state.items.has("local-item-1"), false);
    assert.equal(state.items.has("server-item-1"), true);
    assert.equal(document.querySelector("[data-list-success]").textContent, "Saved offline changes synced.");
    assert.equal(await flushOfflineMutations(root, state), null);

    state.pendingMutations = [{ mutation_id: "m1-left", type: "update" }];
    setGlobalProperty("fetch", async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        client_item_ids: {},
        deleted_item_ids: [],
        items: [],
        applied_mutation_ids: [],
      }),
    }));
    await flushOfflineMutations(root, state);
    assert.equal(state.pendingMutations.length, 1);
    assert.equal(document.querySelector("[data-list-error]").textContent, "Offline. Changes saved locally and will sync when connection returns.");

    state.pendingMutations = [{ mutation_id: "m2", type: "update" }];
    setGlobalProperty("fetch", async () => {
      throw new TypeError("offline");
    });
    await flushOfflineMutations(root, state);
    assert.equal(state.pendingMutations.length, 1);
    assert.equal(document.querySelector("[data-list-error]").textContent, "Offline. Changes saved locally and will sync when connection returns.");

    setGlobalProperty("fetch", async () => ({
      ok: false,
      status: 500,
      json: async () => ({ detail: "Server rejected sync." }),
    }));
    await flushOfflineMutations(root, state);
    assert.equal(document.querySelector("[data-list-error]").textContent, "Server rejected sync.");
  } finally {
    restoreDomGlobals(originals);
    setGlobalProperty("document", originals.document);
    setGlobalProperty("fetch", originals.fetch);
    setGlobalProperty("navigator", originals.navigator);
    setGlobalProperty("window", originals.window);
  }
});

test("renderItemSuggestions adds category color strips for categorized matches", () => {
  const { document, root, window } = createSuggestionRoot();
  const originalHTMLElement = globalThis.HTMLElement;
  const originalHTMLInputElement = globalThis.HTMLInputElement;
  const originalDateNow = Date.now;
  setGlobalProperty("HTMLElement", window.HTMLElement);
  setGlobalProperty("HTMLInputElement", window.HTMLInputElement);
  const state = createState([
    {
      id: "item-1",
      name: "Mehl",
      checked: false,
      category_id: "cat-1",
      note: null,
      quantity_text: null,
    },
    {
      id: "item-2",
      name: "Loose item",
      checked: false,
      category_id: null,
      note: null,
      quantity_text: null,
    },
    {
      id: "item-3",
      name: "Milch",
      checked: false,
      hidden_until: "2026-05-14T14:00:00.000Z",
      category_id: null,
      note: null,
      quantity_text: null,
    },
  ]);
  state.categories.set("cat-1", { id: "cat-1", name: "Backzutaten", color: "#ff3b30" });

  Date.now = () => Date.parse("2026-05-14T10:00:00.000Z");
  try {
    renderItemSuggestions(root, state);

    const suggestions = document.querySelectorAll(".item-suggestion");
    assert.equal(suggestions.length, 2);
    assert.equal(suggestions[0].classList.contains("has-category"), true);
    assert.equal(suggestions[0].style.getPropertyValue("--suggestion-category-color"), "#ff3b30");
    assert.equal(suggestions[1].classList.contains("has-category"), false);
    assert.equal(suggestions[1].style.getPropertyValue("--suggestion-category-color"), "");
  } finally {
    Date.now = originalDateNow;
    setGlobalProperty("HTMLElement", originalHTMLElement);
    setGlobalProperty("HTMLInputElement", originalHTMLInputElement);
  }
});

test("item suggestion fuzzy matching tolerates short typos", () => {
  assert.equal(boundedEditDistance("milch", "milvh", 1), 1);
  assert.equal(boundedEditDistance("milch", "tomate", 1), 2);
  assert.equal(boundedEditDistance("milch", "salz", 1), 2);
  assert.equal(fuzzyItemNameDistance("milch", "mi"), null);
  assert.equal(fuzzyItemNameDistance("brot", "broz"), 1);
  assert.equal(fuzzyItemNameDistance("spaghetti", "spaghetty"), 1);
  assert.equal(fuzzyItemNameDistance("hafermilch", "milch"), 0);
  assert.equal(fuzzyItemNameDistance("milch", "kaffee"), null);
  assert.deepEqual(itemSuggestionMatch("Milch", "milch"), { distance: 0, rank: 0 });
  assert.deepEqual(itemSuggestionMatch("Milchreis", "milch"), { distance: 0, rank: 1 });
  assert.deepEqual(itemSuggestionMatch("Hafermilch", "milch"), { distance: 0, rank: 2 });
  assert.deepEqual(itemSuggestionMatch("Milch", "Milvh"), { distance: 1, rank: 3 });
  assert.equal(itemSuggestionMatch("Brot", "reis"), null);
});

test("renderItemSuggestions shows fuzzy item matches", () => {
  const { document, root, window } = createSuggestionRoot();
  const originalHTMLElement = globalThis.HTMLElement;
  const originalHTMLInputElement = globalThis.HTMLInputElement;
  setGlobalProperty("HTMLElement", window.HTMLElement);
  setGlobalProperty("HTMLInputElement", window.HTMLInputElement);
  document.querySelector("[data-item-name-input]").value = "Milvh";
  const state = createState([
    {
      id: "item-1",
      name: "Milch",
      checked: false,
      category_id: null,
      note: null,
      quantity_text: null,
    },
    {
      id: "item-2",
      name: "Mehl",
      checked: false,
      category_id: null,
      note: null,
      quantity_text: null,
    },
  ]);

  try {
    renderItemSuggestions(root, state);

    const suggestions = document.querySelectorAll(".item-suggestion");
    assert.equal(suggestions.length, 1);
    assert.equal(suggestions[0].querySelector(".item-name").textContent, "Milch");
    assert.equal(document.querySelector("[data-item-suggestions-slot]").classList.contains("is-active"), true);
  } finally {
    setGlobalProperty("HTMLElement", originalHTMLElement);
    setGlobalProperty("HTMLInputElement", originalHTMLInputElement);
  }
});

test("renderItemSuggestions keeps unchanged matches mounted", () => {
  const { document, root, window } = createSuggestionRoot();
  const originalHTMLElement = globalThis.HTMLElement;
  const originalHTMLInputElement = globalThis.HTMLInputElement;
  setGlobalProperty("HTMLElement", window.HTMLElement);
  setGlobalProperty("HTMLInputElement", window.HTMLInputElement);
  const input = document.querySelector("[data-item-name-input]");
  input.value = "Papri";
  const state = createState([
    {
      id: "item-1",
      name: "Paprika",
      checked: false,
      category_id: null,
      note: null,
      quantity_text: null,
    },
  ]);

  try {
    renderItemSuggestions(root, state);
    const firstSuggestion = document.querySelector(".item-suggestion");

    input.value = "Paprik";
    renderItemSuggestions(root, state);

    assert.equal(document.querySelector(".item-suggestion"), firstSuggestion);
    assert.equal(document.querySelector(".item-name").textContent, "Paprika");
  } finally {
    setGlobalProperty("HTMLElement", originalHTMLElement);
    setGlobalProperty("HTMLInputElement", originalHTMLInputElement);
  }
});

test("renderItemSuggestions keeps surviving matches mounted when narrowed", () => {
  const { document, root, window } = createSuggestionRoot();
  const originalHTMLElement = globalThis.HTMLElement;
  const originalHTMLInputElement = globalThis.HTMLInputElement;
  setGlobalProperty("HTMLElement", window.HTMLElement);
  setGlobalProperty("HTMLInputElement", window.HTMLInputElement);
  const input = document.querySelector("[data-item-name-input]");
  input.value = "To";
  const state = createState([
    {
      id: "item-1",
      name: "Tofu",
      checked: false,
      category_id: null,
      note: null,
      quantity_text: null,
    },
    {
      id: "item-2",
      name: "Tomate",
      checked: false,
      category_id: null,
      note: null,
      quantity_text: null,
    },
  ]);

  try {
    renderItemSuggestions(root, state);
    const firstSuggestion = document.querySelector(".item-suggestion");
    assert.equal(firstSuggestion.querySelector(".item-name").textContent, "Tofu");
    assert.equal(document.querySelectorAll(".item-suggestion").length, 2);

    input.value = "Tofu";
    renderItemSuggestions(root, state);

    assert.equal(document.querySelector(".item-suggestion"), firstSuggestion);
    assert.equal(document.querySelectorAll(".item-suggestion").length, 1);
  } finally {
    setGlobalProperty("HTMLElement", originalHTMLElement);
    setGlobalProperty("HTMLInputElement", originalHTMLInputElement);
  }
});

test("demo list helpers reuse the real list page with local data", async () => {
  const { document, payload, root, window } = createDemoListRoot();
  const originals = {
    HTMLElement: globalThis.HTMLElement,
    HTMLInputElement: globalThis.HTMLInputElement,
    HTMLSelectElement: globalThis.HTMLSelectElement,
    document: globalThis.document,
    window: globalThis.window,
  };

  setDomGlobals({ window });
  setGlobalProperty("document", document);
  setGlobalProperty("window", window);

  try {
    const state = {
      categoryOrder: new Map(),
      categories: new Map(),
      checkedRemainingCount: 0,
      demoPayload: getDemoPayload(root),
      editingItemId: null,
      highlightedItemId: null,
      highlightTimers: new Map(),
      items: new Map(),
      nextDemoId: 1,
      socket: null,
      undoAction: null,
      undoTimerId: null,
    };

    assert.equal(isDemoList(root), true);
    assert.equal(state.demoPayload.list.name, payload.list.name);

    await loadListDetail(root, state);
    assert.equal(document.querySelector("[data-list-title]").textContent, "Saturday Groceries");
    assert.equal(document.querySelectorAll(".item-card").length, 2);

    const createdItem = createDemoItem(state, { name: "Dishwasher tabs", category_id: "pantry" });
    assert.equal(createdItem.id, "demo-item-3");
    assert.equal(createdItem.sort_order, 2);

    state.items.set(createdItem.id, createdItem);
    const updatedItem = updateDemoItem(state, "demo-item-3", { note: "Big box" });
    assert.equal(updatedItem.note, "Big box");
    const updatedViaFallback = await updateItemWithOfflineFallback(root, state, "demo-item-3", { note: "Fallback box" });
    assert.equal(updatedViaFallback.note, "Fallback box");

    const checkedItem = setDemoItemChecked(state, "demo-item-1", true);
    assert.equal(checkedItem.checked, true);
    assert.match(checkedItem.checked_at, /T/);

    await restoreCheckedSuggestion(root, state, "demo-item-1");
    assert.equal(state.items.get("demo-item-1").checked, true);

    await restoreToggledItem(root, state, "demo-item-1", "check");
    assert.equal(state.items.get("demo-item-1").checked, false);

    await restoreDeletedItem(root, state, "demo-list", cloneDemoItem(createdItem));
    assert.equal(state.items.get("demo-item-3").name, "Dishwasher tabs");

    setCategoryOrder(state, ["pantry", "produce"]);
    await saveCategoryOrder(root, state);
    assert.deepEqual([...state.categoryOrder.entries()], [["pantry", 0], ["produce", 1]]);

    const olderItems = await loadMoreCheckedItems(root, state);
    assert.deepEqual(olderItems, []);

    connectListSocket(root, state);
    assert.equal(document.querySelector("[data-list-sync-status]").textContent, "Interactive demo running locally.");
    assert.equal(await flushOfflineMutations(root, state), null);
    setListSyncStatus(root, "Manual sync text");
    assert.equal(document.querySelector("[data-list-sync-status]").textContent, "Manual sync text");
  } finally {
    restoreDomGlobals(originals);
    setGlobalProperty("document", originals.document);
    setGlobalProperty("window", originals.window);
  }
});

test("language preference helpers normalize, store, and apply choices", () => {
  const originalDocument = globalThis.document;
  const originalHTMLElement = globalThis.HTMLElement;
  const originalHTMLInputElement = globalThis.HTMLInputElement;
  const originalHTMLSelectElement = globalThis.HTMLSelectElement;
  const originalI18n = globalThis.__appI18n;
  const originalNavigator = globalThis.navigator;
  const originalWindow = globalThis.window;
  const dom = new JSDOM("<!doctype html><html><body></body></html>", {
    url: "https://example.test/settings",
  });

  setGlobalProperty("document", dom.window.document);
  setDomGlobals(dom);
  setGlobalProperty("__appI18n", { locale: "fr", catalog: {} });
  setGlobalProperty("navigator", { language: "fr-FR", languages: ["fr-FR", "en-US"] });
  setGlobalProperty("window", dom.window);

  try {
    assert.equal(normalizeLanguagePreference("de"), "de");
    assert.equal(normalizeLanguagePreference("fr"), "");
    assert.equal(getPreferredLocale(), "fr");
    assert.equal(languagePreferenceLabel(""), "Browser default (fr)");

    assert.equal(storeLanguagePreference("de"), "de");
    assert.equal(getPreferredLocale(), "de");
    assert.equal(applyLanguagePreference(), "de");
    assert.equal(dom.window.document.documentElement.lang, "de");
    assert.equal(languagePreferenceLabel("de"), "Deutsch");

    assert.equal(storeLanguagePreference("fr"), "");
    assert.equal(getPreferredLocale(), "fr");
    assert.equal(applyLanguagePreference(), "");
    assert.equal(dom.window.document.documentElement.lang, "fr");
  } finally {
    setGlobalProperty("document", originalDocument);
    restoreDomGlobals({
      HTMLElement: originalHTMLElement,
      HTMLInputElement: originalHTMLInputElement,
      HTMLSelectElement: originalHTMLSelectElement,
    });
    setGlobalProperty("__appI18n", originalI18n);
    setGlobalProperty("navigator", originalNavigator);
    setGlobalProperty("window", originalWindow);
  }
});

test("language settings dialog syncs and saves the selected language", () => {
  const originalDocument = globalThis.document;
  const originalHTMLElement = globalThis.HTMLElement;
  const originalHTMLInputElement = globalThis.HTMLInputElement;
  const originalHTMLSelectElement = globalThis.HTMLSelectElement;
  const originalI18n = globalThis.__appI18n;
  const originalNavigator = globalThis.navigator;
  const originalNavigate = globalThis.__appNavigateTo;
  const originalWindow = globalThis.window;
  const originalCredential = globalThis.PublicKeyCredential;
  const dom = new JSDOM(
    `<!doctype html>
    <html>
      <body>
        <section data-user-settings>
          <button type="button" data-language-settings-open>Change language</button>
          <strong data-language-settings-summary></strong>
          <div data-settings-error hidden></div>
          <div data-settings-success hidden></div>
          <div data-passkey-error hidden></div>
          <div data-passkey-success hidden></div>
          <div data-language-settings-overlay hidden>
            <section data-language-settings-panel hidden>
              <button type="button" data-language-settings-close>Close</button>
              <form data-language-settings-form>
                <select data-language-settings-select>
                  <option value="">Browser default</option>
                  <option value="en">English</option>
                  <option value="de">Deutsch</option>
                </select>
              </form>
            </section>
          </div>
        </section>
      </body>
    </html>`,
    { url: "https://example.test/settings" },
  );

  setGlobalProperty("document", dom.window.document);
  setDomGlobals(dom);
  setGlobalProperty("__appI18n", {
    locale: "en",
    catalog: { settings: { language_saved: "Language set to {language}." } },
  });
  setGlobalProperty("navigator", { language: "en-US", credentials: undefined });
  setGlobalProperty("window", dom.window);
  setGlobalProperty("PublicKeyCredential", undefined);
  const assigned = [];
  setGlobalProperty("__appNavigateTo", (url) => {
    assigned.push(url);
  });

  try {
    const root = dom.window.document.querySelector("[data-user-settings]");
    const overlay = root.querySelector("[data-language-settings-overlay]");
    const panel = root.querySelector("[data-language-settings-panel]");
    const select = root.querySelector("[data-language-settings-select]");
    const summary = root.querySelector("[data-language-settings-summary]");
    const success = root.querySelector("[data-settings-success]");

    syncLanguageSettings(root);
    assert.equal(summary.textContent, "Browser default (en)");

    setLanguageSettingsOpen(root, true);
    assert.equal(overlay.hidden, false);
    assert.equal(panel.hidden, false);

    select.value = "de";
    initUserSettings();
    root.querySelector("[data-language-settings-form]").dispatchEvent(
      new dom.window.Event("submit", { bubbles: true, cancelable: true }),
    );

    assert.equal(overlay.hidden, true);
    assert.equal(panel.hidden, true);
    assert.equal(summary.textContent, "Deutsch");
    assert.equal(success.hidden, false);
    assert.equal(success.textContent, "Language set to Deutsch.");
    assert.equal(dom.window.document.cookie, "planini_locale=de");
    assert.deepEqual(assigned, ["/settings?lang=de"]);
  } finally {
    setGlobalProperty("document", originalDocument);
    restoreDomGlobals({
      HTMLElement: originalHTMLElement,
      HTMLInputElement: originalHTMLInputElement,
      HTMLSelectElement: originalHTMLSelectElement,
    });
    setGlobalProperty("__appI18n", originalI18n);
    setGlobalProperty("navigator", originalNavigator);
    setGlobalProperty("__appNavigateTo", originalNavigate);
    setGlobalProperty("window", originalWindow);
    setGlobalProperty("PublicKeyCredential", originalCredential);
  }
});

test("date formatters use the stored language preference", () => {
  const originalNavigator = globalThis.navigator;
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;
  const dom = new JSDOM("<!doctype html><html><body></body></html>", {
    url: "https://example.test/settings",
  });

  setGlobalProperty("document", dom.window.document);
  setGlobalProperty("navigator", { language: "en-US" });
  setGlobalProperty("window", dom.window);

  try {
    storeLanguagePreference("de");
    assert.equal(formatPasskeyDate(null), "Never used yet");
    assert.match(formatPasskeyDate("2026-04-06T12:30:00Z"), /06\.04\.2026|06\. Apr\. 2026/);
    assert.match(formatInviteExpiry("2026-04-06T12:30:00Z"), /06\.04\.2026|06\. Apr\. 2026/);
  } finally {
    setGlobalProperty("document", originalDocument);
    setGlobalProperty("navigator", originalNavigator);
    setGlobalProperty("window", originalWindow);
  }
});

test("renderPasskeys only shows the empty state when no passkeys exist", () => {
  const originalDocument = globalThis.document;
  const originalNavigator = globalThis.navigator;
  const originalWindow = globalThis.window;
  const dom = new JSDOM(
    `<!doctype html>
    <html>
      <body>
        <section data-passkey-management>
          <div class="dashboard-empty" data-passkey-empty hidden>
            <h3>No passkeys loaded</h3>
          </div>
          <div data-passkey-list></div>
        </section>
      </body>
    </html>`,
    { url: "https://example.test/settings" },
  );

  setGlobalProperty("document", dom.window.document);
  setGlobalProperty("navigator", { language: "en-US" });
  setGlobalProperty("window", dom.window);

  try {
    const root = dom.window.document.querySelector("[data-passkey-management]");
    const emptyState = root.querySelector("[data-passkey-empty]");
    const list = root.querySelector("[data-passkey-list]");

    renderPasskeys(root, [
      {
        id: "passkey-1",
        name: "Bitwarden - Listerine",
        created_at: "2026-03-18T18:09:00Z",
        last_used_at: "2026-05-12T18:13:00Z",
      },
    ]);

    assert.equal(emptyState.hidden, true);
    assert.equal(emptyState.style.display, "none");
    assert.equal(list.querySelectorAll(".passkey-row").length, 1);
    assert.match(list.textContent, /Bitwarden - Listerine/);

    renderPasskeys(root, []);

    assert.equal(emptyState.hidden, false);
    assert.equal(emptyState.style.display, "");
    assert.equal(list.querySelectorAll(".passkey-row").length, 0);
  } finally {
    setGlobalProperty("document", originalDocument);
    setGlobalProperty("navigator", originalNavigator);
    setGlobalProperty("window", originalWindow);
  }
});
