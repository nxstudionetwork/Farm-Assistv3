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

  /**
   * UI strings for the selector's own chrome.
   *
   * Crop *names* are multilingual through the API (`local_names`), keyed by a
   * language-independent crop id. The component's labels are translated here so
   * every page gets the same wording; callers can override any of it.
   */
  var STRINGS = {
    en: {
      placeholder: 'Search a crop...',
      empty: 'No matching crop',
      searchLabel: 'Search crops',
      domainLabel: 'Filter by agricultural domain',
      categoryLabel: 'Filter by crop category',
      methodFilterLabel: 'Filter by cultivation method',
      cropLabel: 'Crop',
      methodLabel: 'Cultivation method',
      varietyLabel: 'Variety',
      allDomains: 'All domains',
      allCategories: 'All categories',
      anyMethod: 'Any cultivation',
      varietyOptional: 'Variety (optional)',
      addVariety: '+ Add another variety',
      addCrop: 'Add crop not listed',
      unavailable: 'Crop service unavailable.',
      loading: 'Loading crop catalog...',
      noCrops: 'No crops available yet.',
      shownOne: '1 crop shown',
      shownMany: function (n) { return n + ' crops shown'; },
      available: function (n) { return n + ' crops available'; },
      emptyHint: function (empty) {
        return empty + '. Try a different search, or add the crop manually.';
      },
      season: 'season',
      climate: 'climate',
      soil: 'soil',
      water: 'water',
      stages: 'stages',
      days: 'days',
      varietyPrompt: 'Name of the variety you are growing',
      cropPrompt: 'Name of the crop',
      varietyFailed: 'Could not add that variety.',
      cropFailed: 'Could not add that crop.'
    },
    hi: {
      placeholder: 'फसल खोजें...',
      empty: 'कोई फसल नहीं मिली',
      searchLabel: 'फसल खोजें',
      domainLabel: 'कृषि क्षेत्र से छाँटें',
      categoryLabel: 'फसल श्रेणी से छाँटें',
      methodLabel: 'खेती विधि से छाँटें',
      cropLabel: 'फसल',
      methodFilterLabel: 'खेती विधि से छाँटें',
      varietyLabel: 'किस्म',
      allDomains: 'सभी क्षेत्र',
      allCategories: 'सभी श्रेणियाँ',
      anyMethod: 'कोई भी विधि',
      varietyOptional: 'किस्म (वैकल्पिक)',
      addVariety: '+ दूसरी किस्म जोड़ें',
      addCrop: 'सूची में नहीं है? जोड़ें',
      unavailable: 'फसल सेवा उपलब्ध नहीं है।',
      loading: 'फसल सूची लोड हो रही है...',
      noCrops: 'अभी कोई फसल उपलब्ध नहीं।',
      shownOne: '1 फसल दिख रही है',
      shownMany: function (n) { return n + ' फसलें दिख रही हैं'; },
      available: function (n) { return n + ' फसलें उपलब्ध'; },
      emptyHint: function (empty) {
        return empty + '. दूसरी खोज आज़माएँ, या फसल स्वयं जोड़ें।';
      },
      season: 'मौसम',
      climate: 'जलवायु',
      soil: 'मिट्टी',
      water: 'पानी',
      stages: 'अवस्थाएँ',
      days: 'दिन',
      varietyPrompt: 'आपकी किस्म का नाम',
      cropPrompt: 'फसल का नाम',
      varietyFailed: 'वह किस्म जोड़ी नहीं जा सकी।',
      cropFailed: 'वह फसल जोड़ी नहीं जा सकी।'
    },
    te: {
      placeholder: 'పంటను వెతకండి...',
      empty: 'సరిపోలిన పంట లేదు',
      searchLabel: 'పంటలను వెతకండి',
      domainLabel: 'వ్యవసాయ రంగం ద్వారా వడపోత',
      categoryLabel: 'పంట వర్గం ద్వారా వడపోత',
      methodFilterLabel: 'సాగు పద్ధతి ద్వారా వడపోత',
      cropLabel: 'పంట',
      methodLabel: 'సాగు పద్ధతి',
      varietyLabel: 'రకం',
      allDomains: 'అన్ని రంగాలు',
      allCategories: 'అన్ని వర్గాలు',
      anyMethod: 'ఏదైనా పద్ధతి',
      varietyOptional: 'రకం (ఐచ్ఛికం)',
      addVariety: '+ మరో రకం జోడించండి',
      addCrop: 'జాబితాలో లేదు - జోడించండి',
      unavailable: 'పంట సేవ అందుబాటులో లేదు.',
      loading: 'పంట జాబితా లోడ్ అవుతోంది...',
      noCrops: 'ఇంకా పంటలు అందుబాటులో లేవు.',
      shownOne: '1 పంట కనిపిస్తోంది',
      shownMany: function (n) { return n + ' పంటలు కనిపిస్తున్నాయి'; },
      available: function (n) { return n + ' పంటలు అందుబాటులో'; },
      emptyHint: function (empty) {
        return empty + '. వేరే అన్వేషణ ప్రయత్నించండి లేదా పంటను మానuallyగా జోడించండి.';
      },
      season: 'సీజన్',
      climate: 'వాతావరణం',
      soil: 'నేల',
      water: 'నీరు',
      stages: 'దశలు',
      days: 'రోజులు',
      varietyPrompt: 'మీరు పెంచుతున్న రకం పేరు',
      cropPrompt: 'పంట పేరు',
      varietyFailed: 'ఆ రకం జోడించలేకపోయాము.',
      cropFailed: 'ఆ పంట జోడించలేకపోయాము.'
    }
  };

  /** Pick a string set for the active language, falling back to English. */
  function stringsFor(lang) {
    return STRINGS[lang] || STRINGS.en;
  }

  /** Overlay caller-supplied labels on the language's strings. */
  function mergeText(overrides) {
    var base = stringsFor(resolveLang(overrides && overrides.lang));
    if (!overrides || !overrides.text) return base;
    var merged = {};
    Object.keys(base).forEach(function (key) { merged[key] = base[key]; });
    Object.keys(overrides.text).forEach(function (key) { merged[key] = overrides.text[key]; });
    return merged;
  }

  /** Read a string that may be a plain value or a function. */
  function t(text, key, arg) {
    var value = text[key];
    return typeof value === 'function' ? value(arg) : value;
  }

  /**
   * Active UI language.
   *
   * The farmer's own preference wins: `UserStore.getCurrentUser().preferred_language`
   * is the only place the choice is actually written (signup, settings). The
   * `<html lang>` attribute is only a last resort, because it is almost always
   * set to a truthy value such as "en" and would otherwise always win.
   */
  function resolveLang(explicit) {
    if (explicit) return explicit;
    var store = global.UserStore;
    if (store && typeof store.getCurrentUser === 'function') {
      try {
        var user = store.getCurrentUser();
        if (user && user.preferred_language) return user.preferred_language;
      } catch (err) { /* storage unavailable */ }
    }
    try {
      var stored = global.localStorage && localStorage.getItem('fa-language');
      if (stored) return stored;
    } catch (err) { /* storage unavailable */ }
    var docLang = document.documentElement && document.documentElement.lang;
    return docLang || 'en';
  }

  function CropSelector(options) {
    options = options || {};
    this.lang = resolveLang(options.lang);
    this.onChange = options.onChange || function () {};
    this.allowCustom = options.allowCustom !== false;
    this.required = options.required === true;
    this.text = mergeText(options.text);
    this.placeholder = this.text.placeholder;
    this.emptyText = this.text.empty;

    this.crops = [];
    this.methods = [];
    this.domains = [];
    this.categories = [];
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

    var text = this.text;

    var search = el('div', 'crop-selector__search');
    this.searchInput = el('input', 'crop-selector__input');
    this.searchInput.type = 'search';
    this.searchInput.placeholder = this.placeholder;
    this.searchInput.setAttribute('aria-label', text.searchLabel);
    this.searchInput.addEventListener('input', function () {
      self._filters.q = self.searchInput.value || '';
      self._renderCropOptions();
    });
    search.appendChild(this.searchInput);

    var filters = el('div', 'crop-selector__filters');

    this.domainSelect = el('select', 'crop-selector__select');
    this.domainSelect.setAttribute('aria-label', text.domainLabel);
    this.domainSelect.addEventListener('change', function () {
      self._filters.domain = self.domainSelect.value;
      self._filters.category_code = '';
      self.categorySelect.value = '';
      self._renderCategoryOptions();
      self._renderCropOptions();
    });
    filters.appendChild(this.domainSelect);

    this.categorySelect = el('select', 'crop-selector__select');
    this.categorySelect.setAttribute('aria-label', text.categoryLabel);
    this.categorySelect.addEventListener('change', function () {
      self._filters.category_code = self.categorySelect.value;
      self._renderCropOptions();
    });
    filters.appendChild(this.categorySelect);

    this.methodSelect = el('select', 'crop-selector__select');
    this.methodSelect.setAttribute('aria-label', text.methodFilterLabel);
    this.methodSelect.addEventListener('change', function () {
      self._filters.cultivation_method = self.methodSelect.value;
      self._renderCropOptions();
    });
    filters.appendChild(this.methodSelect);

    var row = el('div', 'crop-selector__row');
    this.cropSelect = el('select', 'crop-selector__select crop-selector__select--crop');
    this.cropSelect.setAttribute('aria-label', text.cropLabel);
    if (this.required) this.cropSelect.required = true;
    this.cropSelect.addEventListener('change', function () {
      self._onCropChange();
    });
    row.appendChild(this.cropSelect);

    var methodRow = el('div', 'crop-selector__row');
    this.methodField = el('select', 'crop-selector__select');
    this.methodField.setAttribute('aria-label', text.methodLabel);
    this.methodField.addEventListener('change', function () {
      self._emit();
    });
    methodRow.appendChild(this.methodField);

    this.varietySelect = el('select', 'crop-selector__select');
    this.varietySelect.setAttribute('aria-label', text.varietyLabel);
    this.varietySelect.addEventListener('change', function () {
      if (this.value === '__new__') {
        var typed = global.prompt
          ? global.prompt(text.varietyPrompt)
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
    custom.textContent = text.addCrop;
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
      this._setStatus(this.text.unavailable);
      return Promise.resolve();
    }
    this._setStatus(this.text.loading);
    return Promise.all([
      api.listCrops({ page_size: 500 }).catch(function () { return []; }),
      api.listCultivationMethods().catch(function () { return []; }),
      api.categoryTree({}).catch(function () { return { categories: [], domains: [] }; })
    ]).then(function (results) {
      var tree = results[2] || {};
      self.crops = results[0] || [];
      self.methods = results[1] || [];
      self.domains = tree.domains || [];
      // Flat category list, used to expand a parent node into its children.
      self.categories = (self.domains.reduce(function (acc, d) {
        return acc.concat(d.categories || []);
      }, [])).concat(tree.categories || []);
      self._renderDomainOptions();
      self._renderCategoryOptions();
      self._renderMethodFilter();
      self._renderCropOptions();
      self._renderMethodField();
      self._setStatus(self.crops.length
        ? t(self.text, 'available', self.crops.length)
        : self.text.noCrops);
      return self;
    });
  };

  CropSelector.prototype._renderDomainOptions = function () {
    var select = this.domainSelect;
    clear(select);
    select.appendChild(new Option(this.text.allDomains, ''));
    (this.domains || []).forEach(function (d) {
      select.appendChild(new Option(d.domain + ' (' + (d.crop_count || 0) + ')', d.domain));
    });
  };

  CropSelector.prototype._renderCategoryOptions = function () {
    var select = this.categorySelect;
    clear(select);
    select.appendChild(new Option(this.text.allCategories, ''));
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
    select.appendChild(new Option(this.text.anyMethod, ''));
    (this.methods || []).forEach(function (m) {
      select.appendChild(new Option(m.name, m.code));
    });
  };

  /**
   * Category codes that satisfy the selected filter.
   *
   * Selecting a parent node such as `horticulture.vegetables` must include the
   * crops filed under its subcategories, exactly as the API's `category_code`
   * filter does. Comparing only `crop.category_code` matched nothing and hid
   * whole categories from the UI.
   */
  CropSelector.prototype._categoryScope = function () {
    var wanted = this._filters.category_code;
    if (!wanted) return null;

    var node = (this.categories || []).filter(function (c) {
      return c.code === wanted;
    })[0];
    // An explicit leaf node matches only itself.
    if (!node || node.subcategory) return [wanted];

    // A parent node also matches its subcategories' crops, as the API does.
    var children = (this.categories || []).filter(function (c) {
      return c.domain === node.domain && c.category === node.category;
    }).map(function (c) { return c.code; });
    return [wanted].concat(children);
  };

  CropSelector.prototype._matches = function (crop) {
    var f = this._filters;
    if (f.domain && crop.domain !== f.domain) return false;
    if (f.cultivation_method) {
      var supported = crop.suitable_cultivation_methods || [];
      if (supported.indexOf(f.cultivation_method) === -1) return false;
    }
    var scope = this._categoryScope();
    if (scope && scope.indexOf(crop.category_code) === -1) return false;
    if (f.q) {
      var needle = f.q.trim().toLowerCase();
      if (!needle) return true;
      var haystack = [
          crop.name,
          crop.scientific_name,
          crop.crop_id,
          crop.domain,
          crop.category,
          crop.subcategory,
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
      this._setStatus(t(this.text, 'emptyHint', this.emptyText));
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
    this._setStatus(matching.length === 1
      ? this.text.shownOne
      : t(this.text, 'shownMany', matching.length));
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
    select.appendChild(new Option(this.text.methodLabel, ''));
    this._supportedMethods().forEach(function (m) {
      select.appendChild(new Option(m.name, m.code));
    });
    if (previous) select.value = previous;
  };

  CropSelector.prototype._renderVarietyField = function () {
    var select = this.varietySelect;
    clear(select);
    select.appendChild(new Option(this.text.varietyOptional, ''));
    this.varieties.forEach(function (v) {
      // A variety's local_name is free text in a single language, so it is not
      // safe to substitute for the canonical name. The language-independent
      // `name` stays the label and `local_name` is shown alongside it when set.
      var text_ = v.name;
      if (v.local_name && v.local_name !== v.name) {
        text_ = v.name + ' · ' + v.local_name;
      }
      select.appendChild(new Option(text_, v.id));
    });
    if (this.allowCustom) select.appendChild(new Option(this.text.addVariety, '__new__'));

    // A variety requested by select() may only now exist in the list.
    var pending = this._pendingVarietyId;
    if (pending) {
      this._pendingVarietyId = null;
      if (select.querySelector('option[value="' + pending + '"]')) {
        select.value = pending;
        this._emit();
      }
    }
  };

  CropSelector.prototype._onCropChange = function () {
    var id = this.cropSelect.value;
    this.selected = null;
    this.varieties = [];
    this._pendingVarietyId = null;
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
    var text = this.text;
    var parts = [];
    if (crop.life_cycle_type) parts.push(crop.life_cycle_type);
    if (crop.suitable_seasons) parts.push(text.season + ': ' + crop.suitable_seasons);
    if (crop.suitable_climate) parts.push(text.climate + ': ' + crop.suitable_climate);
    if (crop.suitable_soil_types) parts.push(text.soil + ': ' + crop.suitable_soil_types);
    if (crop.water_requirement) parts.push(text.water + ': ' + crop.water_requirement);
    if (crop.growth_duration_days) parts.push(crop.growth_duration_days + ' ' + text.days);
    var stages = crop.lifecycle_stages || [];
    if (stages.length) parts.push(text.stages + ': ' + stages.join(' → '));
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
      self._setStatus((err && err.detail) || self.text.varietyFailed);
    });
  };

  CropSelector.prototype._addCustomCrop = function () {
    if (!api) return;
    var name = global.prompt ? global.prompt(this.text.cropPrompt) : null;
    if (!name || !name.trim()) return;
    var self = this;
    api.createCrop({ name: name.trim() }).then(function (crop) {
      self.crops = self.crops.concat([crop]);
      self._renderCropOptions();
      self.cropSelect.value = crop.id;
      self._onCropChange();
    }).catch(function (err) {
      self._setStatus((err && err.detail) || self.text.cropFailed);
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
    // Varieties arrive asynchronously, so remember the request and apply it
    // once the crop's list has rendered. `varietyId` used to be dropped
    // entirely whenever no `methodCode` was passed, because `self` was only
    // assigned inside the `if (methodCode)` branch.
    this.cropSelect.value = cropId;
    this._onCropChange();
    this._pendingVarietyId = varietyId || null;
    if (methodCode) this.methodField.value = methodCode;
    this._emit();
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
