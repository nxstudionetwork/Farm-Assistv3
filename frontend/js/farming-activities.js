/**
 * Farming activities offered during onboarding and in "My Farm" > profile.
 *
 * One shared list for signup.html and profile.html so the two surfaces can
 * never drift. The `values` are what gets stored on the farmer profile
 * (`farming_activities`), so the original entries are kept verbatim: existing
 * accounts keep matching on signup, in profile and in any report that groups
 * by activity. New entries are appended, never renamed.
 *
 * The list covers the breadth of agriculture the crop catalog supports, so a
 * farmer can describe what they run without a custom free-text box: field crops,
 * every horticultural branch, the soilless and protected segments, plantation
 * and agroforestry, floriculture, nursery, and the allied livestock, poultry,
 * fisheries and apiculture segments.
 *
 * Usage:
 *   FarmingActivities.all()                 // [{value, label, group}]
 *   FarmingActivities.render(container, {className, selected, onChange})
 */
(function (global) {
  'use strict';

  /** Activities grouped for display only; order is the display order. */
  var GROUPS = [
    {
      key: 'field',
      label: 'Field Crops',
      activities: [
        'Crop Farming',
        'Organic Farming',
        'Fodder Crops'
      ]
    },
    {
      key: 'horticulture',
      label: 'Horticulture',
      activities: [
        'Horticulture',
        'Vegetables',
        'Fruits',
        'Grapes / Viticulture',
        'Flowers & Floriculture',
        'Spices',
        'Medicinal Plants',
        'Aromatic Plants',
        'Nursery & Seedlings',
        'Ornamental Plants'
      ]
    },
    {
      key: 'protected',
      label: 'Protected Cultivation',
      activities: [
        'Hydroponics',
        'Protected Cultivation',
        'Vertical Farming',
        'Polyhouse Farming'
      ]
    },
    {
      key: 'plantation',
      label: 'Plantation & Forestry',
      activities: [
        'Plantation Crops',
        'Coconut & Oil Palm',
        'Agroforestry',
        'Sericulture'
      ]
    },
    {
      key: 'allied',
      label: 'Allied Agriculture',
      activities: [
        'Dairy',
        'Poultry',
        'Fishery',
        'Beekeeping',
        'Goat & Livestock Rearing'
      ]
    }
  ];

  /** Flat value list, in display order, with no duplicates. */
  var ALL = (function () {
    var seen = {};
    var out = [];
    GROUPS.forEach(function (group) {
      group.activities.forEach(function (value) {
        if (seen[value]) return;
        seen[value] = true;
        out.push(value);
      });
    });
    return out;
  })();

  var GROUP_BY_VALUE = (function () {
    var map = {};
    GROUPS.forEach(function (group) {
      group.activities.forEach(function (value) { map[value] = group; });
    });
    return map;
  })();

  /**
   * Add a chip for a stored value that is not in the current list.
   *
   * Profiles saved before an activity was added, or under a value that has since
   * been retired, must still show as selected instead of silently disappearing
   * from the farmer's profile.
   */
  function ensureValueChip(container, value, className) {
    if (!value) return null;
    var existing = container.querySelector(
      '[data-value="' + String(value).replace(/"/g, '\\"') + '"]'
    );
    if (existing) return existing;

    var chip = document.createElement('button');
    chip.type = 'button';
    chip.className = className;
    chip.setAttribute('data-value', value);
    chip.textContent = value;
    chip.classList.add('active');
    container.appendChild(chip);
    return chip;
  }

  var FarmingActivities = {
    GROUPS: GROUPS,

    /** Every activity value, in display order. */
    all: function () { return ALL.slice(); },

    /** Group a value belongs to, or null when it is a retired/custom value. */
    groupOf: function (value) { return GROUP_BY_VALUE[value] || null; },

    /**
     * Render the chips into a container.
     *
     * @param {HTMLElement|string} container element or selector
     * @param {Object} [options]
     *   className  chip class to apply (page specific)
     *   selected   array of values to mark active
     *   onChange   called with the selected array after every toggle
     */
    render: function (container, options) {
      var target = typeof container === 'string'
        ? document.querySelector(container)
        : container;
      if (!target) return null;

      options = options || {};
      var chipClass = options.className || 'chip';
      var selected = (options.selected || []).map(function (v) {
        return String(v).trim();
      });

      // Grouped rendering with headings, so a long list stays readable.
      GROUPS.forEach(function (group) {
        var wrap = document.createElement('div');
        wrap.className = 'farming-activity-group';
        wrap.setAttribute('data-group', group.key);

        var heading = document.createElement('p');
        heading.className = 'farming-activity-group__label';
        heading.textContent = group.label;
        wrap.appendChild(heading);

        var chips = document.createElement('div');
        chips.className = 'farming-activity-group__chips';
        group.activities.forEach(function (value) {
          var chip = document.createElement('button');
          chip.type = 'button';
          chip.className = chipClass;
          chip.setAttribute('data-value', value);
          chip.textContent = value;
          if (selected.indexOf(value) !== -1) chip.classList.add('active');
          chips.appendChild(chip);
        });
        wrap.appendChild(chips);
        target.appendChild(wrap);
      });

      // Never drop a value the farmer already has on file.
      selected.forEach(function (value) {
        if (ALL.indexOf(value) === -1) ensureValueChip(target, value, chipClass);
      });

      if (typeof options.onChange === 'function') {
        target.addEventListener('click', function (event) {
          var chip = event.target.closest('.' + chipClass);
          if (!chip || !target.contains(chip)) return;
          chip.classList.toggle('active');
          options.onChange(FarmingActivities.selected(target, '.' + chipClass));
        });
      }

      return target;
    },

    /** Values currently active inside a container. */
    selected: function (container, selector) {
      var target = typeof container === 'string'
        ? document.querySelector(container)
        : container;
      if (!target) return [];
      var chipSelector = selector || '.chip.active, .pf-chip.active';
      return Array.prototype.slice
        .call(target.querySelectorAll(chipSelector))
        .map(function (chip) { return chip.getAttribute('data-value'); })
        .filter(Boolean);
    },

    /** Mark the given values active inside a container. */
    setSelected: function (container, values, selector) {
      var target = typeof container === 'string'
        ? document.querySelector(container)
        : container;
      if (!target) return;
      var wanted = (values || []).map(function (v) { return String(v).trim(); });
      var chipSelector = selector || '.chip, .pf-chip';
      Array.prototype.slice.call(target.querySelectorAll(chipSelector)).forEach(function (chip) {
        var value = chip.getAttribute('data-value');
        chip.classList.toggle('active', wanted.indexOf(value) !== -1);
        if (wanted.indexOf(value) === -1 && ALL.indexOf(value) === -1) {
          chip.remove();
        }
      });
      // A stored value that is no longer in the list still needs to show.
      wanted.forEach(function (value) {
        if (ALL.indexOf(value) === -1) ensureValueChip(target, value, chipClassFor(target));
      });
    }
  };

  function chipClassFor(container) {
    var chip = container.querySelector('.pf-chip') || container.querySelector('.chip');
    return chip ? chip.className : 'chip';
  }

  global.FarmingActivities = FarmingActivities;
})(window);
