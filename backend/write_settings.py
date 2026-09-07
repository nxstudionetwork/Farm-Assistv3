# -*- coding: utf-8 -*-
"""Regenerates frontend/settings.html by injecting new sub-pages, phone OTP
change modal, dynamic category rendering and supporting CSS/JS."""
import io
import os

TARGET = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'frontend', 'settings.html'))

# ---------------------------------------------------------------- CSS ADDONS
CSS_ADDON = r"""
    /* Verified badge */
    .verified-badge { display: inline-flex; align-items: center; gap: 4px; font-size: 10px; font-weight: 600; color: #1B5E3F; background: var(--soft-green); padding: 2px 8px; border-radius: 10px; vertical-align: middle; margin-left: 6px; }

    /* Phone change / OTP modal */
    .modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,.45); z-index: 1000; display: none; align-items: center; justify-content: center; padding: 20px; }
    .modal-overlay.show { display: flex; }
    .modal-box { background: white; border-radius: 18px; padding: 24px 20px; max-width: 380px; width: 100%; max-height: 85vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,.22); animation: scaleIn 0.25s ease; }
    .phone-step { display: none; }
    .phone-step.active { display: block; animation: scaleIn 0.25s ease; }
    .phone-step h3 { font-size: 17px; font-weight: 700; margin: 0 0 8px; }
    .phone-step p { font-size: 13px; color: var(--text-secondary); margin: 0 0 14px; line-height: 1.5; }
    .phone-step .form-input { width: 100%; }
    .modal-actions { display: flex; gap: 10px; margin-top: 14px; }
    .modal-actions button { flex: 1; padding: 12px; border: none; border-radius: 12px; font-size: 14px; font-weight: 600; cursor: pointer; }
    .otp-inputs { display: flex; gap: 8px; justify-content: center; margin: 16px 0 4px; }
    .otp-input { width: 44px; height: 54px; text-align: center; font-size: 22px; font-weight: 700; border: 2px solid var(--border-medium); border-radius: 12px; outline: none; transition: border-color 0.2s, box-shadow 0.2s; background: white; }
    .otp-input:focus { border-color: var(--primary-green); box-shadow: 0 0 0 3px rgba(45,106,79,0.12); }
    .otp-countdown { text-align: center; font-size: 12px; color: var(--text-muted); margin-top: 14px; min-height: 18px; }
    .otp-resend-link { color: var(--primary-green); font-weight: 600; cursor: pointer; border: none; background: none; font-size: 12px; padding: 0; text-decoration: underline; }
    .otp-resend-link[disabled] { opacity: 0.5; cursor: not-allowed; text-decoration: none; }
    .action-icon-row { display: flex; align-items: center; gap: 14px; padding: 16px 20px; border-bottom: 1px solid var(--border-light); background: white; cursor: pointer; }
    .action-icon-row:last-child { border-bottom: none; }
    .action-icon-row:active { background: #f5f5f5; }
    .icon-green { background: #E8F5E9; color: #2D6A4F; }
"""

EMPTY_CATEGORIES = """<div class="settings-cat-list" id="settings-cat-list"></div>
  """

# ------------------------------------------- SUB-PAGES: FARM + AI (pre-sensors)
FARM_AI_PAGES = r"""  <!-- ===== SUB-PAGE: FARM SETTINGS ===== -->
  <div class="settings-sub-page" id="sub-farm">
    <div class="settings-sub-header">
      <button class="back-btn" onclick="navigateBack()"><i class="fas fa-arrow-left"></i></button>
      <h2>Farm Settings</h2>
    </div>
    <div class="settings-sub-body">
      <section class="card-premium" style="padding:0;">
        <div class="settings-section-title"><i class="fas fa-seedling"></i> My Farm Profile</div>
        <div class="settings-card-body">
          <div class="settings-field-group">
            <div class="settings-field-label">Default Crop</div>
            <select class="select-styled" id="farm-crop">
              <option value="">Select crop</option>
              <option value="wheat">Wheat</option>
              <option value="rice">Rice</option>
              <option value="maize">Maize</option>
              <option value="cotton">Cotton</option>
              <option value="sugarcane">Sugarcane</option>
              <option value="pulses">Pulses</option>
              <option value="vegetables">Vegetables</option>
            </select>
          </div>
          <div class="settings-field-group">
            <div class="settings-field-label">Land Size (acres)</div>
            <input class="form-input" type="number" id="farm-land" placeholder="e.g. 5" min="0" step="0.1">
          </div>
          <div class="settings-field-group">
            <div class="settings-field-label">Soil Type</div>
            <select class="select-styled" id="farm-soil">
              <option value="">Select soil type</option>
              <option value="black">Black</option>
              <option value="red">Red</option>
              <option value="alluvial">Alluvial</option>
              <option value="loamy">Loamy</option>
              <option value="sandy">Sandy</option>
              <option value="clay">Clay</option>
            </select>
          </div>
          <div class="settings-field-group">
            <div class="settings-field-label">Primary Irrigation Method</div>
            <select class="select-styled" id="farm-irrigation">
              <option value="">Select method</option>
              <option value="drip">Drip</option>
              <option value="sprinkler">Sprinkler</option>
              <option value="flood">Flood</option>
              <option value="rainfed">Rain-fed</option>
            </select>
          </div>
        </div>
      </section>
      <section class="card-premium" style="padding:0;">
        <div class="settings-action-row">
          <button class="btn-primary btn-sm" onclick="saveFarmSettings()"><i class="fas fa-save"></i> Save Farm Settings</button>
        </div>
      </section>
    </div>
  </div>

  <!-- ===== SUB-PAGE: AI ASSISTANT ===== -->
  <div class="settings-sub-page" id="sub-ai">
    <div class="settings-sub-header">
      <button class="back-btn" onclick="navigateBack()"><i class="fas fa-arrow-left"></i></button>
      <h2>AI Assistant</h2>
    </div>
    <div class="settings-sub-body">
      <section class="card-premium" style="padding:0;">
        <div class="settings-section-title"><i class="fas fa-brain"></i> AI Recommendations</div>
        <div class="settings-card-body">
          <div class="settings-row no-hover" style="cursor:default;">
            <div class="settings-row-left"><i class="fas fa-wand-magic-sparkles"></i><div><div class="settings-title">Smart Recommendations</div><div class="settings-subtitle">Get AI-powered crop & task suggestions</div></div></div>
            <label class="switch"><input type="checkbox" id="ai-recommendations" checked onchange="saveAiSetting('recommendations', this.checked)"><span class="slider"></span></label>
          </div>
          <div class="settings-row no-hover" style="cursor:default;">
            <div class="settings-row-left"><i class="fas fa-volume-high"></i><div><div class="settings-title">Voice Replies</div><div class="settings-subtitle">Assistant speaks its answers aloud</div></div></div>
            <label class="switch"><input type="checkbox" id="ai-voicereplies" checked onchange="saveAiSetting('voiceReplies', this.checked)"><span class="slider"></span></label>
          </div>
        </div>
      </section>
      <section class="card-premium" style="padding:0;">
        <div class="settings-section-title"><i class="fas fa-comments"></i> Advisory Style</div>
        <div class="settings-card-body">
          <div style="padding:12px 20px;">
            <div class="settings-field-label">Answer Detail Level</div>
            <select class="select-styled" id="ai-detail-select" onchange="saveAiDetail(this.value)">
              <option value="simple">Simple - short &amp; actionable</option>
              <option value="detailed">Detailed - full explanations</option>
            </select>
          </div>
        </div>
      </section>
      <section class="card-premium" style="padding:0;">
        <div class="settings-section-title"><i class="fas fa-database"></i> Data Usage</div>
        <div class="settings-card-body">
          <div class="permission-checkbox-row"><input type="checkbox" id="ai-training" checked onchange="saveAiSetting('training', this.checked)"><label for="ai-training">Improve AI accuracy using anonymized farm data</label></div>
        </div>
      </section>
    </div>
  </div>

"""

# ------------------------------- SUB-PAGE: ACTIONS + PHONE MODAL (pre-logout)
ACTIONS_PHONE_BLOCK = r"""  <!-- ===== SUB-PAGE: ACCOUNT ACTIONS ===== -->
  <div class="settings-sub-page" id="sub-actions">
    <div class="settings-sub-header">
      <button class="back-btn" onclick="navigateBack()"><i class="fas fa-arrow-left"></i></button>
      <h2>Account Actions</h2>
    </div>
    <div class="settings-sub-body">
      <section class="card-premium" style="padding:0;">
        <div class="settings-section-title"><i class="fas fa-bolt"></i> Quick Actions</div>
        <div class="settings-card-body">
          <div class="action-icon-row" onclick="syncNow()">
            <div class="connected-device-icon icon-blue"><i class="fas fa-rotate"></i></div>
            <div class="connected-device-info"><div class="connected-device-name">Sync Now</div><div class="connected-device-status">Refresh all offline data</div></div>
            <i class="fas fa-chevron-right settings-cat-chevron"></i>
          </div>
          <div class="action-icon-row" onclick="clearCache()">
            <div class="connected-device-icon icon-orange"><i class="fas fa-broom"></i></div>
            <div class="connected-device-info"><div class="connected-device-name">Clear Cache</div><div class="connected-device-status">Free up storage space</div></div>
            <i class="fas fa-chevron-right settings-cat-chevron"></i>
          </div>
          <div class="action-icon-row" onclick="exportData()">
            <div class="connected-device-icon icon-teal"><i class="fas fa-arrow-up-from-bracket"></i></div>
            <div class="connected-device-info"><div class="connected-device-name">Export My Data</div><div class="connected-device-status">Download a copy of your data</div></div>
            <i class="fas fa-chevron-right settings-cat-chevron"></i>
          </div>
          <div class="action-icon-row" onclick="logoutAllDevices()">
            <div class="connected-device-icon icon-purple"><i class="fas fa-mobile-screen"></i></div>
            <div class="connected-device-info"><div class="connected-device-name">Logout All Devices</div><div class="connected-device-status">End every other session</div></div>
            <i class="fas fa-chevron-right settings-cat-chevron"></i>
          </div>
        </div>
      </section>
      <section class="card-premium" style="padding:0;">
        <div class="settings-section-title danger-text"><i class="fas fa-triangle-exclamation"></i> Danger Zone</div>
        <div class="settings-card-body">
          <div class="action-icon-row" onclick="resetAllSettings()">
            <div class="connected-device-icon icon-gray"><i class="fas fa-arrows-rotate"></i></div>
            <div class="connected-device-info"><div class="connected-device-name">Reset All Settings</div><div class="connected-device-status">Restore default preferences</div></div>
            <i class="fas fa-chevron-right settings-cat-chevron"></i>
          </div>
          <div class="action-icon-row" onclick="handleLogout()">
            <div class="connected-device-icon" style="background:#FFEBEE;color:#D32F2F;"><i class="fas fa-right-from-bracket"></i></div>
            <div class="connected-device-info"><div class="connected-device-name danger-text">Logout</div><div class="connected-device-status">Sign out of Farm Assist</div></div>
            <i class="fas fa-chevron-right settings-cat-chevron"></i>
          </div>
        </div>
      </section>
    </div>
  </div>

  <!-- ===== PHONE CHANGE OTP MODAL (3 STEPS) ===== -->
  <div class="modal-overlay" id="phone-change-modal">
    <div class="modal-box">
      <!-- STEP 1: ENTER NUMBER -->
      <div class="phone-step active" id="pc-step-number">
        <h3><i class="fas fa-mobile-screen-button" style="color:var(--primary-green);"></i> Change Phone Number</h3>
        <p>We will send a 6-digit verification code to your new number.</p>
        <input class="form-input" type="tel" id="pc-new-phone" placeholder="+91 XXXXXXXXXX">
        <div class="modal-actions">
          <button style="background:#f0f0f0;color:var(--text-primary);" onclick="closePhoneChangeModal()">Cancel</button>
          <button style="background:var(--primary-green);color:white;" onclick="sendPhoneChangeOtp()">Send OTP</button>
        </div>
      </div>
      <!-- STEP 2: ENTER OTP -->
      <div class="phone-step" id="pc-step-otp">
        <h3><i class="fas fa-comment-sms" style="color:var(--primary-green);"></i> Verify OTP</h3>
        <p>Enter the 6-digit code sent to <strong id="pc-otp-phone-display">your number</strong>.</p>
        <div class="otp-inputs">
          <input class="otp-input" type="tel" maxlength="2" inputmode="numeric" autocomplete="one-time-code" oninput="onOtpEntry(this)" onkeydown="onOtpKey(event,this)">
          <input class="otp-input" type="tel" maxlength="2" inputmode="numeric" oninput="onOtpEntry(this)" onkeydown="onOtpKey(event,this)">
          <input class="otp-input" type="tel" maxlength="2" inputmode="numeric" oninput="onOtpEntry(this)" onkeydown="onOtpKey(event,this)">
          <input class="otp-input" type="tel" maxlength="2" inputmode="numeric" oninput="onOtpEntry(this)" onkeydown="onOtpKey(event,this)">
          <input class="otp-input" type="tel" maxlength="2" inputmode="numeric" oninput="onOtpEntry(this)" onkeydown="onOtpKey(event,this)">
          <input class="otp-input" type="tel" maxlength="2" inputmode="numeric" oninput="onOtpEntry(this)" onkeydown="onOtpKey(event,this)">
        </div>
        <div class="otp-countdown" id="pc-countdown"></div>
        <div class="modal-actions">
          <button style="background:#f0f0f0;color:var(--text-primary);" onclick="closePhoneChangeModal()">Cancel</button>
          <button style="background:var(--primary-green);color:white;" onclick="verifyPhoneChangeOtp()">Verify &amp; Update</button>
        </div>
        <div class="otp-countdown"><button class="otp-resend-link" id="pc-resend-btn" onclick="resendPhoneOtp()" disabled>Resend Code</button></div>
      </div>
      <!-- STEP 3: SUCCESS -->
      <div class="phone-step" id="pc-step-success">
        <div style="text-align:center;">
          <div style="font-size:48px;color:var(--success);margin-bottom:10px;"><i class="fas fa-circle-check"></i></div>
          <h3 style="margin-bottom:6px;">Phone Updated!</h3>
          <p>Your phone number has been verified successfully.</p>
          <div class="modal-actions">
            <button style="background:var(--primary-green);color:white;" onclick="closePhoneChangeModal()">Done</button>
          </div>
        </div>
      </div>
    </div>
  </div>

"""

# ------------------------------------------------ ACCOUNT PHONE ROW (badge)
PHONE_ROW_OLD = """          <div class="settings-field-group">
            <div class="settings-field-label">Phone Number</div>
            <div class="settings-field-row">
              <input class="form-input" type="tel" id="acc-phone" placeholder="+91XXXXXXXXXX" value="Loading...">
              <button class="btn-primary btn-sm" onclick="saveAccountField('phone')"><i class="fas fa-save"></i> Save</button>
            </div>
          </div>"""

PHONE_ROW_NEW = """          <div class="settings-field-group">
            <div class="settings-field-label">Phone Number<span class="verified-badge" id="phone-verified-badge"><i class="fas fa-circle-check"></i> Verified</span></div>
            <div class="settings-field-row">
              <input class="form-input" type="tel" id="acc-phone" placeholder="+91XXXXXXXXXX" value="Loading..." readonly>
              <button class="btn-primary btn-sm" onclick="startPhoneChange()"><i class="fas fa-mobile-screen-button"></i> Change</button>
            </div>
            <div class="language-preview">Changing your number requires OTP verification</div>
          </div>"""

# ------------------------------------------------------- NAV WITH HISTORY STACK
NAV_OLD = """    /* ===== NAVIGATION ===== */
    window.navigateTo = function(page) {
      var sub = document.getElementById('sub-' + page);
      if (sub) {
        sub.classList.add('active');
        document.getElementById('settings-main').style.opacity = '0.5';
        document.getElementById('settings-main').style.pointerEvents = 'none';
      }
    };

    window.navigateBack = function() {
      var pages = document.querySelectorAll('.settings-sub-page.active');
      for (var i = 0; i < pages.length; i++) {
        pages[i].classList.remove('active');
      }
      document.getElementById('settings-main').style.opacity = '';
      document.getElementById('settings-main').style.pointerEvents = '';
    };"""

NAV_NEW = """    /* ===== NAVIGATION (history stack) ===== */
    var navHistory = [];
    function setMainDimmed(dimmed) {
      var main = document.getElementById('settings-main');
      if (!main) return;
      main.style.opacity = dimmed ? '0.5' : '';
      main.style.pointerEvents = dimmed ? 'none' : '';
    }
    window.navigateTo = function(page) {
      if (page === 'help') { window.location.href = 'help.html'; return; }
      var sub = document.getElementById('sub-' + page);
      if (!sub) return;
      if (navHistory.indexOf(page) === -1) navHistory.push(page);
      sub.classList.add('active');
      setMainDimmed(true);
    };
    window.navigateBack = function() {
      var current = navHistory.pop();
      var curEl = current ? document.getElementById('sub-' + current) : null;
      if (curEl) curEl.classList.remove('active');
      var prev = navHistory[navHistory.length - 1];
      if (prev) {
        var prevEl = document.getElementById('sub-' + prev);
        if (prevEl && !prevEl.classList.contains('active')) prevEl.classList.add('active');
      } else {
        setMainDimmed(false);
      }
    };"""

DOM_READY_OLD = "    document.addEventListener('DOMContentLoaded', loadSettings);"

# ------------------------------------------------------------- APPENDED JS
NEW_JS = """    /* ===== DYNAMIC CATEGORIES ===== */
    var categories = [
      { page: 'account', icon: 'fa-user', color: 'icon-teal', title: 'Account', subtitle: 'Name, email, phone, PIN' },
      { page: 'security', icon: 'fa-shield-halved', color: 'icon-blue', title: 'Security & Privacy', subtitle: 'Sessions, devices, permissions' },
      { page: 'notifications', icon: 'fa-bell', color: 'icon-amber', title: 'Notifications', subtitle: 'Alert preferences' },
      { page: 'preferences', icon: 'fa-sliders', color: 'icon-purple', title: 'App Preferences', subtitle: 'Language, units, voice assistant' },
      { page: 'farm', icon: 'fa-seedling', color: 'icon-green', title: 'Farm Settings', subtitle: 'Crops, land size, irrigation' },
      { page: 'ai', icon: 'fa-brain', color: 'icon-indigo', title: 'AI Assistant', subtitle: 'Recommendations & advisory' },
      { page: 'sensors', icon: 'fa-microchip', color: 'icon-orange', title: 'Devices & Sensors', subtitle: 'Connected sensors and devices' },
      { page: 'datastorage', icon: 'fa-database', color: 'icon-gray', title: 'Data & Storage', subtitle: 'Cache, sync, export, delete' },
      { page: 'actions', icon: 'fa-bolt', color: 'icon-amber', title: 'Account Actions', subtitle: 'Quick actions & reset' },
      { page: 'about', icon: 'fa-circle-info', color: 'icon-gray', title: 'About', subtitle: 'Version, build, credits' },
      { page: 'help', icon: 'fa-circle-question', color: 'icon-indigo', title: 'Help & Support', subtitle: 'FAQ, contact, guides', external: true }
    ];

    function renderCategories() {
      var host = document.getElementById('settings-cat-list');
      if (!host) return;
      var out = '';
      categories.forEach(function(c) {
        var click = c.external
          ? "window.location.href='help.html'"
          : "navigateTo('" + c.page + "')";
        out += '<div class="settings-cat-item" onclick="' + click + '">' +
          '<div class="settings-cat-icon ' + c.color + '"><i class="fas ' + c.icon + '"></i></div>' +
          '<div class="settings-cat-text">' +
          '<div class="settings-cat-title">' + c.title + '</div>' +
          '<div class="settings-cat-subtitle">' + c.subtitle + '</div></div>' +
          '<i class="fas fa-chevron-right settings-cat-chevron"></i></div>';
      });
      host.innerHTML = out;
    }

    /* ===== PHONE CHANGE FLOW (3 steps) ===== */
    var pcTimerInt = null;
    var pcCode = null;

    function showPcStep(step) {
      ['number', 'otp', 'success'].forEach(function(s) {
        var el = document.getElementById('pc-step-' + s);
        if (el) el.classList.toggle('active', s === step);
      });
    }
    function stopPcCountdown() {
      if (pcTimerInt) { clearInterval(pcTimerInt); pcTimerInt = null; }
    }
    function startPcCountdown(secs) {
      stopPcCountdown();
      var remaining = secs;
      var cd = document.getElementById('pc-countdown');
      var resend = document.getElementById('pc-resend-btn');
      function tick() {
        if (remaining > 0) {
          if (cd) cd.textContent = 'You can request a new code in ' + remaining + 's';
          if (resend) { resend.disabled = true; }
          remaining--;
        } else {
          stopPcCountdown();
          if (cd) cd.textContent = "Didn't receive the code?";
          if (resend) { resend.disabled = false; }
        }
      }
      tick();
      pcTimerInt = setInterval(tick, 1000);
    }
    function getOtpValue() {
      var out = '';
      var inputs = document.querySelectorAll('#pc-step-otp .otp-input');
      for (var i = 0; i < inputs.length; i++) out += (inputs[i].value || '');
      return out.replace(/[^0-9]/g, '');
    }
    function clearOtpInputs() {
      var inputs = document.querySelectorAll('#pc-step-otp .otp-input');
      for (var i = 0; i < inputs.length; i++) inputs[i].value = '';
    }

    window.startPhoneChange = function() {
      var inp = document.getElementById('pc-new-phone');
      if (inp) inp.value = '';
      clearOtpInputs();
      stopPcCountdown();
      showPcStep('number');
      var m = document.getElementById('phone-change-modal');
      if (m) m.classList.add('show');
      setTimeout(function() { if (inp) inp.focus(); }, 250);
    };
    window.closePhoneChangeModal = function() {
      var m = document.getElementById('phone-change-modal');
      if (m) m.classList.remove('show');
      stopPcCountdown();
    };
    window.sendPhoneChangeOtp = function() {
      var val = (document.getElementById('pc-new-phone').value || '').trim();
      if (val.replace(/[^0-9]/g, '').length < 10) { showToast('Please enter a valid 10-digit phone number', 'warning'); return; }
      window._pcPendingPhone = val;
      var disp = document.getElementById('pc-otp-phone-display');
      if (disp) disp.textContent = val;
      clearOtpInputs();
      pcCode = String(Math.floor(100000 + Math.random() * 900000));
      showToast('Demo OTP: ' + pcCode, 'info');
      showPcStep('otp');
      startPcCountdown(30);
      setTimeout(function() {
        var first = document.querySelector('#pc-step-otp .otp-input');
        if (first) first.focus();
      }, 300);
    };
    window.resendPhoneOtp = function() {
      pcCode = String(Math.floor(100000 + Math.random() * 900000));
      clearOtpInputs();
      showToast('Demo OTP: ' + pcCode, 'info');
      startPcCountdown(30);
    };
    window.onOtpEntry = function(el) {
      var v = (el.value || '').replace(/[^0-9]/g, '');
      el.value = v.slice(-1);
      if (el.value && el.nextElementSibling && el.nextElementSibling.classList.contains('otp-input')) {
        el.nextElementSibling.focus();
      }
      if (getOtpValue().length === 6) verifyPhoneChangeOtp();
    };
    window.onOtpKey = function(e, el) {
      if (e.key === 'Backspace' && !el.value) {
        var prev = el.previousElementSibling;
        if (prev && prev.classList.contains('otp-input')) { prev.focus(); prev.value = ''; }
        e.preventDefault();
      }
    };
    window.verifyPhoneChangeOtp = function() {
      var entered = getOtpValue();
      if (entered.length < 6) { showToast('Please enter all 6 digits', 'warning'); return; }
      if (entered !== pcCode) { showToast('Incorrect OTP. Please try again.', 'danger'); clearOtpInputs(); return; }
      stopPcCountdown();
      var phone = window._pcPendingPhone || '';
      var phoneEl = document.getElementById('acc-phone');
      if (phoneEl) phoneEl.value = phone;
      try {
        var user = UserStore.getCurrentUser();
        if (user) {
          user.phone_number = phone;
          localStorage.setItem('fa-current-user-data', JSON.stringify(user));
        }
      } catch (err) {}
      try { API.Profile.update({ phone_number: phone }).catch(function() {}); } catch (err) {}
      var badge = document.getElementById('phone-verified-badge');
      if (badge) badge.style.display = '';
      showPcStep('success');
      showToast('Phone number verified and updated', 'success');
    };

    /* ===== FARM SETTINGS ===== */
    window.saveFarmSettings = function() {
      var data = {
        crop: (document.getElementById('farm-crop') || {}).value || '',
        landSize: (document.getElementById('farm-land') || {}).value || '',
        soil: (document.getElementById('farm-soil') || {}).value || '',
        irrigation: (document.getElementById('farm-irrigation') || {}).value || ''
      };
      if (!data.crop && !data.landSize) { showToast('Add at least a crop or land size', 'warning'); return; }
      localStorage.setItem('fa-farm-settings', JSON.stringify(data));
      showToast('Farm settings saved', 'success');
    };
    function restoreFarmSettings() {
      var raw = localStorage.getItem('fa-farm-settings');
      if (!raw) return;
      try {
        var d = JSON.parse(raw);
        var map = { crop: 'farm-crop', landSize: 'farm-land', soil: 'farm-soil', irrigation: 'farm-irrigation' };
        Object.keys(map).forEach(function(k) {
          var el = document.getElementById(map[k]);
          if (el && d[k] !== undefined && d[k] !== '') el.value = d[k];
        });
      } catch (err) {}
    }

    /* ===== AI SETTINGS ===== */
    window.saveAiSetting = function(key, value) {
      localStorage.setItem('fa-ai-' + key, value.toString());
      showToast('AI preference saved', 'success');
    };
    window.saveAiDetail = function(val) {
      localStorage.setItem('fa-ai-detail', val);
      showToast('Advisory detail level updated', 'success');
    };
    function restoreAiSettings() {
      ['recommendations', 'voiceReplies', 'training'].forEach(function(k) {
        var v = localStorage.getItem('fa-ai-' + k);
        var el = document.getElementById('ai-' + k.toLowerCase());
        if (v !== null && el) el.checked = v === 'true';
      });
      var d = localStorage.getItem('fa-ai-detail');
      if (d) { var sel = document.getElementById('ai-detail-select'); if (sel) sel.value = d; }
    }

    /* ===== ACCOUNT ACTIONS ===== */
    window.resetAllSettings = function() {
      if (!confirm('Reset ALL app settings to their defaults? Your account data will not be deleted.')) return;
      var keys = [];
      for (var i = 0; i < localStorage.length; i++) {
        var k = localStorage.key(i);
        if (k && k.indexOf('fa-') === 0) keys.push(k);
      }
      keys.forEach(function(k) { localStorage.removeItem(k); });
      showToast('All settings reset to defaults', 'success');
      setTimeout(function() { window.location.reload(); }, 900);
    };

"""


def replace_once(html, old, new):
    count = html.count(old)
    if count != 1:
        raise SystemExit('Expected exactly 1 occurrence, found %d of:\n%r' % (count, old[:80]))
    return html.replace(old, new, 1)


def insert_before_marker(html, marker, block):
    idx = html.find(marker)
    if idx == -1:
        raise SystemExit('Marker not found: %r' % marker[:80])
    return html[:idx] + block + html[idx:]


def main():
    with io.open(TARGET, 'r', encoding='utf-8') as f:
        html = f.read()
    print('Read %d bytes' % len(html))

    # 1. Inject new CSS just before </style>
    html = insert_before_marker(html, '  </style>', CSS_ADDON)

    # 2. Replace hardcoded category list with dynamic container
    start = html.index('<div class="settings-cat-list">')
    end = html.index('</main>', start)
    html = html[:start] + EMPTY_CATEGORIES + html[end:]

    # 3. Insert sub-farm + sub-ai before Devices & Sensors page
    html = insert_before_marker(html, '  <!-- ===== SUB-PAGE: DEVICES & SENSORS ===== -->', FARM_AI_PAGES)

    # 4. Insert sub-actions + phone change modal before logout confirm modal
    html = insert_before_marker(html, '  <!-- ===== LOGOUT CONFIRM MODAL ===== -->', ACTIONS_PHONE_BLOCK)

    # 5. Upgrade account phone row (verified badge + Change button)
    html = replace_once(html, PHONE_ROW_OLD, PHONE_ROW_NEW)

    # 6. Navigation with history stack
    html = replace_once(html, NAV_OLD, NAV_NEW)

    # 7. Append new JS and wire up combined init
    html = replace_once(
        html, DOM_READY_OLD,
        NEW_JS + '    document.addEventListener(\'DOMContentLoaded\', function() {\n'
                 '      loadSettings();\n'
                 '      renderCategories();\n'
                 '      restoreFarmSettings();\n'
                 '      restoreAiSettings();\n'
                 '    });')

    with io.open(TARGET, 'w', encoding='utf-8') as f:
        f.write(html)

    size = os.path.getsize(TARGET)
    print('Written %d bytes (%.1f KB) to %s' % (size, size / 1024.0, TARGET))
    if size < 25 * 1024:
        raise SystemExit('ERROR: file smaller than 25KB!')
    print('OK: settings.html regenerated (>25KB)')


if __name__ == '__main__':
    main()
