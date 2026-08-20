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
    }
  };

  var ServiceService = {
    list: function (params) {
      var qs = '';
      if (params) {
        var parts = [];
        Object.keys(params).forEach(function (k) { if (params[k]) parts.push(k + '=' + encodeURIComponent(params[k])); });
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
    }
  };

  var WalletService = {
    getSummary: function () {
      return http('GET', '/wallet/summary').then(unwrap);
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
        Object.keys(params).forEach(function (k) { if (params[k]) parts.push(k + '=' + encodeURIComponent(params[k])); });
        qs = parts.join('&');
      }
      return http('GET', '/transactions' + (qs ? '?' + qs : '')).then(unwrap);
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
    }
  };

  var GovernmentService = {
    listSchemes: function (params) {
      var qs = '';
      if (params) {
        var parts = [];
        Object.keys(params).forEach(function (k) { if (params[k]) parts.push(k + '=' + encodeURIComponent(params[k])); });
        qs = parts.join('&');
      }
      return http('GET', '/government-schemes' + (qs ? '?' + qs : '')).then(unwrap);
    },
    getScheme: function (id) {
      return http('GET', '/government-schemes/' + id).then(unwrap);
    },
    applyScheme: function (id, data) {
      return http('POST', '/government-schemes/' + id + '/apply', data || {}).then(unwrap);
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

  var CommunityService = {
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
    addComment: function (postId, data) {
      return http('POST', '/posts/' + postId + '/comments', data).then(unwrap);
    },
    toggleLike: function (postId) {
      return http('POST', '/posts/' + postId + '/like').then(unwrap);
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
    bookConsultation: function (data) {
      return http('POST', '/consultations', data).then(unwrap);
    },
    listConsultations: function () {
      return http('GET', '/consultations').then(unwrap);
    }
  };

  var NotificationService = {
    list: function (params) {
      var qs = '';
      if (params) {
        var parts = [];
        Object.keys(params).forEach(function (k) { if (params[k]) parts.push(k + '=' + encodeURIComponent(params[k])); });
        qs = parts.join('&');
      }
      return http('GET', '/notifications' + (qs ? '?' + qs : '')).then(unwrap);
    },
    unreadCount: function () {
      return http('GET', '/notifications/unread').then(unwrap);
    },
    markRead: function (id) {
      return http('PUT', '/notifications/' + id + '/read').then(unwrap);
    },
    markAllRead: function () {
      return http('PUT', '/notifications/read-all').then(unwrap);
    }
  };

  var FarmBuzzService = {
    request: function (method, path, body) {
      return http(method, '/farmbuzz' + path, body).then(unwrap);
    },
    feed: function (params) {
      return http('GET', '/farmbuzz/feed' + buildQuery(params)).then(unwrap);
    },
    posts: function (params) {
      return http('GET', '/farmbuzz/posts' + buildQuery(params)).then(unwrap);
    },
    shorts: function (params) {
      return http('GET', '/farmbuzz/shorts' + buildQuery(params)).then(unwrap);
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
    save: function (id) {
      return http('POST', '/farmbuzz/posts/' + id + '/save').then(unwrap);
    },
    share: function (id) {
      return http('POST', '/farmbuzz/posts/' + id + '/share').then(unwrap);
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
      return http('GET', '/farmbuzz/search' + buildQuery(params)).then(unwrap);
    },
    trends: function () {
      return http('GET', '/farmbuzz/trends').then(unwrap);
    },
    uploadMedia: function (file) {
      var fd = new FormData();
      fd.append('file', file);
      return http('POST', '/farmbuzz/media/upload', fd).then(unwrap);
    }
  };

  var WeatherService = {
    getCurrent: function (lat, lon) {
      return http('GET', '/weather/current?latitude=' + lat + '&longitude=' + lon).then(unwrap).then(function (res) {
        return (res && res.data) ? res.data : res;
      });
    },
    getForecast: function (lat, lon) {
      return http('GET', '/weather/forecast?latitude=' + lat + '&longitude=' + lon).then(unwrap).then(function (res) {
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
    getNews: function (category, query, page) {
      var q = '?category=' + (category || 'agriculture') + '&page=' + (page || 1);
      if (query) q += '&query=' + encodeURIComponent(query);
      return http('GET', '/news' + q).then(unwrap);
    }
  };

  var MarketPriceService = {
    getPrices: function (crop, location) {
      var q = '';
      if (crop) q += '?crop=' + encodeURIComponent(crop);
      if (location) q += (q ? '&' : '?') + 'location=' + encodeURIComponent(location);
      return http('GET', '/market-prices' + q).then(unwrap);
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
    getMessages: function (conversationId, params) {
      var q = params ? '?' + buildQuery(params) : '';
      return http('GET', '/messages/conversations/' + conversationId + '/messages' + q).then(unwrap);
    },
    sendMessage: function (conversationId, data) {
      return http('POST', '/messages/conversations/' + conversationId + '/messages', data).then(unwrap);
    },
    markRead: function (conversationId) {
      return http('PUT', '/messages/conversations/' + conversationId + '/read').then(unwrap);
    },
    unreadCount: function () {
      return http('GET', '/messages/unread-count').then(unwrap);
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
  global.NewsService = NewsService;
  global.MarketPriceService = MarketPriceService;
  global.TranslationService = TranslationService;
  global.SpeechService = SpeechService;
  global.QRService = QRService;
  global.MessageService = MessageService;
  global.FeedbackService = FeedbackService;
  global.AnalyticsService = AnalyticsService;

})(window);
