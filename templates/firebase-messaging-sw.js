importScripts('https://www.gstatic.com/firebasejs/8.10.1/firebase-app.js');
importScripts('https://www.gstatic.com/firebasejs/8.10.1/firebase-messaging.js');

firebase.initializeApp({
  apiKey: "AIzaSyD7qnoyAyG2nU3DZOLGy2kkDkQB3FEwvqQ",
  authDomain: "mastan-761bc.firebaseapp.com",
  projectId: "mastan-761bc",
  storageBucket: "mastan-761bc.firebasestorage.app",
  messagingSenderId: "227009036928",
  appId: "1:227009036928:web:fedebf08a23e04442e1c65",
});

const messaging = firebase.messaging();

// Manually parse pure data pushes
messaging.onBackgroundMessage((payload) => {
  console.log('[firebase-messaging-sw.js] Received data background message ', payload);
  
  var data = payload.data || {};
  const title = data.title || 'Notification';
  const options = {
    body: data.body || '',
    icon: data.icon || '/static/images/logo.png',
    data: { link: data.link || '/staff/' }
  };

  self.registration.showNotification(title, options);
});

self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  var notifData = event.notification.data || {};
  const urlToOpen = notifData.link || '/staff/';
  event.waitUntil(
    clients.matchAll({ type: 'window' }).then((windowClients) => {
      if (windowClients.length > 0) {
        return windowClients[0].focus();
      }
      return clients.openWindow(urlToOpen);
    })
  );
});
