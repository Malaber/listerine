import test from "node:test";
import assert from "node:assert/strict";

import { registerServiceWorker } from "./app.js";

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
