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

// RAW push event — fires even when Chrome is fully killed on Android.
// This is the most reliable way to display notifications in all states.
self.addEventListener('push', function(event) {
  var payload = {};
  try { payload = event.data ? event.data.json() : {}; } catch(e) {}

  var notif = payload.notification || {};
  var data  = payload.data || {};

  var title   = notif.title || data.title || 'Notification';
  var body    = notif.body  || data.body  || '';
  var icon    = notif.icon  || data.icon  || '/static/images/logo.png';
  var link    = data.link   || '/staff/';

  var options = {
    body: body,
    icon: icon,
    badge: '/static/icons/icon-192x192.png',
    data: { link: link },
    requireInteraction: false
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

// NOTE: We intentionally do NOT use messaging.onBackgroundMessage() here.
// It conflicts with the raw 'push' event handler above on Android Chrome,
// causing double-display or silent failures. The raw 'push' handler is
// the most reliable approach across all platforms and app states.

self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  var notifData = event.notification.data || {};
  var urlToOpen = notifData.link || '/staff/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(windowClients) {
      for (var i = 0; i < windowClients.length; i++) {
        var client = windowClients[i];
        if (client.url.indexOf(self.location.origin) === 0 && 'focus' in client) {
          return client.focus();
        }
      }
      return clients.openWindow(urlToOpen);
    })
  );
});
