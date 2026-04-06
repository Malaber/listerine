import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

import {
  applyLanguagePreference,
  formatInviteExpiry,
  formatPasskeyDate,
  getPreferredLocale,
  initUserSettings,
  languagePreferenceLabel,
  normalizeLanguagePreference,
  registerServiceWorker,
  setLanguageSettingsOpen,
  storeLanguagePreference,
  syncLanguageSettings,
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
  setGlobalProperty("HTMLSelectElement", dom.window.HTMLSelectElement);
}

function restoreDomGlobals(originals) {
  setGlobalProperty("HTMLElement", originals.HTMLElement);
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

test("language preference helpers normalize, store, and apply choices", () => {
  const originalDocument = globalThis.document;
  const originalHTMLElement = globalThis.HTMLElement;
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
