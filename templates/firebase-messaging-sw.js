importScripts('https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/9.23.0/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: "AIzaSyD7qnoyAyG2nU3DZOLGy2kkDkQB3FEwvqQ",
  authDomain: "mastan-761bc.firebaseapp.com",
  projectId: "mastan-761bc",
  storageBucket: "mastan-761bc.firebasestorage.app",
  messagingSenderId: "227009036928",
  appId: "1:227009036928:web:fedebf08a23e04442e1c65",
});

const messaging = firebase.messaging();

// ── Background Message Handler ──────────────────────────────────────────────
// Uses Firebase SDK's onBackgroundMessage — this is the correct way to handle
// FCM background messages on Android Chrome PWA.
// NOTE: Do NOT add a manual self.addEventListener('push', ...) here — it would
// conflict with Firebase messaging and break Android notifications.
messaging.onBackgroundMessage(function(payload) {
  // Extract from notification block (if backend sends one) or fall back to data
  const notif  = payload.notification || {};
  const data   = payload.data || {};
  const title  = notif.title  || data.title  || "Mastan Catering";
  const body   = notif.body   || data.body   || '';
  const icon   = notif.icon   || data.icon   || '/static/icons/icon-192x192.png';
  const badge  = data.icon    || '/static/icons/icon-192x192.png';
  const link   = data.link    || notif.click_action || '/staff/';

  return self.registration.showNotification(title, {
    body:  body,
    icon:  icon,
    badge: badge,
    data:  { url: link },
    // vibrate pattern for Android
    vibrate: [200, 100, 200],
  }).then(() => {
    if (navigator.setAppBadge) {
      return navigator.setAppBadge(1).catch(() => {});
    }
  });
});

// ── Notification Click Handler ──────────────────────────────────────────────
self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  if (navigator.clearAppBadge) {
    event.waitUntil(navigator.clearAppBadge().catch(() => {}));
  }

  var notifData  = event.notification.data || {};
  var urlToOpen  = notifData.url || '/staff/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(windowClients) {
      for (var i = 0; i < windowClients.length; i++) {
        var client = windowClients[i];
        if (client.url && client.url.indexOf(self.location.origin) === 0 && 'focus' in client) {
          client.focus();
          if ('navigate' in client && client.url !== urlToOpen) {
            client.navigate(urlToOpen);
          }
          return;
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(urlToOpen);
      }
    })
  );
});
