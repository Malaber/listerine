import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";

const serviceWorkerSourceUrl = new URL("./service-worker.js", import.meta.url);
const serviceWorkerSource = await import("node:fs/promises").then((fs) =>
  fs.readFile(serviceWorkerSourceUrl, "utf8"),
);

function createServiceWorkerHarness(options = {}) {
  const listeners = new Map();
  const deletedKeys = [];
  const addAllCalls = [];
  const putCalls = [];
  const fetchCalls = [];
  const matchedRequests = [];

  const openedCache = {
    addAll: async (assets) => {
      addAllCalls.push(assets);
      if (options.addAllError) {
        throw options.addAllError;
      }
    },
    put: async (request, response) => {
      putCalls.push([request, response]);
    },
  };

  const context = {
    URL,
    caches: {
      open: async (name) => {
        assert.equal(name, "listerine-shell-v2");
        return openedCache;
      },
      match: async (request) => {
        matchedRequests.push(request);
        return options.cachedResponse ?? null;
      },
      keys: async () => options.cacheKeys ?? [],
      delete: async (key) => {
        deletedKeys.push(key);
        return true;
      },
    },
    fetch: async (request) => {
      fetchCalls.push(request);
      return options.fetchResponse ?? {
        ok: true,
        redirected: false,
        clone() {
          return { cloned: true };
        },
      };
    },
    self: {
      location: { origin: "https://example.com" },
      clients: {
        claimCalled: false,
        claim() {
          this.claimCalled = true;
        },
      },
      skipWaitingCalled: false,
      skipWaiting() {
        this.skipWaitingCalled = true;
      },
      addEventListener(type, handler) {
        listeners.set(type, handler);
      },
    },
  };

  vm.runInNewContext(serviceWorkerSource, context, { filename: serviceWorkerSourceUrl.pathname });

  return {
    addAllCalls,
    deletedKeys,
    fetchCalls,
    listeners,
    matchedRequests,
    putCalls,
    self: context.self,
  };
}

async function dispatchExtendableEvent(listener, extras = {}) {
  const pending = [];
  listener({
    ...extras,
    waitUntil(promise) {
      pending.push(promise);
    },
  });
  await Promise.all(pending);
}

async function dispatchFetchEvent(listener, request) {
  let responsePromise = null;
  listener({
    request,
    respondWith(promise) {
      responsePromise = promise;
    },
  });
  return responsePromise;
}

test("service worker precaches shell assets and skips waiting", async () => {
  const harness = createServiceWorkerHarness();

  await dispatchExtendableEvent(harness.listeners.get("install"));

  assert.equal(
    JSON.stringify(harness.addAllCalls),
    JSON.stringify([
      [
        "/manifest.webmanifest",
        "/static/app.css",
        "/static/app.js",
        "/static/img/Favicon.png",
        "/static/img/Listerine.png",
        "/static/img/apple-touch-icon.png",
        "/static/img/pwa-192.png",
        "/static/img/pwa-512.png",
      ],
    ]),
  );
  assert.equal(harness.self.skipWaitingCalled, true);
});

test("service worker tolerates precache failures during install", async () => {
  const harness = createServiceWorkerHarness({ addAllError: new Error("cache unavailable") });

  await dispatchExtendableEvent(harness.listeners.get("install"));

  assert.equal(harness.self.skipWaitingCalled, true);
});

test("service worker clears old caches and claims clients on activate", async () => {
  const harness = createServiceWorkerHarness({ cacheKeys: ["listerine-shell-v1", "listerine-shell-v2"] });

  await dispatchExtendableEvent(harness.listeners.get("activate"));

  assert.deepEqual(harness.deletedKeys, ["listerine-shell-v1"]);
  assert.equal(harness.self.clients.claimCalled, true);
});

test("service worker ignores navigation requests so browser redirects stay native", async () => {
  const harness = createServiceWorkerHarness();

  const responsePromise = await dispatchFetchEvent(harness.listeners.get("fetch"), {
    method: "GET",
    mode: "navigate",
    url: "https://example.com/",
  });

  assert.equal(responsePromise, null);
  assert.deepEqual(harness.fetchCalls, []);
  assert.deepEqual(harness.matchedRequests, []);
});

test("service worker ignores admin navigations", async () => {
  const harness = createServiceWorkerHarness();

  const responsePromise = await dispatchFetchEvent(harness.listeners.get("fetch"), {
    method: "GET",
    mode: "navigate",
    url: "https://example.com/admin",
  });

  assert.equal(responsePromise, null);
  assert.deepEqual(harness.fetchCalls, []);
  assert.deepEqual(harness.matchedRequests, []);
});

test("service worker serves cached static assets", async () => {
  const cachedResponse = { cached: true };
  const harness = createServiceWorkerHarness({ cachedResponse });
  const request = { method: "GET", url: "https://example.com/static/app.css" };

  const responsePromise = await dispatchFetchEvent(harness.listeners.get("fetch"), request);

  assert.equal(await responsePromise, cachedResponse);
  assert.deepEqual(harness.fetchCalls, []);
  assert.deepEqual(harness.matchedRequests, [request]);
});

test("service worker fetches and caches uncached static assets", async () => {
  const clonedResponse = { cloned: true };
  const networkResponse = {
    ok: true,
    redirected: false,
    clone() {
      return clonedResponse;
    },
  };
  const harness = createServiceWorkerHarness({ fetchResponse: networkResponse });
  const request = { method: "GET", url: "https://example.com/static/app.css" };

  const responsePromise = await dispatchFetchEvent(harness.listeners.get("fetch"), request);

  assert.equal(await responsePromise, networkResponse);
  assert.deepEqual(harness.fetchCalls, [request]);
  assert.deepEqual(harness.putCalls, [[request, clonedResponse]]);
});

test("service worker avoids caching redirected asset responses", async () => {
  const redirectedResponse = {
    ok: true,
    redirected: true,
    clone() {
      throw new Error("redirected responses should not be cloned");
    },
  };
  const harness = createServiceWorkerHarness({ fetchResponse: redirectedResponse });
  const request = { method: "GET", url: "https://example.com/static/app.css" };

  const responsePromise = await dispatchFetchEvent(harness.listeners.get("fetch"), request);

  assert.equal(await responsePromise, redirectedResponse);
  assert.deepEqual(harness.putCalls, []);
});
