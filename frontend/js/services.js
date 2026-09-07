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
    var meta = document.querySelector('meta[name="api-base-url"], meta[name="api-base"]');
    if (meta && meta.content) return meta.content;
    var origin = window.location.origin || '';
    if (!origin || origin === 'null' || origin.indexOf('file:') === 0) {
      origin = 'http://localhost:8000';
    }
    return origin + '/api/v1';
  }

  var Config = {
    BASE_URL: detectBaseUrl(),
    TIMEOUT: 15000
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
          var err = new Error('The server returned an unexpected response.');
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
        var err = new Error('The server returned an invalid response. Please try again.');
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
      if (isAbortError(e)) {
        var timeoutErr = new Error('Request timed out. Please check your connection and try again.');
        timeoutErr.isTimeout = true;
        throw timeoutErr;
      }
      if (isNetworkError(e)) {
        var netErr = new Error('Unable to connect to server. Please check your connection.');
        netErr.isNetworkError = true;
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
    listTasks: function () {
      return http('GET', '/crop-tasks').then(unwrap);
    },
    createTask: function (data) {
      return http('POST', '/crop-tasks', data).then(unwrap);
    },
    updateTask: function (id, data) {
      return http('PUT', '/crop-tasks/' + id, data).then(unwrap);
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
    }
  };

  var WorkerService = {
    list: function (params) {
      var qs = '';
      if (params) {
        var parts = [];
        Object.keys(params).forEach(function (k) { if (params[k]) parts.push(k + '=' + encodeURIComponent(params[k])); });
        qs = parts.join('&');
      }
      return http('GET', '/workers' + (qs ? '?' + qs : '')).then(unwrap);
    },
    get: function (id) {
      return http('GET', '/workers/' + id).then(unwrap);
    },
    book: function (data) {
      return http('POST', '/worker-bookings', data).then(unwrap);
    },
    listBookings: function () {
      return http('GET', '/worker-bookings').then(unwrap);
    },
    updateBooking: function (id, data) {
      return http('PUT', '/worker-bookings/' + id, data).then(unwrap);
    }
  };

  var EquipmentService = {
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
    }
  };

  var SensorService = {
    list: function (params) {
      var q = params ? '?' + buildQuery(params) : '';
      return http('GET', '/sensors' + q).then(unwrap);
    },
    get: function (sensorId) {
      return http('GET', '/sensors/' + sensorId).then(unwrap);
    },
    getReadings: function (sensorType, hours) {
      return http('GET', '/sensors/' + sensorType + '/readings?hours=' + (hours || 24)).then(unwrap);
    }
  };

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

  function buildQuery(params) {
    var parts = [];
    for (var k in params) {
      if (params.hasOwnProperty(k) && params[k] !== undefined && params[k] !== null && params[k] !== '') {
        parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(params[k]));
      }
    }
    return parts.join('&');
  }

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
    Marketplace: MarketplaceService,
    Government: GovernmentService,
    Community: CommunityService,
    Notification: NotificationService,
    Weather: WeatherService,
    Maps: MapsService,
    AI: AIService,
    Loan: LoanService,
    Sensor: SensorService,
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
  global.MarketplaceService = MarketplaceService;
  global.GovernmentService = GovernmentService;
  global.CommunityService = CommunityService;
  global.FarmBuzzService = FarmBuzzService;
  global.NotificationService = NotificationService;
  global.WeatherService = WeatherService;
  global.MapsService = MapsService;
  global.AIService = AIService;
  global.LoanService = LoanService;
  global.SensorService = SensorService;
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

})(window);
