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

// Let the browser handle the WebPush payload natively!
// Since our Python backend explicitly sends the "webpush.notification" dictionary, Chrome and Safari handle it entirely natively.

self.addEventListener('push', function(event) {
  const payload = event.data ? event.data.json() : {};
  const data = payload.data || {};
  
  const title = data.title || 'Notification';
  const options = {
    body: data.body || '',
    icon: data.icon || '/static/icons/icon-192x192.png',
    badge: data.icon || '/static/icons/icon-192x192.png',
    data: {
      url: data.link || '/staff/'
    }
  };

  event.waitUntil(
    self.registration.showNotification(title, options).then(() => {
      if (navigator.setAppBadge) {
        return navigator.setAppBadge(1).catch(()=>{});
      }
    })
  );
});

self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  if (navigator.clearAppBadge) {
    event.waitUntil(navigator.clearAppBadge().catch(()=>{}));
  }
  
  var notifData = event.notification.data || {};
  var urlToOpen = notifData.url || '/staff/';
  
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
