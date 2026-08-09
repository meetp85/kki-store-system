// Deliberately minimal: this app always needs a live connection to the
// server (login + database), so we do NOT cache pages or data here.
// Caching would risk showing your team a stale/outdated version of the
// app after an update is pushed. This service worker exists only to
// satisfy "installability" requirements so the app can be added to a
// phone's home screen and open in its own window.

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

// Pass every request straight through to the network - no caching.
self.addEventListener('fetch', (event) => {
  event.respondWith(fetch(event.request));
});
