/**
 * Shared, searchable crop selector.
 *
 * One component for every "add a crop" surface (My Farm, onboarding, crop
 * health, hydroponics, marketplace) so the crop list is never hardcoded in a
 * page. All data comes from the API: crops, the taxonomy tree, cultivation
 * methods and the varieties of whichever crop is selected.
 *
 * Usage
 * -----
 *   CropSelector.mount({
 *     mount: '#cropField',          // container element or selector
 *     onChange: function (crop, variety, method) { ... }
 *   });
 *
 * It renders:
 *   - a search box that matches name, scientific name and local names
 *   - a domain / category filter
 *   - a cultivation-method filter (only crops that support it are shown)
 *   - a crop dropdown grouped by domain
 *   - a variety dropdown, populated per crop, with an "add your own" option
 *   - a cultivation method dropdown, limited to the crop's supported methods
 *
 * The component is a plain global (window.CropSelector) so pages can use it
 * without a build step, matching the rest of the app's frontend.
 */
(function (global) {
  'use strict';

  var api = global.API && global.API.Crop;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function clear(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  /** Localised name for the active language, falling back to English. */
  function displayName(crop, lang) {
    if (!crop) return '';
    var names = crop.local_names || {};
    if (lang && names[lang]) return names[lang];
    return crop.name || '';
  }

  function label(crop, lang) {
    var name = displayName(crop, lang);
    if (crop.scientific_name) return name + ' (' + crop.scientific_name + ')';
    return name;
  }

  function CropSelector(options) {
    options = options || {};
    this.lang = options.lang ||
      (document.documentElement && document.documentElement.lang) ||
      (global.localStorage && localStorage.getItem('fa-language')) || 'en';
    this.onChange = options.onChange || function () {};
    this.allowCustom = options.allowCustom !== false;
    this.required = options.required === true;
    this.placeholder = options.placeholder || 'Search a crop...';
    this.emptyText = options.emptyText || 'No matching crop';

    this.crops = [];
    this.methods = [];
    this.selected = null;
    this.varieties = [];

    this._filters = {
      q: '',
      domain: '',
      category_code: '',
      cultivation_method: ''
    };

    this.root = el('div', 'crop-selector');
    this._build();
    this.load();
  }

  CropSelector.prototype._build = function () {
    var self = this;

    var search = el('div', 'crop-selector__search');
    this.searchInput = el('input', 'crop-selector__input');
    this.searchInput.type = 'search';
    this.searchInput.placeholder = this.placeholder;
    this.searchInput.setAttribute('aria-label', this.placeholder);
    this.searchInput.addEventListener('input', function () {
      self._filters.q = self.searchInput.value || '';
      self._renderCropOptions();
    });
    search.appendChild(this.searchInput);

    var filters = el('div', 'crop-selector__filters');

    this.domainSelect = el('select', 'crop-selector__select');
    this.domainSelect.setAttribute('aria-label', 'Filter by agricultural domain');
    this.domainSelect.addEventListener('change', function () {
      self._filters.domain = self.domainSelect.value;
      self._filters.category_code = '';
      self.categorySelect.value = '';
      self._renderCategoryOptions();
      self._renderCropOptions();
    });
    filters.appendChild(this.domainSelect);

    this.categorySelect = el('select', 'crop-selector__select');
    this.categorySelect.setAttribute('aria-label', 'Filter by crop category');
    this.categorySelect.addEventListener('change', function () {
      self._filters.category_code = self.categorySelect.value;
      self._renderCropOptions();
    });
    filters.appendChild(this.categorySelect);

    this.methodSelect = el('select', 'crop-selector__select');
    this.methodSelect.setAttribute('aria-label', 'Filter by cultivation method');
    this.methodSelect.addEventListener('change', function () {
      self._filters.cultivation_method = self.methodSelect.value;
      self._renderCropOptions();
    });
    filters.appendChild(this.methodSelect);

    var row = el('div', 'crop-selector__row');
    this.cropSelect = el('select', 'crop-selector__select crop-selector__select--crop');
    this.cropSelect.setAttribute('aria-label', 'Crop');
    if (this.required) this.cropSelect.required = true;
    this.cropSelect.addEventListener('change', function () {
      self._onCropChange();
    });
    row.appendChild(this.cropSelect);

    var methodRow = el('div', 'crop-selector__row');
    this.methodField = el('select', 'crop-selector__select');
    this.methodField.setAttribute('aria-label', 'Cultivation method');
    this.methodField.addEventListener('change', function () {
      self._emit();
    });
    methodRow.appendChild(this.methodField);

    this.varietySelect = el('select', 'crop-selector__select');
    this.varietySelect.setAttribute('aria-label', 'Variety');
    this.varietySelect.addEventListener('change', function () {
      if (this.value === '__new__') {
        var typed = global.prompt
          ? global.prompt('Name of the variety you are growing')
          : null;
        this.value = '';
        if (typed && typed.trim()) {
          this._addCustomVariety(typed.trim());
          return;
        }
      }
      self._emit();
    });
    methodRow.appendChild(this.varietySelect);

    var custom = el('button', 'btn btn--ghost crop-selector__custom');
    custom.type = 'button';
    custom.textContent = 'Add crop not listed';
    custom.addEventListener('click', function () {
      self._addCustomCrop();
    });

    this.hint = el('p', 'crop-selector__hint');
    this.status = el('p', 'crop-selector__status');
    this.status.setAttribute('role', 'status');

    this.root.appendChild(search);
    this.root.appendChild(filters);
    this.root.appendChild(row);
    this.root.appendChild(methodRow);
    if (this.allowCustom) this.root.appendChild(custom);
    this.root.appendChild(this.hint);
    this.root.appendChild(this.status);
  };

  CropSelector.prototype._setStatus = function (message) {
    this.status.textContent = message || '';
  };

  CropSelector.prototype.load = function () {
    var self = this;
    if (!api) {
      this._setStatus('Crop service unavailable.');
      return Promise.resolve();
    }
    this._setStatus('Loading crop catalog...');
    return Promise.all([
      api.listCrops({ page_size: 500 }).catch(function () { return []; }),
      api.listCultivationMethods().catch(function () { return []; }),
      api.categoryTree({}).catch(function () { return { domains: [] }; })
    ]).then(function (results) {
      self.crops = results[0] || [];
      self.methods = results[1] || [];
      self.domains = (results[2] && results[2].domains) || [];
      self._renderDomainOptions();
      self._renderCategoryOptions();
      self._renderMethodFilter();
      self._renderCropOptions();
      self._renderMethodField();
      self._setStatus(self.crops.length
        ? self.crops.length + ' crops available'
        : 'No crops available yet.');
      return self;
    });
  };

  CropSelector.prototype._renderDomainOptions = function () {
    var select = this.domainSelect;
    clear(select);
    select.appendChild(new Option('All domains', ''));
    (this.domains || []).forEach(function (d) {
      select.appendChild(new Option(d.domain + ' (' + (d.crop_count || 0) + ')', d.domain));
    });
  };

  CropSelector.prototype._renderCategoryOptions = function () {
    var select = this.categorySelect;
    clear(select);
    select.appendChild(new Option('All categories', ''));
    var domain = this.domainSelect.value;
    (this.domains || []).forEach(function (d) {
      if (domain && d.domain !== domain) return;
      (d.categories || []).forEach(function (c) {
        if (!c.crop_count && !c.subcategory) return;
        select.appendChild(new Option(c.display_name + ' (' + c.crop_count + ')', c.code));
      });
    });
  };

  CropSelector.prototype._renderMethodFilter = function () {
    var select = this.methodSelect;
    clear(select);
    select.appendChild(new Option('Any cultivation', ''));
    (this.methods || []).forEach(function (m) {
      select.appendChild(new Option(m.name, m.code));
    });
  };

  CropSelector.prototype._matches = function (crop) {
    var f = this._filters;
    if (f.domain && crop.domain !== f.domain) return false;
    if (f.cultivation_method) {
      var supported = crop.suitable_cultivation_methods || [];
      if (supported.indexOf(f.cultivation_method) === -1) return false;
    }
    if (f.category_code && crop.category_code !== f.category_code) return false;
    if (f.q) {
      var needle = f.q.trim().toLowerCase();
      if (!needle) return true;
      var haystack = [
        crop.name,
        crop.scientific_name,
        crop.crop_id,
        crop.market_type,
        crop.variety
      ].concat(Object.keys(crop.local_names || {}).map(function (k) {
        return crop.local_names[k];
      })).join(' ').toLowerCase();
      return haystack.indexOf(needle) !== -1;
    }
    return true;
  };

  CropSelector.prototype._renderCropOptions = function () {
    var select = this.cropSelect;
    var previous = select.value;
    clear(select);

    var matching = this.crops.filter(this._matches.bind(this));
    if (!matching.length) {
      select.appendChild(new Option(this.emptyText, ''));
      select.disabled = true;
      this._setStatus(this.emptyText + '. Try a different search, or add the crop manually.');
      return;
    }
    select.disabled = false;

    var byDomain = {};
    matching.forEach(function (crop) {
      var key = crop.domain || 'Other';
      (byDomain[key] = byDomain[key] || []).push(crop);
    });

    Object.keys(byDomain).sort().forEach(function (domain) {
      var group = document.createElement('optgroup');
      group.label = domain + ' (' + byDomain[domain].length + ')';
      byDomain[domain]
        .slice()
        .sort(function (a, b) { return (a.name || '').localeCompare(b.name || ''); })
        .forEach(function (crop) {
          var option = new Option(label(crop, this.lang), crop.id);
          option.dataset.cropRef = crop.id;
          group.appendChild(option);
        }, this);
      select.appendChild(group);
    }, this);

    if (previous && matching.some(function (c) { return c.id === previous; })) {
      select.value = previous;
    }
    this._setStatus(matching.length + ' crop' + (matching.length === 1 ? '' : 's') + ' shown');
  };

  CropSelector.prototype._supportedMethods = function () {
    var crop = this.selected;
    if (!crop) return this.methods || [];
    var supported = crop.suitable_cultivation_methods || [];
    if (!supported.length) return this.methods || [];
    return (this.methods || []).filter(function (m) {
      return supported.indexOf(m.code) !== -1;
    });
  };

  CropSelector.prototype._renderMethodField = function () {
    var select = this.methodField;
    var previous = select.value;
    clear(select);
    select.appendChild(new Option('Cultivation method', ''));
    this._supportedMethods().forEach(function (m) {
      select.appendChild(new Option(m.name, m.code));
    });
    if (previous) select.value = previous;
  };

  CropSelector.prototype._renderVarietyField = function () {
    var select = this.varietySelect;
    clear(select);
    select.appendChild(new Option('Variety (optional)', ''));
    this.varieties.forEach(function (v) {
      select.appendChild(new Option(v.name, v.id));
    });
    if (this.allowCustom) select.appendChild(new Option('＋ Add another variety', '__new__'));
  };

  CropSelector.prototype._onCropChange = function () {
    var id = this.cropSelect.value;
    this.selected = null;
    this.varieties = [];
    if (!id) {
      this._renderVarietyField();
      this._renderMethodField();
      this.hint.textContent = '';
      this._emit();
      return;
    }
    var crop = this.crops.filter(function (c) { return c.id === id; })[0];
    this.selected = crop || null;
    this._renderMethodField();
    this._renderHint();

    if (crop && api) {
      var self = this;
      api.listVarieties({ crop_id: id }).then(function (rows) {
        if (!self.selected || self.selected.id !== id) return;
        self.varieties = rows || [];
        self._renderVarietyField();
      }).catch(function () {
        self.varieties = [];
        self._renderVarietyField();
      });
    } else {
      this._renderVarietyField();
    }
    this._emit();
  };

  CropSelector.prototype._renderHint = function () {
    var crop = this.selected;
    if (!crop) {
      this.hint.textContent = '';
      return;
    }
    var parts = [];
    if (crop.life_cycle_type) parts.push(crop.life_cycle_type);
    if (crop.suitable_seasons) parts.push('season: ' + crop.suitable_seasons);
    if (crop.suitable_climate) parts.push('climate: ' + crop.suitable_climate);
    if (crop.suitable_soil_types) parts.push('soil: ' + crop.suitable_soil_types);
    if (crop.water_requirement) parts.push('water: ' + crop.water_requirement);
    if (crop.growth_duration_days) parts.push(crop.growth_duration_days + ' days');
    var stages = crop.lifecycle_stages || [];
    if (stages.length) parts.push('stages: ' + stages.join(' → '));
    this.hint.textContent = parts.join(' · ');
  };

  CropSelector.prototype._addCustomVariety = function (name) {
    var crop = this.selected;
    if (!crop || !api) return;
    var self = this;
    api.createVariety({ crop_id: crop.id, name: name }).then(function (variety) {
      self.varieties = self.varieties.concat([variety]);
      self._renderVarietyField();
      self.varietySelect.value = variety.id;
      self._emit();
    }).catch(function (err) {
      self._setStatus((err && err.detail) || 'Could not add that variety.');
    });
  };

  CropSelector.prototype._addCustomCrop = function () {
    if (!api) return;
    var name = global.prompt ? global.prompt('Name of the crop') : null;
    if (!name || !name.trim()) return;
    var self = this;
    api.createCrop({ name: name.trim() }).then(function (crop) {
      self.crops = self.crops.concat([crop]);
      self._renderCropOptions();
      self.cropSelect.value = crop.id;
      self._onCropChange();
    }).catch(function (err) {
      self._setStatus((err && err.detail) || 'Could not add that crop.');
    });
  };

  CropSelector.prototype._emit = function () {
    var varietyId = this.varietySelect.value;
    var variety = this.varieties.filter(function (v) {
      return v.id === varietyId;
    })[0] || null;
    this.onChange(this.selected, variety, this.methodField.value || null, this);
  };

  CropSelector.prototype.value = function () {
    var varietyId = this.varietySelect.value;
    var variety = this.varieties.filter(function (v) {
      return v.id === varietyId;
    })[0] || null;
    return {
      crop: this.selected,
      crop_id: this.selected ? this.selected.id : null,
      crop_name: this.selected ? this.selected.name : null,
      variety: variety,
      variety_id: variety ? variety.id : null,
      variety_name: variety ? variety.name : null,
      cultivation_method: this.methodField.value || null
    };
  };

  /** Pre-select a crop, e.g. when editing an existing cycle. */
  CropSelector.prototype.select = function (cropId, varietyId, methodCode) {
    if (!cropId) return;
    if (!this.cropSelect.querySelector('option[value="' + cropId + '"]')) {
      // The crop may be outside the current filter, so make sure it is listed.
      this._filters.q = '';
      this._filters.domain = '';
      this._filters.category_code = '';
      this._filters.cultivation_method = '';
      this.domainSelect.value = '';
      this.categorySelect.value = '';
      this.methodSelect.value = '';
      this._renderCategoryOptions();
      this._renderCropOptions();
    }
    this.cropSelect.value = cropId;
    this._onCropChange();
    if (methodCode) {
      var self = this;
      global.setTimeout(function () { self.methodField.value = methodCode; }, 0);
    }
    if (varietyId) {
      var apply = function () { self.varietySelect.value = varietyId; };
      global.setTimeout(apply, 0);
    }
  };

  global.CropSelector = {
    create: function (options) { return new CropSelector(options); },
    mount: function (options) {
      var target = typeof options.mount === 'string'
        ? document.querySelector(options.mount)
        : options.mount;
      if (!target) return null;
      var selector = new CropSelector(options);
      clear(target);
      target.appendChild(selector.root);
      return selector;
    }
  };
})(window);
