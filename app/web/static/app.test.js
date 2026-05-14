import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

import {
  applyLanguagePreference,
  cloneDemoItem,
  createDemoItem,
  formatInviteExpiry,
  formatPasskeyDate,
  getDemoPayload,
  getPreferredLocale,
  initUserSettings,
  isDemoList,
  languagePreferenceLabel,
  loadListDetail,
  loadMoreCheckedItems,
  normalizeLanguagePreference,
  registerServiceWorker,
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
  offlineListStorageKey,
  loadOfflineListState,
  persistOfflineListState,
  applyOfflineListState,
  showOfflineSavedMessage,
  clearCategoryDragState,
  getDisabledCategoryIds,
  itemCountForCategory,
  isCategoryDisabled,
  reorderCategoryIds,
  restoreItemCategoryIds,
  saveDisabledCategories,
  setCategoryDisabled,
  setDisabledCategoryIds,
  unassignCategoryItems,
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

function createListRoot() {
  const dom = new JSDOM(`
    <section data-list-detail data-list-id="list-1">
      <h1 data-list-title>Weekly</h1>
      <div data-list-error hidden></div>
      <div data-list-success hidden></div>
      <p data-list-sync-status></p>
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
      { id: "produce", name: "Produce", color: "#8f7a62" },
      { id: "pantry", name: "Pantry", color: "#8b6b4f" },
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
          <div data-list-settings-category-list></div>
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
    disabledCategoryIds: new Set(),
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
  state.disabledCategoryIds.add("cat-1");
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
    assert.deepEqual(cached.disabledCategoryIds, ["cat-1"]);
    assert.equal(cached.pendingMutations[0].mutation_id, "m1");

    const nextState = createState([]);
    applyOfflineListState(root, nextState, cached);
    assert.equal(nextState.items.get("local-item-1").name, "Offline apples");
    assert.equal(isCategoryDisabled(nextState, "cat-1"), true);
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
  ]);
  state.categories.set("cat-1", { id: "cat-1", name: "Backzutaten", color: "#ff3b30" });

  try {
    renderItemSuggestions(root, state);

    const suggestions = document.querySelectorAll(".item-suggestion");
    assert.equal(suggestions.length, 2);
    assert.equal(suggestions[0].classList.contains("has-category"), true);
    assert.equal(suggestions[0].style.getPropertyValue("--suggestion-category-color"), "#ff3b30");
    assert.equal(suggestions[1].classList.contains("has-category"), false);
    assert.equal(suggestions[1].style.getPropertyValue("--suggestion-category-color"), "");
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
      disabledCategoryIds: new Set(),
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

test("category disabling hides choices and unassigns local items", async () => {
  const { document, root, window } = createDemoListRoot();
  const originals = {
    HTMLElement: globalThis.HTMLElement,
    HTMLInputElement: globalThis.HTMLInputElement,
    document: globalThis.document,
    window: globalThis.window,
  };
  const confirms = [];
  window.confirm = (message) => {
    confirms.push(message);
    return true;
  };

  setDomGlobals({ window });
  setGlobalProperty("document", document);
  setGlobalProperty("window", window);

  try {
    const state = {
      categoryOrder: new Map(),
      categories: new Map(),
      checkedRemainingCount: 0,
      disabledCategoryIds: new Set(),
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

    await loadListDetail(root, state);
    assert.deepEqual(reorderCategoryIds(["produce", "pantry"], "produce", 1), ["pantry", "produce"]);
    assert.deepEqual(reorderCategoryIds(["produce"], "missing", 0), ["produce"]);
    assert.equal(itemCountForCategory(state, "produce"), 1);
    const previousPantryCategories = unassignCategoryItems(state, "pantry");
    assert.equal(itemCountForCategory(state, "pantry"), 0);
    restoreItemCategoryIds(state, previousPantryCategories);
    assert.equal(itemCountForCategory(state, "pantry"), 1);

    const didDisable = await setCategoryDisabled(root, state, "produce", true);
    assert.equal(didDisable, true);
    assert.equal(isCategoryDisabled(state, "produce"), true);
    assert.deepEqual(getDisabledCategoryIds(state), ["produce"]);
    assert.equal(state.items.get("demo-item-1").category_id, null);
    assert.match(confirms[0], /Disable Produce/);
    assert.equal(document.querySelector(".settings-category-row.is-disabled strong").textContent, "Produce");
    assert.equal(document.querySelector(".settings-category-toggle svg").getAttribute("viewBox"), "0 0 24 24");
    document.querySelector(".settings-category-row").classList.add("is-dragging", "is-drag-over");
    clearCategoryDragState(root);
    assert.equal(document.querySelector(".settings-category-row").classList.contains("is-dragging"), false);
    assert.equal(document.querySelectorAll("[data-item-category-radios] .category-radio-option").length, 2);
    assert.equal(document.querySelector("[data-item-category-radios]").textContent.includes("Produce"), false);

    await saveDisabledCategories(root, state);
    const didEnable = await setCategoryDisabled(root, state, "produce", false);
    assert.equal(didEnable, true);
    assert.equal(isCategoryDisabled(state, "produce"), false);
    assert.equal(await setCategoryDisabled(root, state, "produce", false), false);
    assert.equal(await setCategoryDisabled(root, state, "missing", true), false);
    window.confirm = () => false;
    assert.equal(await setCategoryDisabled(root, state, "pantry", true), false);
    assert.equal(isCategoryDisabled(state, "pantry"), false);

    setDisabledCategoryIds(state, ["pantry", "missing"]);
    assert.deepEqual(getDisabledCategoryIds(state), ["pantry"]);
  } finally {
    restoreDomGlobals(originals);
    setGlobalProperty("document", originals.document);
    setGlobalProperty("window", originals.window);
  }
});

test("category disabling restores local state when save fails", async () => {
  const { document, root, window } = createListRoot();
  const originals = {
    HTMLElement: globalThis.HTMLElement,
    HTMLInputElement: globalThis.HTMLInputElement,
    document: globalThis.document,
    fetch: globalThis.fetch,
    window: globalThis.window,
  };
  window.confirm = () => true;

  setDomGlobals({ window });
  setGlobalProperty("document", document);
  setGlobalProperty("window", window);
  setGlobalProperty("fetch", async () => {
    throw new TypeError("offline");
  });

  try {
    const state = createState([
      {
        id: "item-1",
        list_id: "list-1",
        name: "Bananas",
        checked: false,
        checked_at: null,
        category_id: "produce",
        note: null,
        quantity_text: null,
        sort_order: 0,
      },
    ]);
    state.categories.set("produce", { id: "produce", name: "Produce", color: "#22c55e" });

    await assert.rejects(() => setCategoryDisabled(root, state, "produce", true), /offline/);
    assert.equal(isCategoryDisabled(state, "produce"), false);
    assert.equal(state.items.get("item-1").category_id, "produce");

    setGlobalProperty("fetch", async (url, options) => {
      assert.equal(url, "/api/v1/lists/list-1/disabled-categories");
      assert.equal(options.method, "PUT");
      return {
        ok: true,
        status: 200,
        json: async () => ({ category_ids: ["produce"] }),
      };
    });
    assert.equal(await setCategoryDisabled(root, state, "produce", true), true);
    assert.equal(isCategoryDisabled(state, "produce"), true);
    assert.equal(state.items.get("item-1").category_id, null);
  } finally {
    restoreDomGlobals(originals);
    setGlobalProperty("document", originals.document);
    setGlobalProperty("fetch", originals.fetch);
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
