/* Farm Assist - farm/field location & boundary picker.
 *
 * A small reusable Leaflet widget used by My Farm so that farm and field
 * geographic data is captured in one place and stored through the existing
 * farm APIs. It never invents coordinates: unless the farmer taps the map,
 * uses GPS, or types coordinates, nothing is marked as set.
 *
 * Usage:
 *   var picker = FarmGeo.attach(document.getElementById('geo-map'), {
 *     latitude: 17.9, longitude: 78.4, boundary: { points: [...] },
 *     label: 'North Field',
 *     onChange: function (value) { ... }
 *   });
 *   picker.getValue(); // { latitude, longitude, boundary_coordinates }
 *   picker.destroy();
 */
(function (global) {
  'use strict';

  /* The widget ships with its own layout. Leaflet needs an explicit height on
     its container, and without this rule the map collapses to zero height and
     the farmer cannot tap a location or trace a boundary. Keeping the styles
     here means the picker works on any page that attaches it. */
  if (!document.getElementById('fa-geo-styles')) {
    var styleEl = document.createElement('style');
    styleEl.id = 'fa-geo-styles';
    styleEl.textContent = [
      '.fa-geo-wrap{display:flex;flex-direction:column;gap:8px;}',
      '.fa-geo-map{height:240px;width:100%;min-height:240px;border-radius:10px;overflow:hidden;z-index:0;}',
      '.fa-geo-map .leaflet-container{height:100%;width:100%;}',
      '.fa-geo-bar{display:flex;flex-wrap:wrap;gap:6px;}',
      '.fa-geo-btn{display:inline-flex;align-items:center;gap:6px;background:#fff;border:1px solid #d8e3da;',
      'border-radius:8px;padding:6px 10px;font-size:11.5px;font-weight:600;color:#1B5E3F;cursor:pointer;}',
      '.fa-geo-btn:hover:not(:disabled){border-color:#1B5E3F;background:#f1f8f2;}',
      '.fa-geo-btn:disabled{opacity:.5;cursor:not-allowed;}',
      '.fa-geo-btn.active{background:#1B5E3F;color:#fff;border-color:#1B5E3F;}',
      '.fa-geo-hint{font-size:11.5px;color:#5a6b5f;line-height:1.45;}',
      '.fa-geo-coords{font-size:11px;color:#41584a;font-variant-numeric:tabular-nums;word-break:break-word;}'
    ].join('');
    (document.head || document.documentElement).appendChild(styleEl);
  }

  var OSM_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
  var SAT_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

  function isNum(v) {
    return typeof v === 'number' && isFinite(v);
  }

  /* Accepts the normalised {"points": [[lat, lng], ...]} shape as well as a
   * bare list of pairs, so records written by other clients still load. */
  function toPoints(boundary) {
    if (!boundary) return [];
    var points = boundary;
    if (Object.prototype.toString.call(boundary) === '[object Array]') {
      points = boundary;
    } else if (typeof boundary === 'object') {
      points = boundary.points || boundary.coordinates || [];
      if (points && points.length && typeof points[0][0] === 'object') points = points[0];
    }
    if (Object.prototype.toString.call(points) !== '[object Array]') return [];
    var out = [];
    for (var i = 0; i < points.length; i++) {
      var p = points[i];
      if (!p || p.length < 2) continue;
      var lat = parseFloat(p[0]);
      var lng = parseFloat(p[1]);
      if (isNum(lat) && isNum(lng) && lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180) {
        out.push([lat, lng]);
      }
    }
    return out;
  }

  function esc(str) {
    return String(str == null ? '' : str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function formatCoords(lat, lng) {
    return Number(lat).toFixed(6) + ', ' + Number(lng).toFixed(6);
  }

  function FarmGeo() {
    if (!(this instanceof FarmGeo)) return new FarmGeo();
  }

  FarmGeo.prototype = {

    /* ------------------------------------------------------------------ */
    _buildDom: function () {
      var wrap = document.createElement('div');
      wrap.className = 'fa-geo';

      var mapBox = document.createElement('div');
      mapBox.className = 'fa-geo-map';
      wrap.appendChild(mapBox);

      var bar = document.createElement('div');
      bar.className = 'fa-geo-bar';
      bar.innerHTML =
        '<button type="button" class="fa-geo-btn" data-act="gps">' +
        '<i class="fas fa-location-crosshairs"></i> Use Current Location</button>' +
        '<button type="button" class="fa-geo-btn" data-act="sat">' +
        '<i class="fas fa-satellite"></i> Satellite</button>' +
        '<button type="button" class="fa-geo-btn" data-act="undo" disabled>' +
        '<i class="fas fa-undo"></i> Undo Point</button>' +
        '<button type="button" class="fa-geo-btn" data-act="clear" disabled>' +
        '<i class="fas fa-eraser"></i> Clear Boundary</button>';
      wrap.appendChild(bar);

      var hint = document.createElement('div');
      hint.className = 'fa-geo-hint';
      wrap.appendChild(hint);

      var coords = document.createElement('div');
      coords.className = 'fa-geo-coords';
      wrap.appendChild(coords);

      this.dom = wrap;
      this.mapBox = mapBox;
      this.hintEl = hint;
      this.coordsEl = coords;
      this.barEl = bar;
      return wrap;
    },

    _setHint: function (text) {
      this.hintEl.innerHTML = text;
    },

    _updateCoords: function () {
      var parts = [];
      if (this._hasLocation) {
        parts.push('<strong>Location:</strong> ' + esc(formatCoords(this.lat, this.lng)));
      } else {
        parts.push('<strong>Location:</strong> not set');
      }
      var n = this.points.length;
      parts.push(
        n >= 3
          ? '<strong>Boundary:</strong> ' + n + ' points saved'
          : '<strong>Boundary:</strong> ' + (n ? n + ' point' + (n > 1 ? 's' : '') + ' (need 3 or more)' : 'not set')
      );
      this.coordsEl.innerHTML = parts.join(' &nbsp;·&nbsp; ');
    },

    _syncButtons: function () {
      this.barEl.querySelector('[data-act="undo"]').disabled = !this.points.length;
      this.barEl.querySelector('[data-act="clear"]').disabled = !this.points.length;
      this.barEl.querySelector('[data-act="sat"]').classList.toggle('active', !!this._sat);
    },

    _emit: function () {
      this._updateCoords();
      this._syncButtons();
      if (typeof this.opts.onChange === 'function') this.opts.onChange(this.getValue());
    },

    /* ------------------------------------------------------------------ */
    _setLocation: function (lat, lng, source) {
      lat = Number(lat);
      lng = Number(lng);
      if (!isNum(lat) || !isNum(lng) || lat < -90 || lat > 90 || lng < -180 || lng > 180) return false;
      this.lat = Math.round(lat * 1e6) / 1e6;
      this.lng = Math.round(lng * 1e6) / 1e6;
      this._hasLocation = true;
      this._locSource = source || 'manual';

      if (this.centerMarker) this.centerMarker.setLatLng([this.lat, this.lng]);
      this._refreshMarker();

      /* With a real location and no boundary yet, centre on it and let the
       * farmer start tracing from the accurate point. */
      if (!this.points.length && this.map) {
        this.map.setView([this.lat, this.lng], Math.max(this.map.getZoom(), 16));
      }
      this._emit();
      return true;
    },

    _refreshMarker: function () {
      if (!this.centerMarker) return;
      if (this._hasLocation) {
        this.centerMarker.setLatLng([this.lat, this.lng]);
        this.centerMarker.setStyle({ opacity: 1, fillOpacity: 1 });
      } else {
        this.centerMarker.setStyle({ opacity: 0, fillOpacity: 0 });
      }
    },

    _redrawBoundary: function () {
      if (this.boundaryLayer && this.map) this.map.removeLayer(this.boundaryLayer);
      this.vertexLayer = this.vertexLayer || L.layerGroup().addTo(this.map);
      this.vertexLayer.clearLayers();
      this.boundaryLayer = null;

      var self = this;
      this.points.forEach(function (pt, i) {
        L.circleMarker(pt, {
          radius: 4,
          color: '#1B5E3F',
          weight: 2,
          fillColor: '#ffffff',
          fillOpacity: 1
        }).addTo(self.vertexLayer);
      });

      if (this.points.length >= 3) {
        this.boundaryLayer = L.polygon(this.points, {
          color: '#1B5E3F',
          weight: 2,
          fillColor: '#52B788',
          fillOpacity: 0.18
        }).addTo(this.map);
      }
    },

    _fitAll: function () {
      if (!this.map) return;
      var pts = this.points.slice();
      if (this._hasLocation) pts.push([this.lat, this.lng]);
      if (pts.length >= 2) {
        this.map.fitBounds(L.latLngBounds(pts).pad(0.25), { maxZoom: 18 });
      } else if (pts.length === 1) {
        this.map.setView(pts[0], 16);
      }
    },

    /* ------------------------------------------------------------------ */
    attach: function (container, opts) {
      opts = opts || {};
      var self = this;
      this.opts = opts;
      this.points = toPoints(opts.boundary);
      this.lat = isNum(Number(opts.latitude)) ? Number(opts.latitude) : null;
      this.lng = isNum(Number(opts.longitude)) ? Number(opts.longitude) : null;
      this._hasLocation = isNum(this.lat) && isNum(this.lng);
      this._locSource = opts.locationSource || 'manual';
      this._sat = false;
      this._destroyed = false;

      container.innerHTML = '';
      container.appendChild(this._buildDom());

      if (!global.L) {
        this._setHint('<span style="color:#D63031">The map service could not be loaded. You can still type coordinates manually.</span>');
        this._updateCoords();
        this._wireBar();
        this._emit = function () { self._updateCoords(); self._syncButtons(); };
        this._emit();
        return this;
      }

      this.map = L.map(this.mapBox, { zoomControl: true, attributionControl: false, tap: true })
        .setView([20.5937, 78.9629], 5);

      this.osm = L.tileLayer(OSM_URL, {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap contributors'
      }).addTo(this.map);
      this.satellite = L.tileLayer(SAT_URL, { maxZoom: 18 });

      /* Transparent pickup marker; the actual position is a LatLng. */
      this.centerMarker = L.circleMarker([0, 0], {
        radius: 7,
        color: '#1B5E3F',
        weight: 3,
        fillColor: '#ffffff',
        fillOpacity: 1
      }).addTo(this.map);

      this.vertexLayer = L.layerGroup().addTo(this.map);
      this._redrawBoundary();

      if (this._hasLocation) {
        this.centerMarker.setLatLng([this.lat, this.lng]);
      } else {
        this.centerMarker.setStyle({ opacity: 0, fillOpacity: 0 });
      }

      /* `center` only frames the view (e.g. over the parent farm) and never
         marks the location as set, so no coordinates are invented. */
      if (!this._hasLocation && !this.points.length && opts.center) {
        var c = opts.center;
        var clat = Number(c.latitude);
        var clng = Number(c.longitude);
        if (isNum(clat) && isNum(clng) && clat >= -90 && clat <= 90 && clng >= -180 && clng <= 180) {
          this.map.setView([clat, clng], 16);
        }
      } else {
        this._fitAll();
      }

      this._setHint(
        this.points.length
          ? 'Tap the map to adjust your boundary. Each tap adds a corner point.'
          : 'Tap the map to set this location, or tap around the edge to trace a boundary.'
      );

      this.map.on('click', function (e) {
        var pt = [e.latlng.lat, e.latlng.lng];
        self.points.push([Math.round(pt[0] * 1e6) / 1e6, Math.round(pt[1] * 1e6) / 1e6]);
        if (!self._hasLocation) self._setLocation(pt[0], pt[1], 'map');
        self._redrawBoundary();
        self._emit();
        if (self.points.length === 3) self._fitAll();
      });

      this._wireBar();
      this._emit();
      return this;
    },

    _wireBar: function () {
      var self = this;
      this.barEl.addEventListener('click', function (ev) {
        var btn = ev.target.closest ? ev.target.closest('[data-act]') : null;
        if (!btn) return;
        var act = btn.getAttribute('data-act');
        if (act === 'gps') self._useGps(btn);
        else if (act === 'sat') self._toggleSat();
        else if (act === 'undo') { self.points.pop(); self._redrawBoundary(); self._emit(); }
        else if (act === 'clear') {
          self.points = [];
          self._redrawBoundary();
          self._setHint('Boundary cleared. Tap the map to trace a new one.');
          self._emit();
        }
      });
    },

    _toggleSat: function () {
      if (!this.map) return;
      if (this._sat) {
        if (this.map.hasLayer(this.satellite)) this.map.removeLayer(this.satellite);
        if (!this.map.hasLayer(this.osm)) this.osm.addTo(this.map);
      } else {
        if (this.map.hasLayer(this.osm)) this.map.removeLayer(this.osm);
        if (!this.map.hasLayer(this.satellite)) this.satellite.addTo(this.map);
      }
      this._sat = !this._sat;
      this._syncButtons();
    },

    _useGps: function (btn) {
      var self = this;
      if (!('geolocation' in navigator)) {
        this._setHint('<span style="color:#D63031">Location is not supported in this browser. Tap the map instead.</span>');
        return;
      }
      var original = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Locating...';
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          btn.disabled = false;
          btn.innerHTML = original;
          if (self._setLocation(pos.coords.latitude, pos.coords.longitude, 'gps')) {
            self._setHint('Location captured from your device. Tap the map to adjust or trace a boundary.');
            if (self.map) self.map.setView([self.lat, self.lng], 17);
          }
        },
        function (err) {
          btn.disabled = false;
          btn.innerHTML = original;
          var msg = 'Could not get your location. Tap the map to set it manually.';
          if (err && err.code === 1) msg = 'Location permission denied. Tap the map to set it manually.';
          else if (err && err.code === 2) msg = 'Location unavailable right now. Tap the map to set it manually.';
          self._setHint('<span style="color:#B26A00">' + esc(msg) + '</span>');
        },
        { enableHighAccuracy: true, timeout: 12000, maximumAge: 30000 }
      );
    },

    /* ------------------------------------------------------------------ */
    getValue: function () {
      return {
        latitude: this._hasLocation ? this.lat : null,
        longitude: this._hasLocation ? this.lng : null,
        boundary_coordinates: this.points.length >= 3 ? { points: this.points } : null
      };
    },

    setLocation: function (lat, lng, source) {
      return this._setLocation(lat, lng, source);
    },

    hasGeometry: function () {
      return this._hasLocation || this.points.length >= 3;
    },

    invalidate: function () {
      if (this.map) setTimeout(this.map.invalidateSize.bind(this.map), 120);
    },

    destroy: function () {
      this._destroyed = true;
      if (this.map) {
        this.map.remove();
        this.map = null;
      }
      this.dom = null;
      this.mapBox = null;
    }
  };

  FarmGeo.attach = function (container, opts) {
    var inst = new FarmGeo();
    return inst.attach(container, opts);
  };

  FarmGeo.toPoints = toPoints;
  FarmGeo.formatCoords = formatCoords;
  FarmGeo.TILE = { osm: OSM_URL, satellite: SAT_URL };

  global.FarmGeo = FarmGeo;
})(window);
