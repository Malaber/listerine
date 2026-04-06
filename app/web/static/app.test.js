import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

import { loadMoreCheckedItems, registerServiceWorker, renderItems } from "./app.js";

function setGlobalProperty(name, value) {
  Object.defineProperty(globalThis, name, {
    configurable: true,
    writable: true,
    value,
  });
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
      <div data-item-empty></div>
      <div data-item-list></div>
    </section>
  `);
  return {
    document: dom.window.document,
    root: dom.window.document.querySelector("[data-list-detail]"),
  };
}

function createState(items) {
  return {
    categoryOrder: new Map(),
    categories: new Map(),
    checkedRemainingCount: 0,
    editingItemId: null,
    items: new Map(items.map((item) => [item.id, item])),
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
