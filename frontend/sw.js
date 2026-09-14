var CACHE_NAME = 'farm-assist-v19';
var STATIC_CACHE = CACHE_NAME + '-static';
var IMAGE_CACHE = CACHE_NAME + '-images';
var FONT_CACHE = CACHE_NAME + '-fonts';
var API_CACHE = CACHE_NAME + '-api';

var OFFLINE_URL = '/offline.html';

var STATIC_PATHS = [
  '/',
  '/index.html',
  '/splash.html',
  '/login.html',
  '/farm.html',
  '/tasks.html',
  '/marketplace.html',
  '/tools.html',
  '/workers.html',
  '/community.html',
  '/expert.html',
  '/profile.html',
  '/messages.html',
  '/weather.html',
  '/settings.html',
  '/sensors.html',
  '/loans.html',
  '/crop-health.html',
  '/soil-irrigation.html',
  '/farm-calendar.html',
  '/services.html',
  '/service-details.html',
  '/wallet.html',
  '/offline-support.html',
  '/expert.html',
  '/help.html',
  '/ai.html',
  '/input-store.html',
  '/market-prices.html',
  '/privacy.html',
  '/terms.html',
  '/offline.html',
  '/manifest.json',
  '/farmbuzz.html',
  '/techniques.html',
  '/news.html',
  '/notifications.html',
  '/livestock.html',
  '/map.html',
  '/analytics.html',
  '/monitoring.html',
  '/insurance.html',
  '/schemes.html',
  '/documents.html',
  '/command-center.html',
  '/emergency.html',
  '/learning.html',
  '/feedback.html',
  '/404.html',
];

var CSS_PATHS = [
  '/assets/css/style.css',
  '/assets/css/carousel.css',
];

var JS_PATHS = [
  '/assets/js/navigation.js',
  '/assets/js/app.js',
  '/assets/js/pwa.js',
  '/assets/js/carousel.js',
  '/js/services.js',
  '/js/userStore.js',
  '/js/mockData.js',
  '/js/database.js',
  '/js/script.js',
];

var IMAGE_PATHS = [
  '/assets/images/slide-1.jpg',
  '/assets/images/slide-2.jpg',
  '/assets/images/slide-3.jpg',
  '/assets/images/slide-4.jpg',
  '/assets/images/slide-5.jpg',
  '/assets/images/slide-1.webp',
  '/assets/images/slide-2.webp',
  '/assets/images/slide-3.webp',
  '/assets/images/slide-4.webp',
  '/assets/images/slide-5.webp',
];

var CDN_PATTERNS = [
  'cdnjs.cloudflare.com',
  'fonts.googleapis.com',
  'fonts.gstatic.com',
];

var API_PATTERNS = [
  '/api/',
  '/api/v1/',
];

var ALL_STATIC = [].concat(STATIC_PATHS, CSS_PATHS, JS_PATHS);

// ---- Install ----
self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(STATIC_CACHE).then(function (cache) {
      return cache.addAll(ALL_STATIC).catch(function (err) {
        console.warn('SW: Some static assets failed to cache:', err);
      });
    }).then(function () {
      return caches.open(IMAGE_CACHE).then(function (cache) {
        return cache.addAll(IMAGE_PATHS).catch(function (err) {
          console.warn('SW: Some images failed to cache:', err);
        });
      });
    })
  );
  self.skipWaiting();
});

// ---- Activate ----
self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.map(function (key) {
          if (key !== STATIC_CACHE && key !== IMAGE_CACHE && key !== FONT_CACHE && key !== API_CACHE) {
            return caches.delete(key);
          }
        })
      );
    }).then(function () {
      return self.clients.claim();
    })
  );
});

// ---- Helper: is CDN URL ----
function isCDN(url) {
  return CDN_PATTERNS.some(function (p) { return url.indexOf(p) !== -1; });
}

// ---- Helper: is API request ----
function isAPI(url) {
  return API_PATTERNS.some(function (p) { return url.indexOf(p) !== -1; });
}

// ---- Helper: is Same-Origin ----
function isSameOrigin(url) {
  return url.indexOf(self.location.origin) === 0;
}

// ---- Helper: should cache ----
function shouldCache(response) {
  return response && response.ok && response.status === 200;
}

// ---- Fetch ----
self.addEventListener('fetch', function (e) {
  var url = e.request.url;
  var isNavigate = e.request.mode === 'navigate';

  // API requests: Network first, cache fallback
  if (isAPI(url) && !isNavigate) {
    e.respondWith(networkFirst(e.request, API_CACHE));
    return;
  }

  // CDN resources: Cache first with stale-while-revalidate
  if (isCDN(url)) {
    e.respondWith(cacheFirstSWR(e.request, FONT_CACHE));
    return;
  }

  // Images (same-origin): Cache first
  if (isSameOrigin(url) && isImageRequest(url)) {
    e.respondWith(cacheFirstSWR(e.request, IMAGE_CACHE));
    return;
  }

// Static assets: Cache first. JS/CSS are network-first so app code and style
  // updates (services.js, schemes.css, etc.) are picked up instead of serving
  // a stale cached copy.
  if (isSameOrigin(url) && !isNavigate) {
    var path = url.split('?')[0].toLowerCase();
    if (path.indexOf('.js') === path.length - 3 || path.indexOf('.css') === path.length - 4) {
      e.respondWith(networkFirst(e.request, STATIC_CACHE));
    } else {
      e.respondWith(cacheFirst(e.request, STATIC_CACHE));
    }
    return;
  }

  // Navigation: Network first, fallback to cache, then offline page
  if (isNavigate) {
    e.respondWith(
      fetch(e.request).then(function (response) {
        if (shouldCache(response)) {
          var clone = response.clone();
          caches.open(STATIC_CACHE).then(function (c) { c.put(e.request, clone); });
        }
        return response;
      }).catch(function () {
        return caches.match(e.request).then(function (cached) {
          return cached || caches.match(OFFLINE_URL);
        });
      })
    );
    return;
  }

  // Everything else: Network only (don't cache opaque responses)
});

// ---- Strategies ----

function cacheFirst(request, cacheName) {
  return caches.match(request).then(function (cached) {
    return cached || fetchAndCache(request, cacheName);
  });
}

function cacheFirstSWR(request, cacheName) {
  return caches.match(request).then(function (cached) {
    var fetchPromise = fetchAndCache(request, cacheName).catch(function () {});
    return cached || fetchPromise;
  });
}

function networkFirst(request, cacheName) {
  return fetch(request).then(function (response) {
    if (shouldCache(response)) {
      var clone = response.clone();
      caches.open(cacheName).then(function (c) {
        c.put(request, clone);
      });
    }
    return response;
  }).catch(function () {
    return caches.match(request).then(function (cached) {
      return cached || new Response(
        JSON.stringify({ status: 'offline', detail: 'You are offline. Please check your connection.', data: null }),
        { headers: { 'Content-Type': 'application/json' } }
      );
    });
  });
}

function fetchAndCache(request, cacheName) {
  return fetch(request).then(function (response) {
    if (shouldCache(response)) {
      var clone = response.clone();
      caches.open(cacheName).then(function (c) { c.put(request, clone); });
    }
    return response;
  });
}

function isImageRequest(url) {
  var exts = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico'];
  var p = url.split('?')[0].toLowerCase();
  return exts.some(function (ext) { return p.indexOf(ext) === p.length - ext.length; });
}

// ---- Background Sync ----
self.addEventListener('sync', function (e) {
  if (e.tag === 'fa-sync-all') {
    e.waitUntil(syncQueueData());
  }
});

function syncQueueData() {
  return self.clients.matchAll().then(function (clients) {
    clients.forEach(function (client) {
      client.postMessage({ type: 'fa-sync-triggered', timestamp: Date.now() });
    });
  });
}

// ---- Push Notifications ----
self.addEventListener('push', function (e) {
  var data = {};
  try { data = e.data.json(); } catch (ex) { data = { title: 'Farm Assist', body: e.data.text() || 'New update available' }; }
  var options = {
    body: data.body || 'Tap to view in Farm Assist',
    icon: '/assets/icons/icon-192x192.png',
    badge: '/assets/icons/icon-72x72.png',
    vibrate: [200, 100, 200],
    data: { url: data.url || '/' },
    actions: [
      { action: 'open', title: 'Open' },
      { action: 'close', title: 'Dismiss' },
    ],
  };
  e.waitUntil(self.registration.showNotification(data.title || 'Farm Assist', options));
});

self.addEventListener('notificationclick', function (e) {
  e.notification.close();
  if (e.action === 'close') return;
  var url = e.notification.data && e.notification.data.url ? e.notification.data.url : '/';
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
    for (var i = 0; i < clientList.length; i++) {
      var client = clientList[i];
      if (client.url.indexOf(self.location.origin) !== -1 && 'focus' in client) {
        return client.focus().then(function (c) { return c.navigate(url); });
      }
    }
    if (self.clients.openWindow) return self.clients.openWindow(url);
  }));
});

// ---- Message Handler ----
self.addEventListener('message', function (e) {
  if (e.data && e.data.type === 'fa-skip-waiting') {
    self.skipWaiting();
  }
});

