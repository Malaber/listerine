import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

import {
  addCapabilitiesDemoItem,
  applyLanguagePreference,
  createCapabilitiesDemoState,
  formatInviteExpiry,
  formatPasskeyDate,
  getPreferredLocale,
  initCapabilitiesShowcase,
  initUserSettings,
  languagePreferenceLabel,
  loadMoreCheckedItems,
  normalizeLanguagePreference,
  registerServiceWorker,
  renderCapabilitiesDemo,
  renderItems,
  renderItemSuggestions,
  setLanguageSettingsOpen,
  storeLanguagePreference,
  syncLanguageSettings,
  toggleCapabilitiesDemoItem,
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
      <div data-item-empty></div>
      <div data-item-list></div>
    </section>
  `);
  return {
    document: dom.window.document,
    root: dom.window.document.querySelector("[data-list-detail]"),
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

function createCapabilitiesRoot() {
  const dom = new JSDOM(`
    <!doctype html>
    <html>
      <body>
        <section data-capabilities-showcase>
          <article data-demo-list="groceries">
            <p data-demo-summary></p>
            <form data-demo-form>
              <input data-demo-input />
              <button type="submit">Add</button>
            </form>
            <div data-demo-items></div>
          </article>
        </section>
      </body>
    </html>
  `);
  return {
    document: dom.window.document,
    root: dom.window.document.querySelector("[data-demo-list]"),
    showcase: dom.window.document.querySelector("[data-capabilities-showcase]"),
    window: dom.window,
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

test("capabilities showcase demos render, toggle, and add items without backend calls", () => {
  const { document, root, window } = createCapabilitiesRoot();
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
    const state = createCapabilitiesDemoState("groceries");
    renderCapabilitiesDemo(root, state);

    assert.match(document.querySelector("[data-demo-summary]").textContent, /left to do/);
    assert.equal(document.querySelectorAll("[data-demo-item]").length, 6);

    toggleCapabilitiesDemoItem(root, state, "groceries-1");
    assert.equal(document.querySelector('[data-demo-toggle="groceries-1"]').checked, true);

    assert.equal(addCapabilitiesDemoItem(root, state, "  Bananas   "), true);
    assert.equal(document.querySelector('[data-demo-item="groceries-7"] strong').textContent, "Bananas");

    initCapabilitiesShowcase();
    const input = document.querySelector("[data-demo-input]");
    input.value = "Dishwasher tabs";
    document
      .querySelector("[data-demo-form]")
      .dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));

    assert.equal(document.querySelector('[data-demo-item="groceries-7"] strong').textContent, "Dishwasher tabs");

    const checkbox = document.querySelector('[data-demo-toggle="groceries-1"]');
    checkbox.checked = true;
    checkbox.dispatchEvent(new window.Event("change", { bubbles: true }));
    assert.equal(document.querySelector('[data-demo-item="groceries-1"]').classList.contains("is-checked"), true);
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
    assert.equal(dom.window.document.cookie, "listerine_locale=de");
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
