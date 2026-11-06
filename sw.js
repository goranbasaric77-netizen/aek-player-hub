// AEK Player Hub service worker. Bump CACHE on every release.
// Only GET requests of this origin are cached; the Apps Script backend is never cached.
// OneSignal push runs inside this same worker (one service worker per scope).
try { importScripts("https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.sw.js"); } catch (e) { /* offline: caching still works */ }
const CACHE = "aek-player-hub-2026-11-06b";
const FILES = ["./", "./index.html", "./config.js", "./manifest.webmanifest", "./crest.webp", "./icon-192.png", "./icon-512.png", "./apple-touch-icon.png"];

self.addEventListener("install", e => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(FILES.map(f => new Request(f, { cache: "reload" })))));
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // backend, fonts, weather: straight to the network

  // The app page and config: network first, cache when offline.
  if (req.mode === "navigate" || url.pathname.endsWith("/config.js")) {
    e.respondWith(
      fetch(req, { cache: "no-store" })
        .then(res => { if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(req.mode === "navigate" ? "./index.html" : req, copy)); } return res; })
        .catch(() => caches.match(req.mode === "navigate" ? "./index.html" : req))
    );
    return;
  }

  // Photos, crest, icons: cache first, refresh in the background.
  e.respondWith(
    caches.match(req, { ignoreSearch: true }).then(cached => {
      const fresh = fetch(req).then(res => { if (res && res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy)); } return res; }).catch(() => cached);
      return cached || fresh;
    })
  );
});
