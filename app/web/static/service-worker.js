const CACHE_NAME = "planini-shell-v4";
const APP_SHELL_ASSETS = [
  "/manifest.webmanifest",
  "/static/app.css",
  "/static/app.js",
  "/static/img/Favicon.png",
  "/static/img/Planini.png",
  "/static/img/apple-touch-icon.png",
  "/static/img/pwa-192.png",
  "/static/img/pwa-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL_ASSETS)).catch(() => undefined),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))),
    ),
  );
  self.clients.claim();
});

function isCacheableAssetRequest(request) {
  if (request.method !== "GET") {
    return false;
  }

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    return false;
  }

  return url.pathname === "/manifest.webmanifest" || url.pathname.startsWith("/static/");
}

function isMutableShellAssetRequest(request) {
  const url = new URL(request.url);
  return (
    url.pathname === "/manifest.webmanifest" ||
    url.pathname === "/static/app.css" ||
    url.pathname === "/static/app.js"
  );
}

function fetchAndCache(request) {
  return fetch(request).then((response) => {
    if (!response.ok || response.redirected) {
      return response;
    }

    const responseClone = response.clone();
    caches.open(CACHE_NAME).then((cache) => cache.put(request, responseClone));
    return response;
  });
}

self.addEventListener("fetch", (event) => {
  if (!isCacheableAssetRequest(event.request)) {
    return;
  }

  event.respondWith(
    isMutableShellAssetRequest(event.request)
      ? fetchAndCache(event.request).catch(() => caches.match(event.request))
      : caches.match(event.request).then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }

          return fetchAndCache(event.request);
        }),
  );
});
