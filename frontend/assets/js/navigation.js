/* ========================================================================
   FARM ASSIST - SINGLE REUSABLE NAVIGATION COMPONENT v7.0
   Renders identical navigation on every page: Top Bar, Sidebar,
   Bottom Nav, Inbox Dropdown, Profile Dropdown, Command Palette,
   and Toasts.
   ======================================================================== */
(function (global) {
  'use strict';

  var COLLAPSE_KEY = 'fa-sidebar-collapsed';
  var GROUPS_KEY = 'fa-sidebar-groups';
  var FARM_SELECT_KEY = 'fa-selected-farm';
  var SKIP_PAGES = ['login.html', 'signup.html', 'forgot.html', 'onboarding.html'];
  var AVATAR_URL = 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?fit=crop&w=150&h=150';
  var DEFAULT_FARMS = ['Shiv Sai Farm', 'North Field', 'South Field', 'East Field', 'West Field', 'Greenhouse A'];

  /* ------------------------------------------------------------------
     NAVIGATION STRUCTURE
     ------------------------------------------------------------------ */
  var NAV = [
    { type: 'header', label: 'MAIN' },
    { type: 'item', label: 'Dashboard', icon: 'fa-house', href: 'index.html' },
    { type: 'separator' },
    { type: 'header', label: 'FARM MANAGEMENT' },
    { type: 'item', label: 'My Farm', icon: 'fa-tractor', href: 'farm.html' },
    { type: 'item', label: 'Farm Calendar', icon: 'fa-calendar-days', href: 'farm-calendar.html' },
    { type: 'item', label: 'Tasks', icon: 'fa-list-check', href: 'tasks.html' },
    { type: 'item', label: 'Crop Health', icon: 'fa-leaf', href: 'crop-health.html' },
    { type: 'item', label: 'Soil & Irrigation', icon: 'fa-droplet', href: 'soil-irrigation.html' },
    { type: 'item', label: 'Weather', icon: 'fa-cloud-sun', href: 'weather.html' },
    { type: 'item', label: 'Farm Map', icon: 'fa-map-location-dot', href: 'map.html' },
    { type: 'item', label: 'Sensors', icon: 'fa-microchip', href: 'sensors.html' },
    { type: 'item', label: 'Livestock', icon: 'fa-cow', href: 'livestock.html' },
    { type: 'item', label: 'Documents', icon: 'fa-folder-open', href: 'documents.html' },
    { type: 'separator' },
    { type: 'header', label: 'RESOURCES' },
    { type: 'item', label: 'Tools & Equipment', icon: 'fa-toolbox', href: 'tools.html' },
    { type: 'item', label: 'Workers', icon: 'fa-users', href: 'workers.html' },
    { type: 'item', label: 'Input Store', icon: 'fa-cubes', href: 'input-store.html' },
    { type: 'separator' },
    { type: 'header', label: 'MONITORING & ANALYTICS' },
    { type: 'item', label: 'Smart Monitoring', icon: 'fa-eye', href: 'monitoring.html' },
    { type: 'item', label: 'Analytics', icon: 'fa-chart-pie', href: 'analytics.html' },
    { type: 'separator' },
    { type: 'header', label: 'MARKET' },
    { type: 'item', label: 'Marketplace', icon: 'fa-shopping-bag', href: 'marketplace.html' },
    { type: 'item', label: 'Market Prices', icon: 'fa-chart-line', href: 'market-prices.html' },
    { type: 'item', label: 'Insurance', icon: 'fa-shield-halved', href: 'insurance.html' },
    { type: 'item', label: 'Loans', icon: 'fa-hand-holding-dollar', href: 'loans.html' },
    { type: 'item', label: 'Government Schemes', icon: 'fa-landmark', href: 'schemes.html' },
    { type: 'separator' },
    { type: 'header', label: 'COMMUNITY' },
    { type: 'item', label: 'Community', icon: 'fa-people-group', href: 'community.html' },
    { type: 'item', label: 'FarmBuzz', icon: 'fa-film', href: 'farmbuzz.html' },
    { type: 'item', label: 'Experts', icon: 'fa-user-doctor', href: 'expert.html' },
    { type: 'item', label: 'Messages', icon: 'fa-comment-dots', href: 'messages.html' },
    { type: 'item', label: 'News Center', icon: 'fa-newspaper', href: 'news.html' },
    { type: 'item', label: 'Notifications', icon: 'fa-bell', href: 'notifications.html' },
    { type: 'separator' },
    { type: 'header', label: 'LEARNING' },
    { type: 'item', label: 'Farm Techniques', icon: 'fa-book-open', href: 'techniques.html' },
    { type: 'item', label: 'Learning Hub', icon: 'fa-graduation-cap', href: 'learning.html' },
    { type: 'separator' },
    { type: 'header', label: 'SERVICES' },
    { type: 'item', label: 'Services', icon: 'fa-concierge-bell', href: 'services.html' },
    { type: 'item', label: 'Command Center', icon: 'fa-terminal', href: 'command-center.html' },
    { type: 'item', label: 'Emergency', icon: 'fa-triangle-exclamation', href: 'emergency.html' },
    { type: 'separator' },
    { type: 'header', label: 'AI' },
    { type: 'item', label: 'AI Assist', icon: 'fa-robot', href: 'ai.html' },
    { type: 'separator' },
    { type: 'header', label: 'ACCOUNT' },
    { type: 'item', label: 'Profile', icon: 'fa-user-circle', href: 'profile.html' },
    { type: 'item', label: 'Digital Wallet', icon: 'fa-wallet', href: 'wallet.html' },
    { type: 'item', label: 'Settings', icon: 'fa-gear', href: 'settings.html' },
    { type: 'item', label: 'Feedback', icon: 'fa-pen-to-square', href: 'feedback.html' },
    { type: 'item', label: 'Help & Support', icon: 'fa-circle-question', href: 'help.html' }
  ];

  var BOTTOM_NAV = [
    { label: 'AI', icon: 'fa-robot', href: 'ai.html' },
    { label: 'Market', icon: 'fa-store', href: 'marketplace.html' },
    { label: 'Home', icon: 'fa-home', href: 'index.html', center: true },
    { label: 'Farm', icon: 'fa-tractor', href: 'farm.html' },
    { label: 'Services', icon: 'fa-concierge-bell', href: 'services.html' }
  ];

  /* ------------------------------------------------------------------
     NOTIFICATION DATA (fetched from backend, no mock data)
     ------------------------------------------------------------------ */
  var NOTIF_DATA = [];

  /* ------------------------------------------------------------------
     HELPERS
     ------------------------------------------------------------------ */
  function currentPage() {
    return window.location.pathname.split('/').pop() || 'index.html';
  }

  function getOpenGroups() {
    try { return JSON.parse(localStorage.getItem(GROUPS_KEY) || '{}'); } catch (e) { return {}; }
  }

  function setOpenGroups(g) {
    try { localStorage.setItem(GROUPS_KEY, JSON.stringify(g)); } catch (e) {}
  }

  function isCollapsed() {
    return localStorage.getItem(COLLAPSE_KEY) === '1';
  }

  function setCollapsed(val) {
    localStorage.setItem(COLLAPSE_KEY, val ? '1' : '0');
  }

  function getUserData() {
    try {
      if (window.UserStore && UserStore.getCurrentUser) {
        var u = UserStore.getCurrentUser();
        if (u) return {
          full_name: u.full_name || u.fullName || 'Farmer',
          fullName: u.full_name || u.fullName || 'Farmer',
          email: u.email || '',
          farmer_id: u.farmer_id || u.farmerId || '',
          role: u.role || 'farmer',
          profile_image: u.profile_image || u.photo || ''
        };
      }
    } catch (e) {}
    var name = '';
    try { name = localStorage.getItem('user-name') || ''; } catch (e) {}
    return { full_name: name || 'Farmer', fullName: name || 'Farmer', email: '', role: 'farmer', profile_image: '' };
  }

  function getUserAvatar() {
    try {
      if (window.UserStore && UserStore.avatarFor) return UserStore.avatarFor(getUserData());
    } catch (e) {}
    return AVATAR_URL;
  }

  function getFarmId() {
    var u = getUserData();
    return u.farmer_id || 'FA-AS-00000001';
  }

  var _unreadCount = 0;
  function getUnreadCount() { return _unreadCount; }
  function fetchUnreadCount() {
    try {
      var token = localStorage.getItem('fa-auth-token');
      if (!token) return;
      fetch('/api/v1/notifications/unread', { headers: { 'Authorization': 'Bearer ' + token } })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d && d.status === 'success' && d.data) {
            _unreadCount = d.data.unread_count || 0;
            updateInboxBadge();
          }
        }).catch(function () {});
    } catch (e) {}
  }

  function isLoginPage() {
    return SKIP_PAGES.indexOf(currentPage()) !== -1;
  }

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  /* ------------------------------------------------------------------
     REMOVE EXISTING INLINE NAVIGATION
     ------------------------------------------------------------------ */
  function removeExistingNav() {
    var selectors = [
      'header.top-bar', '.sidebar-backdrop', 'aside.sidebar',
      'nav.bottom-nav', '.profile-dropdown', '.inbox-dropdown',
      '.cmd-palette-backdrop', '.toast-container', '#superapp-shell-injected'
    ];
    selectors.forEach(function (sel) {
      document.querySelectorAll(sel).forEach(function (el) { el.remove(); });
    });
  }

  function getFarmOptions() {
    var farms = [];
    try {
      if (window.AppMockData && AppMockData.farms && AppMockData.farms.length) {
        farms = AppMockData.farms.map(function (f) {
          return f.name || f.farm_name || 'Farm';
        });
      }
    } catch (e) {}
    if (!farms.length) farms = DEFAULT_FARMS.slice();
    return farms;
  }

  function getSelectedFarm() {
    try { return localStorage.getItem(FARM_SELECT_KEY) || ''; } catch (e) { return ''; }
  }

  /* ------------------------------------------------------------------
     INJECT TOP BAR
     ------------------------------------------------------------------ */
  function injectTopBar() {
    if (document.querySelector('header.top-bar')) return;
    var farmSelectHtml = '';
    var farmOptions = getFarmOptions();
    if (farmOptions.length > 1) {
      var savedFarm = getSelectedFarm();
      farmSelectHtml = '<div class="global-farm-wrap" title="Select farm">' +
        '<i class="fas fa-tractor"></i>' +
        '<select id="global-farm-select" class="global-farm-select" aria-label="Select farm">';
      farmOptions.forEach(function (f) {
        farmSelectHtml += '<option value="' + escapeHtml(f) + '"' + (f === savedFarm ? ' selected' : '') + '>' + escapeHtml(f) + '</option>';
      });
      farmSelectHtml += '</select></div>';
    }
    var header = document.createElement('header');
    header.className = 'top-bar';
    header.innerHTML =
      '<div class="top-bar-left">' +
        '<button class="hamburger-btn" id="menu-btn" aria-label="Toggle Navigation Drawer" aria-expanded="false">' +
          '<i class="fas fa-bars"></i>' +
        '</button>' +
        '<a href="index.html" class="app-logo">' +
          '<img src="assets/icons/icon.svg" alt="" width="28" height="28" style="margin-right:8px;">' +
          '<span class="app-logo-text">Farm Assist</span>' +
        '</a>' +
      '</div>' +
      farmSelectHtml +
      '<div class="top-bar-right">' +
        '<a href="map.html" class="top-btn" aria-label="Farm Map" title="Farm Map">' +
          '<i class="fas fa-map-location-dot"></i>' +
        '</a>' +
        '<a href="wallet.html" class="top-btn" aria-label="Digital Wallet" title="Digital Wallet">' +
          '<i class="fas fa-wallet"></i>' +
        '</a>' +
        '<a href="messages.html" class="top-btn" id="inbox-btn" aria-label="Messages" title="Messages" ' +
          'data-nav-swap="messages">' +
          '<i class="fas fa-comment-dots"></i>' +
        '</a>' +
        '<button class="profile-avatar top-bar-avatar" id="nav-profile-avatar" aria-label="Profile Menu">' +
          '<img data-user-avatar src="' + AVATAR_URL + '" alt="Profile">' +
        '</button>' +
      '</div>';
    document.body.insertBefore(header, document.body.firstChild);
  }

  /* ------------------------------------------------------------------
     INJECT SIDEBAR BACKDROP
     ------------------------------------------------------------------ */
  function injectBackdrop() {
    if (document.querySelector('.sidebar-backdrop')) return;
    var bd = document.createElement('div');
    bd.className = 'sidebar-backdrop';
    bd.id = 'sidebar-backdrop';
    document.body.appendChild(bd);
  }

  /* ------------------------------------------------------------------
     INJECT SIDEBAR
     ------------------------------------------------------------------ */
  function injectSidebar() {
    if (document.querySelector('aside.sidebar')) return;
    var page = currentPage();
    var user = getUserData();

    var menuHtml = '';
    NAV.forEach(function (n) {
      if (n.type === 'item') {
        menuHtml += buildSidebarItem(n, page);
      } else if (n.type === 'separator') {
        menuHtml += '<div class="sb-separator"></div>';
      } else if (n.type === 'header') {
        menuHtml += '<div class="sb-section-header">' + escapeHtml(n.label) + '</div>';
      }
    });

    var aside = document.createElement('aside');
    aside.className = 'sidebar';
    aside.id = 'sidebar';
    aside.innerHTML =
      '<div class="sidebar-header">' +
        '<div class="sidebar-brand">' +
          '<img src="assets/icons/icon.svg" alt="" width="32" height="32" class="sidebar-logo-img">' +
          '<div class="sidebar-brand-info">' +
            '<div class="sidebar-brand-name">Farm Assist</div>' +
          '</div>' +
        '</div>' +
        '<div class="sidebar-header-actions">' +
          '<button class="sidebar-collapse-toggle" id="sidebar-collapse-toggle" title="Collapse sidebar" aria-label="Collapse sidebar"><i class="fas fa-angles-left"></i></button>' +
          '<button class="sidebar-close" id="sidebar-close" aria-label="Close sidebar"><i class="fas fa-times"></i></button>' +
        '</div>' +
      '</div>' +
      '<div class="sidebar-user">' +
        '<img data-user-avatar src="' + AVATAR_URL + '" alt="Profile" class="sidebar-user-avatar">' +
        '<div class="sidebar-user-info">' +
          '<h4 id="sidebar-name">' + escapeHtml(user.full_name || user.fullName || 'Farmer') + '</h4>' +
          '<p>' + escapeHtml(user.farmer_id || user.email || user.role || 'farmer') + '</p>' +
        '</div>' +
      '</div>' +
      '<nav class="sidebar-menu" id="sidebar-menu" aria-label="Main navigation">' +
        menuHtml +
      '</nav>' +
      '<div class="sidebar-footer">' +
        '<div class="sidebar-footer-brand">' +
          '<span class="sidebar-footer-powered">Powered by</span>' +
          '<span class="sidebar-footer-ifx">IFX Group</span>' +
        '</div>' +
      '</div>';
    document.body.appendChild(aside);
  }

  function isItemActive(itemHref, page) {
    if (itemHref === page) return true;
    var itemBase = itemHref.split('#')[0];
    var pageBase = page.split('#')[0];
    return itemBase === pageBase;
  }

  function buildSidebarItem(item, page) {
    var active = isItemActive(item.href, page) ? ' active' : '';
    var safeLabel = escapeHtml(item.label);
    return '<a href="' + item.href + '" class="sidebar-item' + active + '" data-tooltip="' + safeLabel + '">' +
      '<i class="fas ' + item.icon + '"></i><span class="sb-label">' + safeLabel + '</span></a>';
  }

  /* ------------------------------------------------------------------
     INJECT BOTTOM NAV
     ------------------------------------------------------------------ */
  function injectBottomNav() {
    if (document.querySelector('nav.bottom-nav')) return;
    var page = currentPage();
    var html = '';
    BOTTOM_NAV.forEach(function (item) {
      var active = item.href === page ? ' active' : '';
      var cls = 'bottom-nav-item' + active + (item.center ? ' home-highlight' : '');
      html += '<a href="' + item.href + '" class="' + cls + '" aria-label="' + escapeHtml(item.label) + '">';
      html += '<i class="fas ' + item.icon + '"></i>';
      html += '<span>' + escapeHtml(item.label) + '</span></a>';
    });
    var nav = document.createElement('nav');
    nav.className = 'bottom-nav';
    nav.id = 'bottom-nav';
    nav.setAttribute('aria-label', 'Bottom navigation');
    nav.innerHTML = html;
    document.body.appendChild(nav);
  }

  /* ------------------------------------------------------------------
     INJECT INBOX DROPDOWN
     ------------------------------------------------------------------ */
  function injectInboxDropdown() {
    if (document.getElementById('inbox-dropdown')) return;
    var dd = document.createElement('div');
    dd.className = 'inbox-dropdown';
    dd.id = 'inbox-dropdown';
    dd.innerHTML = buildInboxHTML('all');
    document.body.appendChild(dd);
  }

  function buildInboxHTML(filter) {
    var messages = [];
    if (filter && filter !== 'all') {
      if (filter === 'unread') {
        messages = messages.filter(function (m) { return m.unread; });
      } else {
        messages = messages.filter(function (m) { return m.type === filter; });
      }
    }

    var avatarColors = ['#1B5E3F', '#40916C', '#E9B640', '#8B6F47', '#0F2E1E', '#52B788', '#2D8659'];

    var html =
      '<div class="inbox-header">' +
        '<h3><i class="fas fa-inbox"></i> Inbox</h3>' +
        '<button class="inbox-mark-read" id="inbox-mark-all" aria-label="Mark all messages as read">Mark all read</button>' +
      '</div>' +
      '<div class="inbox-filters">' +
        '<button class="inbox-filter-chip' + (filter === 'all' ? ' active' : '') + '" data-filter="all">All</button>' +
        '<button class="inbox-filter-chip' + (filter === 'unread' ? ' active' : '') + '" data-filter="unread">Unread</button>' +
        '<button class="inbox-filter-chip' + (filter === 'community' ? ' active' : '') + '" data-filter="community">Community</button>' +
        '<button class="inbox-filter-chip' + (filter === 'expert' ? ' active' : '') + '" data-filter="expert">Experts</button>' +
        '<button class="inbox-filter-chip' + (filter === 'alert' ? ' active' : '') + '" data-filter="alert">Alerts</button>' +
      '</div>' +
      '<div class="inbox-list">';

    if (messages.length === 0) {
      html += '<div class="inbox-empty"><i class="fas fa-check-circle"></i><p>All caught up!</p></div>';
    } else {
      messages.forEach(function (m, idx) {
        var color = avatarColors[m.id % avatarColors.length];
        html +=
          '<div class="inbox-item' + (m.unread ? ' unread' : '') + '" data-id="' + m.id + '" tabindex="0">' +
            '<div class="inbox-item-avatar" style="background:' + color + ';">' +
              '<span>' + escapeHtml(m.avatar) + '</span>' +
            '</div>' +
            '<div class="inbox-item-content">' +
              '<div class="inbox-item-top">' +
                '<span class="inbox-item-sender">' + escapeHtml(m.sender) + '</span>' +
                '<span class="inbox-item-time">' + escapeHtml(m.time) + '</span>' +
              '</div>' +
              '<p class="inbox-item-msg">' + escapeHtml(m.msg) + '</p>' +
            '</div>' +
            (m.unread ? '<span class="inbox-unread-dot"></span>' : '') +
          '</div>';
      });
    }

    html += '</div>' +
      '<div class="inbox-footer">' +
        '<a href="messages.html" class="inbox-view-all">View All Messages <i class="fas fa-arrow-right"></i></a>' +
      '</div>';
    return html;
  }

  /* ------------------------------------------------------------------
     INJECT PROFILE DROPDOWN
     ------------------------------------------------------------------ */
  function injectProfileDropdown() {
    if (document.getElementById('profile-dropdown')) return;
    var user = getUserData();
    var avatar = getUserAvatar();
    var menu = document.createElement('div');
    menu.className = 'profile-dropdown';
    menu.id = 'profile-dropdown';
    menu.setAttribute('role', 'menu');
    menu.innerHTML =
      '<div class="pd-head">' +
        '<img src="' + avatar + '" alt="avatar" class="pd-avatar">' +
        '<div class="pd-head-info">' +
          '<h5>' + escapeHtml(user.full_name || user.fullName || 'Farmer') + '</h5>' +
          '<p>' + escapeHtml(user.farmer_id || user.email || user.role || 'farmer') + '</p>' +
        '</div>' +
      '</div>' +
      '<div class="pd-divider"></div>' +
      '<a href="profile.html" class="pd-item" role="menuitem"><i class="fas fa-user"></i> My Profile</a>' +
      '<a href="farm.html" class="pd-item" role="menuitem"><i class="fas fa-tractor"></i> My Farms</a>' +
      '<a href="settings.html" class="pd-item" role="menuitem"><i class="fas fa-gear"></i> Settings</a>' +
      '<a href="documents.html" class="pd-item" role="menuitem"><i class="fas fa-folder"></i> Documents</a>' +
      '<a href="help.html" class="pd-item" role="menuitem"><i class="fas fa-circle-question"></i> Help</a>' +
      '<div class="pd-divider"></div>' +
      '<button type="button" class="pd-item pd-logout" id="nav-pd-logout" role="menuitem"><i class="fas fa-right-from-bracket"></i> Logout</button>';
    document.body.appendChild(menu);
  }

  /* ------------------------------------------------------------------
     INJECT COMMAND PALETTE
     ------------------------------------------------------------------ */
  function injectCommandPalette() {
    if (document.getElementById('cmd-palette-backdrop')) return;
    var cmd = document.createElement('div');
    cmd.id = 'cmd-palette-backdrop';
    cmd.className = 'cmd-palette-backdrop';
    cmd.setAttribute('role', 'dialog');
    cmd.setAttribute('aria-modal', 'true');
    cmd.innerHTML =
      '<div class="cmd-palette-box">' +
        '<div class="cmd-palette-header">' +
          '<i class="fas fa-search" style="color:var(--premium-green);"></i>' +
          '<input type="text" id="cmd-search-input" class="cmd-palette-input" placeholder="Search pages... (Ctrl+K)" autocomplete="off" aria-label="Search pages">' +
          '<kbd class="cmd-palette-kbd">ESC</kbd>' +
        '</div>' +
        '<div class="cmd-palette-results" id="cmd-search-results">' +
          '<div class="cmd-search-placeholder">Type to search pages and actions...</div>' +
        '</div>' +
      '</div>';
    document.body.appendChild(cmd);
  }

  /* ------------------------------------------------------------------
     INJECT TOAST CONTAINER
     ------------------------------------------------------------------ */
  function injectToastContainer() {
    if (document.getElementById('toast-container')) return;
    var tc = document.createElement('div');
    tc.id = 'toast-container';
    tc.className = 'toast-container';
    tc.setAttribute('aria-live', 'polite');
    document.body.appendChild(tc);
  }

  /* ------------------------------------------------------------------
     EVENT BINDING
     ------------------------------------------------------------------ */
  function bindEvents() {
    var menuBtn = document.getElementById('menu-btn');
    var sidebar = document.getElementById('sidebar');
    var backdrop = document.getElementById('sidebar-backdrop');
    var closeBtn = document.getElementById('sidebar-close');

    if (menuBtn) {
      menuBtn.addEventListener('click', function () {
        if (window.innerWidth >= 1024) {
          var isCollapsed = document.body.classList.contains('sidebar-collapsed');
          document.body.classList.toggle('sidebar-collapsed', !isCollapsed);
          try { localStorage.setItem(COLLAPSE_KEY, isCollapsed ? '0' : '1'); } catch (e) {}
          var icon = menuBtn.querySelector('i');
          if (icon) icon.className = isCollapsed ? 'fas fa-bars' : 'fas fa-bars';
          return;
        }
        var isOpen = sidebar.classList.contains('open');
        sidebar.classList.toggle('open', !isOpen);
        backdrop.classList.toggle('active', !isOpen);
        menuBtn.setAttribute('aria-expanded', String(!isOpen));
      });
    }

    function closeSidebarFn() {
      sidebar.classList.remove('open');
      backdrop.classList.remove('active');
      if (menuBtn) menuBtn.setAttribute('aria-expanded', 'false');
    }

    if (closeBtn) closeBtn.addEventListener('click', closeSidebarFn);
    if (backdrop) backdrop.addEventListener('click', closeSidebarFn);

    /* -- Sidebar collapse toggle (desktop) ---------------------------- */
    var collapseToggle = document.getElementById('sidebar-collapse-toggle');
    if (collapseToggle) {
      collapseToggle.addEventListener('click', function () {
        if (window.innerWidth < 1024) return;
        var nowCollapsed = !isCollapsed();
        setCollapsed(nowCollapsed);
        applyCollapse();
      });
    }

    /* -- Sidebar item click auto-close on mobile ---------------------- */
    var sidebarMenu = document.getElementById('sidebar-menu');
    if (sidebarMenu) {
      sidebarMenu.addEventListener('click', function (e) {
        var item = e.target.closest('.sidebar-item');
        if (item && window.innerWidth < 1024) {
          closeSidebarFn();
        }
      });
    }

    /* -- Logout ------------------------------------------------------ */
    var pdLogout = document.getElementById('nav-pd-logout');
    if (pdLogout) {
      pdLogout.addEventListener('click', function () {
        if (confirm('Are you sure you want to log out?')) {
          closeProfileDropdown();
          if (window.API && window.API.Auth) {
            window.API.Auth.logout().catch(function () {});
          }
          try {
            localStorage.removeItem('fa-auth-token');
            localStorage.removeItem('fa-current-user-data');
            localStorage.removeItem('fa-auth');
            localStorage.removeItem('user-logged-in');
            localStorage.removeItem('user-name');
            localStorage.removeItem('user-role');
            localStorage.removeItem('session-last-activity');
          } catch (e) {}
          window.location.href = 'login.html';
        }
      });
    }

    /* -- Inbox dropdown ---------------------------------------------- */
    bindInboxDropdown();

    /* -- Global farm selector ---------------------------------------- */
    var farmSelect = document.getElementById('global-farm-select');
    if (farmSelect) {
      farmSelect.addEventListener('change', function () {
        var val = this.value;
        try { localStorage.setItem(FARM_SELECT_KEY, val); } catch (e) {}
        showToast('Viewing: ' + val, 'info');
        document.dispatchEvent(new CustomEvent('farm-selected', { detail: { farm: val } }));
      });
    }

    /* -- Profile avatar dropdown ------------------------------------- */
    bindProfileDropdown();

    /* -- Keyboard shortcuts ------------------------------------------ */
    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        toggleCommandPalette();
      }
      if (e.key === 'Escape') {
        closeCommandPalette();
        closeInboxDropdown();
        closeProfileDropdown();
      }
    });

    /* -- Command palette backdrop click to close --------------------- */
    var cmdBackdrop = document.getElementById('cmd-palette-backdrop');
    if (cmdBackdrop) {
      cmdBackdrop.addEventListener('click', function (e) {
        if (e.target === cmdBackdrop) closeCommandPalette();
      });
    }

    /* -- Window resize: manage sidebar collapse state ----------------- */
    window.addEventListener('resize', function () {
      if (window.innerWidth < 1024) {
        document.body.classList.remove('sidebar-collapsed');
        closeSidebarFn();
      } else {
        applyCollapse();
      }
    });

    /* -- Init command palette search --------------------------------- */
    initCommandPaletteSearch();
  }

  /* ------------------------------------------------------------------
     INBOX DROPDOWN LOGIC
     ------------------------------------------------------------------ */
  function bindInboxDropdown() {
    var inboxBtn = document.getElementById('inbox-btn');
    var dd = document.getElementById('inbox-dropdown');
    if (!inboxBtn) return;

    inboxBtn.addEventListener('click', function (e) {
      closeProfileDropdown();
    });

    if (!dd) return;

    document.addEventListener('click', function (e) {
      if (!dd.contains(e.target) && e.target !== inboxBtn && !inboxBtn.contains(e.target)) {
        closeInboxDropdown();
      }
    });
  }

  function closeInboxDropdown() {
    var dd = document.getElementById('inbox-dropdown');
    if (dd) dd.classList.remove('open');
  }

  function bindInboxFilters() {
    var dd = document.getElementById('inbox-dropdown');
    if (!dd) return;
    dd.querySelectorAll('.inbox-filter-chip').forEach(function (chip) {
      chip.addEventListener('click', function () {
        var filter = this.getAttribute('data-filter');
        dd.innerHTML = buildInboxHTML(filter);
        bindInboxFilters();
        bindInboxItems();
      });
    });
    var markAll = document.getElementById('inbox-mark-all');
    if (markAll) {
      markAll.addEventListener('click', function () {
        NOTIF_DATA.forEach(function (m) { m.unread = false; });
        dd.innerHTML = buildInboxHTML('all');
        bindInboxFilters();
        bindInboxItems();
        updateInboxBadge();
        showToast('All messages marked as read', 'success');
      });
    }
  }

  function bindInboxItems() {
    var dd = document.getElementById('inbox-dropdown');
    if (!dd) return;
    dd.querySelectorAll('.inbox-item').forEach(function (item) {
      function handleClick() {
        var id = parseInt(item.getAttribute('data-id'));
        var msg = NOTIF_DATA.find(function (m) { return m.id === id; });
        if (msg) msg.unread = false;
        item.classList.remove('unread');
        var dot = item.querySelector('.inbox-unread-dot');
        if (dot) dot.remove();
        updateInboxBadge();
        closeInboxDropdown();
        window.location.href = 'messages.html';
      }
      item.addEventListener('click', handleClick);
      item.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleClick(); }
      });
    });
  }

  function updateInboxBadge() {
    var badge = document.getElementById('inbox-badge');
    if (badge) badge.remove();
  }

  /* ------------------------------------------------------------------
     PROFILE DROPDOWN LOGIC
     ------------------------------------------------------------------ */
  function bindProfileDropdown() {
    var headerAvatar = document.getElementById('nav-profile-avatar');
    var menu = document.getElementById('profile-dropdown');
    if (!headerAvatar || !menu) return;

    function positionMenu() {
      var r = headerAvatar.getBoundingClientRect();
      menu.style.top = (r.bottom + 8) + 'px';
      menu.style.right = Math.max(8, window.innerWidth - r.right) + 'px';
      menu.style.left = 'auto';
      if (window.innerWidth < 400) {
        menu.style.left = '8px';
        menu.style.right = '8px';
      }
    }

    headerAvatar.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      closeInboxDropdown();
      positionMenu();
      menu.classList.toggle('open');
    });

    document.addEventListener('click', function (e) {
      if (!menu.contains(e.target) && e.target !== headerAvatar && !headerAvatar.contains(e.target)) {
        menu.classList.remove('open');
      }
    });

    window.addEventListener('resize', function () {
      if (menu.classList.contains('open')) positionMenu();
    });
  }

  function closeProfileDropdown() {
    var menu = document.getElementById('profile-dropdown');
    if (menu) menu.classList.remove('open');
  }

  /* ------------------------------------------------------------------
     COMMAND PALETTE SEARCH LOGIC
     ------------------------------------------------------------------ */
  function initCommandPaletteSearch() {
    var input = document.getElementById('cmd-search-input');
    var results = document.getElementById('cmd-search-results');
    if (!input || !results) return;

    input.addEventListener('input', function () {
      clearTimeout(input._debounce);
      input._debounce = setTimeout(function () { performSearch(input.value.trim()); }, 150);
    });

    input.addEventListener('keydown', function (e) {
      var items = results.querySelectorAll('.cmd-item');
      var selected = results.querySelector('.cmd-item.selected');
      var idx = Array.prototype.indexOf.call(items, selected);

      if (e.key === 'Enter') {
        e.preventDefault();
        if (selected) { selected.click(); return; }
        if (items.length) items[0].click();
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        items.forEach(function (i) { i.classList.remove('selected'); });
        if (idx < items.length - 1) items[idx + 1].classList.add('selected');
        else if (items.length) items[0].classList.add('selected');
        var newSel = results.querySelector('.cmd-item.selected');
        if (newSel) newSel.scrollIntoView({ block: 'nearest' });
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        items.forEach(function (i) { i.classList.remove('selected'); });
        if (idx > 0) items[idx - 1].classList.add('selected');
        else if (items.length) items[items.length - 1].classList.add('selected');
        var newSel2 = results.querySelector('.cmd-item.selected');
        if (newSel2) newSel2.scrollIntoView({ block: 'nearest' });
      }
    });

    function performSearch(query) {
      if (!query) {
        showSuggestions();
        return;
      }
      var q = query.toLowerCase();
      var allPages = [];
      NAV.forEach(function (n) {
        if (n.type === 'item') allPages.push({ label: n.label, icon: n.icon, href: n.href });
      });

      var matches = allPages.filter(function (p) {
        return p.label.toLowerCase().indexOf(q) !== -1;
      });

      var html = '';
      if (matches.length) {
        html += '<div class="cmd-section-label"><i class="fas fa-search"></i> Pages</div>';
        matches.forEach(function (m) {
          html += '<div class="cmd-item" data-href="' + m.href + '" tabindex="0">';
          html += '<i class="fas ' + m.icon + '"></i><span class="cmd-item-title">' + escapeHtml(m.label) + '</span>';
          html += '<span class="cmd-item-category">Page</span></div>';
        });
      } else {
        html += '<div class="cmd-empty"><i class="fas fa-search"></i><p>No results for "' + escapeHtml(query) + '"</p></div>';
      }
      results.innerHTML = html;
      bindResultClickes();
    }

    function showSuggestions() {
      var quickPages = [
        { href: 'index.html', label: 'Dashboard', icon: 'fa-house' },
        { href: 'farm.html', label: 'My Farm', icon: 'fa-tractor' },
        { href: 'ai.html', label: 'AI Assist', icon: 'fa-robot' },
        { href: 'marketplace.html', label: 'Marketplace', icon: 'fa-shopping-bag' },
        { href: 'services.html', label: 'Services', icon: 'fa-concierge-bell' },
        { href: 'community.html', label: 'Community', icon: 'fa-people-group' },
        { href: 'weather.html', label: 'Weather', icon: 'fa-cloud-sun' },
        { href: 'map.html', label: 'Farm Map', icon: 'fa-map-location-dot' }
      ];

      var html = '<div class="cmd-section-label"><i class="fas fa-bolt"></i> Quick Access</div>';
      quickPages.forEach(function (item) {
        html += '<div class="cmd-item" data-href="' + item.href + '" tabindex="0">';
        html += '<i class="fas ' + item.icon + '"></i><span class="cmd-item-title">' + escapeHtml(item.label) + '</span>';
        html += '<span class="cmd-item-category">Page</span></div>';
      });
      results.innerHTML = html;
      bindResultClickes();
    }

    function bindResultClickes() {
      results.querySelectorAll('.cmd-item').forEach(function (item) {
        function navigate() {
          var href = item.getAttribute('data-href');
          if (href) window.location.href = href;
        }
        item.addEventListener('click', navigate);
        item.addEventListener('keydown', function (e) {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(); }
        });
      });
    }

    showSuggestions();
  }

  /* ------------------------------------------------------------------
     PUBLIC API
     ------------------------------------------------------------------ */
  function toggleSidebar() {
    var sidebar = document.getElementById('sidebar');
    var backdrop = document.getElementById('sidebar-backdrop');
    var menuBtn = document.getElementById('menu-btn');
    if (!sidebar) return;
    if (window.innerWidth >= 1024) {
      var isCollapsed = document.body.classList.contains('sidebar-collapsed');
      document.body.classList.toggle('sidebar-collapsed', !isCollapsed);
      try { localStorage.setItem(COLLAPSE_KEY, isCollapsed ? '0' : '1'); } catch (e) {}
      return;
    }
    var isOpen = sidebar.classList.contains('open');
    sidebar.classList.toggle('open', !isOpen);
    if (backdrop) backdrop.classList.toggle('active', !isOpen);
    if (menuBtn) menuBtn.setAttribute('aria-expanded', String(!isOpen));
  }

  function closeSidebar() {
    var sidebar = document.getElementById('sidebar');
    var backdrop = document.getElementById('sidebar-backdrop');
    var menuBtn = document.getElementById('menu-btn');
    if (sidebar) sidebar.classList.remove('open');
    if (backdrop) backdrop.classList.remove('active');
    if (menuBtn) menuBtn.setAttribute('aria-expanded', 'false');
  }

  function toggleCommandPalette() {
    var palette = document.getElementById('cmd-palette-backdrop');
    if (!palette) return;
    palette.classList.toggle('active');
    if (palette.classList.contains('active')) {
      var input = document.getElementById('cmd-search-input');
      if (input) { input.value = ''; input.focus(); }
    }
  }

  function closeCommandPalette() {
    var p = document.getElementById('cmd-palette-backdrop');
    if (p) p.classList.remove('active');
  }

  function navigateTo(href) {
    window.location.href = href;
  }

  function showToast(message, type) {
    type = type || 'success';
    var container = document.getElementById('toast-container');
    if (!container) return;
    var toast = document.createElement('div');
    toast.className = 'toast-msg ' + type;
    var icons = { success: 'fa-check-circle', error: 'fa-exclamation-circle', info: 'fa-info-circle', danger: 'fa-exclamation-circle', warning: 'fa-exclamation-triangle' };
    var icon = icons[type] || icons.success;
    toast.innerHTML = '<i class="fas ' + icon + '"></i><span>' + escapeHtml(message) + '</span>';
    container.appendChild(toast);
    requestAnimationFrame(function () { toast.classList.add('show'); });
    setTimeout(function () {
      toast.classList.remove('show');
      toast.classList.add('hide');
      setTimeout(function () { toast.remove(); }, 300);
    }, 3000);
  }

  function updateBadge(count) {
    count = typeof count === 'number' ? count : getUnreadCount();
    var badge = document.getElementById('inbox-badge');
    var btn = document.getElementById('inbox-btn');
    if (count > 0) {
      if (badge) {
        badge.textContent = count;
      } else if (btn) {
        var el = document.createElement('span');
        el.className = 'badge';
        el.id = 'inbox-badge';
        el.textContent = count;
        btn.appendChild(el);
      }
    } else if (badge) {
      badge.remove();
    }
  }

  function showProfileDropdown() {
    var menu = document.getElementById('profile-dropdown');
    var avatar = document.getElementById('nav-profile-avatar');
    if (!menu || !avatar) return;
    closeInboxDropdown();
    var r = avatar.getBoundingClientRect();
    menu.style.top = (r.bottom + 8) + 'px';
    menu.style.right = Math.max(8, window.innerWidth - r.right) + 'px';
    menu.style.left = 'auto';
    if (window.innerWidth < 400) {
      menu.style.left = '8px';
      menu.style.right = '8px';
    }
    menu.classList.add('open');
  }

  function showInboxDropdown() {
    var dd = document.getElementById('inbox-dropdown');
    var btn = document.getElementById('inbox-btn');
    if (!dd || !btn) return;
    closeProfileDropdown();
    var r = btn.getBoundingClientRect();
    dd.style.top = (r.bottom + 8) + 'px';
    dd.style.right = Math.max(8, window.innerWidth - r.right - 10) + 'px';
    dd.style.left = 'auto';
    if (window.innerWidth < 600) {
      dd.style.left = '8px';
      dd.style.right = '8px';
    }
    dd.classList.add('open');
    bindInboxFilters();
    bindInboxItems();
  }

  function applyCollapse() {
    if (window.innerWidth < 1024) {
      document.body.classList.remove('sidebar-collapsed');
      return;
    }
    var collapsed = isCollapsed();
    document.body.classList.toggle('sidebar-collapsed', collapsed);
    var icon = document.querySelector('#sidebar-collapse-toggle i');
    if (icon) {
      icon.className = collapsed ? 'fas fa-angles-right' : 'fas fa-angles-left';
    }
    var toggle = document.getElementById('sidebar-collapse-toggle');
    if (toggle) {
      toggle.title = collapsed ? 'Expand sidebar' : 'Collapse sidebar';
    }
  }

  function initDefaultCollapseByViewport() {
    if (window.innerWidth < 1024) {
      document.body.classList.remove('sidebar-collapsed');
      return;
    }
    var stored = localStorage.getItem(COLLAPSE_KEY);
    if (stored === null) {
      setCollapsed(window.innerWidth < 1280);
    }
    applyCollapse();
  }

  /* ------------------------------------------------------------------
     INIT
     ------------------------------------------------------------------ */
  function injectFullscreenStyles() {
    var style = document.createElement('style');
    style.textContent =
      'body.fullscreen-mode .sidebar,' +
      'body.fullscreen-mode .top-bar,' +
      'body.fullscreen-mode .bottom-nav,' +
      'body.fullscreen-mode .sidebar-backdrop {' +
      '  display: none !important;' +
      '}' +
      'body.fullscreen-mode {' +
      '  padding-left: 0 !important;' +
      '  padding-top: 0 !important;' +
      '  padding-bottom: 0 !important;' +
      '}' +
      '.global-farm-wrap{display:flex;align-items:center;gap:6px;background:rgba(255,255,255,0.12);' +
      'border:1px solid rgba(255,255,255,0.15);border-radius:12px;padding:5px 10px;margin-left:auto;margin-right:10px}' +
      '.global-farm-wrap i{color:var(--light-green,#52B788);font-size:12px}' +
      '.global-farm-select{background:transparent;border:none;color:#fff;font-size:12px;font-weight:600;' +
      'max-width:130px;cursor:pointer;outline:none;font-family:inherit}' +
      '.global-farm-select option{color:#1B2E21}' +
      '@media(max-width:560px){.global-farm-wrap{display:none}}';
    document.head.appendChild(style);
  }

  function syncProfileImage() {
    var saved = localStorage.getItem('fa-profile-image');
    document.querySelectorAll('img[data-user-avatar]').forEach(function (img) {
      if (saved) {
        img.src = saved;
      } else {
        var user = getUserData();
        if (user && user.full_name) {
          img.src = UserStore.avatarFor ? UserStore.avatarFor(user) : AVATAR_URL;
        } else {
          img.src = AVATAR_URL;
        }
      }
    });
  }

  function init() {
    if (isLoginPage()) return;

    /* Global scroll behavior: every new page opens from the top. */
    if ('scrollRestoration' in history) {
      try { history.scrollRestoration = 'manual'; } catch (e) {}
    }
    window.scrollTo(0, 0);

    injectFullscreenStyles();

    var skipPages = ['messages.html', 'chat.html', 'contacts.html'];
    var currentPath = window.location.pathname.split('/').pop() || 'index.html';
    var html = document.documentElement;
    if (html.getAttribute('data-hide-nav') === 'true' || skipPages.indexOf(currentPath) !== -1) {
      document.body.classList.add('fullscreen-mode');
      return;
    }

    removeExistingNav();

    injectTopBar();
    injectBackdrop();
    injectSidebar();
    injectBottomNav();
    injectInboxDropdown();
    injectProfileDropdown();
    injectCommandPalette();
    injectToastContainer();

    initDefaultCollapseByViewport();
    applyCollapse();

    bindEvents();

    var displayName = localStorage.getItem('user-display-name');
    if (displayName) {
      var sidebarName = document.getElementById('sidebar-name');
      if (sidebarName) sidebarName.textContent = displayName;
    }

    syncProfileImage();

    document.addEventListener('profile-image-changed', function () {
      syncProfileImage();
    });

    console.log('[Farm Assist Navigation] v7.0 Initialized');

    fetchUnreadCount();
    setInterval(fetchUnreadCount, 30000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  global.Navigation = {
    init: init,
    navigateTo: navigateTo,
    showToast: showToast,
    updateBadge: updateBadge,
    showProfileDropdown: showProfileDropdown,
    showInboxDropdown: showInboxDropdown,
    getSelectedFarm: getSelectedFarm,
    NAV: NAV,
    BOTTOM_NAV: BOTTOM_NAV
  };

  global.showToast = showToast;
  global.updateBadge = updateBadge;
  global.updateInboxBadge = updateInboxBadge;

})(window);
