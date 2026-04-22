importScripts('/firebase-messaging-sw.js');

const CACHE_NAME = 'mastans-catering-v16';
const STATIC_ASSETS = [
    '/staff/login/',
    '/static/icons/icon-192x192.png',
    '/static/icons/icon-512x512.png',
    '/static/images/logo.png',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
    'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Playfair+Display:ital,wght@0,600;0,700;1,600&display=swap'
];

self.addEventListener('install', event => {
    self.skipWaiting();
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            console.log('[SW] Pre-caching core assets (tolerate 404s)');
            // Fallback tolerant caching instead of strict cache.addAll
            return Promise.allSettled(
                STATIC_ASSETS.map(url => cache.add(url).catch(err => console.warn('[SW] Cache add failed for', url, err)))
            );
        })
    );
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys => Promise.all(
            keys.map(key => {
                if (key !== CACHE_NAME) return caches.delete(key);
            })
        ))
    );
    self.clients.claim(); // Claim clients immediately so the new SW takes over.
});

self.addEventListener('fetch', event => {
    if (event.request.method !== 'GET') return;
    
    const url = new URL(event.request.url);
    
    // Network-First for all HTML Page Navigations (Including Root /)
    if (event.request.mode === 'navigate' || url.pathname === '/') {
        event.respondWith(
            fetch(event.request).then(response => {
                return caches.open(CACHE_NAME).then(cache => {
                    cache.put(event.request, response.clone());
                    return response;
                });
            }).catch(() => {
                return caches.match(event.request);
            })
        );
        return;
    }

    // Cache-First for core static assets ONLY
    if (STATIC_ASSETS.includes(url.pathname) || STATIC_ASSETS.includes(url.href)) {
        event.respondWith(
            caches.match(event.request).then(response => response || fetch(event.request))
        );
        return;
    }

    // Stale-While-Revalidate for other GET requests (excluding admin)
    if (!url.pathname.startsWith('/admin')) {
        event.respondWith(
            caches.open(CACHE_NAME).then(cache => {
                return cache.match(event.request).then(cachedResponse => {
                    const fetchedResponse = fetch(event.request).then(networkResponse => {
                        cache.put(event.request, networkResponse.clone());
                        return networkResponse;
                    });
                    return cachedResponse || fetchedResponse;
                });
            })
        );
    }
});
