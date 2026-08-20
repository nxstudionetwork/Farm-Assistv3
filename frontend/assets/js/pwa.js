(function () {
  'use strict';

  var PWA = {
    SW_PATH: 'sw.js',
    REGISTRATION_KEY: 'fa-sw-registered',
    INSTALL_PROMPT_KEY: 'fa-install-dismissed',
    INSTALL_PROMPT_TIME_KEY: 'fa-install-dismissed-time',
    INSTALL_DISMISS_HOURS: 72,
    BG_SYNC_INTERVAL_MINUTES: 5,
    deferredPrompt: null,
    registration: null,
  };

  // ---- Service Worker Registration ----
  function registerServiceWorker() {
    if (!('serviceWorker' in navigator)) {
      console.log('PWA: Service Workers not supported');
      return;
    }
    window.addEventListener('load', function () {
      navigator.serviceWorker.register(PWA.SW_PATH, { scope: '/' }).then(function (reg) {
        PWA.registration = reg;
        localStorage.setItem(PWA.REGISTRATION_KEY, 'true');
        console.log('PWA: SW registered, scope:', reg.scope);

        reg.addEventListener('updatefound', function () {
          var installing = reg.installing;
          if (installing) {
            installing.addEventListener('statechange', function () {
              if (installing.state === 'installed' && navigator.serviceWorker.controller) {
                showUpdateNotification();
              }
            });
          }
        });
      }).catch(function (err) {
        console.warn('PWA: SW registration failed:', err);
      });
    });
  }

  // ---- Update Notification ----
  function showUpdateNotification() {
    var toast = document.getElementById('toast-container');
    if (!toast) return;
    var el = document.createElement('div');
    el.className = 'toast toast-warning toast-sm';
    el.style.cssText = 'position:fixed;bottom:80px;left:50%;transform:translateX(-50%);background:#0B3D2E;color:#fff;padding:10px 18px;border-radius:8px;font-size:13px;z-index:9999;display:flex;align-items:center;gap:10px;box-shadow:0 4px 12px rgba(0,0,0,0.2);max-width:90%;animation:slideUp 0.3s ease;';
    el.innerHTML = 'New version available. <button onclick="location.reload()" style="background:#4CAF50;border:none;color:#fff;padding:6px 14px;border-radius:6px;cursor:pointer;font-weight:600;font-size:12px;">Refresh</button>';
    toast.appendChild(el);
    setTimeout(function () { el.remove(); }, 30000);
  }

  // ---- Install Prompt ----
  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    PWA.deferredPrompt = e;
    var dismissed = localStorage.getItem(PWA.INSTALL_PROMPT_KEY);
    var dismissTime = parseInt(localStorage.getItem(PWA.INSTALL_PROMPT_TIME_KEY) || '0', 10);
    var hoursSince = (Date.now() - dismissTime) / (1000 * 60 * 60);
    if (dismissed === 'true' && hoursSince < PWA.INSTALL_DISMISS_HOURS) return;
    showInstallPrompt();
  });

  function showInstallPrompt() {
    var existing = document.getElementById('fa-install-prompt');
    if (existing) return;
    var el = document.createElement('div');
    el.id = 'fa-install-prompt';
    el.style.cssText = 'position:fixed;bottom:16px;left:16px;right:16px;max-width:400px;margin:0 auto;background:linear-gradient(135deg,#0B3D2E,#1B5E3F);color:#fff;border-radius:16px;padding:18px;z-index:99999;box-shadow:0 8px 32px rgba(0,0,0,0.3);display:flex;flex-direction:column;gap:10px;animation:slideUp 0.4s ease;font-family:Outfit,Segoe UI,sans-serif;';
    el.innerHTML = '<div style="display:flex;align-items:center;gap:12px;">' +
      '<img src="assets/icons/icon-72x72.png" alt="" style="width:48px;height:48px;border-radius:12px;">' +
      '<div style="flex:1;"><div style="font-weight:700;font-size:15px;">Farm Assist</div><div style="font-size:12px;opacity:0.8;">Your All-in-One Agriculture App</div></div>' +
      '<button id="fa-install-close" style="background:none;border:none;color:#fff;font-size:20px;cursor:pointer;opacity:0.7;padding:4px;">&times;</button></div>' +
      '<button id="fa-install-btn" style="background:#4CAF50;border:none;color:#fff;padding:12px;border-radius:10px;font-weight:700;font-size:14px;cursor:pointer;width:100%;">Install Farm Assist</button>' +
      '<button id="fa-install-later" style="background:transparent;border:1px solid rgba(255,255,255,0.3);color:#fff;padding:8px;border-radius:8px;font-size:12px;cursor:pointer;width:100%;">Maybe Later</button>';
    document.body.appendChild(el);
    document.getElementById('fa-install-btn').addEventListener('click', function () {
      if (PWA.deferredPrompt) {
        PWA.deferredPrompt.prompt();
        PWA.deferredPrompt.userChoice.then(function (choice) {
          if (choice.outcome === 'accepted') {
            localStorage.removeItem(PWA.INSTALL_PROMPT_KEY);
          }
          PWA.deferredPrompt = null;
        });
      }
      el.remove();
    });
    document.getElementById('fa-install-close').addEventListener('click', function () {
      localStorage.setItem(PWA.INSTALL_PROMPT_KEY, 'true');
      localStorage.setItem(PWA.INSTALL_PROMPT_TIME_KEY, Date.now().toString());
      el.remove();
    });
    document.getElementById('fa-install-later').addEventListener('click', function () {
      localStorage.setItem(PWA.INSTALL_PROMPT_KEY, 'true');
      localStorage.setItem(PWA.INSTALL_PROMPT_TIME_KEY, Date.now().toString());
      el.remove();
    });
  }

  // ---- App Installed ----
  window.addEventListener('appinstalled', function () {
    localStorage.removeItem(PWA.INSTALL_PROMPT_KEY);
    var el = document.getElementById('fa-install-prompt');
    if (el) el.remove();
    var toast = document.getElementById('toast-container');
    if (toast) {
      var t = document.createElement('div');
      t.className = 'toast toast-success';
      t.textContent = 'Farm Assist installed successfully! Open from your home screen.';
      toast.appendChild(t);
      setTimeout(function () { t.remove(); }, 4000);
    }
  });

  // ---- Background Sync ----
  function initBackgroundSync() {
    if ('serviceWorker' in navigator && 'SyncManager' in window) {
      navigator.serviceWorker.ready.then(function (reg) {
        function trySync() {
          reg.sync.register('fa-sync-all').catch(function () {
            fallbackSync();
          });
        }
        trySync();
        setInterval(trySync, PWA.BG_SYNC_INTERVAL_MINUTES * 60 * 1000);
      });
    } else {
      setInterval(fallbackSync, 2 * 60 * 1000);
    }
  }

  function fallbackSync() {
    var queue = getSyncQueue();
    if (queue.length === 0) return;
    var remaining = [];
    queue.forEach(function (item) {
      try {
        var opts = {
          method: item.method || 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: item.body ? JSON.stringify(item.body) : undefined,
        };
        var token = localStorage.getItem('fa-auth-token');
        if (token) opts.headers['Authorization'] = 'Bearer ' + token;
        fetch(item.url, opts).then(function (r) {
          if (r.ok) {
            removeFromSyncQueue(item.id);
          } else {
            remaining.push(item);
          }
        }).catch(function () {
          remaining.push(item);
        });
      } catch (e) {
        remaining.push(item);
      }
    });
    if (remaining.length < queue.length) {
      localStorage.setItem('fa-sync-queue', JSON.stringify(remaining));
    }
  }

  function getSyncQueue() {
    try { return JSON.parse(localStorage.getItem('fa-sync-queue') || '[]'); } catch (e) { return []; }
  }

  function removeFromSyncQueue(id) {
    var q = getSyncQueue().filter(function (i) { return i.id !== id; });
    localStorage.setItem('fa-sync-queue', JSON.stringify(q));
  }

  window._addToSyncQueue = function (url, method, body) {
    var q = getSyncQueue();
    q.push({ id: Date.now() + '-' + Math.random().toString(36).slice(2, 8), url: url, method: method || 'POST', body: body, timestamp: Date.now() });
    localStorage.setItem('fa-sync-queue', JSON.stringify(q));
  };

  // ---- Push Notification Subscription ----
  function initPushNotifications() {
    if (!('Notification' in window) || !('serviceWorker' in navigator) || !('PushManager' in window)) return;
    if (Notification.permission === 'granted') {
      subscribePush();
    } else if (Notification.permission === 'default') {
      if (localStorage.getItem('fa-push-prompted') !== 'true') {
        setTimeout(function () {
          Notification.requestPermission().then(function (perm) {
            localStorage.setItem('fa-push-prompted', 'true');
            if (perm === 'granted') subscribePush();
          });
        }, 30000);
      }
    }
  }

  function subscribePush() {
    if (!navigator.serviceWorker.controller) return;
    // VAPID keys would be configured by the server
    // For now, store that push is ready
    localStorage.setItem('fa-push-subscribed', 'true');
  }

  // ---- Online/Offline Detection ----
  function initOnlineDetection() {
    function updateStatus() {
      if (navigator.onLine) {
        document.body.classList.remove('fa-offline');
        var banner = document.getElementById('fa-offline-banner');
        if (banner) banner.remove();
      } else {
        document.body.classList.add('fa-offline');
        if (!document.getElementById('fa-offline-banner')) {
          var b = document.createElement('div');
          b.id = 'fa-offline-banner';
          b.style.cssText = 'position:fixed;top:0;left:0;right:0;background:#f44336;color:#fff;text-align:center;padding:6px 12px;font-size:12px;font-weight:600;z-index:99999;';
          b.textContent = 'You are offline - Showing last synced data.';
          document.body.insertBefore(b, document.body.firstChild);
        }
      }
    }
    window.addEventListener('online', updateStatus);
    window.addEventListener('offline', updateStatus);
    updateStatus();
  }

  // ---- Sync status display ----
  function initSyncDisplay() {
    var syncInfo = JSON.parse(localStorage.getItem('fa-last-sync') || '{"time":null}');
    window._getLastSyncTime = function () {
      return syncInfo.time ? new Date(syncInfo.time).toLocaleString() : 'Never';
    };
    window._updateSyncTime = function () {
      syncInfo.time = Date.now();
      localStorage.setItem('fa-last-sync', JSON.stringify(syncInfo));
    };
    navigator.serviceWorker.ready.then(function () {
      window._updateSyncTime();
    });
  }

  // ---- Init ----
  function init() {
    registerServiceWorker();
    initOnlineDetection();
    initBackgroundSync();
    initPushNotifications();
    initSyncDisplay();
  }

  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    init();
  } else {
    document.addEventListener('DOMContentLoaded', init);
  }

  window.PWA = PWA;
  window._showInstallPrompt = showInstallPrompt;
})();
