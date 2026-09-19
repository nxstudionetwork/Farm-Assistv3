/*
================================================================================
FARM ASSIST - BACKEND SERVICE LAYER
================================================================================
Single data-access boundary. All API calls go through here.
Backend: FastAPI served from the same origin (port 8000).
================================================================================
*/
(function (global) {
  'use strict';

  function detectBaseUrl() {
    if (window._API_BASE_URL) return window._API_BASE_URL;
    var cfg = global.FARM_ASSIST_CONFIG;
    if (cfg && cfg.API_BASE_URL) return cfg.API_BASE_URL;
    var meta = document.querySelector('meta[name="api-base-url"], meta[name="api-base"]');
    if (meta && meta.content) return meta.content;

    var origin = (window.location && window.location.origin) || '';
    var host = (window.location && window.location.hostname) || '';
    var localBackend = 'http://localhost:8000/api/v1';

    if (!origin || origin === 'null' || origin.indexOf('file:') === 0) {
      return localBackend;
    }

    if (origin.indexOf('localhost:8000') !== -1 || origin.indexOf('127.0.0.1:8000') !== -1 || origin.indexOf('0.0.0.0:8000') !== -1) {
      return origin + '/api/v1';
    }

    if (host === 'localhost' || host === '127.0.0.1' || host === '0.0.0.0') {
      return localBackend;
    }

    if (origin.indexOf('localhost:5500') !== -1 || origin.indexOf('localhost:3000') !== -1 || origin.indexOf('localhost:8080') !== -1 ||
        origin.indexOf('127.0.0.1:5500') !== -1 || origin.indexOf('127.0.0.1:3000') !== -1 || origin.indexOf('127.0.0.1:8080') !== -1) {
      return localBackend;
    }

    return origin + '/api/v1';
  }

  var Config = {
    BASE_URL: detectBaseUrl(),
    TIMEOUT: 15000
  };

  global.APP_CONFIG = {
    API_BASE_URL: Config.BASE_URL,
    API_HOST: Config.BASE_URL.replace(/\/api\/v1\/?$/, '')
  };

  function isNetworkError(e) {
    return e && (e.name === 'TypeError' || e.message === 'Failed to fetch' || e.message === 'NetworkError' || e.message === 'Load failed' || (e.code && (e.code === 'NETWORK_ERR' || e.code === 20)));
  }

  function isAbortError(e) {
    return e && e.name === 'AbortError';
  }

  function parseResponse(r) {
    var contentType = (r.headers && r.headers.get && r.headers.get('content-type')) || '';
    if (contentType.indexOf('application/json') === -1) {
      return r.text().then(function (text) {
        var trimmed = (text || '').trim();
        if (trimmed) {
          try { return JSON.parse(trimmed); } catch (e) { /* fall through */ }
          var err = new Error('The server returned an unexpected response (HTTP ' + r.status + '). The backend may be stopped, outdated, or the API endpoint is missing. Retry once the backend is running.');
          err.status = r.status;
          err.isInvalidJson = true;
          err.rawText = trimmed;
          throw err;
        }
        return { status: 'success', data: null };
      });
    }
    return r.text().then(function (text) {
      var trimmed = (text || '').trim();
      if (!trimmed) {
        if (r.ok) return { status: 'success', data: null };
        throw new Error('HTTP ' + r.status);
      }
      try {
        return JSON.parse(trimmed);
      } catch (e) {
        var err = new Error('The server returned an invalid response (HTTP ' + r.status + '). Check the backend console for errors and retry.');
        err.status = r.status;
        err.isInvalidJson = true;
        err.rawText = trimmed;
        throw err;
      }
    });
  }

  function http(method, path, body, noAuth) {
    var token = localStorage.getItem('fa-auth-token');
    var isForm = typeof FormData !== 'undefined' && body instanceof FormData;
    var headers = {};
    if (!isForm) headers['Content-Type'] = 'application/json';
    if (token && !noAuth) headers['Authorization'] = 'Bearer ' + token;
    var opts = { method: method, headers: headers, credentials: 'same-origin' };
    if (body && method !== 'GET') opts.body = isForm ? body : JSON.stringify(body);
    var controller = new AbortController();
    var timeoutId = setTimeout(function () { controller.abort(); }, Config.TIMEOUT);
    opts.signal = controller.signal;
    return fetch(Config.BASE_URL + path, opts).then(function (r) {
      clearTimeout(timeoutId);
      if (r.status === 204) return { status: 'success', data: null };
      return parseResponse(r).then(function (data) {
        if (!r.ok) {
          var err = new Error((data && data.detail) || 'HTTP ' + r.status);
          err.status = r.status;
          err.data = data;
          err.isAuthError = (r.status === 401 || r.status === 403);
          throw err;
        }
        return data;
      });
    }).catch(function (e) {
      clearTimeout(timeoutId);
      if (!e || typeof e !== 'object') e = new Error(String(e || 'Request failed'));
      if (!e.reqUrl) e.reqUrl = Config.BASE_URL + path;
      if (isAbortError(e)) {
        var timeoutErr = new Error('Request timed out. Please check your connection and try again.');
        timeoutErr.isTimeout = true;
        timeoutErr.reqUrl = e.reqUrl || (Config.BASE_URL + path);
        throw timeoutErr;
      }
      if (isNetworkError(e)) {
        var netErr = new Error('Unable to connect to server. Please check your connection.');
        netErr.isNetworkError = true;
        netErr.reqUrl = e.reqUrl || (Config.BASE_URL + path);
        throw netErr;
      }
      throw e;
    });
  }

  function unwrap(res) {
    if (res && res.status === 'success' && res.data !== undefined) return res.data;
    return res;
  }

  var Storage = {
    get: function (key, fallback) {
      try {
        var raw = localStorage.getItem(key);
        if (raw === null) return fallback === undefined ? null : fallback;
        try { return JSON.parse(raw); } catch (e) { return raw; }
      } catch (e) { return fallback === undefined ? null : fallback; }
    },
    set: function (key, value) {
      try { localStorage.setItem(key, typeof value === 'string' ? value : JSON.stringify(value)); return true; }
      catch (e) { return false; }
    },
    remove: function (key) { try { localStorage.removeItem(key); } catch (e) {} }
  };

  function clearAuthStorage() {
    localStorage.removeItem('fa-auth-token');
    localStorage.removeItem('fa-current-user-data');
    localStorage.removeItem('fa-auth');
    localStorage.removeItem('user-logged-in');
    localStorage.removeItem('user-name');
    localStorage.removeItem('user-role');
  }

  var AuthService = {
    register: function (payload) {
      return http('POST', '/auth/register', {
        full_name: payload.full_name,
        phone_number: payload.phone_number,
        email: payload.email,
        pin: payload.pin,
        preferred_language: payload.preferred_language || 'en',
        password: payload.password,
        date_of_birth: payload.date_of_birth,
        gender: payload.gender,
        farming_experience: payload.farming_experience,
        preferred_crops: payload.preferred_crops,
        state: payload.state,
        district: payload.district,
        mandal: payload.mandal,
        village: payload.village,
        address_line: payload.address_line,
        pincode: payload.pincode,
        farm_name: payload.farm_name,
        farm_type: payload.farm_type,
        preferred_crops: payload.preferred_crops,
        irrigation_type: payload.irrigation_type,
        aadhaar_number: payload.aadhaar_number,
        pan_number: payload.pan_number,
        total_area: payload.total_area,
        area_unit: payload.area_unit,
        soil_type: payload.soil_type,
      }).then(unwrap);
    },
    login: function (payload) {
      return http('POST', '/auth/login', payload, true).then(function (res) {
        var data = unwrap(res);
        if (data && data.access_token) {
          localStorage.setItem('fa-auth-token', data.access_token);
          localStorage.setItem('fa-current-user-data', JSON.stringify(data.user));
          localStorage.setItem('fa-auth', 'true');
          localStorage.setItem('user-logged-in', 'true');
          localStorage.setItem('user-name', data.user.full_name || 'Farmer');
          localStorage.setItem('user-role', data.user.role || 'farmer');
        }
        return data;
      });
    },
    sendOtp: function (phone, email) {
      var body = {};
      if (phone) body.phone_number = phone;
      if (email) body.email = email;
      return http('POST', '/auth/send-otp', body, true).then(unwrap);
    },
    sendFarmerOtp: function (farmerId, channel) {
      return http('POST', '/auth/send-farmer-otp', { farmer_id: farmerId, channel: channel || 'phone' }, true).then(unwrap);
    },
    verifyFarmerOtp: function (farmerId, channel, otp) {
      return http('POST', '/auth/verify-farmer-otp', { farmer_id: farmerId, channel: channel || 'phone', otp_code: otp }, true).then(function (res) {
        var data = unwrap(res);
        if (data && data.access_token) {
          localStorage.setItem('fa-auth-token', data.access_token);
          localStorage.setItem('fa-current-user-data', JSON.stringify(data.user));
          localStorage.setItem('fa-auth', 'true');
          localStorage.setItem('user-logged-in', 'true');
          localStorage.setItem('user-name', data.user.full_name || 'Farmer');
        }
        return data;
      });
    },
    verifyOtp: function (phone, email, otp) {
      var body = { otp_code: otp };
      if (phone) body.phone_number = phone;
      if (email) body.email = email;
      return http('POST', '/auth/verify-otp', body, true).then(function (res) {
        var data = unwrap(res);
        if (data && data.access_token) {
          localStorage.setItem('fa-auth-token', data.access_token);
          localStorage.setItem('fa-current-user-data', JSON.stringify(data.user));
          localStorage.setItem('fa-auth', 'true');
          localStorage.setItem('user-logged-in', 'true');
          localStorage.setItem('user-name', data.user.full_name || 'Farmer');
        }
        return data;
      });
    },
    forgotPin: function (phone, email, newPin) {
      var body = { new_pin: newPin };
      if (phone) body.phone_number = phone;
      if (email) body.email = email;
      return http('POST', '/auth/forgot-pin', body, true).then(unwrap);
    },
    lookupProfile: function (phone, email, farmerId) {
      var body = {};
      if (phone) body.phone_number = phone;
      if (email) body.email = email;
      if (farmerId) body.farmer_id = farmerId;
      return http('POST', '/auth/lookup-profile', body, true).then(unwrap);
    },
    logout: function () {
      return http('POST', '/auth/logout').then(function () {
        clearAuthStorage();
      }).catch(function () {
        clearAuthStorage();
      });
    },
    getMe: function () {
      return http('GET', '/auth/me').then(function (res) {
        var data = unwrap(res);
        if (data) localStorage.setItem('fa-current-user-data', JSON.stringify(data));
        return data;
      });
    },
    changePin: function (oldPin, newPin) {
      return http('PUT', '/auth/change-pin', { old_pin: oldPin, new_pin: newPin }).then(unwrap);
    },
    sendPhoneChangeOtp: function (newPhoneNumber) {
      return http('POST', '/auth/send-phone-change-otp', { new_phone_number: newPhoneNumber }).then(unwrap);
    },
    verifyPhoneChangeOtp: function (newPhoneNumber, otpCode) {
      return http('POST', '/auth/verify-phone-change-otp', { new_phone_number: newPhoneNumber, otp_code: otpCode }).then(function (res) {
        var data = unwrap(res);
        if (data && data.user) {
          localStorage.setItem('fa-current-user-data', JSON.stringify(data.user));
          localStorage.setItem('user-name', data.user.full_name || 'Farmer');
        }
        return data;
      });
    }
  };

  var LocationService = {
    getStates: function () {
      return http('GET', '/locations/states', null, true).then(unwrap);
    },
    getDistricts: function (state) {
      return http('GET', '/locations/districts/' + encodeURIComponent(state), null, true).then(unwrap);
    },
    getMandals: function (state, district) {
      return http('GET', '/locations/mandals/' + encodeURIComponent(state) + '/' + encodeURIComponent(district), null, true).then(unwrap);
    },
    getVillages: function (state, district, mandal) {
      return http('GET', '/locations/villages/' + encodeURIComponent(state) + '/' + encodeURIComponent(district) + '/' + encodeURIComponent(mandal), null, true).then(unwrap);
    }
  };

  var ProfileService = {
    get: function () {
      return http('GET', '/users/profile').then(unwrap);
    },
    update: function (data) {
      return http('PUT', '/users/profile', data).then(unwrap);
    },
    updateAddress: function (data) {
      return http('PUT', '/users/address', data).then(unwrap);
    },
    uploadPicture: function (file) {
      var formData = new FormData();
      formData.append('file', file);
      return http('POST', '/users/profile-picture', formData).then(unwrap);
    },
    getStats: function () {
      return http('GET', '/users/stats').then(unwrap);
    },
    getActivity: function (limit) {
      return http('GET', '/users/activity' + (limit ? '?limit=' + limit : '')).then(unwrap);
    },
    getRequestsTimeline: function (limit) {
      return http('GET', '/users/requests-timeline' + (limit ? '?limit=' + limit : '')).then(unwrap);
    },
    getFarms: function () {
      return http('GET', '/users/farms').then(unwrap);
    },
    exportData: function () {
      return http('GET', '/users/export').then(unwrap);
    },
    deleteAccount: function () {
      return http('POST', '/users/delete-account', { force: true }).then(unwrap);
    }
  };

  var SupportService = {
    listTickets: function () {
      return http('GET', '/tickets').then(function (res) {
        var data = unwrap(res);
        return (data && data.tickets) ? data.tickets : [];
      });
    },
    createTicket: function (data) {
      return http('POST', '/tickets', {
        name: data.name,
        category: data.category,
        subject: data.subject,
        description: data.description
      }).then(unwrap);
    }
  };

  var FarmService = {
    list: function () {
      return http('GET', '/farms').then(unwrap);
    },
    get: function (id) {
      return http('GET', '/farms/' + id).then(unwrap);
    },
    create: function (data) {
      return http('POST', '/farms', data).then(unwrap);
    },
    update: function (id, data) {
      return http('PUT', '/farms/' + id, data).then(unwrap);
    },
    delete: function (id) {
      return http('DELETE', '/farms/' + id).then(unwrap);
    },
    getPlots: function (farmId) {
      return http('GET', '/farms/' + farmId + '/plots').then(unwrap);
    },
    createPlot: function (farmId, data) {
      return http('POST', '/farms/' + farmId + '/plots', data).then(unwrap);
    },
    updatePlot: function (plotId, data) {
      return http('PUT', '/plots/' + plotId, data).then(unwrap);
    },
    deletePlot: function (plotId) {
      return http('DELETE', '/plots/' + plotId).then(unwrap);
    }
  };

  var CropService = {
    listCrops: function () {
      return http('GET', '/crops').then(unwrap);
    },
    listCycles: function () {
      return http('GET', '/crop-cycles').then(unwrap);
    },
    createCycle: function (data) {
      return http('POST', '/crop-cycles', data).then(unwrap);
    },
    updateCycle: function (id, data) {
      return http('PUT', '/crop-cycles/' + id, data).then(unwrap);
    },
    deleteCycle: function (id) {
      return http('DELETE', '/crop-cycles/' + id).then(unwrap);
    },
    listTasks: function (params) {
      var qs = params || '';
      return http('GET', '/crop-tasks' + (qs ? '?' + qs : '')).then(unwrap);
    },
    suggestTasks: function () {
      return http('GET', '/crop-tasks/ai-suggest').then(unwrap);
    },
    createTask: function (data) {
      return http('POST', '/crop-tasks', data).then(unwrap);
    },
    updateTask: function (id, data) {
      return http('PUT', '/crop-tasks/' + id, data).then(unwrap);
    },
    deleteTask: function (id) {
      return http('DELETE', '/crop-tasks/' + id).then(unwrap);
    },
    createJournal: function (data) {
      return http('POST', '/farm-journal', data).then(unwrap);
    },
    listJournal: function () {
      return http('GET', '/farm-journal').then(unwrap);
    }
  };

  var FinanceService = {
    getSummary: function () {
      return http('GET', '/finance/summary').then(unwrap);
    },
    listTransactions: function (params) {
      var qs = params || '';
      return http('GET', '/transactions' + (qs ? '?' + qs : '')).then(unwrap);
    },
    createTransaction: function (data) {
      return http('POST', '/transactions', data).then(unwrap);
    },
    listExpenses: function (params) {
      var qs = params || '';
      return http('GET', '/expenses' + (qs ? '?' + qs : '')).then(unwrap);
    },
    createExpense: function (data) {
      return http('POST', '/expenses', data).then(unwrap);
    },
    listIncome: function (params) {
      var qs = params || '';
      return http('GET', '/income' + (qs ? '?' + qs : '')).then(unwrap);
    },
    createIncome: function (data) {
      return http('POST', '/income', data).then(unwrap);
    },
    getIncome: function (id) {
      return http('GET', '/income/' + encodeURIComponent(id)).then(unwrap);
    },
    updateIncome: function (id, data) {
      return http('PUT', '/income/' + encodeURIComponent(id), data).then(unwrap);
    },
    deleteIncome: function (id) {
      return http('DELETE', '/income/' + encodeURIComponent(id)).then(unwrap);
    },
    getExpense: function (id) {
      return http('GET', '/expenses/' + encodeURIComponent(id)).then(unwrap);
    },
    updateExpense: function (id, data) {
      return http('PUT', '/expenses/' + encodeURIComponent(id), data).then(unwrap);
    },
    deleteExpense: function (id) {
      return http('DELETE', '/expenses/' + encodeURIComponent(id)).then(unwrap);
    },
    getTransactionDetail: function (id) {
      return http('GET', '/transactions/' + encodeURIComponent(id)).then(unwrap);
    }
  };

  var ServiceService = {
    listCatalog: function (params) {
      var qs = '';
      if (params) {
        var parts = [];
        Object.keys(params).forEach(function (k) {
          if (params[k] !== undefined && params[k] !== null && params[k] !== '') {
            parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(params[k]));
          }
        });
        qs = parts.join('&');
      }
      return http('GET', '/services' + (qs ? '?' + qs : '')).then(unwrap);
    },
    getCatalogItem: function (id) {
      return http('GET', '/services/' + encodeURIComponent(id)).then(unwrap);
    },
    getCategories: function () {
      return http('GET', '/services/categories').then(unwrap);
    },
    getCompleted: function () {
      return http('GET', '/services/completed').then(unwrap);
    },
    list: function (params) {
      var qs = '';
      if (params) {
        var parts = [];
        Object.keys(params).forEach(function (k) {
          if (params[k] !== undefined && params[k] !== null && params[k] !== '') {
            parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(params[k]));
          }
        });
        qs = parts.join('&');
      }
      return http('GET', '/service-requests' + (qs ? '?' + qs : '')).then(unwrap);
    },
    create: function (data) {
      return http('POST', '/service-requests', data).then(unwrap);
    },
    createCustom: function (data) {
      return http('POST', '/custom-service-requests', data).then(unwrap);
    },
    get: function (id) {
      return http('GET', '/service-requests/' + encodeURIComponent(id)).then(unwrap);
    },
    updateStatus: function (id, data) {
      return http('PUT', '/service-requests/' + encodeURIComponent(id) + '/status', data).then(unwrap);
    },
    rate: function (id, data) {
      return http('POST', '/service-requests/' + encodeURIComponent(id) + '/rate', data).then(unwrap);
    }
  };

  var WalletService = {
    get: function () {
      return http('GET', '/wallet').then(unwrap);
    },
    getSummary: function (params) {
      var qs = '';
      if (params) {
        var parts = [];
        Object.keys(params).forEach(function (k) { if (params[k] !== undefined && params[k] !== null && params[k] !== '') parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(params[k])); });
        qs = parts.join('&');
      }
      return http('GET', '/wallet/summary' + (qs ? '?' + qs : '')).then(unwrap);
    },
    setup: function (data) {
      return http('POST', '/wallet/setup', data).then(unwrap);
    },
    verifyPin: function (walletPin) {
      return http('POST', '/wallet/verify-pin', { wallet_pin: walletPin }).then(unwrap);
    },
    addMoney: function (data) {
      return http('POST', '/wallet/add-money', data).then(unwrap);
    },
    transfer: function (data) {
      return http('POST', '/wallet/transfer', data).then(unwrap);
    },
    listTransactions: function (params) {
      var qs = '';
      if (params) {
        var parts = [];
        Object.keys(params).forEach(function (k) { if (params[k] !== undefined && params[k] !== null && params[k] !== '') parts.push(k + '=' + encodeURIComponent(params[k])); });
        qs = parts.join('&');
      }
      return http('GET', '/wallet/transactions' + (qs ? '?' + qs : '')).then(unwrap);
    },
    getTransaction: function (txnId) {
      return http('GET', '/wallet/transactions/' + txnId).then(unwrap);
    },
    listBeneficiaries: function () {
      return http('GET', '/wallet/beneficiaries').then(unwrap);
    },
    addBeneficiary: function (data) {
      return http('POST', '/wallet/beneficiaries', data).then(unwrap);
    },
    removeBeneficiary: function (id) {
      return http('DELETE', '/wallet/beneficiaries/' + id).then(unwrap);
    },
    searchUser: function (query) {
      return http('POST', '/wallet/search-user', { query: query }).then(unwrap);
    },
    listMoneyRequests: function (params) {
      var qs = '';
      if (params) {
        var parts = [];
        Object.keys(params).forEach(function (k) { if (params[k] !== undefined && params[k] !== null && params[k] !== '') parts.push(k + '=' + encodeURIComponent(params[k])); });
        qs = parts.join('&');
      }
      return http('GET', '/wallet/money-requests' + (qs ? '?' + qs : '')).then(unwrap);
    },
    createMoneyRequest: function (data) {
      return http('POST', '/wallet/money-requests', data).then(unwrap);
    },
    acceptMoneyRequest: function (requestId, walletPin) {
      return http('POST', '/wallet/money-requests/' + requestId + '/accept', { wallet_pin: walletPin }).then(unwrap);
    },
    declineMoneyRequest: function (requestId) {
      return http('POST', '/wallet/money-requests/' + requestId + '/decline').then(unwrap);
    },
    cancelMoneyRequest: function (requestId) {
      return http('POST', '/wallet/money-requests/' + requestId + '/cancel').then(unwrap);
    },
    listBankAccounts: function () {
      return http('GET', '/wallet/bank-accounts').then(unwrap);
    },
    addBankAccount: function (data) {
      return http('POST', '/wallet/bank-accounts', data).then(unwrap);
    },
    removeBankAccount: function (accountId) {
      return http('DELETE', '/wallet/bank-accounts/' + accountId).then(unwrap);
    },
    setDefaultBankAccount: function (accountId) {
      return http('POST', '/wallet/bank-accounts/' + accountId + '/default').then(unwrap);
    },
    changePin: function (data) {
      return http('POST', '/wallet/change-pin', data).then(unwrap);
    },
    securityInfo: function () {
      return http('GET', '/wallet/security-info').then(unwrap);
    },
    withdraw: function (data) {
      return http('POST', '/wallet/withdraw', data).then(unwrap);
    }
  };

  var WorkerService = {
    list: function (params) {
      var qs = '';
      if (params) {
        var parts = [];
        Object.keys(params).forEach(function (k) { if (params[k] !== undefined && params[k] !== null && params[k] !== '') parts.push(k + '=' + encodeURIComponent(params[k])); });
        qs = parts.join('&');
      }
      return http('GET', '/workers' + (qs ? '?' + qs : '')).then(unwrap);
    },
    get: function (id) {
      return http('GET', '/workers/' + encodeURIComponent(id)).then(unwrap);
    },
    getFilters: function () {
      return http('GET', '/workers/filters').then(unwrap);
    },
    book: function (data) {
      return http('POST', '/worker-bookings', data).then(unwrap);
    },
    listBookings: function (params) {
      var qs = '';
      if (params) {
        var parts = [];
        Object.keys(params).forEach(function (k) { if (params[k] !== undefined && params[k] !== null && params[k] !== '') parts.push(k + '=' + encodeURIComponent(params[k])); });
        qs = parts.join('&');
      }
      return http('GET', '/worker-bookings' + (qs ? '?' + qs : '')).then(unwrap);
    },
    getBooking: function (id) {
      return http('GET', '/worker-bookings/' + encodeURIComponent(id)).then(unwrap);
    },
    updateBooking: function (id, data) {
      return http('PUT', '/worker-bookings/' + encodeURIComponent(id), data).then(unwrap);
    },
    addReview: function (workerId, data) {
      return http('POST', '/workers/' + encodeURIComponent(workerId) + '/reviews', data).then(unwrap);
    },
    getReviews: function (workerId, params) {
      var qs = '';
      if (params) {
        var parts = [];
        Object.keys(params).forEach(function (k) { if (params[k] !== undefined && params[k] !== null && params[k] !== '') parts.push(k + '=' + encodeURIComponent(params[k])); });
        qs = parts.join('&');
      }
      return http('GET', '/workers/' + encodeURIComponent(workerId) + '/reviews' + (qs ? '?' + qs : '')).then(unwrap);
    }
  };

  var InputStoreService = {
    // Agricultural-input BUY side storefront (isolated from the farmer
    // SELLING side in MarketplaceSellerService and the Tools & Equipment
    // storefront in EquipmentService).
    listProducts: function (params) {
      var qs = params ? '?' + buildQuery(params) : '';
      return http('GET', '/input-store/products' + qs).then(unwrap);
    },
    getProduct: function (id) {
      return http('GET', '/input-store/products/' + encodeURIComponent(id)).then(unwrap);
    },
    getCategories: function () {
      return http('GET', '/input-store/categories').then(unwrap);
    },
    getFilters: function () {
      return http('GET', '/input-store/filters').then(unwrap);
    },
    getRecommended: function (params) {
      var qs = params && params.limit ? '?limit=' + encodeURIComponent(params.limit) : '';
      return http('GET', '/input-store/recommended' + qs).then(unwrap);
    }
  };

  var EquipmentService = {
    // Buy Mode - Tools & Equipment Products
    listProducts: function (params) {
      var qs = '';
      if (params) {
        var parts = [];
        Object.keys(params).forEach(function (k) {
          if (params[k] !== undefined && params[k] !== null && params[k] !== '') {
            parts.push(k + '=' + encodeURIComponent(params[k]));
          }
        });
        qs = parts.join('&');
      }
      return http('GET', '/tools-equipment/products' + (qs ? '?' + qs : '')).then(unwrap);
    },
    getProduct: function (id) {
      return http('GET', '/tools-equipment/products/' + encodeURIComponent(id)).then(unwrap);
    },
    getCategories: function () {
      return http('GET', '/tools-equipment/categories').then(unwrap);
    },
    getFilters: function () {
      return http('GET', '/tools-equipment/filters').then(unwrap);
    },
    browse: function (params) {
      var qs = '';
      if (params) {
        var parts = [];
        Object.keys(params).forEach(function (k) {
          if (params[k] !== undefined && params[k] !== null && params[k] !== '') {
            parts.push(k + '=' + encodeURIComponent(params[k]));
          }
        });
        qs = parts.join('&');
      }
      return http('GET', '/tools-equipment/browse' + (qs ? '?' + qs : '')).then(unwrap);
    },
    getRecommended: function (params) {
      var qs = '';
      if (params && params.limit) qs = '?limit=' + encodeURIComponent(params.limit);
      return http('GET', '/tools-equipment/recommended' + qs).then(unwrap);
    },
    getRecentlyViewed: function (params) {
      var qs = '';
      if (params && params.limit) qs = '?limit=' + encodeURIComponent(params.limit);
      return http('GET', '/tools-equipment/recent' + qs).then(unwrap);
    },
    recordView: function (id) {
      return http('POST', '/tools-equipment/viewed/' + encodeURIComponent(id)).then(unwrap);
    },
    compare: function (ids) {
      var param = Array.isArray(ids) ? ids.join(',') : ids;
      return http('GET', '/tools-equipment/compare?ids=' + encodeURIComponent(param)).then(unwrap);
    },

    // Rent Mode - Machinery Rentals
    listRentals: function (params) {
      var qs = '';
      if (params) {
        var parts = [];
        Object.keys(params).forEach(function (k) {
          if (params[k] !== undefined && params[k] !== null && params[k] !== '') {
            parts.push(k + '=' + encodeURIComponent(params[k]));
          }
        });
        qs = parts.join('&');
      }
      return http('GET', '/tools-equipment/rentals/list' + (qs ? '?' + qs : '')).then(unwrap);
    },
    bookRental: function (data) {
      return http('POST', '/tools-equipment/rentals/book', data).then(unwrap);
    },
    getMyRentals: function () {
      return http('GET', '/tools-equipment/rentals/my-bookings').then(unwrap);
    },
    getRentalDetail: function (id) {
      return http('GET', '/tools-equipment/rentals/' + encodeURIComponent(id)).then(unwrap);
    },
    getRentalAvailability: function (id, params) {
      var qs = '';
      if (params) {
        var parts = [];
        Object.keys(params).forEach(function (k) { if (params[k] !== undefined && params[k] !== null && params[k] !== '') parts.push(k + '=' + encodeURIComponent(params[k])); });
        qs = parts.join('&');
      }
      return http('GET', '/tools-equipment/rentals/' + encodeURIComponent(id) + '/availability' + (qs ? '?' + qs : '')).then(unwrap);
    },
    cancelRentalBooking: function (bookingId) {
      return http('PATCH', '/tools-equipment/rentals/bookings/' + encodeURIComponent(bookingId)).then(unwrap);
    },
    getActivity: function (limit) {
      var qs = limit ? '?limit=' + encodeURIComponent(limit) : '';
      return http('GET', '/tools-equipment/activity' + qs).then(unwrap);
    },
    getMyListings: function () {
      return http('GET', '/tools-equipment/mylistings').then(unwrap);
    },
    createRentListing: function (data) {
      return http('POST', '/tools-equipment/mylistings/rent', data).then(unwrap);
    },
    updateRentListing: function (id, data) {
      return http('PUT', '/tools-equipment/mylistings/rent/' + encodeURIComponent(id), data).then(unwrap);
    },
    setRentListingStatus: function (id, data) {
      return http('PATCH', '/tools-equipment/mylistings/rent/' + encodeURIComponent(id) + '/status', data).then(unwrap);
    },
    deleteRentListing: function (id) {
      return http('DELETE', '/tools-equipment/mylistings/rent/' + encodeURIComponent(id)).then(unwrap);
    },
    createBuyListing: function (data) {
      return http('POST', '/tools-equipment/mylistings/buy', data).then(unwrap);
    },
    updateBuyListing: function (id, data) {
      return http('PUT', '/tools-equipment/mylistings/buy/' + encodeURIComponent(id), data).then(unwrap);
    },
    deleteBuyListing: function (id) {
      return http('DELETE', '/tools-equipment/mylistings/buy/' + encodeURIComponent(id)).then(unwrap);
    },
    reportListing: function (data) {
      return http('POST', '/tools-equipment/report', data).then(unwrap);
    },

    // Legacy compatibility for worker equipment rental
    list: function (params) {
      var qs = '';
      if (params) {
        var parts = [];
        Object.keys(params).forEach(function (k) { if (params[k]) parts.push(k + '=' + encodeURIComponent(params[k])); });
        qs = parts.join('&');
      }
      return http('GET', '/equipment' + (qs ? '?' + qs : '')).then(unwrap);
    },
    book: function (data) {
      return http('POST', '/equipment-bookings', data).then(unwrap);
    }
  };

  var MarketplaceService = {
    listProducts: function (params) {
      var qs = '';
      if (params) {
        var parts = [];
        Object.keys(params).forEach(function (k) { if (params[k]) parts.push(k + '=' + encodeURIComponent(params[k])); });
        qs = parts.join('&');
      }
      return http('GET', '/products' + (qs ? '?' + qs : '')).then(unwrap);
    },
    getProduct: function (id) {
      return http('GET', '/products/' + id).then(unwrap);
    },
    createProduct: function (data) {
      return http('POST', '/products', data).then(unwrap);
    },
    listCategories: function () {
      return http('GET', '/product-categories').then(unwrap);
    },
    createOrder: function (data) {
      return http('POST', '/orders', data).then(unwrap);
    },
    listOrders: function () {
      return http('GET', '/orders').then(unwrap);
    },
    getOrder: function (id) {
      return http('GET', '/orders/' + id).then(unwrap);
    },
    updateOrder: function (id, data) {
      return http('PUT', '/orders/' + id, data).then(unwrap);
    },
    getCart: function () {
      return http('GET', '/cart').then(unwrap);
    },
    addToCart: function (data) {
      return http('POST', '/cart', data).then(unwrap);
    },
    updateCartItem: function (id, data) {
      return http('PATCH', '/cart/' + encodeURIComponent(id), data).then(unwrap);
    },
    removeCartItem: function (id) {
      return http('DELETE', '/cart/' + encodeURIComponent(id)).then(unwrap);
    },
    getWishlist: function () {
      return http('GET', '/wishlist').then(unwrap);
    },
    saveWishlist: function (productId) {
      return http('POST', '/wishlist/' + encodeURIComponent(productId)).then(unwrap);
    },
    removeWishlist: function (productId) {
      return http('DELETE', '/wishlist/' + encodeURIComponent(productId)).then(unwrap);
    }
  };

  // Marketplace - Farmer SELLING side (separate from the Input Store BUY side).
  var M = '/marketplace';
  var enc = encodeURIComponent;
  var MarketplaceSellerService = {
    dashboard: function () {
      return http('GET', M + '/dashboard').then(unwrap);
    },
    categories: function () {
      return http('GET', M + '/categories').then(unwrap);
    },
    listListings: function (params) {
      return http('GET', M + '/listings' + (params ? '?' + buildQuery(params) : '')).then(unwrap);
    },
    getListing: function (id) {
      return http('GET', M + '/listings/' + enc(id)).then(unwrap);
    },
    createListing: function (data) {
      return http('POST', M + '/listings', data).then(unwrap);
    },
    updateListing: function (id, data) {
      return http('PUT', M + '/listings/' + enc(id), data).then(unwrap);
    },
    updateListingStatus: function (id, status) {
      return http('PATCH', M + '/listings/' + enc(id) + '/status', { status: status }).then(unwrap);
    },
    deleteListing: function (id) {
      return http('DELETE', M + '/listings/' + enc(id)).then(unwrap);
    },
    recordSale: function (listingId, data) {
      return http('POST', M + '/listings/' + enc(listingId) + '/sales', data).then(unwrap);
    },
    listSales: function (params) {
      return http('GET', M + '/sales' + (params ? '?' + buildQuery(params) : '')).then(unwrap);
    },
    getSale: function (id) {
      return http('GET', M + '/sales/' + enc(id)).then(unwrap);
    },
    updateSale: function (id, data) {
      return http('PATCH', M + '/sales/' + enc(id), data).then(unwrap);
    },
    listEnquiries: function (params) {
      return http('GET', M + '/enquiries' + (params ? '?' + buildQuery(params) : '')).then(unwrap);
    },
    replyEnquiry: function (id, message) {
      return http('POST', M + '/enquiries/' + enc(id) + '/reply', { message: message }).then(unwrap);
    },
    updateEnquiryStatus: function (id, status) {
      return http('PATCH', M + '/enquiries/' + enc(id) + '/status', { status: status }).then(unwrap);
    },
    insights: function () {
      return http('GET', M + '/insights').then(unwrap);
    },
    listBuyers: function (params) {
      return http('GET', M + '/buyers' + (params ? '?' + buildQuery(params) : '')).then(unwrap);
    },
    sendBuyerMessage: function (buyerId, message) {
      return http('POST', M + '/buyers/' + enc(buyerId) + '/message', { message: message }).then(unwrap);
    },
    setBuyerRecommendation: function (buyerId, recommended) {
      return http('POST', M + '/buyers/' + enc(buyerId) + '/recommend', { recommended: !!recommended }).then(unwrap);
    }
  };

  var GovernmentService = {
    listSchemes: function (params) {
      var qs = '';
      if (params) {
        var parts = [];
        Object.keys(params).forEach(function (k) { if (params[k] !== undefined && params[k] !== null && params[k] !== '') parts.push(k + '=' + encodeURIComponent(params[k])); });
        qs = parts.join('&');
      }
      return http('GET', '/government-schemes' + (qs ? '?' + qs : '')).then(unwrap);
    },
    getScheme: function (id) {
      return http('GET', '/government-schemes/' + encodeURIComponent(id)).then(unwrap);
    },
    categories: function () {
      return http('GET', '/government-schemes/categories').then(unwrap);
    },
    savedSchemes: function (params) {
      var qs = params ? '?page=' + (params.page || 1) + '&limit=' + (params.limit || 50) : '';
      return http('GET', '/government-schemes/saved' + qs).then(unwrap);
    },
    saveScheme: function (id) {
      return http('POST', '/government-schemes/' + encodeURIComponent(id) + '/save').then(unwrap);
    },
    unsaveScheme: function (id) {
      return http('DELETE', '/government-schemes/' + encodeURIComponent(id) + '/save').then(unwrap);
    },
    checkEligibility: function (data) {
      return http('POST', '/government-schemes/check-eligibility', data || {}).then(unwrap);
    },
    recommended: function (params) {
      var qs = params && params.limit ? '?limit=' + params.limit : '';
      return http('GET', '/government-schemes/recommended' + qs).then(unwrap);
    },
    syncStatus: function () {
      return http('GET', '/government-schemes/sync').then(unwrap);
    },
    syncNow: function () {
      return http('POST', '/government-schemes/sync').then(unwrap);
    },
    states: function () {
      return http('GET', '/government-schemes/states').then(unwrap);
    },
    applyScheme: function (id, data) {
      return http('POST', '/government-schemes/' + encodeURIComponent(id) + '/apply', data || {}).then(unwrap);
    },
    listApplications: function () {
      return http('GET', '/scheme-applications').then(unwrap);
    },
    listInsurance: function () {
      return http('GET', '/insurance-policies').then(unwrap);
    },
    createInsurance: function (data) {
      return http('POST', '/insurance-policies', data).then(unwrap);
    },
    listClaims: function () {
      return http('GET', '/insurance-claims').then(unwrap);
    },
    createClaim: function (data) {
      return http('POST', '/insurance-claims', data).then(unwrap);
    }
  };

  function cmQ(params) {
    if (!params) return '';
    var parts = [];
    Object.keys(params).forEach(function (k) { if (params[k] !== undefined && params[k] !== null && params[k] !== '') parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(params[k])); });
    return parts.length ? '?' + parts.join('&') : '';
  }

  var CommunityService = {
    feed: function (params) {
      return http('GET', '/communities/feed' + cmQ(params)).then(unwrap);
    },
    categories: function () {
      return http('GET', '/communities/categories').then(unwrap);
    },
    listPosts: function (params) {
      var qs = '';
      if (params) {
        var parts = [];
        Object.keys(params).forEach(function (k) { if (params[k]) parts.push(k + '=' + encodeURIComponent(params[k])); });
        qs = parts.join('&');
      }
      return http('GET', '/posts' + (qs ? '?' + qs : '')).then(unwrap);
    },
    createPost: function (data) {
      return http('POST', '/posts', data).then(unwrap);
    },
    getPost: function (id) {
      return http('GET', '/posts/' + id).then(unwrap);
    },
    updatePost: function (id, data) {
      return http('PATCH', '/posts/' + id, data).then(unwrap);
    },
    deletePost: function (id) {
      return http('DELETE', '/posts/' + id).then(unwrap);
    },
    addComment: function (postId, data) {
      return http('POST', '/posts/' + postId + '/comments', data).then(unwrap);
    },
    listComments: function (postId) {
      return http('GET', '/posts/' + postId + '/comments').then(unwrap);
    },
    deleteComment: function (commentId) {
      return http('DELETE', '/comments/' + commentId).then(unwrap);
    },
    toggleLike: function (postId) {
      return http('POST', '/posts/' + postId + '/like').then(unwrap);
    },
    unlike: function (postId) {
      return http('DELETE', '/posts/' + postId + '/like').then(unwrap);
    },
    savePost: function (postId) {
      return http('POST', '/posts/' + postId + '/save').then(unwrap);
    },
    unsave: function (postId) {
      return http('DELETE', '/posts/' + postId + '/save').then(unwrap);
    },
    listSaved: function (params) {
      return http('GET', '/posts/saved/list' + cmQ(params)).then(unwrap);
    },
    sharePost: function (postId) {
      return http('POST', '/posts/' + postId + '/share').then(unwrap);
    },
    addAnswer: function (postId, content) {
      return http('POST', '/posts/' + postId + '/answers', { content: content }).then(unwrap);
    },
    markBestAnswer: function (postId, answerId) {
      return http('POST', '/posts/' + postId + '/answers/' + answerId + '/best').then(unwrap);
    },
    listGroups: function (params) {
      return http('GET', '/communities/groups' + cmQ(params)).then(unwrap);
    },
    getGroup: function (groupId) {
      return http('GET', '/communities/groups/' + groupId).then(unwrap);
    },
    createGroup: function (data) {
      return http('POST', '/communities/groups', data).then(unwrap);
    },
    joinGroup: function (groupId) {
      return http('POST', '/communities/groups/' + groupId + '/join').then(unwrap);
    },
    leaveGroup: function (groupId) {
      return http('POST', '/communities/groups/' + groupId + '/leave').then(unwrap);
    },
    myGroups: function () {
      return http('GET', '/communities/my-groups').then(unwrap);
    },
    myActivity: function (params) {
      return http('GET', '/communities/my-activity' + cmQ(params)).then(unwrap);
    },
    report: function (data) {
      return http('POST', '/report', data).then(unwrap);
    },
    getFarmerProfile: function (farmerId) {
      return http('GET', '/farmers/' + farmerId + '/profile').then(unwrap);
    },
    listExperts: function (params) {
      var qs = '';
      if (params) {
        var parts = [];
        Object.keys(params).forEach(function (k) { if (params[k]) parts.push(k + '=' + encodeURIComponent(params[k])); });
        qs = parts.join('&');
      }
      return http('GET', '/experts' + (qs ? '?' + qs : '')).then(unwrap);
    },
    getExpert: function (id) {
      return http('GET', '/experts/' + id).then(unwrap);
    },
    getExpertSlots: function (expertId, date) {
      return http('GET', '/experts/' + encodeURIComponent(expertId) + '/slots' + (date ? '?date=' + encodeURIComponent(date) : '')).then(unwrap);
    },
    bookConsultation: function (data) {
      return http('POST', '/consultations', data).then(unwrap);
    },
    listConsultations: function (params) {
      var qs = '';
      if (params) {
        var parts = [];
        Object.keys(params).forEach(function (k) { if (params[k]) parts.push(k + '=' + encodeURIComponent(params[k])); });
        qs = parts.join('&');
      }
      return http('GET', '/consultations' + (qs ? '?' + qs : '')).then(unwrap);
    },
    getConsultation: function (id) {
      return http('GET', '/consultations/' + id).then(unwrap);
    },
    updateConsultation: function (id, data) {
      return http('PATCH', '/consultations/' + id, data).then(unwrap);
    },
    reviewConsultation: function (id, data) {
      return http('POST', '/consultations/' + id + '/review', data).then(unwrap);
    }
  };

  var NotificationService = {
    list: function (params) {
      return http('GET', '/notifications' + (params ? '?' + buildQuery(params) : '')).then(unwrap);
    },
    listArchived: function (params) {
      return http('GET', '/notifications/archived' + (params ? '?' + buildQuery(params) : '')).then(unwrap);
    },
    get: function (id) {
      return http('GET', '/notifications/' + encodeURIComponent(id)).then(unwrap);
    },
    unreadCount: function () {
      return http('GET', '/notifications/unread').then(unwrap);
    },
    markRead: function (id) {
      return http('PUT', '/notifications/' + encodeURIComponent(id) + '/read').then(unwrap);
    },
    markUnread: function (id) {
      return http('PUT', '/notifications/' + encodeURIComponent(id) + '/unread').then(unwrap);
    },
    markAllRead: function () {
      return http('PUT', '/notifications/read-all').then(unwrap);
    },
    archive: function (id) {
      return http('PUT', '/notifications/' + encodeURIComponent(id) + '/archive').then(unwrap);
    },
    unarchive: function (id) {
      return http('PUT', '/notifications/' + encodeURIComponent(id) + '/unarchive').then(unwrap);
    },
    remove: function (id) {
      return http('DELETE', '/notifications/' + encodeURIComponent(id)).then(unwrap);
    },
    create: function (data) {
      return http('POST', '/notifications', data).then(unwrap);
    }
  };

  var FarmBuzzService = {
    request: function (method, path, body) {
      return http(method, '/farmbuzz' + path, body).then(unwrap);
    },
    feed: function (params) {
      var q = params ? '?' + buildQuery(params) : '';
      return http('GET', '/farmbuzz/feed' + q).then(unwrap);
    },
    posts: function (params) {
      var q = params ? '?' + buildQuery(params) : '';
      return http('GET', '/farmbuzz/posts' + q).then(unwrap);
    },
    shorts: function (params) {
      var q = params ? '?' + buildQuery(params) : '';
      return http('GET', '/farmbuzz/shorts' + q).then(unwrap);
    },
    getPost: function (id) {
      return http('GET', '/farmbuzz/posts/' + id).then(unwrap);
    },
    createPost: function (data) {
      return http('POST', '/farmbuzz/posts', data).then(unwrap);
    },
    updatePost: function (id, data) {
      return http('PUT', '/farmbuzz/posts/' + id, data).then(unwrap);
    },
    deletePost: function (id) {
      return http('DELETE', '/farmbuzz/posts/' + id).then(unwrap);
    },
    like: function (id) {
      return http('POST', '/farmbuzz/posts/' + id + '/like').then(unwrap);
    },
    comment: function (id, data) {
      return http('POST', '/farmbuzz/posts/' + id + '/comment', data).then(unwrap);
    },
    comments: function (id) {
      return http('GET', '/farmbuzz/posts/' + id + '/comments').then(unwrap);
    },
    deleteComment: function (id, commentId) {
      return http('DELETE', '/farmbuzz/posts/' + id + '/comments/' + commentId).then(unwrap);
    },
    save: function (id) {
      return http('POST', '/farmbuzz/posts/' + id + '/save').then(unwrap);
    },
    share: function (id) {
      return http('POST', '/farmbuzz/posts/' + id + '/share').then(unwrap);
    },
    view: function (id) {
      return http('POST', '/farmbuzz/posts/' + id + '/view').then(unwrap);
    },
    report: function (id, data) {
      return http('POST', '/farmbuzz/posts/' + id + '/report', data).then(unwrap);
    },
    saved: function (params) {
      var q = params ? '?' + buildQuery(params) : '';
      return http('GET', '/farmbuzz/saved' + q).then(unwrap);
    },
    stories: function () {
      return http('GET', '/farmbuzz/stories').then(unwrap);
    },
    createStory: function (data) {
      return http('POST', '/farmbuzz/stories', data).then(unwrap);
    },
    deleteStory: function (storyId) {
      return http('DELETE', '/farmbuzz/stories/' + storyId).then(unwrap);
    },
    storyView: function (storyId) {
      return http('POST', '/farmbuzz/stories/' + storyId + '/view').then(unwrap);
    },
    follow: function (userId) {
      return http('POST', '/farmbuzz/users/' + userId + '/follow').then(unwrap);
    },
    profile: function () {
      return http('GET', '/farmbuzz/profile').then(unwrap);
    },
    updateProfile: function (data) {
      return http('PUT', '/farmbuzz/profile', data).then(unwrap);
    },
    userProfile: function (userId) {
      return http('GET', '/farmbuzz/users/' + userId + '/profile').then(unwrap);
    },
    search: function (params) {
      var q = params ? '?' + buildQuery(params) : '';
      return http('GET', '/farmbuzz/search' + q).then(unwrap);
    },
    trends: function () {
      return http('GET', '/farmbuzz/trends').then(unwrap);
    },
    uploadMedia: function (file, kind) {
      var fd = new FormData();
      fd.append('file', file);
      var k = (kind === 'video') ? 'video' : 'image';
      return http('POST', '/farmbuzz/media/upload?kind=' + k, fd).then(unwrap);
    },
    recommendedShorts: function (params) {
      var q = params ? '?' + buildQuery(params) : '';
      return http('GET', '/farmbuzz/shorts/recommended' + q).then(unwrap);
    },
    shortCategories: function () {
      return http('GET', '/farmbuzz/shorts/categories').then(unwrap);
    },
    recordEvent: function (id, data) {
      return http('POST', '/farmbuzz/posts/' + id + '/event', data || {}).then(unwrap);
    },
    unlike: function (id) {
      return http('DELETE', '/farmbuzz/posts/' + id + '/like').then(unwrap);
    },
    unsave: function (id) {
      return http('DELETE', '/farmbuzz/posts/' + id + '/save').then(unwrap);
    }
  };

  var WeatherService = {
    getCurrent: function (lat, lon) {
      var query = '';
      if (typeof lat === 'number' && typeof lon === 'number') {
        query = '?latitude=' + lat + '&longitude=' + lon;
      }
      return http('GET', '/weather/current' + query).then(unwrap).then(function (res) {
        return (res && res.data) ? res.data : res;
      });
    },
    getForecast: function (lat, lon) {
      var query = '';
      if (typeof lat === 'number' && typeof lon === 'number') {
        query = '?latitude=' + lat + '&longitude=' + lon;
      }
      return http('GET', '/weather/forecast' + query).then(unwrap).then(function (res) {
        return (res && res.data) ? res.data : res;
      });
    }
  };

  var MapsService = {
    geocode: function (address) {
      return http('GET', '/maps/geocode?address=' + encodeURIComponent(address)).then(unwrap);
    },
    reverseGeocode: function (lat, lon) {
      return http('GET', '/maps/reverse-geocode?lat=' + lat + '&lon=' + lon).then(unwrap);
    }
  };

  var AIService = {
    chat: function (message, conversationId, model) {
      return http('POST', '/ai/chat', { message: message, conversation_id: conversationId, model: model }).then(unwrap);
    },
    getRecommendations: function (farmId) {
      return http('POST', '/ai/recommendations', { farm_id: farmId }).then(unwrap);
    },
    analyzeFarm: function (farmId) {
      return http('POST', '/ai/analyze-farm', { farm_id: farmId }).then(unwrap);
    },
    diagnose: function (symptoms, imageUrl) {
      return http('POST', '/ai/diagnose', { symptoms: symptoms, image_url: imageUrl }).then(unwrap);
    }
  };

  var LoanService = {
    list: function (params) {
      var q = params ? '?' + buildQuery(params) : '';
      return http('GET', '/loans' + q).then(unwrap);
    },
    create: function (data) {
      return http('POST', '/loans', data).then(unwrap);
    },
    update: function (loanId, data) {
      return http('PUT', '/loans/' + loanId, data).then(unwrap);
    },
    summary: function () {
      return http('GET', '/loans/summary').then(unwrap);
    },
    categories: function () {
      return http('GET', '/loans/categories').then(unwrap);
    },
    filterOptions: function () {
      return http('GET', '/loans/filters').then(unwrap);
    },
    products: function (params) {
      return http('GET', '/loans/products' + (params ? '?' + buildQuery(params) : '')).then(unwrap);
    },
    searchProducts: function (q) {
      return http('GET', '/loans/search?q=' + encodeURIComponent(q || '')).then(unwrap);
    },
    getProduct: function (productId) {
      return http('GET', '/loans/products/' + encodeURIComponent(productId)).then(unwrap);
    },
    saveProduct: function (productId) {
      return http('POST', '/loans/products/' + encodeURIComponent(productId) + '/save', {}).then(unwrap);
    },
    unsaveProduct: function (productId) {
      return http('DELETE', '/loans/products/' + encodeURIComponent(productId) + '/save').then(unwrap);
    },
    savedProducts: function (params) {
      return http('GET', '/loans/products/saved' + (params ? '?' + buildQuery(params) : '')).then(unwrap);
    },
    checkEligibility: function (data) {
      return http('POST', '/loans/check-eligibility', data).then(unwrap);
    },
    applications: function (params) {
      return http('GET', '/loans/applications' + (params ? '?' + buildQuery(params) : '')).then(unwrap);
    },
    getApplication: function (applicationId) {
      return http('GET', '/loans/applications/' + encodeURIComponent(applicationId)).then(unwrap);
    },
    createApplication: function (data) {
      return http('POST', '/loans/applications', data).then(unwrap);
    },
    updateApplication: function (applicationId, data) {
      return http('PATCH', '/loans/applications/' + encodeURIComponent(applicationId), data).then(unwrap);
    },
    uploadDocument: function (applicationId, file, documentType) {
      var formData = new FormData();
      formData.append('file', file);
      formData.append('document_type', documentType || 'other');
      return http('POST', '/loans/applications/' + encodeURIComponent(applicationId) + '/documents', formData).then(unwrap);
    },
    documentUrl: function (applicationId, documentId) {
      return Config.BASE_URL + '/loans/applications/' + encodeURIComponent(applicationId) + '/documents/' + encodeURIComponent(documentId) + '/file';
    },
    fetchDocument: function (applicationId, documentId, download) {
      var token = localStorage.getItem('fa-auth-token');
      var url = Config.BASE_URL + '/loans/applications/' + encodeURIComponent(applicationId) + '/documents/' + encodeURIComponent(documentId) + '/file' + (download ? '?download=true' : '');
      var headers = {};
      if (token) headers['Authorization'] = 'Bearer ' + token;
      return fetch(url, { method: 'GET', headers: headers, credentials: 'same-origin' }).then(function (r) {
        if (!r.ok) {
          return r.json().then(function (data) {
            var err = new Error((data && data.detail) || 'HTTP ' + r.status);
            err.status = r.status;
            throw err;
          });
        }
        return r.blob();
      });
    },
    farmerLoans: function (params) {
      return http('GET', '/loans/farmer-loans' + (params ? '?' + buildQuery(params) : '')).then(unwrap);
    },
    farmerLoanRepayments: function (farmerLoanId) {
      return http('GET', '/loans/farmer-loans/' + encodeURIComponent(farmerLoanId) + '/repayments').then(unwrap);
    },
    repay: function (farmerLoanId, amount, walletPin) {
      return http('POST', '/loans/farmer-loans/' + encodeURIComponent(farmerLoanId) + '/repay', {
        amount: amount,
        wallet_pin: walletPin
      }).then(unwrap);
    },
    overview: function () {
      return http('GET', '/loans/overview').then(unwrap);
    }
  };

  var InsuranceService = {
    overview: function () {
      return http('GET', '/insurance/overview').then(unwrap);
    },
    categories: function () {
      return http('GET', '/insurance/categories').then(unwrap);
    },
    filters: function () {
      return http('GET', '/insurance/filters').then(unwrap);
    },
    products: function (params) {
      return http('GET', '/insurance/products' + (params ? '?' + buildQuery(params) : '')).then(unwrap);
    },
    search: function (q) {
      return http('GET', '/insurance/search?q=' + encodeURIComponent(q || '')).then(unwrap);
    },
    getProduct: function (productId) {
      return http('GET', '/insurance/products/' + encodeURIComponent(productId)).then(unwrap);
    },
    saveProduct: function (productId) {
      return http('POST', '/insurance/products/' + encodeURIComponent(productId) + '/save', {}).then(unwrap);
    },
    unsaveProduct: function (productId) {
      return http('DELETE', '/insurance/products/' + encodeURIComponent(productId) + '/save').then(unwrap);
    },
    savedProducts: function (params) {
      return http('GET', '/insurance/products/saved' + (params ? '?' + buildQuery(params) : '')).then(unwrap);
    },
    checkEligibility: function (data) {
      return http('POST', '/insurance/check-eligibility', data).then(unwrap);
    },
    applications: function (params) {
      return http('GET', '/insurance/applications' + (params ? '?' + buildQuery(params) : '')).then(unwrap);
    },
    getApplication: function (applicationId) {
      return http('GET', '/insurance/applications/' + encodeURIComponent(applicationId)).then(unwrap);
    },
    createApplication: function (data) {
      return http('POST', '/insurance/applications', data).then(unwrap);
    },
    uploadApplicationDocument: function (applicationId, file, documentType) {
      var formData = new FormData();
      formData.append('file', file);
      formData.append('document_type', documentType || 'other');
      return http('POST', '/insurance/applications/' + encodeURIComponent(applicationId) + '/documents', formData).then(unwrap);
    },
    applicationDocumentUrl: function (applicationId, documentId) {
      return Config.BASE_URL + '/insurance/applications/' + encodeURIComponent(applicationId) + '/documents/' + encodeURIComponent(documentId) + '/file';
    },
    fetchApplicationDocument: function (applicationId, documentId, download) {
      var token = localStorage.getItem('fa-auth-token');
      var url = Config.BASE_URL + '/insurance/applications/' + encodeURIComponent(applicationId) + '/documents/' + encodeURIComponent(documentId) + '/file' + (download ? '?download=true' : '');
      var headers = {};
      if (token) headers['Authorization'] = 'Bearer ' + token;
      return fetch(url, { method: 'GET', headers: headers, credentials: 'same-origin' }).then(function (r) {
        if (!r.ok) {
          return r.json().then(function (data) {
            var err = new Error((data && data.detail) || 'HTTP ' + r.status);
            err.status = r.status;
            throw err;
          });
        }
        return r.blob();
      });
    },
    policies: function (params) {
      return http('GET', '/insurance/policies' + (params ? '?' + buildQuery(params) : '')).then(unwrap);
    },
    getPolicy: function (policyId) {
      return http('GET', '/insurance/policies/' + encodeURIComponent(policyId)).then(unwrap);
    },
    policyPayments: function (policyId) {
      return http('GET', '/insurance/policies/' + encodeURIComponent(policyId) + '/payments').then(unwrap);
    },
    payPremium: function (policyId, amount, walletPin) {
      return http('POST', '/insurance/policies/' + encodeURIComponent(policyId) + '/pay-premium', {
        amount: amount,
        wallet_pin: walletPin
      }).then(unwrap);
    },
    renewPolicy: function (policyId, walletPin) {
      var formData = new FormData();
      if (walletPin) formData.append('wallet_pin', walletPin);
      return http('POST', '/insurance/policies/' + encodeURIComponent(policyId) + '/renew', formData).then(unwrap);
    },
    claims: function (params) {
      return http('GET', '/insurance/claims' + (params ? '?' + buildQuery(params) : '')).then(unwrap);
    },
    getClaim: function (claimId) {
      return http('GET', '/insurance/claims/' + encodeURIComponent(claimId)).then(unwrap);
    },
    createClaim: function (data) {
      return http('POST', '/insurance/claims', data).then(unwrap);
    },
    uploadClaimDocument: function (claimId, file, documentType) {
      var formData = new FormData();
      formData.append('file', file);
      formData.append('document_type', documentType || 'other');
      return http('POST', '/insurance/claims/' + encodeURIComponent(claimId) + '/documents', formData).then(unwrap);
    },
    claimDocumentUrl: function (claimId, documentId) {
      return Config.BASE_URL + '/insurance/claims/' + encodeURIComponent(claimId) + '/documents/' + encodeURIComponent(documentId) + '/file';
    },
    fetchClaimDocument: function (claimId, documentId, download) {
      var token = localStorage.getItem('fa-auth-token');
      var url = Config.BASE_URL + '/insurance/claims/' + encodeURIComponent(claimId) + '/documents/' + encodeURIComponent(documentId) + '/file' + (download ? '?download=true' : '');
      var headers = {};
      if (token) headers['Authorization'] = 'Bearer ' + token;
      return fetch(url, { method: 'GET', headers: headers, credentials: 'same-origin' }).then(function (r) {
        if (!r.ok) {
          return r.json().then(function (data) {
            var err = new Error((data && data.detail) || 'HTTP ' + r.status);
            err.status = r.status;
            throw err;
          });
        }
        return r.blob();
      });
    }
  };

  // Live sensor/monitoring services are defined below (see MONITORING SERVICE
  // and SENSOR SERVICE sections) as the single source of truth.

  var StorageService = {
    upload: function (file, subdir) {
      var formData = new FormData();
      formData.append('file', file);
      return http('POST', '/storage/upload?subdir=' + (subdir || 'uploads'), formData).then(unwrap);
    },
    uploadBase64: function (imageData, subdir) {
      return http('POST', '/storage/upload-base64', { image_data: imageData, subdir: subdir || 'images' }).then(unwrap);
    },
    delete: function (filePath) {
      return http('DELETE', '/storage/' + filePath).then(unwrap);
    }
  };

  var NewsService = {
    list: function (params) {
      return http('GET', '/news' + (params ? '?' + buildQuery(params) : '')).then(unwrap);
    },
    get: function (id) {
      return http('GET', '/news/' + encodeURIComponent(id)).then(unwrap);
    },
    getBrief: function () {
      return http('GET', '/news/brief').then(unwrap);
    },
    getCategories: function () {
      return http('GET', '/news/categories').then(unwrap);
    },
    getSources: function () {
      return http('GET', '/news/sources').then(unwrap);
    },
    toggleBookmark: function (id) {
      return http('POST', '/news/' + encodeURIComponent(id) + '/bookmark').then(unwrap);
    },
    getSaved: function (params) {
      return http('GET', '/news/saved/list' + (params ? '?' + buildQuery(params) : '')).then(unwrap);
    },
    getPrices: function (crop, location) {
      var q = '';
      if (crop) q += '?crop=' + encodeURIComponent(crop);
      if (location) q += (q ? '&' : '?') + 'location=' + encodeURIComponent(location);
      return http('GET', '/market-prices' + q).then(unwrap);
    }
  };

  var MarketPriceService = {
    list: function (params) {
      return http('GET', '/market-prices' + (params ? '?' + buildQuery(params) : '')).then(unwrap);
    },
    get: function (id) {
      return http('GET', '/market-prices/' + encodeURIComponent(id)).then(unwrap);
    },
    aiOverview: function (params) {
      return http('GET', '/market-prices/ai-overview' + (params ? '?' + buildQuery(params) : '')).then(unwrap);
    },
    search: function (q) {
      return http('GET', '/market-prices/search?q=' + encodeURIComponent(q)).then(unwrap);
    },
    categories: function () {
      return http('GET', '/market-prices/categories').then(unwrap);
    },
    markets: function (params) {
      return http('GET', '/market-prices/markets' + (params ? '?' + buildQuery(params) : '')).then(unwrap);
    },
    summary: function () {
      return http('GET', '/market-prices/summary').then(unwrap);
    },
    history: function (params) {
      return http('GET', '/market-prices/history' + (params ? '?' + buildQuery(params) : '')).then(unwrap);
    },
    compare: function (params) {
      return http('GET', '/market-prices/compare' + (params ? '?' + buildQuery(params) : '')).then(unwrap);
    },
    recommended: function () {
      return http('GET', '/market-prices/recommended').then(unwrap);
    },
    refresh: function (params) {
      return http('POST', '/market-prices/refresh' + (params ? '?' + buildQuery(params) : '')).then(unwrap);
    },
    getWatchlist: function () {
      return http('GET', '/market-prices/watchlist').then(unwrap);
    },
    addWatchlist: function (payload) {
      return http('POST', '/market-prices/watchlist', payload).then(unwrap);
    },
    removeWatchlist: function (watchId) {
      return http('DELETE', '/market-prices/watchlist/' + encodeURIComponent(watchId)).then(unwrap);
    },
    getAlerts: function () {
      return http('GET', '/market-prices/alerts').then(unwrap);
    },
    createAlert: function (payload) {
      return http('POST', '/market-prices/alerts', payload).then(unwrap);
    },
    removeAlert: function (alertId) {
      return http('DELETE', '/market-prices/alerts/' + encodeURIComponent(alertId)).then(unwrap);
    }
  };

  var TranslationService = {
    getLanguages: function () {
      return http('GET', '/translations/languages').then(unwrap);
    },
    translate: function (text, targetLang, sourceLang) {
      return http('POST', '/translations/translate', { text: text, target_language: targetLang, source_language: sourceLang || 'en' }).then(unwrap);
    }
  };

  var SpeechService = {
    textToSpeech: function (text, lang) {
      return http('POST', '/speech/text-to-speech', { text: text, language: lang || 'en' }).then(unwrap);
    },
    speechToText: function (audioData, lang) {
      return http('POST', '/speech/speech-to-text', { audio_data: audioData, language: lang || 'en' }).then(unwrap);
    }
  };

  var QRService = {
    generate: function (data, size) {
      return http('POST', '/qrcode/generate', { data: data, size: size || 200 }).then(unwrap);
    },
    farmerQR: function () {
      return http('GET', '/qrcode/farmer-id').then(unwrap);
    }
  };

  var AnalyticsService = {
    dashboard: function () {
      return http('GET', '/analytics/dashboard').then(unwrap);
    },
    usage: function (days) {
      return http('GET', '/analytics/usage?days=' + (days || 30)).then(unwrap);
    },
    farmHealth: function () {
      return http('GET', '/analytics/farm-health').then(unwrap);
    },
    _qs: function (params) {
      if (!params) return '';
      var parts = [];
      ['farm_id', 'plot_id', 'date_from', 'date_to'].forEach(function (k) {
        var v = params[k];
        if (v != null && v !== '' && v !== 'all') parts.push(k + '=' + encodeURIComponent(v));
      });
      return parts.length ? '?' + parts.join('&') : '';
    },
    context: function () {
      return http('GET', '/analytics/context').then(unwrap);
    },
    overview: function (params) {
      return http('GET', '/analytics/overview' + this._qs(params)).then(unwrap);
    },
    performance: function (params) {
      return http('GET', '/analytics/performance' + this._qs(params)).then(unwrap);
    },
    crops: function (params) {
      return http('GET', '/analytics/crops' + this._qs(params)).then(unwrap);
    },
    yield: function (params) {
      return http('GET', '/analytics/yield' + this._qs(params)).then(unwrap);
    },
    production: function (params) {
      return http('GET', '/analytics/production' + this._qs(params)).then(unwrap);
    },
    financial: function (params) {
      return http('GET', '/analytics/financial' + this._qs(params)).then(unwrap);
    },
    tasks: function (params) {
      return http('GET', '/analytics/tasks' + this._qs(params)).then(unwrap);
    },
    calendar: function (params) {
      return http('GET', '/analytics/calendar' + this._qs(params)).then(unwrap);
    },
    weather: function (params) {
      return http('GET', '/analytics/weather' + this._qs(params)).then(unwrap);
    },
    market: function (params) {
      return http('GET', '/analytics/market' + this._qs(params)).then(unwrap);
    },
    sustainability: function (params) {
      return http('GET', '/analytics/sustainability' + this._qs(params)).then(unwrap);
    },
    risks: function (params) {
      return http('GET', '/analytics/risks' + this._qs(params)).then(unwrap);
    },
    completeness: function (params) {
      return http('GET', '/analytics/completeness' + this._qs(params)).then(unwrap);
    },
    insights: function (params) {
      return http('GET', '/analytics/insights' + this._qs(params)).then(unwrap);
    },
    ai: function (params) {
      return http('GET', '/analytics/ai' + this._qs(params)).then(unwrap);
    },
    reportsList: function () {
      return http('GET', '/analytics/reports').then(unwrap);
    },
    reportGet: function (id) {
      return http('GET', '/analytics/reports/' + encodeURIComponent(id)).then(unwrap);
    },
    reportCreate: function (data) {
      return http('POST', '/analytics/reports', data).then(unwrap);
    },
    reportDelete: function (id) {
      return http('DELETE', '/analytics/reports/' + encodeURIComponent(id)).then(unwrap);
    }
  };

  var IntegrationService = {
    status: function () {
      return http('GET', '/integrations/status').then(unwrap);
    }
  };

  var MessageService = {
    listConversations: function () {
      return http('GET', '/messages/conversations').then(unwrap);
    },
    createConversation: function (data) {
      return http('POST', '/messages/conversations', data).then(unwrap);
    },
    getConversation: function (id) {
      return http('GET', '/messages/conversations/' + id).then(unwrap);
    },
    deleteConversation: function (id) {
      return http('DELETE', '/messages/conversations/' + id).then(unwrap);
    },
    restoreConversation: function (id) {
      return http('POST', '/messages/conversations/' + id + '/restore').then(unwrap);
    },
    toggleMute: function (id) {
      return http('PUT', '/messages/conversations/' + id + '/mute').then(unwrap);
    },
    getMessages: function (conversationId, params) {
      var q = params ? '?' + buildQuery(params) : '';
      return http('GET', '/messages/conversations/' + conversationId + '/messages' + q).then(unwrap);
    },
    sendMessage: function (conversationId, data) {
      return http('POST', '/messages/conversations/' + conversationId + '/messages', data).then(unwrap);
    },
    deleteMessage: function (conversationId, messageId) {
      return http('DELETE', '/messages/conversations/' + conversationId + '/messages/' + messageId).then(unwrap);
    },
    markRead: function (conversationId) {
      return http('PUT', '/messages/conversations/' + conversationId + '/read').then(unwrap);
    },
    markUnread: function (conversationId) {
      return http('PUT', '/messages/conversations/' + conversationId + '/unread').then(unwrap);
    },
    unreadCount: function () {
      return http('GET', '/messages/unread-count').then(unwrap);
    },
    listContacts: function () {
      return http('GET', '/messages/contacts').then(unwrap);
    },
    addContact: function (data) {
      return http('POST', '/messages/contacts', data).then(unwrap);
    },
    removeContact: function (id) {
      return http('DELETE', '/messages/contacts/' + id).then(unwrap);
    },
    searchUsers: function (q) {
      return http('GET', '/messages/users/search?q=' + encodeURIComponent(q)).then(unwrap);
    },
    upload: function (file) {
      var fd = new FormData();
      fd.append('file', file);
      var token = localStorage.getItem('fa-auth-token');
      var origin = window.location.origin || '';
      if (!origin || origin === 'null' || origin.indexOf('file:') === 0) origin = 'http://localhost:8000';
      return fetch(origin + '/api/v1/messages/upload', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + token },
        body: fd
      }).then(function(r) {
        return r.json().then(function(d) {
          if (!r.ok || d.status === 'error') throw new Error(d.message || d.detail || 'Upload failed');
          return d.data || d;
        });
      });
    },
    addReaction: function (conversationId, messageId, emoji) {
      return http('POST', '/messages/conversations/' + conversationId + '/messages/' + messageId + '/reactions', { emoji: emoji }).then(unwrap);
    },
    setOnline: function () {
      return http('POST', '/messages/presence/online').then(unwrap);
    },
    setOffline: function () {
      return http('POST', '/messages/presence/offline').then(unwrap);
    },
    getPresence: function (userId) {
      return http('GET', '/messages/presence/' + userId).then(unwrap);
    },
    setTyping: function (conversationId) {
      return http('POST', '/messages/conversations/' + conversationId + '/typing').then(unwrap);
    }
  };

  var DocumentService = {
    list: function (params) {
      var query = '';
      if (params) {
        var queryParts = [];
        
        // Handle backward compatibility: if params is a string (category)
        if (typeof params === 'string') {
          if (params && params !== 'All') {
            queryParts.push('category=' + encodeURIComponent(params));
          }
        } else if (typeof params === 'object') {
          // New params object format
          if (params.category && params.category !== 'All') {
            queryParts.push('category=' + encodeURIComponent(params.category));
          }
          if (params.doc_type) {
            queryParts.push('doc_type=' + encodeURIComponent(params.doc_type));
          }
          if (params.search) {
            queryParts.push('search=' + encodeURIComponent(params.search));
          }
          if (params.date_range && params.date_range !== 'all') {
            queryParts.push('date_range=' + encodeURIComponent(params.date_range));
          }
          if (params.status) {
            queryParts.push('status=' + encodeURIComponent(params.status));
          }
          if (params.sort_by) {
            queryParts.push('sort_by=' + encodeURIComponent(params.sort_by));
          }
        }
        
        if (queryParts.length > 0) {
          query = '?' + queryParts.join('&');
        }
      }
      return http('GET', '/documents' + query).then(unwrap);
    },
    get: function (id) {
      return http('GET', '/documents/' + id).then(unwrap);
    },
    rename: function (id, documentName) {
      return http('PUT', '/documents/' + id + '/rename', { document_name: documentName }).then(unwrap);
    },
    getPreview: function (id) {
      return http('GET', '/documents/' + id + '/preview').then(unwrap);
    },
    getFilterOptions: function () {
      return http('GET', '/documents/filter/options').then(unwrap);
    },
    storageSummary: function () {
      return http('GET', '/documents/storage/summary').then(unwrap);
    },
    fetchBlob: function (id, download) {
      var token = localStorage.getItem('fa-auth-token');
      var url = Config.BASE_URL + '/documents/' + id + '/file' + (download ? '?download=true' : '');
      var headers = {};
      if (token) headers['Authorization'] = 'Bearer ' + token;
      return fetch(url, { method: 'GET', headers: headers, credentials: 'same-origin' }).then(function (r) {
        if (!r.ok) {
          return r.json().then(function (data) {
            var err = new Error((data && data.detail) || 'HTTP ' + r.status);
            err.status = r.status;
            throw err;
          });
        }
        return r.blob();
      });
    },
    upload: function (fileOrFormData, category, description) {
      // Handle both old and new calling conventions
      var formData;
      if (fileOrFormData instanceof FormData) {
        formData = fileOrFormData;
      } else {
        // Old convention: (file, category, description)
        formData = new FormData();
        formData.append('file', fileOrFormData);
        formData.append('document_category', category || 'Other');
        formData.append('description', description || '');
      }
      return http('POST', '/documents/upload', formData).then(unwrap);
    },
    delete: function (id) {
      return http('DELETE', '/documents/' + id).then(unwrap);
    }
  };

  var UserSettingsService = {
    get: function () {
      return http('GET', '/users/settings').then(unwrap);
    },
    update: function (data) {
      return http('PUT', '/users/settings', data).then(unwrap);
    },
    getSessions: function () {
      return http('GET', '/users/sessions').then(unwrap);
    },
    updateLanguage: function (lang) {
      return http('PUT', '/users/language', { language: lang }).then(unwrap);
    },
    logoutAllDevices: function () {
      return http('POST', '/users/logout-all-devices').then(unwrap);
    }
  };

  var FeedbackService = {
    submit: function (data) {
      return http('POST', '/feedback', data).then(unwrap);
    },
    list: function () {
      return http('GET', '/feedback').then(unwrap);
    },
    get: function (feedbackId) {
      return http('GET', '/feedback/' + feedbackId).then(unwrap);
    }
  };

  var LearningService = {
    listCourses: function (params) {
      var q = params ? '?' + buildQuery(params) : '';
      return http('GET', '/courses' + q).then(unwrap);
    },
    getCourse: function (courseId) {
      return http('GET', '/courses/' + courseId).then(unwrap);
    },
    enroll: function (courseId) {
      return http('POST', '/courses/enroll', { course_id: courseId }).then(unwrap);
    },
    myLearning: function (status) {
      var q = status ? '?status=' + encodeURIComponent(status) : '';
      return http('GET', '/my-learning' + q).then(unwrap);
    },
    completeLesson: function (enrollmentId, lessonId) {
      return http('POST', '/enrollments/' + enrollmentId + '/complete-lesson/' + lessonId).then(unwrap);
    },
    getCategories: function () {
      return http('GET', '/categories').then(unwrap);
    },
    getCourseTutorials: function (courseId) {
      return http('GET', '/courses/' + courseId + '/tutorials').then(unwrap);
    },
    getTutorial: function (tutorialId) {
      return http('GET', '/tutorials/' + tutorialId).then(unwrap);
    },
    startTutorial: function (tutorialId) {
      return http('POST', '/tutorials/' + tutorialId + '/start').then(unwrap);
    },
    submitQuiz: function (tutorialId, answers) {
      return http('POST', '/tutorials/' + tutorialId + '/quiz/submit', { answers: answers }).then(unwrap);
    },
    completeTutorial: function (tutorialId) {
      return http('POST', '/tutorials/' + tutorialId + '/complete').then(unwrap);
    },
    learningProgress: function () {
      return http('GET', '/learning/progress').then(unwrap);
    }
  };

  var TechniqueService = {
    list: function (params) {
      var q = params ? '?' + buildQuery(params) : '';
      return http('GET', '/techniques' + q).then(unwrap);
    },
    get: function (techniqueId) {
      return http('GET', '/techniques/' + techniqueId).then(unwrap);
    },
    bookmark: function (techniqueId) {
      return http('POST', '/techniques/' + techniqueId + '/bookmark').then(unwrap);
    },
    getBookmarks: function () {
      return http('GET', '/techniques/bookmarks/list').then(unwrap);
    },
    getCategories: function () {
      return http('GET', '/techniques/categories/all').then(unwrap);
    },
    getCrops: function () {
      return http('GET', '/techniques/crops/all').then(unwrap);
    }
  };

  var CalendarService = {
    listEvents: function (params) {
      var q = params ? '?' + buildQuery(params) : '';
      return http('GET', '/calendar/events' + q).then(unwrap);
    },
    getEvent: function (eventId) {
      return http('GET', '/calendar/events/' + encodeURIComponent(eventId)).then(unwrap);
    },
    createEvent: function (data) {
      return http('POST', '/calendar/events', data).then(unwrap);
    },
    updateEvent: function (eventId, data) {
      return http('PUT', '/calendar/events/' + encodeURIComponent(eventId), data).then(unwrap);
    },
    deleteEvent: function (eventId) {
      return http('DELETE', '/calendar/events/' + encodeURIComponent(eventId)).then(unwrap);
    },
    today: function () {
      return http('GET', '/calendar/today').then(unwrap);
    },
    upcoming: function (limit) {
      var q = limit ? '?limit=' + limit : '';
      return http('GET', '/calendar/upcoming' + q).then(unwrap);
    },
    filters: function () {
      return http('GET', '/calendar/filters').then(unwrap);
    },
    sync: function () {
      return http('POST', '/calendar/sync').then(unwrap);
    }
  };

  var LivestockService = {
    overview: function () {
      return http('GET', '/livestock/overview').then(unwrap);
    },
    eventsUpcoming: function () {
      return http('GET', '/livestock/events/upcoming').then(unwrap);
    },
    list: function () {
      return http('GET', '/livestock').then(unwrap);
    },
    create: function (data) {
      return http('POST', '/livestock', data).then(unwrap);
    },
    get: function (animalId) {
      return http('GET', '/livestock/' + encodeURIComponent(animalId)).then(unwrap);
    },
    update: function (animalId, data) {
      return http('PUT', '/livestock/' + encodeURIComponent(animalId), data).then(unwrap);
    },
    remove: function (animalId) {
      return http('DELETE', '/livestock/' + encodeURIComponent(animalId)).then(unwrap);
    },
    full: function (animalId) {
      return http('GET', '/livestock/' + encodeURIComponent(animalId) + '/full').then(unwrap);
    },
    attentionSummary: function () {
      return http('GET', '/livestock/attention/summary').then(unwrap);
    },
    recentActivity: function () {
      return http('GET', '/livestock/activity/recent').then(unwrap);
    },
    health: function (animalId) {
      return http('GET', '/livestock/' + encodeURIComponent(animalId) + '/health').then(unwrap);
    },
    addHealth: function (animalId, data) {
      return http('POST', '/livestock/' + encodeURIComponent(animalId) + '/health', data).then(unwrap);
    },
    updateHealth: function (animalId, recordId, data) {
      return http('PUT', '/livestock/' + encodeURIComponent(animalId) + '/health/' + encodeURIComponent(recordId), data).then(unwrap);
    },
    vaccinations: function (animalId) {
      return http('GET', '/livestock/' + encodeURIComponent(animalId) + '/vaccinations').then(unwrap);
    },
    addVaccination: function (animalId, data) {
      return http('POST', '/livestock/' + encodeURIComponent(animalId) + '/vaccinations', data).then(unwrap);
    },
    updateVaccination: function (animalId, vaccId, data) {
      return http('PUT', '/livestock/' + encodeURIComponent(animalId) + '/vaccinations/' + encodeURIComponent(vaccId), data).then(unwrap);
    },
    treatments: function (animalId) {
      return http('GET', '/livestock/' + encodeURIComponent(animalId) + '/treatments').then(unwrap);
    },
    addTreatment: function (animalId, data) {
      return http('POST', '/livestock/' + encodeURIComponent(animalId) + '/treatments', data).then(unwrap);
    },
    updateTreatment: function (animalId, treatmentId, data) {
      return http('PUT', '/livestock/' + encodeURIComponent(animalId) + '/treatments/' + encodeURIComponent(treatmentId), data).then(unwrap);
    },
    feeding: function (animalId) {
      return http('GET', '/livestock/' + encodeURIComponent(animalId) + '/feeding').then(unwrap);
    },
    addFeeding: function (animalId, data) {
      return http('POST', '/livestock/' + encodeURIComponent(animalId) + '/feeding', data).then(unwrap);
    },
    updateFeeding: function (animalId, feedId, data) {
      return http('PUT', '/livestock/' + encodeURIComponent(animalId) + '/feeding/' + encodeURIComponent(feedId), data).then(unwrap);
    },
    breeding: function (animalId) {
      return http('GET', '/livestock/' + encodeURIComponent(animalId) + '/breeding').then(unwrap);
    },
    addBreeding: function (animalId, data) {
      return http('POST', '/livestock/' + encodeURIComponent(animalId) + '/breeding', data).then(unwrap);
    },
    updateBreeding: function (animalId, breedingId, data) {
      return http('PUT', '/livestock/' + encodeURIComponent(animalId) + '/breeding/' + encodeURIComponent(breedingId), data).then(unwrap);
    },
    weight: function (animalId) {
      return http('GET', '/livestock/' + encodeURIComponent(animalId) + '/weight').then(unwrap);
    },
    addWeight: function (animalId, data) {
      return http('POST', '/livestock/' + encodeURIComponent(animalId) + '/weight', data).then(unwrap);
    },
    updateWeight: function (animalId, weightId, data) {
      return http('PUT', '/livestock/' + encodeURIComponent(animalId) + '/weight/' + encodeURIComponent(weightId), data).then(unwrap);
    },
    production: function (animalId) {
      return http('GET', '/livestock/' + encodeURIComponent(animalId) + '/production').then(unwrap);
    },
    addProduction: function (animalId, data) {
      return http('POST', '/livestock/' + encodeURIComponent(animalId) + '/production', data).then(unwrap);
    },
    updateProduction: function (animalId, productionId, data) {
      return http('PUT', '/livestock/' + encodeURIComponent(animalId) + '/production/' + encodeURIComponent(productionId), data).then(unwrap);
    },
    expenses: function (animalId) {
      return http('GET', '/livestock/' + encodeURIComponent(animalId) + '/expenses').then(unwrap);
    },
    addExpense: function (animalId, data) {
      return http('POST', '/livestock/' + encodeURIComponent(animalId) + '/expenses', data).then(unwrap);
    },
    photos: function (animalId) {
      return http('GET', '/livestock/' + encodeURIComponent(animalId) + '/photos').then(unwrap);
    },
    addPhoto: function (animalId, data) {
      return http('POST', '/livestock/' + encodeURIComponent(animalId) + '/photos', data).then(unwrap);
    },
    updatePhoto: function (animalId, photoId, data) {
      return http('PUT', '/livestock/' + encodeURIComponent(animalId) + '/photos/' + encodeURIComponent(photoId), data).then(unwrap);
    },
    deletePhoto: function (animalId, photoId) {
      return http('DELETE', '/livestock/' + encodeURIComponent(animalId) + '/photos/' + encodeURIComponent(photoId)).then(unwrap);
    },
    updateExpense: function (animalId, expenseId, data) {
      return http('PUT', '/livestock/' + encodeURIComponent(animalId) + '/expenses/' + encodeURIComponent(expenseId), data).then(unwrap);
    }
  };

  function buildQuery(params) {
    var parts = [];
    for (var k in params) {
      if (params.hasOwnProperty(k) && params[k] !== undefined && params[k] !== null && params[k] !== '') {
        parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(params[k]));
      }
    }
    return parts.join('&');
  }

  /* =========================================================================
   * MONITORING SERVICE — Smart Monitoring real-data API layer
   * All calls are scoped to the authenticated farmer. No mock data.
   * ========================================================================= */
  function monQ(params) {
    if (!params) return '';
    var parts = [];
    Object.keys(params).forEach(function (k) {
      if (params[k] !== undefined && params[k] !== null && params[k] !== '') {
        parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(params[k]));
      }
    });
    return parts.length ? '?' + parts.join('&') : '';
  }

  var MonitoringService = {
    /** List authenticated farmer's farms */
    farms: function () {
      return http('GET', '/monitoring/farms').then(unwrap);
    },
    /** List plots for a farm (pass farm_id string) */
    plots: function (farmId) {
      return http('GET', '/monitoring/plots' + monQ({ farm_id: farmId })).then(unwrap);
    },
    /** List sensors for a farm/plot */
    sensors: function (farmId, plotId) {
      return http('GET', '/monitoring/sensors' + monQ({ farm_id: farmId, plot_id: plotId })).then(unwrap);
    },
    /** Full overview — current conditions, sensors, alerts, weather, crops, thresholds */
    overview: function (farmId, plotId) {
      return http('GET', '/monitoring/overview' + monQ({ farm_id: farmId, plot_id: plotId })).then(unwrap);
    },
    /** Historical readings for charts */
    history: function (farmId, plotId, days, metric) {
      return http('GET', '/monitoring/history' + monQ({ farm_id: farmId, plot_id: plotId, days: days, metric: metric })).then(unwrap);
    },
    /** Active and recent alerts */
    alerts: function (farmId, plotId, status) {
      return http('GET', '/monitoring/alerts' + monQ({ farm_id: farmId, plot_id: plotId, status: status })).then(unwrap);
    },
    /** Connect a sensor to a farm/plot */
    connectSensor: function (payload) {
      return http('POST', '/monitoring/sensors/connect', payload).then(unwrap);
    },
    /** Disconnect a sensor */
    disconnectSensor: function (sensorId) {
      return http('POST', '/monitoring/sensors/' + encodeURIComponent(sensorId) + '/disconnect').then(unwrap);
    },
    /** Ingest a sensor reading */
    ingestReading: function (sensorId, payload) {
      return http('POST', '/monitoring/sensors/' + encodeURIComponent(sensorId) + '/readings', payload).then(unwrap);
    },
    /** Acknowledge a monitoring alert */
    acknowledgeAlert: function (alertId) {
      return http('POST', '/monitoring/alerts/' + encodeURIComponent(alertId) + '/acknowledge').then(unwrap);
    },
    /** Resolve a monitoring alert */
    resolveAlert: function (alertId) {
      return http('POST', '/monitoring/alerts/' + encodeURIComponent(alertId) + '/resolve').then(unwrap);
    },
    /** List thresholds */
    thresholds: function (farmId) {
      return http('GET', '/monitoring/thresholds' + monQ({ farm_id: farmId })).then(unwrap);
    },
    /** Create or upsert a threshold */
    createThreshold: function (payload) {
      return http('POST', '/monitoring/thresholds', payload).then(unwrap);
    },
    /** Update an existing threshold */
    updateThreshold: function (thresholdId, payload) {
      return http('PATCH', '/monitoring/thresholds/' + encodeURIComponent(thresholdId), payload).then(unwrap);
    },
    /** Create a farm task from a monitoring alert */
    createTask: function (payload) {
      return http('POST', '/monitoring/tasks', payload).then(unwrap);
    },
    /** AI insights for real monitoring data */
    insights: function (farmId, plotId) {
      return http('GET', '/monitoring/insights' + monQ({ farm_id: farmId, plot_id: plotId })).then(unwrap);
    },
    /** Check drone operating hours availability */
    droneAvailability: function () {
      return http('GET', '/monitoring/drone/availability').then(unwrap);
    },
    /** Get authorized drone context (farm, plot, crop, stream config) */
    droneContext: function (farmId, plotId) {
      return http('GET', '/monitoring/drone/context' + monQ({ farm_id: farmId, plot_id: plotId })).then(unwrap);
    }
  };

  /* =========================================================================
   * SENSOR SERVICE — direct sensor CRUD (separate from monitoring context)
   * ========================================================================= */
  var SensorService = {
    list: function (params) {
      return http('GET', '/sensors' + monQ(params)).then(unwrap);
    },
    get: function (sensorId) {
      return http('GET', '/sensors/' + encodeURIComponent(sensorId)).then(unwrap);
    },
    /** Supported sensor type catalogue (labels, units, icons) */
    types: function () {
      return http('GET', '/sensors/types').then(unwrap);
    },
    /** Registered devices not yet connected to any farmer */
    available: function () {
      return http('GET', '/sensors/available').then(unwrap);
    },
    /** Verify a device id with the backend before connecting */
    verify: function (payload) {
      return http('POST', '/sensors/verify', payload).then(unwrap);
    },
    /** Connect a verified device to the farmer's farm/plot */
    connect: function (payload) {
      return http('POST', '/sensors/connect', payload).then(unwrap);
    },
    /** Historical stored readings for one owned sensor */
    readings: function (sensorId, hours) {
      return http('GET', '/sensors/' + encodeURIComponent(sensorId) + '/readings' + monQ({ hours: hours })).then(unwrap);
    },
    /** Current status + latest reading for one sensor */
    status: function (sensorId) {
      return http('GET', '/sensors/' + encodeURIComponent(sensorId) + '/status').then(unwrap);
    },
    /** Alerts for one owned sensor */
    alerts: function (sensorId) {
      return http('GET', '/sensors/' + encodeURIComponent(sensorId) + '/alerts').then(unwrap);
    },
    /** Force-refresh live state from the backend */
    refresh: function (sensorId) {
      return http('POST', '/sensors/' + encodeURIComponent(sensorId) + '/refresh').then(unwrap);
    },
    /** Reactivate a disconnected sensor */
    reconnect: function (sensorId) {
      return http('POST', '/sensors/' + encodeURIComponent(sensorId) + '/reconnect').then(unwrap);
    },
    /** Disconnect a sensor (history is retained) */
    disconnect: function (sensorId) {
      return http('POST', '/sensors/' + encodeURIComponent(sensorId) + '/disconnect').then(unwrap);
    },
    /** Update sensor config: name, farm, plot */
    update: function (sensorId, payload) {
      return http('PATCH', '/sensors/' + encodeURIComponent(sensorId), payload).then(unwrap);
    },
    /** Register the farmer's own physical sensor device (Add Sensor flow) */
    register: function (payload) {
      return http('POST', '/sensors/register', payload).then(unwrap);
    },
    /** Regenerate the sensor auth token; the returned plaintext is shown once */
    rotateToken: function (sensorId) {
      return http('POST', '/sensors/' + encodeURIComponent(sensorId) + '/rotate-token').then(unwrap);
    },
    /** Submit authenticated readings as physical hardware (X-Sensor-Token) */
    ingest: function (payload, authToken) {
      var headers = { 'Content-Type': 'application/json' };
      if (authToken) headers['X-Sensor-Token'] = authToken;
      var controller = new AbortController();
      var timeoutId = setTimeout(function () { controller.abort(); }, Config.TIMEOUT);
      return fetch(Config.BASE_URL + '/sensors/data', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(payload),
        signal: controller.signal
      }).then(function (r) {
        clearTimeout(timeoutId);
        if (r.status === 204) return { status: 'success', data: null };
        return parseResponse(r).then(function (data) {
          if (!r.ok) {
            var err = new Error((data && data.detail) || 'HTTP ' + r.status);
            err.status = r.status;
            err.data = data;
            throw err;
          }
          return data;
        });
      }).catch(function (e) {
        clearTimeout(timeoutId);
        throw e;
      });
    },
    /** Aggregate latest readings across the farmer's sensors of a type (back-compat) */
    getReadings: function (sensorType, hours) {
      return SensorService.list({ sensor_type: sensorType, per_page: 100 })
        .then(function (sensors) {
          if (!sensors || !sensors.length) return [];
          return Promise.all(sensors.map(function (s) {
            return SensorService.readings(s.id, hours).catch(function () { return null; });
          })).then(function (chunks) {
            var out = [];
            chunks.forEach(function (c) {
              if (c && c.length) out = out.concat(c);
            });
            out.sort(function (a, b) { return String(a.recorded_at).localeCompare(String(b.recorded_at)); });
            return out;
          });
        });
    }
  };

  /* =========================================================================
   * SOIL IRRIGATION SERVICE
   * ========================================================================= */
  var SoilIrrigationService = {
    getSoilRecords: function(farmId, plotId, cropId, limit) {
      return http('GET', '/soil-irrigation/soil-records' + buildQuery({
        farm_id: farmId,
        plot_id: plotId,
        crop_id: cropId,
        limit: limit
      })).then(unwrap);
    },
    getLatestSoilData: function(farmId, plotId, cropId) {
      return http('GET', '/soil-irrigation/soil-latest' + buildQuery({
        farm_id: farmId,
        plot_id: plotId,
        crop_id: cropId
      })).then(unwrap);
    },
    getIrrigationRecords: function(farmId, plotId, cropId, days, limit) {
      return http('GET', '/soil-irrigation/irrigation-records' + buildQuery({
        farm_id: farmId,
        plot_id: plotId,
        crop_id: cropId,
        days: days,
        limit: limit
      })).then(unwrap);
    },
    getIrrigationSummary: function(farmId, plotId, cropId, days) {
      return http('GET', '/soil-irrigation/irrigation-summary' + buildQuery({
        farm_id: farmId,
        plot_id: plotId,
        crop_id: cropId,
        days: days
      })).then(unwrap);
    },
    getCropContext: function(farmId, plotId) {
      return http('GET', '/soil-irrigation/crop-context' + buildQuery({
        farm_id: farmId,
        plot_id: plotId
      })).then(unwrap);
    },
    getSoilHealthStatus: function(farmId, plotId) {
      return http('GET', '/soil-irrigation/soil-health-status' + buildQuery({
        farm_id: farmId,
        plot_id: plotId
      })).then(unwrap);
    },
    getIrrigationStatus: function(farmId, plotId) {
      return http('GET', '/soil-irrigation/irrigation-status' + buildQuery({
        farm_id: farmId,
        plot_id: plotId
      })).then(unwrap);
    },
    aiOverview: function(farmId, plotId, cropId) {
      return http('GET', '/soil-irrigation/ai-overview' + buildQuery({
        farm_id: farmId,
        plot_id: plotId,
        crop_id: cropId
      })).then(unwrap);
    }
  };

  /* =========================================================================
   * CROP HEALTH SERVICE — care dashboard (no scanning / diagnosis)
   * ========================================================================= */
  var CropHealthService = {
    overview: function (farmId, plotId, cycleId) {
      return http('GET', '/crop-health/overview' + monQ({
        farm_id: farmId,
        plot_id: plotId,
        cycle_id: cycleId
      })).then(unwrap);
    },
    aiOverview: function (farmId, plotId, cycleId) {
      return http('GET', '/crop-health/ai-overview' + monQ({
        farm_id: farmId,
        plot_id: plotId,
        cycle_id: cycleId
      })).then(unwrap);
    }
  };

  /* =========================================================================
   * STORAGE / FILE SERVICE
   * ========================================================================= */
  var StorageService = {
    upload: function (formData) {
      return http('POST', '/storage/upload', formData).then(unwrap);
    },
    list: function (params) {
      return http('GET', '/storage/files' + monQ(params)).then(unwrap);
    },
    get: function (fileId) {
      return http('GET', '/storage/files/' + encodeURIComponent(fileId)).then(unwrap);
    },
    delete: function (fileId) {
      return http('DELETE', '/storage/files/' + encodeURIComponent(fileId)).then(unwrap);
    }
  };

  /* =========================================================================
   * DOCUMENT SERVICE
   * ========================================================================= */
  var DocumentService = {
    list: function (params) {
      return http('GET', '/documents' + monQ(params)).then(unwrap);
    },
    get: function (docId) {
      return http('GET', '/documents/' + encodeURIComponent(docId)).then(unwrap);
    },
    upload: function (formData) {
      return http('POST', '/documents/upload', formData).then(unwrap);
    },
    delete: function (docId) {
      return http('DELETE', '/documents/' + encodeURIComponent(docId)).then(unwrap);
    }
  };

  /* =========================================================================
   * MARKET PRICE SERVICE
   * ========================================================================= */
  var MarketPriceService = {
    list: function (params) {
      return http('GET', '/market-prices' + monQ(params)).then(unwrap);
    },
    commodities: function () {
      return http('GET', '/market-prices/commodities').then(unwrap);
    },
    trends: function (commodity, days) {
      return http('GET', '/market-prices/trends' + monQ({ commodity: commodity, days: days })).then(unwrap);
    }
  };

  /* =========================================================================
   * USER SETTINGS SERVICE
   * ========================================================================= */
  var UserSettingsService = {
    get: function () {
      return http('GET', '/users/settings').then(unwrap);
    },
    update: function (payload) {
      return http('PATCH', '/users/settings', payload).then(unwrap);
    }
  };

  global.API = {
    config: Config,
    Storage: Storage,
    Auth: AuthService,
    Locations: LocationService,
    Profile: ProfileService,
    Farm: FarmService,
    Crop: CropService,
    Finance: FinanceService,
    Worker: WorkerService,
    Service: ServiceService,
    Wallet: WalletService,
    Equipment: EquipmentService,
    InputStore: InputStoreService,
    Marketplace: MarketplaceService,
    MarketplaceSeller: MarketplaceSellerService,
    Government: GovernmentService,
    GovernmentService: GovernmentService,
    Community: CommunityService,
    Notification: NotificationService,
    Weather: WeatherService,
    Maps: MapsService,
    AI: AIService,
    Loan: LoanService,
    Insurance: InsuranceService,
    Sensor: SensorService,
    Monitoring: MonitoringService,
    SoilIrrigation: SoilIrrigationService,
    CropHealth: CropHealthService,
    FileStorage: StorageService,
    Documents: DocumentService,
    FarmBuzz: FarmBuzzService,
    News: NewsService,
    MarketPrice: MarketPriceService,
    Translation: TranslationService,
    Speech: SpeechService,
    QR: QRService,
    Analytics: AnalyticsService,
    Integrations: IntegrationService,
    Messages: MessageService,
    Feedback: FeedbackService,
    UserSettings: UserSettingsService,
    Support: SupportService,
    Learning: LearningService,
    Technique: TechniqueService,
    Calendar: CalendarService,
    Livestock: LivestockService,
    buildQuery: buildQuery
  };

  global.AuthService = AuthService;
  global.LocationService = LocationService;
  global.FarmService = FarmService;
  global.CropService = CropService;
  global.FinanceService = FinanceService;
  global.WorkerService = WorkerService;
  global.ServiceService = ServiceService;
  global.WalletService = WalletService;
  global.EquipmentService = EquipmentService;
  global.InputStoreService = InputStoreService;
  global.MarketplaceService = MarketplaceService;
  global.MarketplaceSellerService = MarketplaceSellerService;
  global.GovernmentService = GovernmentService;
  global.CommunityService = CommunityService;
  global.FarmBuzzService = FarmBuzzService;
  global.NotificationService = NotificationService;
  global.WeatherService = WeatherService;
  global.MapsService = MapsService;
  global.AIService = AIService;
  global.LoanService = LoanService;
  global.InsuranceService = InsuranceService;
  global.SensorService = SensorService;
  global.MonitoringService = MonitoringService;
  global.SoilIrrigationService = SoilIrrigationService;
  global.CropHealthService = CropHealthService;
  global.StorageService = StorageService;
  global.DocumentService = DocumentService;
  global.NewsService = NewsService;
  global.MarketPriceService = MarketPriceService;
  global.TranslationService = TranslationService;
  global.SpeechService = SpeechService;
  global.QRService = QRService;
  global.MessageService = MessageService;
  global.FeedbackService = FeedbackService;
  global.AnalyticsService = AnalyticsService;
  global.LearningService = LearningService;
  global.TechniqueService = TechniqueService;
  global.CalendarService = CalendarService;
  global.LivestockService = LivestockService;

})(window);
