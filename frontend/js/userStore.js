/*
================================================================================
FARM ASSIST - USER STORE (Backend-Connected)
================================================================================
Manages authentication state, user data, and DOM synchronization.
All data comes from the backend API via JWT tokens.
================================================================================
*/
(function (global) {
  'use strict';

  function _read(key, fallback) {
    try {
      var raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) { return fallback; }
  }

  function _persist(key, val) {
    try { localStorage.setItem(key, typeof val === 'string' ? val : JSON.stringify(val)); } catch (e) {}
  }

  function initialsFor(name) {
    var n = (name || 'Farmer').trim();
    if (!n) return 'F';
    var parts = n.split(/\s+/).filter(Boolean);
    if (parts.length === 1) return parts[0].charAt(0).toUpperCase();
    return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
  }

  function avatarFor(user) {
    if (user && user.profile_image && /^data:|^https?:\/\//.test(user.profile_image)) return user.profile_image;
    var name = (user && user.full_name) || (user && user.fullName) || 'Farmer';
    var svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">' +
      '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">' +
      '<stop offset="0" stop-color="#2D8659"/><stop offset="1" stop-color="#1B5E3F"/>' +
      '</linearGradient></defs>' +
      '<rect width="100" height="100" rx="50" fill="url(#g)"/>' +
      '<text x="50" y="50" dy="0.35em" text-anchor="middle" ' +
      'font-family="Outfit, Segoe UI, Arial, sans-serif" font-size="42" font-weight="700" fill="#ffffff">' +
      initialsFor(name) + '</text></svg>';
    return 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
  }

  function getUserData() {
    return _read('fa-current-user-data', null);
  }

  /*
   * The role is only ever *displayed* from here. Access control lives on the
   * server, which reads the role off the users row on every request; these
   * helpers exist so the interface can show the right dashboard and the right
   * navigation without a round trip, not to decide what anybody may reach.
   */
  function currentRole() {
    var u = getUserData();
    if (u && u.role) return u.role;
    return localStorage.getItem('user-role') || 'farmer';
  }

  var UserStore = {
    isLoggedIn: function () {
      return localStorage.getItem('fa-auth') === 'true' && !!localStorage.getItem('fa-auth-token');
    },

    getCurrentUser: function () {
      return getUserData();
    },

    getAuthToken: function () {
      return localStorage.getItem('fa-auth-token');
    },

    getRole: currentRole,

    isCustomer: function () {
      return currentRole() === 'customer';
    },

    isFarmer: function () {
      return !this.isCustomer();
    },

    /* The Customer ID, for display only. Logins never send it as a selector. */
    getCustomerId: function () {
      var u = getUserData();
      if (u && u.customer_id) return u.customer_id;
      if (u && u.customer && u.customer.customer_id) return u.customer.customer_id;
      return localStorage.getItem('customer-id') || null;
    },

    /* Where this account belongs after signing in. */
    dashboardFor: function (role) {
      return (role || currentRole()) === 'customer' ? 'customer.html' : 'index.html';
    },

    setSession: function (userData) {
      _persist('fa-current-user-data', userData);
      localStorage.setItem('fa-auth', 'true');
      localStorage.setItem('user-logged-in', 'true');
      localStorage.setItem('session-last-activity', Date.now().toString());
      localStorage.setItem('user-role', userData.role || 'farmer');
      localStorage.setItem('user-name', userData.full_name || 'Farmer');
      var cid = userData.customer_id || (userData.customer && userData.customer.customer_id);
      if (cid) localStorage.setItem('customer-id', cid);
    },

    logout: function () {
      localStorage.removeItem('fa-auth-token');
      localStorage.removeItem('fa-current-user-data');
      localStorage.removeItem('fa-auth');
      localStorage.removeItem('user-logged-in');
      localStorage.removeItem('user-name');
      localStorage.removeItem('user-role');
      localStorage.removeItem('customer-id');
      localStorage.removeItem('session-last-activity');
      sessionStorage.clear();
    },

    avatarFor: avatarFor,
    initialsFor: initialsFor,

    hydrate: function () {
      var u = this.getCurrentUser();
      if (!u) return;
      document.querySelectorAll('[data-user]').forEach(function (el) {
        var field = el.getAttribute('data-user');
        var val = u[field];
        if (val == null || val === '') val = el.getAttribute('data-user-empty') || '';
        if (val != null && val !== '') el.textContent = val;
      });
      document.querySelectorAll('[data-user-greet]').forEach(function (el) {
        var name = u.full_name || u.fullName || 'Farmer';
        var first = name.split(' ')[0];
        el.textContent = 'Hello, ' + first;
      });
      document.querySelectorAll('img[data-user-avatar]').forEach(function (img) {
        img.src = avatarFor(u);
        img.alt = (u.full_name || 'Farmer') + ' avatar';
      });
    }
  };

  global.UserStore = UserStore;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { UserStore.hydrate(); });
  } else {
    UserStore.hydrate();
  }
})(window);
