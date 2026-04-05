const CACHE_NAME = "listerine-shell-v3";
const APP_SHELL_ASSETS = [
  "/manifest.webmanifest",
  "/static/app.css",
  "/static/app.js",
  "/static/img/Favicon.png",
  "/static/img/Listerine.png",
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

self.addEventListener("fetch", (event) => {
  if (!isCacheableAssetRequest(event.request)) {
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }

      return fetch(event.request).then((response) => {
        if (!response.ok || response.redirected) {
          return response;
        }

        const responseClone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseClone));
        return response;
      });
    }),
  );
});
