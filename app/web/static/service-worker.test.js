import test from "node:test";
import assert from "node:assert/strict";

function setGlobalProperty(name, value) {
  Object.defineProperty(globalThis, name, {
    configurable: true,
    writable: true,
    value,
  });
}

async function loadServiceWorkerModule() {
  const listeners = new Map();
  const originalSelf = globalThis.self;
  const originalCaches = globalThis.caches;
  const originalFetch = globalThis.fetch;

  setGlobalProperty("self", {
    location: { origin: "https://example.com" },
    skipWaiting() {},
    clients: { claim() {} },
    addEventListener(type, listener) {
      listeners.set(type, listener);
    },
  });

  try {
    await import(new URL(`./service-worker.js?case=${Date.now()}-${Math.random()}`, import.meta.url));
    return {
      listeners,
      restore() {
        setGlobalProperty("self", originalSelf);
        setGlobalProperty("caches", originalCaches);
        setGlobalProperty("fetch", originalFetch);
      },
    };
  } catch (error) {
    setGlobalProperty("self", originalSelf);
    setGlobalProperty("caches", originalCaches);
    setGlobalProperty("fetch", originalFetch);
    throw error;
  }
}

test("service worker precaches only static shell assets", async () => {
  const openedCaches = [];
  let cachedAssets = null;
  const { listeners, restore } = await loadServiceWorkerModule();

  setGlobalProperty("caches", {
    open: async (name) => {
      openedCaches.push(name);
      return {
        addAll: async (assets) => {
          cachedAssets = assets;
        },
      };
    },
  });

  try {
    const install = listeners.get("install");
    assert.equal(typeof install, "function");

    let installPromise = null;
    install({
      waitUntil(promise) {
        installPromise = promise;
      },
    });

    await installPromise;
    assert.deepEqual(openedCaches, ["listerine-shell-v2"]);
    assert.ok(Array.isArray(cachedAssets));
    assert.ok(cachedAssets.includes("/static/app.css"));
    assert.ok(cachedAssets.includes("/manifest.webmanifest"));
    assert.ok(!cachedAssets.includes("/"));
    assert.ok(!cachedAssets.includes("/login"));
  } finally {
    restore();
  }
});

test("service worker ignores admin navigations", async () => {
  const { listeners, restore } = await loadServiceWorkerModule();

  try {
    const fetchListener = listeners.get("fetch");
    assert.equal(typeof fetchListener, "function");

    let respondWithCalled = false;
    fetchListener({
      request: {
        method: "GET",
        url: "https://example.com/admin",
        mode: "navigate",
      },
      respondWith() {
        respondWithCalled = true;
      },
    });

    assert.equal(respondWithCalled, false);
  } finally {
    restore();
  }
});

test("service worker serves static assets from cache when available", async () => {
  const cachedResponse = { ok: true, source: "cache" };
  const { listeners, restore } = await loadServiceWorkerModule();

  setGlobalProperty("caches", {
    match: async () => cachedResponse,
  });
  setGlobalProperty("fetch", async () => {
    throw new Error("fetch should not run when the asset is cached");
  });

  try {
    const fetchListener = listeners.get("fetch");
    let responsePromise = null;

    fetchListener({
      request: {
        method: "GET",
        url: "https://example.com/static/app.css",
      },
      respondWith(promise) {
        responsePromise = promise;
      },
    });

    assert.equal(await responsePromise, cachedResponse);
  } finally {
    restore();
  }
});

test("service worker caches successful static fetches", async () => {
  const puts = [];
  const networkResponse = {
    ok: true,
    clone: () => ({ ok: true, cloned: true }),
  };
  const { listeners, restore } = await loadServiceWorkerModule();

  setGlobalProperty("caches", {
    match: async () => undefined,
    open: async () => ({
      put(request, response) {
        puts.push({ request, response });
      },
    }),
  });
  setGlobalProperty("fetch", async () => networkResponse);

  try {
    const fetchListener = listeners.get("fetch");
    let responsePromise = null;
    const request = {
      method: "GET",
      url: "https://example.com/static/app.js",
    };

    fetchListener({
      request,
      respondWith(promise) {
        responsePromise = promise;
      },
    });

    assert.equal(await responsePromise, networkResponse);
    assert.equal(puts.length, 1);
    assert.equal(puts[0].request, request);
    assert.deepEqual(puts[0].response, { ok: true, cloned: true });
  } finally {
    restore();
  }
});
