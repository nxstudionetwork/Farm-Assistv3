/*
 ============================================================================
   FARM ASSIST - APPLICATION SHELL (app.js)
   Consolidated global system: Auth, Session, Toast, Theme, Accessibility,
   Search/Command Palette, Voice Assistant, Offline, Bookmarks, Favorites,
   Recently Viewed, Gamification, Counters, Micro Interactions, Skeletons,
   Page Persistence, Settings, Calendar, Calculators, Notifications,
   Empty States, Dialogs, Lazy Loading, PWA, UI State, Transitions.
   Replaces superapp.js and superapp-ultimate.js.
 ============================================================================
 */
(function () {
  'use strict';

  var PUBLIC_PAGES = ['login.html', 'signup.html', 'forgot.html'];

  function currentPage() {
    return window.location.pathname.split('/').pop() || 'index.html';
  }

  function isPublicPage() {
    return PUBLIC_PAGES.indexOf(currentPage()) !== -1;
  }

  /* ========================================================================
     APP STATE
     ======================================================================== */
  var App = {
    version: '4.0.0',
    initialized: false,
    db: {},
    bookmarks: JSON.parse(localStorage.getItem('farm-bookmarks') || '[]'),
    favorites: JSON.parse(localStorage.getItem('farm-favorites') || '[]'),
    recentlyViewed: JSON.parse(localStorage.getItem('farm-recently-viewed') || '[]'),
    history: JSON.parse(localStorage.getItem('farm-search-history') || '[]'),
    syncQueue: JSON.parse(localStorage.getItem('farm-sync-queue') || '[]'),
    achievements: JSON.parse(localStorage.getItem('farm-achievements') || '[]'),
    streak: parseInt(localStorage.getItem('farm-streak') || '0', 10),
    lastVisit: localStorage.getItem('farm-last-visit') || null,
    notes: JSON.parse(localStorage.getItem('farm-notes') || '[]')
  };

  /* ========================================================================
     SESSION CONSTANTS
     ======================================================================== */
  var SESSION = {
    inactivityLimitMs: 12 * 60 * 60 * 1000,
    _warned: false,
    _timer: null
  };

  /* ========================================================================
     1. INITIALIZATION
     ======================================================================== */
  document.addEventListener('DOMContentLoaded', function () {
    if (App.initialized) return;

    // Auth pages: only theme manager
    if (isPublicPage()) {
      initThemeEngine();
      return;
    }

    App.initialized = true;

    // injectShell, initHeaderEnhancements, initGlobalKeyboard, initCommandPalette,
    // initVoiceAssistant — all handled by navigation.js (single source of truth)
    initAuthGuard();
    initAppActions();
    initThemeEngine();
    initAccessibilityEngine();
    initOfflineSimulator();
    initToastSystem();
    initGamification();
    initBookmarkSystem();
    initFavoriteSystem();
    initRecentlyViewed();
    initSkeletonLoaders();
    initSmoothTransitions();
    initAnimatedCounters();
    initMicroInteractions();
    initSettingsRestore();
    initCalendarSystem();
    initCalculatorTools();
    initNotificationsCenter();
    initAnalyticsCharts();
    initEmptyStates();
    initDialogSystem();
    initLazyLoading();
    initPageSpecificFeatures();
    initPWA();
  });

  /* ========================================================================
     2. SHELL INJECTION — REMOVED (handled by navigation.js)
     ======================================================================== */
  function injectShell() { /* delegated to navigation.js */ }

  /* ========================================================================
     3. AUTH GUARD
     ======================================================================== */
  function initAuthGuard() {
    var hasToken = !!localStorage.getItem('fa-auth-token');
    var authFlag = localStorage.getItem('fa-auth') === 'true';

    if (!hasToken || !authFlag) {
      try { sessionStorage.setItem('redirect-after-login', currentPage()); } catch (e) { /* ignore */ }
      window.location.href = 'login.html';
      return;
    }

    if (isPublicPage()) {
      var dest;
      try { dest = sessionStorage.getItem('redirect-after-login'); } catch (e) { /* ignore */ }
      dest = dest || 'index.html';
      try { sessionStorage.removeItem('redirect-after-login'); } catch (e) { /* ignore */ }
      window.location.href = dest;
      return;
    }

    initPersistentSession();
    hydrateUserDisplay();
    updateStreak();

    if (window.API && window.API.Auth) {
      window.API.Auth.getMe().catch(function(err) {
        if (err && err.isAuthError) {
          localStorage.removeItem('fa-auth-token');
          localStorage.removeItem('fa-auth');
          localStorage.removeItem('fa-current-user-data');
          localStorage.removeItem('user-logged-in');
          window.location.href = 'login.html';
        }
      });
    }
  }

  function hydrateUserDisplay() {
    if (window.UserStore) {
      UserStore.hydrate();
    } else {
      var name = localStorage.getItem('user-name') || localStorage.getItem('user-display-name') || 'Farmer';
      document.querySelectorAll('.user-name-display, #farmer-name-display, #sidebar-name').forEach(function (el) {
        if (el && !el.hasAttribute('data-user')) el.textContent = name;
      });
    }
  }

  function updateStreak() {
    var today = new Date().toDateString();
    if (App.lastVisit !== today) {
      if (App.lastVisit) {
        var yesterday = new Date(Date.now() - 86400000).toDateString();
        App.streak = (App.lastVisit === yesterday) ? App.streak + 1 : 1;
      } else {
        App.streak = 1;
      }
      localStorage.setItem('farm-streak', String(App.streak));
      localStorage.setItem('farm-last-visit', today);
      App.lastVisit = today;
    }
  }

  /* ========================================================================
     4. PERSISTENT SESSION
     ======================================================================== */
  function initPersistentSession() {
    markSessionActivity();

    var lastMark = 0;
    function onActivity() {
      var now = Date.now();
      if (now - lastMark > 15000) {
        lastMark = now;
        markSessionActivity();
        if (SESSION._warned) dismissSessionWarning();
      }
    }
    ['click', 'keydown', 'mousemove', 'scroll', 'touchstart'].forEach(function (evt) {
      window.addEventListener(evt, onActivity, { passive: true });
    });

    window.addEventListener('beforeunload', function () {
      saveUnsavedFormData();
      savePageState();
    });

    window.addEventListener('storage', function (e) {
      if (e.key === 'user-logged-in' && e.newValue !== 'true') {
        window.location.href = 'login.html';
      }
    });

    if (SESSION._timer) clearInterval(SESSION._timer);
    SESSION._timer = setInterval(checkSessionActivity, 30000);
  }

  function markSessionActivity() {
    try { localStorage.setItem('session-last-activity', String(Date.now())); } catch (e) { /* ignore */ }
  }

  function checkSessionActivity() {
    var last = parseInt(localStorage.getItem('session-last-activity') || '0', 10);
    if (!last) { markSessionActivity(); return; }
    if (Date.now() - last >= SESSION.inactivityLimitMs) showSessionWarning();
  }

  function showSessionWarning() {
    if (SESSION._warned) return;
    SESSION._warned = true;
    var bd = document.getElementById('session-warning-backdrop');
    if (!bd) {
      bd = document.createElement('div');
      bd.id = 'session-warning-backdrop';
      bd.className = 'session-warning-backdrop';
      bd.innerHTML =
        '<div class="session-warning-box" role="alertdialog" aria-modal="true" aria-labelledby="session-warn-title">' +
          '<div class="session-warning-icon"><i class="fas fa-user-clock"></i></div>' +
          '<h3 id="session-warn-title">Are you still there?</h3>' +
          '<p>You\'ve been inactive for a while. For your security your session will be paused. Would you like to stay logged in?</p>' +
          '<div class="session-warning-actions">' +
            '<button class="btn-primary" id="session-stay-btn"><i class="fas fa-check"></i> Stay Logged In</button>' +
            '<button class="btn-secondary" id="session-logout-btn">Log Out</button>' +
          '</div>' +
        '</div>';
      document.body.appendChild(bd);
      document.getElementById('session-stay-btn').addEventListener('click', function () {
        markSessionActivity();
        dismissSessionWarning();
        if (typeof window.showToast === 'function') window.showToast('Welcome back! Session extended.', 'success');
      });
      document.getElementById('session-logout-btn').addEventListener('click', function () {
        window.__app.appLogout();
      });
    }
    bd.classList.add('active');
  }

  function dismissSessionWarning() {
    SESSION._warned = false;
    var bd = document.getElementById('session-warning-backdrop');
    if (bd) bd.classList.remove('active');
  }

  /* ========================================================================
     5. APP LOGOUT
     ======================================================================== */
  function appLogout() {
    saveUnsavedFormData();
    if (window.UserStore) UserStore.logout();
    localStorage.removeItem('user-logged-in');
    localStorage.removeItem('session-last-activity');
    try { sessionStorage.removeItem('redirect-after-login'); } catch (e) { /* ignore */ }
    if (typeof window.showToast === 'function') window.showToast('Logged out successfully.', 'success');
    setTimeout(function () { window.location.href = 'login.html'; }, 500);
  }

  /* ========================================================================
     6. TOAST SYSTEM
     ======================================================================== */
  function initToastSystem() { /* noop */ }

  function showToast(message, type, duration) {
    type = type || 'success';
    duration = duration || 3500;
    var container = document.getElementById('toast-container');
    if (!container) return;

    var toast = document.createElement('div');
    toast.className = 'toast-msg ' + type;
    var icons = { success: 'fa-check-circle', danger: 'fa-exclamation-circle', warning: 'fa-exclamation-triangle', info: 'fa-info-circle' };
    var icon = icons[type] || icons.success;
    toast.innerHTML = '<i class="fas ' + icon + '"></i><span>' + message + '</span>';
    container.appendChild(toast);
    requestAnimationFrame(function () { toast.classList.add('show'); });

    setTimeout(function () {
      toast.classList.remove('show');
      toast.classList.add('hide');
      setTimeout(function () { toast.remove(); }, 300);
    }, duration);
  }

  /* ========================================================================
     7. THEME ENGINE (Light only, preset support)
     ======================================================================== */
  function initThemeEngine() {
    var preset = localStorage.getItem('theme-preset') || 'forest';
    document.documentElement.setAttribute('data-theme', 'light');
    document.documentElement.setAttribute('data-theme-preset', preset);
  }

  function selectThemePreset(preset) {
    document.documentElement.setAttribute('data-theme-preset', preset);
    localStorage.setItem('theme-preset', preset);
    showToast('Theme preset switched to: ' + preset.toUpperCase(), 'success');
  }

  /* ========================================================================
     8. ACCESSIBILITY ENGINE
     ======================================================================== */
  function initAccessibilityEngine() {
    if (localStorage.getItem('access-large-text') === 'true') {
      document.body.classList.add('large-text-layout');
    }
    var contrast = localStorage.getItem('access-contrast') || 'normal';
    document.documentElement.setAttribute('data-contrast', contrast);
    var colorblind = localStorage.getItem('access-colorblind') || 'none';
    document.documentElement.setAttribute('data-colorblind', colorblind);
    var motion = localStorage.getItem('access-motion') || 'normal';
    document.documentElement.setAttribute('data-motion', motion);
  }

  /* ========================================================================
     9. GLOBAL KEYBOARD SHORTCUTS — REMOVED (handled by navigation.js)
     ======================================================================== */
  function initGlobalKeyboard() { /* delegated to navigation.js */ }

  /* ========================================================================
     10. COMMAND PALETTE & GLOBAL SEARCH — REMOVED (handled by navigation.js)
     ======================================================================== */
  function initCommandPalette() { /* delegated to navigation.js */ }

  function toggleCommandPalette() {
    if (window.FarmNav) FarmNav.toggleCommandPalette();
    else { var p = document.getElementById('cmd-palette-backdrop'); if (p) p.classList.toggle('active'); }
  }

  function closeCommandPalette() {
    if (window.FarmNav) FarmNav.closeCommandPalette();
    else { var p = document.getElementById('cmd-palette-backdrop'); if (p) p.classList.remove('active'); }
  }

  function showSuggestions() {
    if (window.FarmNav && FarmNav._showSuggestions) FarmNav._showSuggestions();
  }

  function searchTerm(term) {
    if (window.FarmNav) FarmNav.searchTerm(term);
    else { var input = document.getElementById('cmd-search-input'); if (input) { input.value = term; input.dispatchEvent(new Event('input')); } }
  }

  function clearSearchHistory() {
    if (window.FarmNav) FarmNav.clearSearchHistory();
    else {
      App.history = [];
      localStorage.setItem('farm-search-history', JSON.stringify([]));
      showToast('Search history cleared', 'warning');
    }
  }

  function performSearch(query) {
    if (window.FarmNav) return;
    var results = document.getElementById('cmd-search-results');
    if (!results || !query) { if (showSuggestions) showSuggestions(); return; }
    if (App.history.indexOf(query) === -1) {
      App.history.push(query);
      localStorage.setItem('farm-search-history', JSON.stringify(App.history));
    }
  }

  /* ========================================================================
     11. VOICE ASSISTANT — REMOVED (handled by navigation.js)
     ======================================================================== */
  function initVoiceAssistant() { /* delegated to navigation.js */ }

  function toggleVoiceAssistant() {
    if (window.FarmNav) FarmNav.toggleVoiceAssistant();
    else { var v = document.getElementById('voice-backdrop'); if (v) v.classList.toggle('active'); }
  }

  function closeVoiceAssistant() {
    if (window.FarmNav) FarmNav.closeVoiceAssistant();
    else { var v = document.getElementById('voice-backdrop'); if (v) v.classList.remove('active'); }
  }

  /* ========================================================================
     12. OFFLINE SIMULATOR
     ======================================================================== */
  function initOfflineSimulator() {
    var offline = localStorage.getItem('app-offline-state') === 'true';
    var bar = document.getElementById('system-status-bar');
    if (!bar) return;
    if (offline) {
      bar.className = 'system-status-bar active';
      bar.innerHTML = '<i class="fas fa-wifi-slash"></i> Offline Mode &bull; Pending Sync: <span id="sync-count">' + App.syncQueue.length + '</span> items';
    } else {
      bar.className = 'system-status-bar';
    }
  }

  function toggleOfflineState(state) {
    localStorage.setItem('app-offline-state', String(state));
    showToast(state ? 'Offline mode activated. Changes will sync later.' : 'Online! Syncing data...', state ? 'warning' : 'success');
    if (!state) {
      App.syncQueue = [];
      localStorage.setItem('farm-sync-queue', JSON.stringify([]));
    }
    initOfflineSimulator();
  }

  /* ========================================================================
     13. BOOKMARK SYSTEM
     ======================================================================== */
  function initBookmarkSystem() {
    App.bookmarks = JSON.parse(localStorage.getItem('farm-bookmarks') || '[]');
  }

  function toggleBookmark(type, id, btn) {
    var key = type + '-' + id;
    var idx = App.bookmarks.indexOf(key);
    if (idx > -1) {
      App.bookmarks.splice(idx, 1);
      showToast('Bookmark removed', 'warning');
      if (btn) btn.classList.remove('active');
    } else {
      App.bookmarks.push(key);
      showToast('Bookmarked!', 'success');
      if (btn) btn.classList.add('active');
    }
    localStorage.setItem('farm-bookmarks', JSON.stringify(App.bookmarks));
    updateBookmarkIcons();
  }

  function updateBookmarkIcons() {
    document.querySelectorAll('[data-bookmark]').forEach(function (el) {
      el.classList.toggle('active', App.bookmarks.indexOf(el.dataset.bookmark) !== -1);
    });
  }

  /* ========================================================================
     14. FAVORITE SYSTEM
     ======================================================================== */
  function initFavoriteSystem() {
    App.favorites = JSON.parse(localStorage.getItem('farm-favorites') || '[]');
  }

  function toggleFavorite(type, id, btn) {
    var key = type + '-' + id;
    var idx = App.favorites.indexOf(key);
    if (idx > -1) {
      App.favorites.splice(idx, 1);
      showToast('Removed from Favorites', 'warning');
      if (btn) btn.classList.remove('active');
    } else {
      App.favorites.push(key);
      showToast('Added to Favorites!', 'success');
      if (btn) btn.classList.add('active');
    }
    localStorage.setItem('farm-favorites', JSON.stringify(App.favorites));
  }

  /* ========================================================================
     15. RECENTLY VIEWED
     ======================================================================== */
  function initRecentlyViewed() {
    App.recentlyViewed = JSON.parse(localStorage.getItem('farm-recently-viewed') || '[]');
  }

  function addRecentlyViewed(type, id, title) {
    var entry = { type: type, id: id, title: title, time: Date.now() };
    App.recentlyViewed = App.recentlyViewed.filter(function (r) { return !(r.type === type && r.id === id); });
    App.recentlyViewed.unshift(entry);
    if (App.recentlyViewed.length > 20) App.recentlyViewed.pop();
    localStorage.setItem('farm-recently-viewed', JSON.stringify(App.recentlyViewed));
  }

  /* ========================================================================
     16. GAMIFICATION
     ======================================================================== */
  function initGamification() {
    App.achievements = JSON.parse(localStorage.getItem('farm-achievements') || '[]');
    var streakEl = document.querySelector('.streak-count');
    if (streakEl) streakEl.textContent = App.streak;
  }

  function unlockAchievement(id, title) {
    if (App.achievements.indexOf(id) !== -1) return;
    App.achievements.push(id);
    localStorage.setItem('farm-achievements', JSON.stringify(App.achievements));
    showToast('Achievement Unlocked: ' + title, 'success');
  }

  /* ========================================================================
     17. ANIMATED COUNTERS
     ======================================================================== */
  function initAnimatedCounters() {
    document.querySelectorAll('.animate-counter').forEach(function (el) {
      var target = parseInt(el.dataset.target) || 0;
      var duration = parseInt(el.dataset.duration) || 1500;
      var step = target / (duration / 16);
      var current = 0;
      function update() {
        current += step;
        if (current >= target) { el.textContent = target; return; }
        el.textContent = Math.floor(current);
        requestAnimationFrame(update);
      }
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) { if (e.isIntersecting) { update(); observer.unobserve(el); } });
      });
      observer.observe(el);
    });
  }

  /* ========================================================================
     18. MICRO INTERACTIONS
     ======================================================================== */
  function initMicroInteractions() {
    document.querySelectorAll('.card-premium, .stat-box, .plot-card').forEach(function (el) {
      el.addEventListener('mouseenter', function () {
        this.style.transform = 'translateY(-4px)';
        this.style.boxShadow = 'var(--shadow-hover)';
      });
      el.addEventListener('mouseleave', function () {
        this.style.transform = '';
        this.style.boxShadow = '';
      });
    });

    document.querySelectorAll('.btn-primary, .btn-secondary').forEach(function (el) {
      el.addEventListener('click', function (e) {
        var ripple = document.createElement('span');
        ripple.className = 'ripple-effect';
        var rect = this.getBoundingClientRect();
        ripple.style.left = (e.clientX - rect.left) + 'px';
        ripple.style.top = (e.clientY - rect.top) + 'px';
        this.appendChild(ripple);
        setTimeout(function () { ripple.remove(); }, 600);
      });
    });

    document.querySelectorAll('.smooth-counter').forEach(function (el) {
      var finalVal = parseInt(el.textContent.replace(/[^0-9]/g, '')) || 0;
      var suffix = el.textContent.indexOf('%') !== -1 ? '%' : '';
      var obs = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting) {
            var current = 0;
            var step = Math.ceil(finalVal / 30);
            var interval = setInterval(function () {
              current += step;
              if (current >= finalVal) { el.textContent = finalVal + suffix; clearInterval(interval); }
              else el.textContent = current + suffix;
            }, 40);
            obs.unobserve(el);
          }
        });
      }, { threshold: 0.5 });
      obs.observe(el);
    });
  }

  /* ========================================================================
     19. SKELETON LOADERS
     ======================================================================== */
  function initSkeletonLoaders() {
    document.querySelectorAll('.skeleton-loader').forEach(function (el) {
      setTimeout(function () {
        el.classList.add('loaded');
        el.style.background = 'transparent';
      }, 800 + Math.random() * 1200);
    });
  }

  /* ========================================================================
     20. PAGE STATE PERSISTENCE
     ======================================================================== */
  function savePageState() {
    try {
      var page = currentPage();
      localStorage.setItem('last-active-page', page);
      localStorage.setItem('last-scroll-' + page, String(window.scrollY || 0));
    } catch (e) { /* ignore */ }
  }

  function restorePageState() {
    try {
      var page = currentPage();
      localStorage.setItem('last-active-page', page);
    } catch (e) { /* ignore */ }
  }

  function saveUnsavedFormData() {
    try {
      var page = currentPage();
      var draft = {};
      document.querySelectorAll('input[data-persist], textarea[data-persist], select[data-persist]').forEach(function (el) {
        var key = el.id || el.name;
        if (key) draft[key] = el.type === 'checkbox' ? el.checked : el.value;
      });
      if (Object.keys(draft).length) {
        localStorage.setItem('form-draft-' + page, JSON.stringify(draft));
      }
    } catch (e) { /* ignore */ }
  }

  function restoreUnsavedFormData() {
    try {
      var page = currentPage();
      var raw = localStorage.getItem('form-draft-' + page);
      if (!raw) return;
      var draft = JSON.parse(raw);
      Object.keys(draft).forEach(function (key) {
        var el = document.getElementById(key) || document.querySelector('[name="' + key + '"]');
        if (el) {
          if (el.type === 'checkbox') el.checked = draft[key];
          else el.value = draft[key];
        }
      });
    } catch (e) { /* ignore */ }
  }

  /* ========================================================================
     21. SETTINGS RESTORE
     ======================================================================== */
  function initSettingsRestore() {
    var settings = JSON.parse(localStorage.getItem('app-settings') || '{}');
    Object.keys(settings).forEach(function (key) {
      var val = settings[key];
      if (key === 'largeText' && val) document.body.classList.add('large-text-layout');
      if (key === 'denseLayout' && val) document.body.classList.add('dense-layout');
      if (key === 'reducedMotion' && val) document.documentElement.setAttribute('data-motion', 'reduced');
      var toggle = document.querySelector('[data-setting="' + key + '"]');
      if (toggle && toggle.type === 'checkbox') toggle.checked = val;
    });
  }

  function saveSetting(key, value) {
    var settings = JSON.parse(localStorage.getItem('app-settings') || '{}');
    settings[key] = value;
    localStorage.setItem('app-settings', JSON.stringify(settings));
    if (key === 'largeText') document.body.classList.toggle('large-text-layout', value);
    if (key === 'denseLayout') document.body.classList.toggle('dense-layout', value);
    if (key === 'reducedMotion') document.documentElement.setAttribute('data-motion', value ? 'reduced' : 'normal');
    if (key === 'highContrast') document.documentElement.setAttribute('data-contrast', value ? 'high' : 'normal');
    showToast('Setting saved', 'success');
  }

  /* ========================================================================
     22. CALENDAR SYSTEM
     ======================================================================== */
  function initCalendarSystem() {
    var el = document.getElementById('calendar-container');
    if (!el) return;

    var events = App.db.events || [];
    var now = new Date();
    var month = now.toLocaleString('default', { month: 'long' });
    var year = now.getFullYear();
    var daysInMonth = new Date(year, now.getMonth() + 1, 0).getDate();
    var firstDay = new Date(year, now.getMonth(), 1).getDay();

    var html =
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;">' +
        '<h3 style="font-size:16px;"><i class="fas fa-calendar" style="color:var(--premium-green);margin-right:8px;"></i> ' + month + ' ' + year + '</h3>' +
        '<div style="display:flex;gap:8px;">' +
          '<button class="btn-secondary" style="padding:8px 12px;font-size:11px;border-radius:10px;" onclick="window.__app.showToast(\'Week view loaded\',\'info\')">Week</button>' +
          '<button class="btn-primary" style="padding:8px 12px;font-size:11px;border-radius:10px;" onclick="window.__app.showToast(\'Month view loaded\',\'info\')">Month</button>' +
        '</div>' +
      '</div>' +
      '<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:4px;text-align:center;font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:8px;">' +
        ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].map(function (d) { return '<div>' + d + '</div>'; }).join('') +
      '</div>' +
      '<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:4px;">';

    for (var i = 0; i < firstDay; i++) html += '<div></div>';
    for (var d = 1; d <= daysInMonth; d++) {
      var dateStr = month + ' ' + d + ', ' + year;
      var dayEvents = events.filter(function (e) { return e.date && e.date.indexOf(String(d)) !== -1; });
      var isToday = d === now.getDate();
      var hasEvent = dayEvents.length > 0;
      html +=
        '<div class="calendar-day ' + (isToday ? 'today' : '') + ' ' + (hasEvent ? 'has-event' : '') + '" onclick="window.__app.showToast(\'Events for ' + dateStr + '\',\'info\')">' +
          '<div style="font-size:13px;font-weight:' + (isToday ? '800' : '500') + ';color:' + (isToday ? 'var(--premium-green)' : 'var(--text-primary)') + ';">' + d + '</div>' +
          (hasEvent ? '<div style="font-size:8px;color:var(--premium-green);margin-top:2px;">' + dayEvents.length + ' event' + (dayEvents.length > 1 ? 's' : '') + '</div>' : '') +
        '</div>';
    }
    html += '</div>';

    html += '<div style="margin-top:15px;"><h4 style="font-size:13px;margin-bottom:10px;"><i class="fas fa-list" style="color:var(--premium-green);margin-right:8px;"></i> Upcoming Events</h4>';
    events.filter(function (e) { return e.date; }).slice(0, 5).forEach(function (e) {
      html +=
        '<div class="alert-strip info" style="border-left-color:var(--premium-green);padding:10px 14px;">' +
          '<div class="alert-content" style="font-size:12px;">' +
            '<i class="fas fa-circle" style="color:var(--premium-green);font-size:6px;"></i>' +
            '<div><strong>' + e.title + '</strong><div style="font-size:10px;color:var(--text-secondary);">' + e.date + ' &bull; ' + (e.time || 'All day') + '</div></div>' +
          '</div>' +
        '</div>';
    });
    html += '</div>';
    el.innerHTML = html;
  }

  /* ========================================================================
     23. CALCULATOR TOOLS
     ======================================================================== */
  function initCalculatorTools() {
    var calc = document.getElementById('calc-container');
    if (!calc) return;
    calc.innerHTML =
      '<div class="calc-card">' +
        '<h3 style="font-size:16px;margin-bottom:15px;"><i class="fas fa-calculator" style="color:var(--premium-green);margin-right:8px;"></i> Farm Profit Calculator</h3>' +
        '<div class="calc-input-group">' +
          '<label class="form-label">Total Production (Quintals): <span class="calc-val-display" id="calc-yield">100</span></label>' +
          '<input type="range" class="calc-slider" min="1" max="500" value="100" oninput="window.__app.updateCalc()" id="calc-yield-input">' +
        '</div>' +
        '<div class="calc-input-group">' +
          '<label class="form-label">Market Price per Quintal (\u20B9): <span class="calc-val-display" id="calc-price">2500</span></label>' +
          '<input type="range" class="calc-slider" min="500" max="10000" value="2500" step="100" oninput="window.__app.updateCalc()" id="calc-price-input">' +
        '</div>' +
        '<div class="calc-input-group">' +
          '<label class="form-label">Total Expenses (\u20B9): <span class="calc-val-display" id="calc-cost">35000</span></label>' +
          '<input type="range" class="calc-slider" min="1000" max="500000" value="35000" step="1000" oninput="window.__app.updateCalc()" id="calc-cost-input">' +
        '</div>' +
        '<div class="calc-result-box" id="calc-result">' +
          '<div style="font-size:14px;font-weight:700;color:var(--premium-green);">\u20B9 2,15,000</div>' +
          '<div style="font-size:11px;color:var(--text-secondary);">Estimated Net Profit</div>' +
        '</div>' +
      '</div>' +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">' +
        '<div class="calc-card" style="cursor:pointer;" onclick="window.__app.showToast(\'Seed Calculator: 20kg seeds needed for 1 acre\', \'info\')"><i class="fas fa-seedling" style="font-size:24px;color:var(--premium-green);margin-bottom:8px;display:block;"></i><h4 style="font-size:13px;">Seed Calculator</h4><p style="font-size:10px;color:var(--text-muted);">Calculate seeds per acre</p></div>' +
        '<div class="calc-card" style="cursor:pointer;" onclick="window.__app.showToast(\'Fertilizer Calculator: NPK 19:19:19 at 2kg/acre\', \'info\')"><i class="fas fa-leaf" style="font-size:24px;color:var(--premium-green);margin-bottom:8px;display:block;"></i><h4 style="font-size:13px;">Fertilizer Calc</h4><p style="font-size:10px;color:var(--text-muted);">NPK dosage calculator</p></div>' +
        '<div class="calc-card" style="cursor:pointer;" onclick="window.__app.showToast(\'Water Calculator: 2.5 acre-inches needed for rice\', \'info\')"><i class="fas fa-tint" style="font-size:24px;color:var(--premium-green);margin-bottom:8px;display:block;"></i><h4 style="font-size:13px;">Water Calculator</h4><p style="font-size:10px;color:var(--text-muted);">Irrigation requirements</p></div>' +
        '<div class="calc-card" style="cursor:pointer;" onclick="window.__app.showToast(\'Loan EMI: \u20B912,500/month for 5 years at 7%\', \'info\')"><i class="fas fa-rupee-sign" style="font-size:24px;color:var(--premium-green);margin-bottom:8px;display:block;"></i><h4 style="font-size:13px;">Loan Calculator</h4><p style="font-size:10px;color:var(--text-muted);">EMI & interest breakdown</p></div>' +
      '</div>';
  }

  function updateCalc() {
    var yieldVal = parseInt((document.getElementById('calc-yield-input') || {}).value || 100);
    var priceVal = parseInt((document.getElementById('calc-price-input') || {}).value || 2500);
    var costVal = parseInt((document.getElementById('calc-cost-input') || {}).value || 35000);
    var yEl = document.getElementById('calc-yield');
    var pEl = document.getElementById('calc-price');
    var cEl = document.getElementById('calc-cost');
    var rEl = document.getElementById('calc-result');
    if (yEl) yEl.textContent = yieldVal;
    if (pEl) pEl.textContent = priceVal;
    if (cEl) cEl.textContent = costVal;
    var revenue = yieldVal * priceVal;
    var profit = revenue - costVal;
    if (rEl) rEl.innerHTML =
      '<div style="font-size:14px;font-weight:700;color:' + (profit >= 0 ? 'var(--premium-green)' : 'var(--danger)') + ';">\u20B9 ' + profit.toLocaleString() + '</div>' +
      '<div style="font-size:11px;color:var(--text-secondary);">' + (profit >= 0 ? 'Estimated Net Profit' : 'Net Loss') + '</div>' +
      '<div style="font-size:10px;color:var(--text-muted);margin-top:4px;">Revenue: \u20B9' + revenue.toLocaleString() + ' | Cost: \u20B9' + costVal.toLocaleString() + '</div>';
  }

  /* ========================================================================
     24. NOTIFICATIONS CENTER
     ======================================================================== */
  function initNotificationsCenter() {
    var el = document.getElementById('notif-list-container');
    if (!el) return;

    var notifs = App.db.notifications || [];
    var grouped = {};
    notifs.forEach(function (n) {
      var key = n.read ? 'Earlier' : 'New';
      if (!grouped[key]) grouped[key] = [];
      grouped[key].push(n);
    });

    var html = '';
    if (grouped['New']) {
      html += '<div class="notif-section-title">New (' + grouped['New'].length + ')</div>';
      grouped['New'].forEach(function (n) { html += notifCard(n, true); });
    }
    if (grouped['Earlier']) {
      html += '<div class="notif-section-title">Earlier</div>';
      grouped['Earlier'].forEach(function (n) { html += notifCard(n, false); });
    }
    if (!html) {
      html = emptyState('notifications', 'All caught up! No new notifications.', 'notifications.html');
    }
    el.innerHTML = html;
  }

  function notifCard(n, unread) {
    var icons = { weather: 'fa-cloud-sun', market: 'fa-chart-line', ai: 'fa-robot', finance: 'fa-wallet', government: 'fa-landmark', community: 'fa-users', learning: 'fa-graduation-cap' };
    var icon = icons[n.type] || 'fa-bell';
    return '<div class="notif-card ' + (unread ? 'unread' : '') + '" onclick="this.classList.remove(\'unread\');window.__app.showToast(\'Notification opened\', \'info\')">' +
      '<div class="notif-icon-circle ' + n.type + '"><i class="fas ' + icon + '"></i></div>' +
      '<div class="notif-body"><h4 class="notif-title">' + n.title + '</h4><p class="notif-desc">' + (n.desc || n.text || '') + '</p><div class="notif-time">' + (n.time || 'Just now') + (n.priority ? ' &bull; ' + n.priority : '') + '</div></div>' +
      (unread ? '<div class="notif-unread-dot"></div>' : '') +
      '<button class="notif-action-btn" onclick="event.stopPropagation();this.closest(\'.notif-card\').remove();window.__app.showToast(\'Notification dismissed\',\'warning\')"><i class="fas fa-times"></i></button>' +
    '</div>';
  }

  function markAllNotificationsRead() {
    document.querySelectorAll('.notif-card.unread').forEach(function (el) {
      el.classList.remove('unread');
      var dot = el.querySelector('.notif-unread-dot');
      if (dot) dot.remove();
    });
    showToast('All notifications marked as read', 'success');
  }

  function clearAllNotifications() {
    document.querySelectorAll('.notif-card').forEach(function (el) { el.remove(); });
    showToast('All notifications cleared', 'warning');
  }

  /* ========================================================================
     25. ANALYTICS CHARTS (SVG-based)
     ======================================================================== */
  function initAnalyticsCharts() {
    document.querySelectorAll('[data-chart]').forEach(function (el) {
      var type = el.dataset.chart;
      if (type === 'line') renderLineChart(el);
      if (type === 'bar') renderBarChart(el);
      if (type === 'pie') renderPieChart(el);
      if (type === 'ring') renderRingChart(el);
    });
  }

  function renderLineChart(el) {
    var data = JSON.parse(el.dataset.values || '[20,35,25,45,40,55,50,65,55,70,60,75]');
    var w = el.clientWidth || 300;
    var h = 160;
    var padding = 30;
    var max = Math.max.apply(null, data);
    var stepX = (w - padding * 2) / (data.length - 1);
    var scaleY = (h - padding * 2) / max;
    var points = data.map(function (v, i) { return (padding + i * stepX) + ',' + (h - padding - v * scaleY); }).join(' ');
    el.innerHTML =
      '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '" style="width:100%;height:' + h + 'px;">' +
        '<polyline points="' + points + '" fill="none" stroke="var(--premium-green)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>' +
        '<polygon points="' + points + ' ' + (padding + (data.length - 1) * stepX) + ',' + (h - padding) + ' ' + padding + ',' + (h - padding) + '" fill="url(#lineGradient)" opacity="0.15"/>' +
        '<defs><linearGradient id="lineGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="var(--premium-green)"/><stop offset="100%" stop-color="var(--premium-green)" stop-opacity="0"/></linearGradient></defs>' +
      '</svg>';
  }

  function renderBarChart(el) {
    var data = JSON.parse(el.dataset.values || '[30,50,40,60,45,70]');
    var w = el.clientWidth || 300;
    var h = 160;
    var padding = 25;
    var max = Math.max.apply(null, data);
    var barW = (w - padding * 2) / data.length * 0.6;
    var svg = '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '" style="width:100%;height:' + h + 'px;">';
    data.forEach(function (v, i) {
      var x = padding + i * ((w - padding * 2) / data.length) + ((w - padding * 2) / data.length - barW) / 2;
      var barH = (v / max) * (h - padding * 2);
      svg += '<rect x="' + x + '" y="' + (h - padding - barH) + '" width="' + barW + '" height="' + barH + '" rx="4" fill="var(--premium-green)" opacity="0.85">' +
        '<animate attributeName="height" from="0" to="' + barH + '" dur="0.5s" fill="freeze"/>' +
        '<animate attributeName="y" from="' + (h - padding) + '" to="' + (h - padding - barH) + '" dur="0.5s" fill="freeze"/>' +
      '</rect>';
    });
    svg += '</svg>';
    el.innerHTML = svg;
  }

  function renderPieChart(el) {
    var data = JSON.parse(el.dataset.values || '[30,25,20,15,10]');
    var colors = ['var(--premium-green)', 'var(--light-green)', 'var(--warning)', 'var(--danger)', 'var(--mud-accent)'];
    var total = data.reduce(function (a, b) { return a + b; }, 0);
    var cx = 80, cy = 80, r = 65;
    var current = 0;
    var svg = '<svg width="160" height="160" viewBox="0 0 160 160"><g transform="translate(' + cx + ',' + cy + ')">';
    data.forEach(function (v) {
      var angle = (v / total) * 360;
      var start = (current - 90) * Math.PI / 180;
      var end = (current + angle - 90) * Math.PI / 180;
      var x1 = r * Math.cos(start);
      var y1 = r * Math.sin(start);
      var x2 = r * Math.cos(end);
      var y2 = r * Math.sin(end);
      var large = angle > 180 ? 1 : 0;
      svg += '<path d="M0,0 L' + x1 + ',' + y1 + ' A' + r + ',' + r + ' 0 ' + large + ',1 ' + x2 + ',' + y2 + ' Z" fill="' + colors[current % colors.length] + '" opacity="0.85"/>';
      current += angle;
    });
    svg += '<circle cx="0" cy="0" r="' + (r * 0.5) + '" fill="var(--bg-card-solid)"/>' +
      '<text x="0" y="-5" text-anchor="middle" font-size="20" font-weight="800" fill="var(--text-primary)">' + total + '</text>' +
      '<text x="0" y="12" text-anchor="middle" font-size="9" fill="var(--text-secondary)">Total</text>' +
      '</g></svg>';
    el.innerHTML = svg;
  }

  function renderRingChart(el) {
    var val = parseInt(el.dataset.value || '75');
    var max = parseInt(el.dataset.max || '100');
    var size = parseInt(el.dataset.size || '80');
    var stroke = 6;
    var cx = size / 2, cy = size / 2;
    var radius = (size - stroke) / 2;
    var circumference = 2 * Math.PI * radius;
    var offset = circumference * (1 - val / max);
    var colors = el.dataset.colors || 'var(--premium-green)';
    el.innerHTML =
      '<svg width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '">' +
        '<circle cx="' + cx + '" cy="' + cy + '" r="' + radius + '" fill="none" stroke="var(--border-light)" stroke-width="' + stroke + '"/>' +
        '<circle cx="' + cx + '" cy="' + cy + '" r="' + radius + '" fill="none" stroke="' + colors + '" stroke-width="' + stroke + '" stroke-dasharray="' + circumference + '" stroke-dashoffset="' + offset + '" stroke-linecap="round" transform="rotate(-90 ' + cx + ' ' + cy + ')">' +
          '<animate attributeName="stroke-dashoffset" from="' + circumference + '" to="' + offset + '" dur="1s" fill="freeze"/>' +
        '</circle>' +
        '<text x="' + cx + '" y="' + (cy - 4) + '" text-anchor="middle" font-size="' + (size > 80 ? 18 : 14) + '" font-weight="800" fill="var(--text-primary)">' + val + '%</text>' +
        '<text x="' + cx + '" y="' + (cy + 12) + '" text-anchor="middle" font-size="8" fill="var(--text-secondary)">' + (el.dataset.label || '') + '</text>' +
      '</svg>';
  }

  /* ========================================================================
     26. EMPTY STATES
     ======================================================================== */
  function initEmptyStates() {
    document.querySelectorAll('[data-empty-state]').forEach(function (el) {
      var type = el.dataset.emptyState;
      var message = el.dataset.emptyMessage || 'Nothing here yet';
      var action = el.dataset.emptyAction || '';
      var actionText = el.dataset.emptyActionText || 'Get Started';
      el.innerHTML = emptyState(type, message, action, actionText);
    });
  }

  function emptyState(type, message, action, actionText) {
    var icons = {
      products: 'fa-shopping-bag', expert: 'fa-user-md', news: 'fa-newspaper',
      community: 'fa-users', notifications: 'fa-bell', documents: 'fa-file-invoice',
      bookmarks: 'fa-bookmark', favorites: 'fa-heart', orders: 'fa-truck',
      tasks: 'fa-tasks', learning: 'fa-graduation-cap', generic: 'fa-inbox'
    };
    var icon = icons[type] || icons.generic;
    return '<div style="text-align:center;padding:40px 20px;">' +
      '<div style="font-size:48px;color:var(--text-muted);margin-bottom:15px;opacity:0.5;"><i class="fas ' + icon + '"></i></div>' +
      '<h4 style="font-size:16px;color:var(--text-secondary);margin-bottom:8px;">' + message + '</h4>' +
      '<p style="font-size:12px;color:var(--text-muted);margin-bottom:20px;">' + (type === 'bookmarks' ? 'Save items using the bookmark icon' : 'Check back later for updates') + '</p>' +
      (action ? '<button class="btn-primary" style="padding:10px 24px;font-size:13px;border-radius:12px;" onclick="window.location.href=\'' + action + '\'">' + actionText + '</button>' : '') +
    '</div>';
  }

  /* ========================================================================
     27. DIALOG SYSTEM
     ======================================================================== */
  function initDialogSystem() {
    document.querySelectorAll('[data-dialog]').forEach(function (el) {
      el.addEventListener('click', function () {
        var type = el.dataset.dialog;
        var title = el.dataset.dialogTitle || 'Confirm';
        var message = el.dataset.dialogMessage || 'Are you sure?';
        var callback = el.dataset.dialogCallback;
        if (type === 'confirm') {
          if (confirm(title + '\n\n' + message)) {
            showToast('Action confirmed', 'success');
            if (callback && window[callback]) window[callback]();
          }
        } else if (type === 'delete') {
          if (confirm(title + '\n\n' + message + '\n\nThis action cannot be undone.')) {
            showToast('Item deleted', 'danger');
            el.closest('.delete-target');
            if (callback && window[callback]) window[callback]();
          }
        } else if (type === 'alert') {
          alert(title + '\n\n' + message);
        }
      });
    });
  }

  function closeModal() {
    document.querySelectorAll('.modal-backdrop.active, .cmd-palette-backdrop.active, .camera-overlay.active').forEach(function (el) {
      el.classList.remove('active');
    });
  }

  /* ========================================================================
     28. LAZY LOADING
     ======================================================================== */
  function initLazyLoading() {
    document.querySelectorAll('[data-lazy]').forEach(function (el) {
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting) {
            var content = el.dataset.lazy;
            if (el.dataset.lazySrc) el.src = el.dataset.lazySrc;
            if (content) el.innerHTML = content;
            el.classList.add('lazy-loaded');
            observer.unobserve(el);
          }
        });
      }, { rootMargin: '200px' });
      observer.observe(el);
    });
  }

  /* ========================================================================
     29. PWA REGISTRATION
     ======================================================================== */
  function initPWA() {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('sw.js').catch(function () { /* noop */ });
    }
  }

  /* ========================================================================
     30. UI STATE HELPERS
     ======================================================================== */
  function UIState() {}

  UIState.empty = function (container, message, icon) {
    var el = typeof container === 'string' ? document.getElementById(container) : container;
    if (!el) return;
    el.innerHTML = '<div style="text-align:center;padding:40px 20px;">' +
      '<div style="font-size:48px;color:var(--text-muted);margin-bottom:15px;opacity:0.5;"><i class="fas ' + (icon || 'fa-inbox') + '"></i></div>' +
      '<h4 style="font-size:16px;color:var(--text-secondary);margin-bottom:8px;">' + (message || 'Nothing here yet') + '</h4>' +
    '</div>';
  };

  UIState.error = function (container, message, retryFn) {
    var el = typeof container === 'string' ? document.getElementById(container) : container;
    if (!el) return;
    el.innerHTML = '<div style="text-align:center;padding:40px 20px;">' +
      '<div style="font-size:48px;color:var(--danger);margin-bottom:15px;opacity:0.5;"><i class="fas fa-exclamation-triangle"></i></div>' +
      '<h4 style="font-size:16px;color:var(--text-secondary);margin-bottom:8px;">' + (message || 'Something went wrong') + '</h4>' +
      (retryFn ? '<button class="btn-primary" style="padding:10px 24px;font-size:13px;border-radius:12px;margin-top:10px;">Retry</button>' : '') +
    '</div>';
    if (retryFn) {
      var btn = el.querySelector('.btn-primary');
      if (btn) btn.addEventListener('click', retryFn);
    }
  };

  UIState.loading = function (container) {
    var el = typeof container === 'string' ? document.getElementById(container) : container;
    if (!el) return;
    el.innerHTML = '<div style="text-align:center;padding:40px 20px;">' +
      '<div class="skeleton-loader" style="height:20px;width:200px;margin:0 auto 10px;border-radius:8px;"></div>' +
      '<div class="skeleton-loader" style="height:14px;width:160px;margin:0 auto;border-radius:8px;"></div>' +
    '</div>';
    initSkeletonLoaders();
  };

  /* ========================================================================
     31. CONTEXTUAL PAGE ACTIONS
     ======================================================================== */
  function initAppActions() {
    window.AppActions = {
      emergency: function () {
        if (confirm('EMERGENCY SOS: Send alert to local emergency services and community network?')) {
          showToast('SOS Alert sent! Help is on the way.', 'danger');
        }
      },
      scanCrop: function () {
        showToast('Opening crop scanner...', 'info');
        var cam = document.getElementById('camera-overlay');
        if (!cam) {
          cam = document.createElement('div');
          cam.id = 'camera-overlay';
          cam.className = 'camera-overlay';
          cam.innerHTML =
            '<div class="camera-viewfinder"></div>' +
            '<div style="position:absolute;top:20px;width:100%;text-align:center;color:white;font-size:14px;font-weight:600;">Point at crop to scan for diseases</div>' +
            '<div class="camera-actions"><button class="btn-capture" onclick="window.__app.closeCamera()"></button></div>' +
            '<div style="position:absolute;bottom:120px;width:100%;text-align:center;"><button onclick="window.__app.closeCamera()" style="background:rgba(255,255,255,0.2);color:white;border:none;padding:10px 24px;border-radius:30px;font-weight:600;cursor:pointer;"><i class="fas fa-times"></i> Cancel</button></div>';
          document.body.appendChild(cam);
        }
        cam.classList.add('active');
      },
      addFarm: function () {
        var name = prompt('Enter new farm name:');
        if (name) showToast('Farm "' + name + '" created successfully!', 'success');
      },
      quickCalc: function () { window.location.href = 'tools.html'; },
      addNote: function () {
        var note = prompt('Quick note:');
        if (note) {
          App.notes.push({ text: note, date: new Date().toLocaleString() });
          localStorage.setItem('farm-notes', JSON.stringify(App.notes));
          showToast('Note saved!', 'success');
        }
      }
    };
  }

  function closeCamera() {
    var cam = document.getElementById('camera-overlay');
    if (cam) cam.classList.remove('active');
  }

  /* ========================================================================
     32. HEADER ENHANCEMENTS — REMOVED (handled by navigation.js)
     ======================================================================== */
  function initHeaderEnhancements() { /* delegated to navigation.js */ }

  /* ========================================================================
     33. PAGE-SPECIFIC FEATURES
     ======================================================================== */
  function initPageSpecificFeatures() {
    var page = currentPage();
    if (page === 'tools.html') { initCalculatorTools(); initCalendarSystem(); }
    if (page === 'notifications.html') initNotificationsCenter();

    setTimeout(function () { initAnimatedCounters(); }, 500);
    setTimeout(function () { initAnalyticsCharts(); }, 300);
  }

  /* ========================================================================
     34. SMOOTH PAGE TRANSITIONS
     ======================================================================== */
  function initSmoothTransitions() {
    document.querySelectorAll('.page-container').forEach(function (el) {
      el.style.animation = 'pageSlideUp 0.5s cubic-bezier(0.16,1,0.3,1) forwards';
    });
  }

  /* ========================================================================
     EXPOSE TO WINDOW
     ======================================================================== */
  var api = {
    appLogout: appLogout,
    showToast: showToast,
    toggleBookmark: toggleBookmark,
    toggleFavorite: toggleFavorite,
    addRecentlyViewed: addRecentlyViewed,
    unlockAchievement: unlockAchievement,
    saveSetting: saveSetting,
    toggleOfflineState: toggleOfflineState,
    toggleCommandPalette: toggleCommandPalette,
    closeCommandPalette: closeCommandPalette,
    closeVoiceAssistant: closeVoiceAssistant,
    toggleVoiceAssistant: toggleVoiceAssistant,
    closeCamera: closeCamera,
    closeModal: closeModal,
    markAllNotificationsRead: markAllNotificationsRead,
    clearAllNotifications: clearAllNotifications,
    clearSearchHistory: clearSearchHistory,
    searchTerm: searchTerm,
    searchForTerm: searchTerm,
    updateCalc: updateCalc,
    selectThemePreset: selectThemePreset,
    restoreUnsavedFormData: restoreUnsavedFormData,
    UIState: UIState,
    App: App
  };

  window.__app = api;
  window.appLogout = appLogout;
  window.showToast = showToast;
  window.toggleBookmark = toggleBookmark;
  window.toggleFavorite = toggleFavorite;
  window.addRecentlyViewed = addRecentlyViewed;
  window.unlockAchievement = unlockAchievement;
  window.saveSetting = saveSetting;
  window.toggleOfflineState = toggleOfflineState;
  window.toggleCommandPalette = toggleCommandPalette;
  window.closeCommandPalette = closeCommandPalette;
  window.closeVoiceAssistant = closeVoiceAssistant;
  window.toggleVoiceAssistant = toggleVoiceAssistant;
  window.closeCamera = closeCamera;
  window.closeModal = closeModal;
  window.markAllNotificationsRead = markAllNotificationsRead;
  window.clearAllNotifications = clearAllNotifications;
  window.clearSearchHistory = clearSearchHistory;
  window.searchTerm = searchTerm;
  window.searchForTerm = searchTerm;
  window.updateCalc = updateCalc;
  window.selectThemePreset = selectThemePreset;
  window.restoreUnsavedFormData = restoreUnsavedFormData;
  window.UIState = UIState;
  window.App = App;

})();
