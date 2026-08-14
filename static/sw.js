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
// If a request genuinely fails (a real network hiccup), fail gracefully
// instead of throwing an unhandled rejection that can leave the page in a
// broken, half-updated state.
self.addEventListener('fetch', (event) => {
  event.respondWith(
    fetch(event.request).catch(() => {
      return new Response('Network error — please check your connection and try again.', {
        status: 503,
        statusText: 'Service Unavailable',
        headers: { 'Content-Type': 'text/plain' },
      });
    })
  );
});

// Show a real OS-level notification when a push arrives, even if the app
// isn't open. The server sends {title, body} as JSON in the push payload.
self.addEventListener('push', (event) => {
  let data = { title: 'KKI Stores', body: 'Something changed in the store.' };
  try { if (event.data) data = event.data.json(); } catch (e) {}
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/static/icon-192.png',
      badge: '/static/icon-192.png',
      // A unique tag per notification (instead of one fixed tag for all of
      // them) so each new one stacks alongside earlier ones, instead of
      // silently replacing whatever notification came before it.
      tag: 'kki-update-' + Date.now() + '-' + Math.random().toString(36).slice(2),
    })
  );
});

// Tapping the notification opens the app (or focuses it if already open).
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ('focus' in client) return client.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow('/');
    })
  );
});
