(function() {
'use strict';

const DB = () => window.FarmDB || {};

// Reusable UI state helpers (empty / error / loading) available app-wide
window.UIState = window.UIState || {
  empty: function(target, opts) {
    opts = opts || {};
    var el = typeof target === 'string' ? document.getElementById(target) : target;
    if (!el) return;
    el.innerHTML = '<div class="state-block"><div class="state-icon"><i class="fas fa-' + (opts.icon || 'inbox') + '"></i></div>' +
      '<h3>' + (opts.title || 'Nothing here yet') + '</h3><p>' + (opts.message || 'There is no data to display right now.') + '</p>' +
      (opts.action ? '<button class="btn-primary" onclick="' + opts.action + '">' + (opts.actionLabel || 'Refresh') + '</button>' : '') + '</div>';
  },
  error: function(target, opts) {
    opts = opts || {};
    var el = typeof target === 'string' ? document.getElementById(target) : target;
    if (!el) return;
    el.innerHTML = '<div class="state-block error"><div class="state-icon"><i class="fas fa-' + (opts.icon || 'triangle-exclamation') + '"></i></div>' +
      '<h3>' + (opts.title || 'Something went wrong') + '</h3><p>' + (opts.message || 'We could not load this content. Please try again.') + '</p>' +
      '<button class="btn-primary" onclick="' + (opts.action || 'location.reload()') + '"><i class="fas fa-rotate-right"></i> ' + (opts.actionLabel || 'Retry') + '</button></div>';
  },
  loading: function(target, count) {
    var el = typeof target === 'string' ? document.getElementById(target) : target;
    if (!el) return;
    var n = count || 3, html = '';
    for (var i = 0; i < n; i++) { html += '<div class="skeleton skeleton-card"></div>'; }
    el.innerHTML = html;
  }
};

// Navigation (sidebar, topbar, bottom-nav) handled by navigation.js
// Auth, session, theme, command palette, voice, toasts handled by app.js
document.addEventListener("DOMContentLoaded", () => {
  initDynamicPageLogic();
});

/* PAGE ROUTER */
function initDynamicPageLogic() {
  const page = window.location.pathname.split("/").pop() || "index.html";
  setTimeout(() => {
    if (page === "index.html") loadHomeTasks();
    else if (page === "farm.html") { loadFarmPlots(); initFarmJournal(); }
    else if (page === "ai.html") initAIChatbot();
    else if (page === "monitoring.html") initMonitoringSystem();
    else if (page === "marketplace.html") initMarketplaceShop();
    else if (page === "weather.html") initWeatherForecast();
    else if (page === "news.html") initNewsCenter();
    else if (page === "community.html") initCommunityFeed();
    else if (page === "notifications.html") initNotificationsManager();
    else if (page === "water.html") { initWaterManagement('water-content'); showIrrigationScheduler(); }
    else if (page === "fertilizer.html") initFertilizerCenter('fert-content');
    else if (page === "equipment.html") initEquipmentRental('equip-content');
    else if (page === "seeds.html") initSeedCenter('seeds-content');
    else if (page === "soil.html") initSoilHealth('soil-content');
    else if (page === "crop-protection.html") initCropProtection('protection-content');
    else if (page === "livestock.html") initLivestockHealth('livestock-content');
    else if (page === "schemes.html") initGovSchemes('schemes-content');
    else if (page === "sustainability.html") initSustainability();
  }, 100);
}

/* ===== HOME ===== */
function loadHomeTasks() {
  const taskList = document.getElementById("home-tasks-list");
  if (!taskList) return;
  const tasks = (DB().tasks || []).slice(0, 3);
  taskList.innerHTML = tasks.map(t => `
    <div style="display:flex;align-items:center;gap:8px;padding:4px 0;">
      <span style="width:16px;height:16px;border-radius:4px;border:2px solid var(--primary-green);display:flex;align-items:center;justify-content:center;font-size:9px;cursor:pointer;${t.completed?'background:var(--primary-green);color:white;':''}">${t.completed?'<i class="fas fa-check"></i>':''}</span>
      <span style="font-size:12px;${t.completed?'text-decoration:line-through;color:var(--text-muted);':''}">${t.text}</span>
    </div>
  `).join('');
}

/* ===== FARM ===== */
function loadFarmPlots() {
  const container = document.getElementById("farm-plots-container");
  if (!container) return;
  const plots = (DB().plots || []).slice(0, 6);
  container.innerHTML = plots.map(p => {
    const ndvi = parseInt(p.ndvi) || 70;
    const sc = p.status === "Needs Water" ? "warning" : p.status === "Pest Risk" ? "danger" : "success";
    return `
    <div class="feature-card" onclick="showToast('${p.name}: ${p.crop} • NDVI: ${p.ndvi} • Moisture: ${p.moisture}','info')">
      <div style="display:flex;justify-content:space-between;"><i class="fas fa-seedling"></i><span class="badge badge-${sc}">${p.status}</span></div>
      <h4 style="font-size:13px;">${p.name}</h4>
      <p style="font-size:11px;color:var(--text-muted);">${p.crop} • NDVI: ${p.ndvi}</p>
      <div class="progress-bar"><div class="progress-fill" style="width:${ndvi}%"></div></div>
      <div style="display:flex;justify-content:space-between;font-size:9px;color:var(--text-muted);margin-top:4px;">
        <span>Moisture: ${p.moisture || 'N/A'}</span><span>Temp: ${p.temp || 'N/A'}</span>
      </div>
    </div>`;
  }).join('');
}

function initFarmJournal() {
  const form = document.getElementById("journal-form");
  const timeline = document.getElementById("journal-timeline");
  if (!form || !timeline) return;
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const plot = document.getElementById("journal-plot");
    const activity = document.getElementById("journal-activity");
    const notes = document.getElementById("journal-notes");
    if (!activity || !activity.value.trim()) return;
    const item = document.createElement("div");
    item.className = "alert-strip info";
    item.style.borderLeftColor = "var(--primary-green)";
    item.innerHTML = `<div class="alert-content"><i class="fas fa-book-open" style="color:var(--primary-green);margin-right:8px;"></i><div><strong>${plot.value}: ${activity.value}</strong><div style="font-size:11px;color:var(--text-secondary);">${notes.value}</div></div></div><span style="font-size:10px;color:var(--text-muted);white-space:nowrap;">Just Now</span>`;
    timeline.prepend(item);
    activity.value = ""; if (notes) notes.value = "";
    showToast('Journal entry recorded!', 'success');
  });
}

/* ===== AI CHAT ===== */
function initAIChatbot() {
  var chatMessages = document.getElementById("chat-messages");
  var chatInput = document.getElementById("chat-input");
  var sendBtn = document.getElementById("chat-send-btn");
  var micBtn = document.getElementById("chat-mic-btn");
  if (!chatMessages) return;
  if (!chatInput) return;

  // Mock AI responses keyed by keywords
  var responses = {
    paddy: "For your paddy crop at this stage: maintain 5-7cm water level. Apply 30kg/acre DAP if crop is at tillering stage. Watch for stem borer - install pheromone traps at 12 per acre. Consider top dressing of urea at 25kg/acre within a week for better yield.",
    rain: "Based on satellite imagery and regional forecasts, light rain (2-5mm) is expected tomorrow morning. I recommend: 1) Delay irrigation for 2 days, 2) Secure polythene covers on seedlings, 3) Harvest any mature produce today before the rain arrives.",
    yellow: "Yellowing leaves can indicate several issues: 1) Nitrogen deficiency - apply urea 20kg/acre, 2) Iron chlorosis - check soil pH and apply ferrous sulphate 5g/L spray, 3) Overwatering - reduce irrigation frequency, 4) Pest damage - inspect undersides of leaves. Send me a photo for precise diagnosis.",
    irrigate: "Based on your farm sensor data: Rice field soil moisture is at 48% - irrigate within 24 hours. Maintain 5-7cm standing water for rice. Cotton field - moisture at 55%, can wait 2 more days. Consider drip irrigation for 40% water savings.",
    crop: "For your land type (loamy soil, temperate climate), I recommend: 1) Rice - high yield potential with good market price, 2) Maize - short duration (100-110 days) with lower water requirement, 3) Cotton - profitable but needs pest management. Consider water availability and labor before deciding.",
    fertilizer: "General NPK recommendations per hectare: Rice - 120:60:40 kg, Cotton - 80:40:40 kg, Maize - 100:50:50 kg, Wheat - 120:60:40 kg. Apply in 2-3 splits for best efficiency. Always combine with organic manure like vermicompost at 2t/ha.",
    pest: "Pest alert for your farm: 1) Cotton Bollworm - apply Neem oil 5ml/L or Spinosad 2ml/L, 2) Rice Stem Borer - use Carbofuran granules 10kg/acre, 3) Fall Armyworm in Maize - spray Emamectin benzoate. Install yellow sticky traps at 12 per acre for monitoring.",
    market: "Today's mandi prices: Basmati Rice Rs 2,450-2,550/qtl (up 2%), Cotton Rs 6,600-6,800/qtl (up 1.5%), Maize Rs 1,900-2,000/qtl (stable), Sugarcane Rs 340-360/qtl. Good time to sell rice inventory this week as prices are trending upward.",
    weather: "Current conditions: 32 degrees C, humidity 65%, wind 12 km/h. 3-day forecast: Tomorrow - 28 degrees C with light rain, Day 3 - 30 degrees C cloudy, Day 4 - 33 degrees C sunny. Favorable conditions for transplanting and pesticide application.",
    soil: "Your farm soil report: Type - Loamy, pH 6.8 (ideal for most crops), Organic Carbon 0.6%, Nitrogen - Medium, Phosphorus - Low, Potassium - Medium. Recommendation: Apply 100kg DAP/ha before next sowing. Add vermicompost 2t/ha for organic matter.",
    disease: "Common crop diseases this season: 1) Rice Blast - use Tricyclazole 1g/L spray, 2) Cotton Leaf Curl - remove and destroy infected plants, 3) Wheat Rust - apply Mancozeb 2g/L, 4) Maize Downy Mildew - seed treatment with Metalaxyl. Practice 3-year crop rotation."
  };

  // Crop diagnosis responses based on symptom keywords
  var diagnosis = {
    yellow: { crop: "Multiple crops", disease: "Nutrient deficiency (N/Fe) or water stress", solution: "Apply urea 20kg/acre + ferrous sulphate 5g/L foliar spray. Ensure proper drainage." },
    wilt: { crop: "Cotton, Tomato, Chillies", disease: "Fusarium wilt or Bacterial wilt", solution: "Remove infected plants. Drench soil with Copper oxychloride 3g/L. Apply Trichoderma biofungicide at 5g per plant." },
    curl: { crop: "Cotton, Tomato", disease: "Leaf curl virus", solution: "Remove and destroy infected plants. Control whitefly vector with Imidacloprid 0.5ml/L. Use virus-resistant varieties next season." },
    spot: { crop: "Multiple crops", disease: "Leaf spot (fungal or bacterial)", solution: "Apply Mancozeb 2g/L or Copper fungicide 3g/L. Improve air circulation by maintaining proper plant spacing." },
    blight: { crop: "Rice, Potato, Tomato", disease: "Early or Late blight", solution: "Apply Chlorothalonil 2g/L or Metalaxyl-MZ 2.5g/L. Avoid overhead irrigation. Use disease-free seeds." },
    rust: { crop: "Wheat, Pulses", disease: "Rust disease", solution: "Apply Tebuconazole 1g/L or Mancozeb 2g/L. Sow resistant varieties. Early sowing reduces incidence." },
    mildew: { crop: "Maize, Grapes, Pulses", disease: "Downy or Powdery mildew", solution: "Apply Metalaxyl 2g/L or Sulfur 3g/L. Ensure proper drainage and avoid dense planting." },
    rot: { crop: "Multiple crops", disease: "Root or Stem rot", solution: "Improve soil drainage. Drench with Carbendazim 1g/L. Apply neem cake at 100kg/ha as soil amendment." },
    hole: { crop: "Multiple crops", disease: "Insect infestation", solution: "Identify pest type. Apply Neem oil 5ml/L or appropriate insecticide. Use pheromone traps for monitoring." },
    stunt: { crop: "Rice, Maize", disease: "Stunting (nutrient deficiency or nematodes)", solution: "Test soil for NPK levels. Apply balanced fertilizer. Check for root nematodes - apply Carbofuran 10kg/acre." }
  };

  // Helper: get AI response for user text
  function getResponse(userText) {
    var q = userText.toLowerCase();

    // Check for diagnosis/crop health keywords first
    var symptomKeys = ["yellowing", "yellow", "wilting", "wilt", "curling", "curl", "spots", "spot", "blight", "rust", "mildew", "rot", "rotting", "holes", "hole", "stunted", "stunt", "brown", "drooping", "burn"];
    var matchedKey = null;
    for (var si = 0; si < symptomKeys.length; si++) {
      if (q.indexOf(symptomKeys[si]) !== -1) {
        matchedKey = symptomKeys[si];
        break;
      }
    }
    if (matchedKey) {
      var diagKey = matchedKey;
      if (matchedKey === "yellowing") diagKey = "yellow";
      else if (matchedKey === "wilting") diagKey = "wilt";
      else if (matchedKey === "curling") diagKey = "curl";
      else if (matchedKey === "spots") diagKey = "spot";
      else if (matchedKey === "rotting") diagKey = "rot";
      else if (matchedKey === "holes") diagKey = "hole";
      else if (matchedKey === "stunted") diagKey = "stunt";
      else if (matchedKey === "brown") diagKey = "spot";
      else if (matchedKey === "drooping") diagKey = "wilt";
      else if (matchedKey === "burn") diagKey = "spot";
      if (diagnosis[diagKey]) {
        var d = diagnosis[diagKey];
        return "I have diagnosed the issue based on your description:\n\nAffected Crop: " + d.crop + "\nPossible Disease: " + d.disease + "\nRecommended Solution: " + d.solution + "\n\nFor a more accurate diagnosis, please send a photo of the affected plant parts. Would you like me to suggest preventive measures?";
      }
    }

    // Check response categories
    if (q.indexOf("paddy") !== -1 || q.indexOf("rice") !== -1) {
      return responses.paddy;
    }
    if ((q.indexOf("crop") !== -1 && (q.indexOf("today") !== -1 || q.indexOf("do") !== -1)) && q.indexOf("best") === -1 && q.indexOf("which") === -1) {
      return responses.paddy;
    }
    if (q.indexOf("rain") !== -1 || q.indexOf("tomorrow") !== -1) {
      return responses.rain;
    }
    if (q.indexOf("yellow") !== -1 || q.indexOf("leave") !== -1 || q.indexOf("leaf") !== -1) {
      return responses.yellow;
    }
    if (q.indexOf("irrigat") !== -1 || q.indexOf("water") !== -1) {
      return responses.irrigate;
    }
    if (q.indexOf("best") !== -1 || (q.indexOf("which") !== -1 && q.indexOf("crop") !== -1) || q.indexOf("recommend") !== -1) {
      return responses.crop;
    }
    if (q.indexOf("fertilizer") !== -1 || q.indexOf("npk") !== -1 || q.indexOf("urea") !== -1 || q.indexOf("dap") !== -1) {
      return responses.fertilizer;
    }
    if (q.indexOf("pest") !== -1 || q.indexOf("bug") !== -1 || q.indexOf("insect") !== -1 || q.indexOf("bollworm") !== -1) {
      return responses.pest;
    }
    if (q.indexOf("price") !== -1 || q.indexOf("market") !== -1 || q.indexOf("mandi") !== -1 || q.indexOf("sell") !== -1) {
      return responses.market;
    }
    if (q.indexOf("weather") !== -1 || q.indexOf("temperature") !== -1 || q.indexOf("forecast") !== -1) {
      return responses.weather;
    }
    if (q.indexOf("soil") !== -1 || q.indexOf("ph") !== -1 || q.indexOf("nutrient") !== -1) {
      return responses.soil;
    }
    if (q.indexOf("disease") !== -1 || q.indexOf("infection") !== -1 || q.indexOf("fungus") !== -1 || q.indexOf("bacteria") !== -1) {
      return responses.disease;
    }

    // Generic fallback
    var userName = localStorage.getItem('user-name') || 'Farmer';
    return "Thank you for your question, " + userName + "! I am analyzing this based on your farm data and regional conditions. Based on current telemetry, soil moisture is at optimal levels and weather conditions are favorable for most operations. Could you provide more specific details so I can give you a more targeted recommendation? You can also try one of the example questions above for quick guidance.";
  }

  // Append a message bubble with avatar wrapper
  function appendMsg(text, sender) {
    var wrapper = document.createElement("div");
    wrapper.className = "chat-bubble-wrapper";

    var avatar = document.createElement("div");
    var bubble = document.createElement("div");
    bubble.className = "chat-bubble " + sender;
    bubble.textContent = text;

    if (sender === "ai") {
      wrapper.className = "chat-bubble-wrapper";
      avatar.className = "chat-avatar ai-avatar";
      avatar.innerHTML = '<i class="fas fa-robot"></i>';
      wrapper.appendChild(avatar);
      wrapper.appendChild(bubble);
    } else {
      wrapper.className = "chat-bubble-wrapper user-wrapper";
      avatar.className = "chat-avatar user-avatar";
      avatar.innerHTML = '<i class="fas fa-user"></i>';
      wrapper.appendChild(bubble);
      wrapper.appendChild(avatar);
    }

    chatMessages.appendChild(wrapper);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    saveHistory();
  }

  // Simulate AI reply with typing indicator
  function aiReply(userText) {
    var wrapper = document.createElement("div");
    wrapper.className = "chat-bubble-wrapper";

    var avatar = document.createElement("div");
    avatar.className = "chat-avatar ai-avatar";
    avatar.innerHTML = '<i class="fas fa-robot"></i>';

    var typing = document.createElement("div");
    typing.className = "chat-bubble ai typing";
    typing.innerHTML = '<span class="typing-dots"><span></span><span></span><span></span></span>';

    wrapper.appendChild(avatar);
    wrapper.appendChild(typing);
    chatMessages.appendChild(wrapper);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    var applyReply = function (reply) {
      wrapper.remove();
      appendMsg(reply, "ai");
    };

    // Prefer the real backend AI endpoint when authenticated; fall back to the local keyword engine.
    if (window.API && localStorage.getItem('fa-auth-token')) {
      window.API.AI.chat(userText, window._faConversationId, window._faActiveModel || 'local').then(function (res) {
        if (res && res.response) {
          if (res.conversation_id) window._faConversationId = res.conversation_id;
          applyReply(res.response);
        } else {
          setTimeout(function () { applyReply(getResponse(userText)); }, 400);
        }
      }).catch(function () {
        setTimeout(function () { applyReply(getResponse(userText)); }, 400);
      });
      return;
    }

    setTimeout(function () {
      applyReply(getResponse(userText));
    }, 1200);
  }

  // Handle send button / Enter key
  function handleSend() {
    var text = chatInput.value.trim();
    if (!text) return;
    if (attachedFile) {
      text = "[Attached: " + attachedFile.name + "]\n" + text;
    }
    appendMsg(text, "user");
    chatInput.value = "";
    clearAttachedFile();
    hideWelcome();
    aiReply(text);
  }

  /* ---- Welcome / history helpers ---- */
  function hideWelcome() {
    var w = document.getElementById("ai-welcome");
    if (w) w.style.display = "none";
    chatMessages.classList.add("has-messages");
  }

  function showWelcome() {
    var w = document.getElementById("ai-welcome");
    if (w) w.style.display = "";
    chatMessages.classList.remove("has-messages");
  }

  function saveHistory() {
    var msgs = [];
    chatMessages.querySelectorAll(".chat-bubble-wrapper").forEach(function (w) {
      var bubble = w.querySelector(".chat-bubble");
      if (!bubble || !bubble.textContent) return;
      var sender = bubble.classList.contains("user") ? "user" : "ai";
      if (bubble.classList.contains("typing")) return;
      msgs.push({ sender: sender, text: bubble.textContent });
    });
    try { localStorage.setItem("fa-ai-history", JSON.stringify(msgs)); } catch (e) {}
  }

  function restoreHistory() {
    var raw = null;
    try { raw = localStorage.getItem("fa-ai-history"); } catch (e) {}
    if (!raw) return;
    var arr = null;
    try { arr = JSON.parse(raw); } catch (e) {}
    if (!arr || !arr.length) return;
    arr.forEach(function (m) {
      var wrapper = document.createElement("div");
      wrapper.className = "chat-bubble-wrapper restored";
      var avatar = document.createElement("div");
      var bubble = document.createElement("div");
      bubble.className = "chat-bubble " + (m.sender === "user" ? "user" : "ai");
      bubble.textContent = m.text;
      if (m.sender === "user") {
        wrapper.className = "chat-bubble-wrapper user-wrapper restored";
        avatar.className = "chat-avatar user-avatar";
        avatar.innerHTML = '<i class="fas fa-user"></i>';
        wrapper.appendChild(bubble);
        wrapper.appendChild(avatar);
      } else {
        avatar.className = "chat-avatar ai-avatar";
        avatar.innerHTML = '<i class="fas fa-robot"></i>';
        wrapper.appendChild(avatar);
        wrapper.appendChild(bubble);
      }
      chatMessages.appendChild(wrapper);
    });
    hideWelcome();
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  /* ---- Attachments ---- */
  var attachedFile = null;
  var attachBtn = document.getElementById("ai-attach-btn");
  var fileInput = document.getElementById("ai-file-input");

  function clearAttachedFile() {
    attachedFile = null;
    if (fileInput) fileInput.value = "";
    var chip = document.getElementById("ai-attach-chip");
    if (chip) chip.remove();
    var bar = document.querySelector(".ai-input-bar");
    if (bar) bar.classList.remove("has-attachment");
  }

  if (attachBtn && fileInput) {
    attachBtn.addEventListener("click", function () { fileInput.click(); });
    fileInput.addEventListener("change", function () {
      if (fileInput.files && fileInput.files.length) {
        attachedFile = fileInput.files[0];
        var chip = document.getElementById("ai-attach-chip");
        if (chip) chip.remove();
        chip = document.createElement("div");
        chip.className = "ai-attach-chip";
        chip.id = "ai-attach-chip";
        chip.innerHTML = '<i class="fas fa-paperclip"></i> ' + (attachedFile.name.length > 28 ? attachedFile.name.slice(0, 28) + '…' : attachedFile.name) +
          '<span class="ai-attach-x" title="Remove">&times;</span>';
        chip.querySelector(".ai-attach-x").addEventListener("click", clearAttachedFile);
        var bar = document.querySelector(".ai-input-bar");
        bar.insertBefore(chip, bar.firstChild);
        bar.classList.add("has-attachment");
        if (typeof showToast === "function") showToast("Attached: " + attachedFile.name, "success");
      }
    });
  }

  if (sendBtn && chatInput) {
    sendBtn.addEventListener("click", handleSend);
    chatInput.addEventListener("keypress", function(e) {
      if (e.key === "Enter") handleSend();
    });
  }

  /* ---- Voice input (Web Speech API with mock fallback) ---- */
  var recognition = null;
  if (window.SpeechRecognition || window.webkitSpeechRecognition) {
    recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
    recognition.lang = "en-IN";
    recognition.continuous = false;
    recognition.interimResults = false;
  }

  if (micBtn) {
    micBtn.addEventListener("click", function() {
      if (recognition) {
        micBtn.innerHTML = '<i class="fas fa-microphone-lines"></i>';
        if (typeof showToast === "function") showToast("Listening… speak now", "info");
        recognition.onresult = function (event) {
          var transcript = "";
          for (var ri = 0; ri < event.results.length; ri++) {
            transcript += event.results[ri][0].transcript;
          }
          chatInput.value = transcript;
          chatInput.focus();
          micBtn.innerHTML = '<i class="fas fa-microphone"></i>';
        };
        recognition.onerror = function () {
          micBtn.innerHTML = '<i class="fas fa-microphone"></i>';
        };
        recognition.onend = function () {
          micBtn.innerHTML = '<i class="fas fa-microphone"></i>';
        };
        try { recognition.start(); } catch (e) { /* already started */ }
        return;
      }
      appendMsg("Listening...", "ai");
      setTimeout(function() {
        var voiceQuery = "Show me weather and crop advisory";
        appendMsg(voiceQuery, "user");
        hideWelcome();
        aiReply(voiceQuery);
      }, 2000);
    });
  }

  /* ---- New conversation ---- */
  var newChatBtn = document.getElementById("ai-new-chat");
  if (newChatBtn) {
    newChatBtn.addEventListener("click", function () {
      chatMessages.querySelectorAll(".chat-bubble-wrapper").forEach(function (w) { w.remove(); });
      clearAttachedFile();
      try { localStorage.removeItem("fa-ai-history"); } catch (e) {}
      showWelcome();
      chatInput.focus();
      if (typeof showToast === "function") showToast("Started a new conversation", "success");
    });
  }

  // Example question chips - fill input and send on click
  var exampleChips = document.querySelectorAll(".example-chip");
  for (var ei = 0; ei < exampleChips.length; ei++) {
    (function(chip) {
      chip.addEventListener("click", function() {
        var query = chip.getAttribute("data-query");
        if (query) {
          chatInput.value = query;
          chatInput.focus();
        }
      });
    })(exampleChips[ei]);
  }

  // Feature cards - send query directly
  var featureCards = document.querySelectorAll(".ai-feature-card");
  for (var fi = 0; fi < featureCards.length; fi++) {
    (function(card) {
      card.addEventListener("click", function() {
        var query = card.getAttribute("data-query");
        if (query) {
          chatInput.value = query;
          handleSend();
        }
      });
    })(featureCards[fi]);
  }

  // Contextual suggestion chips - send directly as message
  var contextualChips = document.querySelectorAll(".contextual-chip");
  for (var ci = 0; ci < contextualChips.length; ci++) {
    (function(chip) {
      chip.addEventListener("click", function() {
        var tagEl = chip.querySelector(".chip-tag");
        var text = chip.textContent.trim();
        if (tagEl) {
          text = chip.textContent.replace(tagEl.textContent, "").trim();
        }
        if (text) {
          appendMsg(text, "user");
          aiReply(text);
        }
      });
    })(contextualChips[ci]);
  }

  // Model selection chips
  var modelChips = document.querySelectorAll(".model-chip");
  for (var mi = 0; mi < modelChips.length; mi++) {
    (function(chip) {
      chip.addEventListener("click", function() {
        var allModels = document.querySelectorAll(".model-chip");
        for (var mj = 0; mj < allModels.length; mj++) {
          allModels[mj].classList.remove("active");
        }
        chip.classList.add("active");
        var modelName = chip.getAttribute("data-model");
        window._faActiveModel = modelName || 'local';
        if (chip.getAttribute("data-needs-config") === "true") {
          showToast(modelName + " requires API key configuration. Please go to Settings.", "warning");
        } else {
          showToast("Switched to " + modelName, "success");
        }
      });
    })(modelChips[mi]);
  }

  // Restore previous conversation (if any)
  restoreHistory();
}

/* ===== MONITORING ===== */
function initMonitoringSystem() {
  const toggle = document.getElementById("drone-toggle-btn");
  const status = document.getElementById("drone-status-txt");
  if (toggle && status) {
    toggle.addEventListener("click", () => {
      const active = toggle.classList.contains("btn-primary");
      toggle.className = active ? "btn-secondary" : "btn-primary";
      toggle.innerHTML = active ? '<i class="fas fa-plane-departure"></i> Launch Drone' : '<i class="fas fa-location-arrow"></i> Recall Drone';
      status.textContent = active ? "Status: Docked (98%)" : "Status: In-Flight (Alt: 40m)";
      status.style.color = active ? "var(--text-secondary)" : "var(--success)";
      showToast(active ? 'Drone docked' : 'Drone launched for aerial survey', 'info');
    });
  }
  setTimeout(() => {
    document.querySelectorAll(".chart-bar-fill").forEach(b => {
      b.style.height = b.getAttribute("data-height") || "50%";
    });
  }, 300);
}

/* ===== MARKETPLACE ===== */
window.cartCount = 0;
function initMarketplaceShop() {
  const grid = document.getElementById("marketplace-grid");
  const badge = document.getElementById("cart-count-badge");
  const searchInput = document.getElementById("marketplace-search-input");
  if (!grid) return;

  const render = (items) => {
    grid.innerHTML = items.length === 0
      ? '<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--text-muted);">No products found.</div>'
      : items.map(p => `
        <div class="feature-card" style="cursor:default;">
          <span class="badge badge-green" style="float:right;">${p.tag || 'Featured'}</span>
          <i class="fas ${p.icon || 'fa-shopping-bag'}" style="font-size:28px;"></i>
          <h4 style="font-size:13px;">${p.name}</h4>
          <p style="font-size:10px;color:var(--text-muted);">${p.brand || 'Generic'} • ⭐${p.rating || '4.5'}</p>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px;">
            <span style="font-size:16px;font-weight:800;color:var(--primary-green);">₹${p.price}</span>
            <button class="btn-primary btn-sm" onclick="showToast('${p.name} added to cart! ₹${p.price}','success');window.cartCount++;var cb=document.getElementById('cart-count-badge');if(cb){cb.textContent=window.cartCount;cb.style.display='flex';}"><i class="fas fa-shopping-cart"></i></button>
          </div>
        </div>
      `).join('');
  };

  const allProducts = DB().products || [];
  render(allProducts.slice(0, 20));

  document.querySelectorAll(".category-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      document.querySelectorAll(".category-chip").forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      const cat = chip.getAttribute("data-filter");
      render(cat === "all" ? allProducts.slice(0, 20) : allProducts.filter(p => p.category === cat).slice(0, 20));
    });
  });

  if (searchInput) {
    searchInput.addEventListener("input", () => {
      const q = searchInput.value.toLowerCase();
      render(allProducts.filter(p => p.name.toLowerCase().includes(q)).slice(0, 20));
    });
  }
}

/* ===== FINANCE ===== */
/* ===== WEATHER ===== */
function initWeatherForecast() {
  const hourly = document.getElementById("weather-hourly-list");
  if (!hourly) return;
  const hours = ["3 PM", "4 PM", "5 PM", "6 PM", "7 PM", "8 PM", "9 PM", "10 PM"];
  const temps = [28, 27, 27, 26, 25, 24, 24, 23];
  const icons = ["fa-sun", "fa-cloud-sun", "fa-cloud", "fa-cloud-rain", "fa-cloud-showers-heavy", "fa-moon", "fa-moon", "fa-cloud-moon"];
  hourly.innerHTML = hours.map((h, i) => `
    <div class="weather-hour-box" onclick="showToast('${h}: ${temps[i]}°C • ${icons[i].replace('fa-','').replace('-',' ')}','info')">
      <div style="font-size:10px;color:var(--text-muted);">${h}</div>
      <i class="fas ${icons[i]}"></i>
      <div style="font-size:12px;font-weight:700;">${temps[i]}°C</div>
    </div>
  `).join('');

  // Populate 7-day forecast from DB
  const forecastContainer = document.querySelector('.card-premium:last-child');
  if (forecastContainer && DB().weatherData) {
    const data = DB().weatherData.slice(1, 8);
    const items = forecastContainer.querySelectorAll('.price-card');
    if (items.length === 7) {
      data.forEach((d, i) => {
        if (items[i]) {
          const icon = d.condition.includes('Rain') ? 'fa-cloud-rain' : d.condition.includes('Cloud') ? 'fa-cloud' : d.condition.includes('Sun') || d.condition.includes('Clear') ? 'fa-sun' : 'fa-cloud-sun';
          items[i].querySelector('.price-icon i').className = `fas ${icon}`;
          items[i].querySelector('.price-crop').textContent = d.date;
          items[i].querySelectorAll('div')[2].innerHTML = `${d.temp.max}°C / ${d.temp.min}°C`;
          items[i].querySelectorAll('div')[3].innerHTML = `${d.condition}`;
        }
      });
    }
  }
}

/* ===== NEWS (Enhanced with full articles) ===== */
function initNewsCenter() {
  const list = document.getElementById("news-list-container");
  if (!list) return;
  const articles = DB().newsArticles || [];
  const cats = ["All","Agriculture","Technology","Weather","Markets","Livestock","Government","Export","Research","Sustainability"];
  const render = (items) => {
    if (items.length === 0) {
      list.innerHTML = '<div class="empty-state"><i class="fas fa-newspaper"></i><h4>No news articles</h4><p>Check back later for updates</p></div>';
      return;
    }
    list.innerHTML = items.map(a => `
      <div class="feature-card" onclick="showArticleDetail(${a.id})" style="cursor:pointer;">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;">
          <span class="badge badge-green" style="font-size:9px;">${a.category}</span>
          <span style="font-size:10px;color:var(--text-muted);">${a.readTime || '3 min read'}</span>
        </div>
        <div style="width:100%;height:80px;background:linear-gradient(135deg,var(--soft-green),var(--pale-green));border-radius:var(--radius-sm);display:flex;align-items:center;justify-content:center;margin:8px 0;font-size:36px;color:var(--primary-green);opacity:0.6;">
          <i class="fas ${a.image || 'fa-newspaper'}"></i>
        </div>
        <h4 style="font-size:13px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;">${a.headline}</h4>
        <p style="font-size:11px;color:var(--text-secondary);margin:4px 0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;">${a.summary}</p>
        <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--text-muted);margin-top:6px;">
          <span>${a.source || 'AgriNews'} • ${a.date || ''}</span>
          <span>${a.author || 'Staff'}</span>
        </div>
        <div style="display:flex;gap:6px;margin-top:8px;font-size:10px;color:var(--text-muted);">
          <span style="cursor:pointer;" onclick="event.stopPropagation();showToast('Article bookmarked!','success')"><i class="far fa-bookmark"></i> Save</span>
          <span style="cursor:pointer;" onclick="event.stopPropagation();showToast('Share link copied!','info')"><i class="fas fa-share-alt"></i> Share</span>
        </div>
      </div>
    `).join('');
  };

  // Search & filter bar
  let topHtml = `<div class="page-header"><h1><i class="fas fa-newspaper" style="color:var(--primary-green);"></i> Agri News</h1><span style="font-size:12px;color:var(--text-muted);">${articles.length} articles</span></div>`;
  topHtml += `<div class="search-bar"><i class="fas fa-search"></i><input type="text" placeholder="Search news..." oninput="filterNews(this.value)" id="news-search"></div>`;
  topHtml += `<div class="filter-tabs" id="news-filter-tabs">${cats.map((c,i) => `<button class="filter-tab ${i===0?'active':''}" data-ncat="${c.toLowerCase()}">${c}</button>`).join('')}</div>`;
  topHtml += `<div id="news-grid" class="grid-2">`;
  list.innerHTML = ''; // Clear for our new structure
  list.insertAdjacentHTML('afterbegin', topHtml);

  const grid = list.querySelector('#news-grid');
  // Move render target
  const renderFn = (items) => {
    if (items.length === 0) {
      grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--text-muted);">No articles found</div>';
      return;
    }
    grid.innerHTML = items.map(a => `
      <div class="feature-card" onclick="showArticleDetail(${a.id})" style="cursor:pointer;">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;">
          <span class="badge badge-green" style="font-size:9px;">${a.category}</span>
          <span style="font-size:10px;color:var(--text-muted);">${a.readTime || '3 min'}</span>
        </div>
        <div style="width:100%;height:80px;background:linear-gradient(135deg,var(--soft-green),var(--pale-green));border-radius:var(--radius-sm);display:flex;align-items:center;justify-content:center;margin:8px 0;font-size:36px;color:var(--primary-green);opacity:0.6;">
          <i class="fas ${a.image || 'fa-newspaper'}"></i>
        </div>
        <h4 style="font-size:13px;display:-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;">${a.headline}</h4>
        <p style="font-size:11px;color:var(--text-secondary);margin:4px 0;display:-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;">${a.summary}</p>
        <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--text-muted);margin-top:6px;">
          <span>${a.source || 'AgriNews'}</span><span>${a.date || ''}</span>
        </div>
        <div style="display:flex;gap:8px;margin-top:8px;">
          <button class="btn-primary btn-sm" style="flex:1;font-size:10px;" onclick="event.stopPropagation();showArticleDetail(${a.id})">Read More</button>
          <button class="btn-secondary btn-sm" style="font-size:10px;padding:6px 8px;" onclick="event.stopPropagation();showToast('Article saved!','success')"><i class="far fa-bookmark"></i></button>
        </div>
      </div>
    `).join('');
  };

  renderFn(articles);

  if (window.API && localStorage.getItem('fa-auth-token')) {
    API.News.getNews('agriculture', null, 1).then(res => {
      const items = (res && res.articles) || [];
      if (items.length) {
        articles.length = 0;
        items.forEach((art, i) => {
          articles.push({
            id: 1000 + i,
            category: 'Agriculture',
            headline: art.title || 'Agri News',
            summary: art.description || '',
            source: art.source || 'AgriNews',
            date: art.published_at ? String(art.published_at).slice(0, 10) : '',
            readTime: '3 min read',
            author: art.source || 'Staff',
            image: 'fa-newspaper',
            full: art.description || ''
          });
        });
        renderFn(articles);
        const countEl = list.querySelector('.page-header span');
        if (countEl) countEl.textContent = articles.length + ' articles';
      }
    }).catch(() => {});
  }

  // Filter tabs
  list.querySelectorAll('#news-filter-tabs .filter-tab').forEach(tab => {
    tab.addEventListener('click', function() {
      list.querySelectorAll('#news-filter-tabs .filter-tab').forEach(t => t.classList.remove('active'));
      this.classList.add('active');
      const cat = this.dataset.ncat;
      renderFn(cat === 'all' ? articles : articles.filter(a => a.category.toLowerCase() === cat));
    });
  });
}
window.initNewsCenter = initNewsCenter;

function filterNews(query) {
  const q = query.toLowerCase();
  document.querySelectorAll('#news-grid .feature-card').forEach(c => {
    c.style.display = c.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
}
window.filterNews = filterNews;

function showArticleDetail(id) {
  const a = (window.FarmDB && window.FarmDB.newsArticles || []).find(x => x.id === id);
  if (!a) return;
  const b = document.createElement('div'); b.className = 'modal-backdrop active'; b.onclick = function(e) { if (e.target === this) this.remove(); };
  const related = (window.FarmDB && window.FarmDB.newsArticles || []).filter(x => (a.related||[]).includes(x.id));
  b.innerHTML = `<div class="modal-box" style="max-width:600px;max-height:90vh;overflow-y:auto;padding:24px;" onclick="event.stopPropagation()">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
      <span class="badge badge-green">${a.category}</span>
      <span style="font-size:22px;cursor:pointer;color:var(--text-muted);" onclick="this.closest('.modal-backdrop').remove()">&times;</span>
    </div>
    <div style="width:100%;height:120px;background:linear-gradient(135deg,var(--soft-green),var(--pale-green));border-radius:var(--radius-md);display:flex;align-items:center;justify-content:center;margin-bottom:16px;font-size:48px;color:var(--primary-green);opacity:0.5;">
      <i class="fas ${a.image || 'fa-newspaper'}"></i>
    </div>
    <h2 style="font-size:18px;margin-bottom:6px;">${a.headline}</h2>
    <div style="font-size:11px;color:var(--text-muted);margin-bottom:12px;">${a.source || 'AgriNews'} • ${a.author || 'Staff'} • ${a.date || ''} • ${a.readTime || '3 min'}</div>
    <p style="font-size:13px;color:var(--text-secondary);margin-bottom:16px;line-height:1.7;">${a.summary}</p>
    <div style="padding:12px;background:var(--bg-card-soft);border-radius:var(--radius-md);margin-bottom:16px;font-size:13px;line-height:1.8;color:var(--text-secondary);">
      <p>${a.full || a.summary}</p>
    </div>
    ${related.length > 0 ? `<div style="margin-bottom:12px;"><strong style="font-size:12px;">📰 Related Articles</strong>${related.map(r => `<div style="padding:8px 0;font-size:12px;cursor:pointer;border-bottom:1px solid var(--border-light);display:flex;justify-content:space-between;" onclick="this.closest('.modal-backdrop').remove();showArticleDetail(${r.id})"><span>${r.headline}</span><span style="color:var(--text-muted);font-size:10px;">${r.readTime}</span></div>`).join('')}</div>` : ''}
    <div style="display:flex;gap:8px;margin-top:16px;">
      <button class="btn-primary" style="flex:1;" onclick="showToast('Article bookmarked!','success')"><i class="far fa-bookmark"></i> Bookmark</button>
      <button class="btn-secondary" onclick="showToast('Comment feature coming soon!','info')"><i class="far fa-comment"></i> Comment</button>
      <button class="btn-secondary" onclick="showToast('Share link copied!','info')"><i class="fas fa-share-alt"></i> Share</button>
    </div>
  </div>`;
  document.body.appendChild(b);
}
window.showArticleDetail = showArticleDetail;

/* ===== COMMUNITY ===== */
function initCommunityFeed() {
  const feed = document.getElementById("community-feed-container");
  if (!feed) return;
  const posts = (DB().posts || []).slice(0, 15);
  posts.forEach(post => {
    const card = document.createElement("div");
    card.className = "post-card";
    card.innerHTML = `
      <div class="post-header">
        <div class="post-author">
          <div style="width:40px;height:40px;border-radius:50%;background:var(--primary-green);color:white;display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:700;">${post.author.charAt(0)}</div>
          <div><div class="post-author-name">${post.author}</div><div class="post-author-role">${post.role || 'Farmer'}</div></div>
        </div>
        <span class="post-follow-btn" style="cursor:pointer;font-size:11px;font-weight:600;color:var(--primary-green);">${post.followed ? 'Unfollow' : 'Follow'}</span>
      </div>
      <div class="post-text">${post.text}</div>
      <div class="post-actions-bar">
        <div class="post-action" style="cursor:pointer;"><i class="${post.liked ? 'fas' : 'far'} fa-heart" style="color:${post.liked ? 'var(--danger)' : ''};"></i> <span>${post.likes} Likes</span></div>
        <div class="post-action" style="cursor:pointer;"><i class="far fa-comment"></i> <span>${post.commentsCount || 0} Comments</span></div>
      </div>
      <div class="post-comments" id="comments-${post.id}" style="display:none;">
        ${(post.comments || []).map(c => `<div class="comment-item"><strong>${c.user}:</strong> ${c.text}</div>`).join('')}
        <div style="display:flex;gap:8px;margin-top:8px;">
          <input type="text" placeholder="Add comment..." class="form-input" style="padding:6px 12px;font-size:11px;border-radius:10px;flex:1;" id="ci-${post.id}">
          <button class="btn-primary btn-sm" onclick="addComment(${post.id})">Post</button>
        </div>
      </div>
    `;
    card.querySelector('.post-follow-btn').addEventListener('click', function() {
      post.followed = !post.followed; this.textContent = post.followed ? 'Unfollow' : 'Follow';
    });
    card.querySelector('.post-actions-bar .post-action:last-child').addEventListener('click', function() {
      const box = document.getElementById(`comments-${post.id}`);
      box.style.display = box.style.display === 'none' ? 'block' : 'none';
    });
    card.querySelector('.post-actions-bar .post-action:first-child').addEventListener('click', function() {
      post.liked = !post.liked;
      post.likes += post.liked ? 1 : -1;
      this.querySelector('i').className = post.liked ? 'fas fa-heart' : 'far fa-heart';
      this.querySelector('i').style.color = post.liked ? 'var(--danger)' : '';
      this.querySelector('span').textContent = `${post.likes} Likes`;
    });
    feed.appendChild(card);
  });
}

window.addComment = function(postId) {
  const input = document.getElementById(`ci-${postId}`);
  if (!input || !input.value.trim()) return;
  const post = (DB().posts || []).find(p => p.id === postId);
  if (post) {
    if (!post.comments) post.comments = [];
    post.comments.push({ user: 'You', text: input.value });
    post.commentsCount = (post.commentsCount || 0) + 1;
    const box = document.getElementById(`comments-${postId}`);
    const newItem = document.createElement('div');
    newItem.className = 'comment-item';
    newItem.innerHTML = `<strong>You:</strong> ${input.value}`;
    box.insertBefore(newItem, box.lastElementChild);
    input.value = '';
    showToast('Comment posted!', 'success');
  }
};

/* ===== NOTIFICATIONS ===== */
function initNotificationsManager() {
  const container = document.getElementById("notif-list-container");
  if (!container) return;
  let notifs = DB().notifications || [];

  function renderNotifs() {
    const groups = {};
    (Array.isArray(notifs) ? notifs : []).forEach(n => {
      const key = n.read ? 'Earlier' : 'New';
      if (!groups[key]) groups[key] = [];
      groups[key].push(n);
    });
    let html = '';
    ['New', 'Earlier'].forEach(group => {
      if (groups[group]) {
        html += `<div class="notif-section-title">${group} (${groups[group].length})</div>`;
        groups[group].forEach(n => {
          const icons = { weather: 'fa-cloud-sun', market: 'fa-chart-line', ai: 'fa-robot', finance: 'fa-wallet', government: 'fa-landmark', community: 'fa-users', scheme: 'fa-landmark' };
          const icon = icons[n.type] || (n.icon || 'fa-bell');
          html += `
            <div class="notif-card ${n.read ? '' : 'unread'}" onclick="markNotifRead(this, '${n.id}')">
              <div class="notif-icon-circle ${n.type}"><i class="fas ${icon}"></i></div>
              <div class="notif-body">
                <h4 class="notif-title">${n.title}</h4>
                <p class="notif-desc">${n.desc || n.text || ''}</p>
                <div class="notif-time">${n.time || 'Just now'} ${n.priority ? '• '+n.priority : ''}</div>
              </div>
              ${n.read ? '' : '<div class="notif-unread-dot"></div>'}
            </div>`;
        });
      }
    });
    if (!html) html = '<div style="text-align:center;padding:40px;color:var(--text-muted);">No notifications yet</div>';
    container.innerHTML = html;
  }

  if (window.API && localStorage.getItem('fa-auth-token')) {
    API.Notification.list().then(res => {
      const items = (res && res.items) || [];
      if (items.length) {
        notifs = items.map(n => ({
          id: n.notification_id || n.id,
          type: n.notification_type || 'ai',
          title: n.title || 'Update',
          desc: n.message || '',
          time: n.created_at ? String(n.created_at).slice(0, 16) : 'Just now',
          read: !!n.is_read,
          icon: n.icon || 'fa-bell',
          priority: n.priority || ''
        }));
        renderNotifs();
      }
    }).catch(() => {});
  }
  renderNotifs();

  const clearBtn = document.getElementById("notif-clear-all");
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      if (window.API && localStorage.getItem('fa-auth-token')) {
        API.Notification.markAllRead().catch(() => {});
      }
      container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-muted);">All cleared</div>';
      showToast('Notifications cleared', 'warning');
    });
  }
}
window.markNotifRead = function(el, id) {
  if (el.classList.contains('unread')) {
    el.classList.remove('unread');
    if (window.API && id && localStorage.getItem('fa-auth-token')) {
      API.Notification.markRead(id).catch(() => {});
    }
  }
  showToast('Notification', 'info');
};

/* ===== WATER & IRRIGATION ===== */
function initWaterManagement(containerId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const sources = (DB().waterSources || []).slice(0, 10);
  let html = `<div class="grid-2">`;
  sources.forEach(s => {
    const badge = s.status === 'Critical' ? 'badge-danger' : s.status === 'Low' ? 'badge-warning' : 'badge-green';
    html += `
      <div class="feature-card" onclick="showToast('${s.name}: ${s.currentLevel} • ${s.depth} • Last maint: ${s.lastMaintenance}','info')">
        <i class="fas fa-water"></i>
        <h4>${s.name}</h4>
        <p>${s.type} • ${s.currentLevel}</p>
        <div class="progress-bar"><div class="progress-fill" style="width:${parseInt(s.currentLevel)}%;background:${s.status==='Critical'?'var(--danger)':s.status==='Low'?'var(--warning)':'var(--primary-green)'};"></div></div>
        <span class="badge ${badge}">${s.status}</span>
      </div>`;
  });
  html += `</div>
    <div class="grid-2" style="margin-top:12px;">
      <div class="calc-card" onclick="showToast('Total water capacity: 1,250 KL across all sources','info')"><i class="fas fa-chart-pie" style="font-size:24px;color:var(--primary-green);display:block;margin-bottom:6px;"></i><h4>Usage Report</h4></div>
      <div class="calc-card" onclick="showToast('Tip: Drip irrigation saves 40% water. Install soil moisture sensors.','success')"><i class="fas fa-lightbulb" style="font-size:24px;color:var(--warning);display:block;margin-bottom:6px;"></i><h4>Saving Tips</h4></div>
      <div class="calc-card" onclick="showToast('Rainwater: 1 acre rooftop collects ~50,000L/year. Build storage tank.','info')"><i class="fas fa-cloud-rain" style="font-size:24px;color:var(--info);display:block;margin-bottom:6px;"></i><h4>Rainwater Guide</h4></div>
      <div class="calc-card" onclick="showToast('AI: Irrigate Plot C tomorrow morning. Soil moisture dropping to 45%.','success')"><i class="fas fa-robot" style="font-size:24px;color:var(--primary-green);display:block;margin-bottom:6px;"></i><h4>AI Suggestion</h4></div>
    </div>`;
  el.innerHTML = html;
};
window.initWaterManagement = initWaterManagement;

function showIrrigationScheduler() {
  const schedules = (DB().irrigationSchedules || []).slice(0, 8);
  let html = `<div style="display:flex;flex-direction:column;gap:8px;">`;
  schedules.forEach(s => {
    const bc = s.status === 'Overdue' ? 'danger' : s.status === 'Due Today' ? 'warning' : 'success';
    html += `<div class="alert-strip ${bc}" onclick="showToast('${s.crop}: ${s.method} • ${s.duration} • ${s.frequency}','info')">
      <div class="alert-content"><div><strong>${s.crop}</strong> • Plot ${s.plotId}<div style="font-size:10px;color:var(--text-muted);">${s.method} • ${s.duration} • Next: ${s.nextWatering}</div></div></div>
      <span class="badge badge-${bc}">${s.status}</span>
    </div>`;
  });
  html += `</div>`;
  const el = document.getElementById('irrigation-schedule-content');
  if (el) el.innerHTML = html;
};
window.showIrrigationScheduler = showIrrigationScheduler;

function showWaterCalculator() {
  showToast('Water requirements: Rice 1200mm, Cotton 700mm, Wheat 450mm, Sugarcane 2000mm per season', 'info');
}
window.showWaterCalculator = showWaterCalculator;

/* ===== FERTILIZER ===== */
function initFertilizerCenter(containerId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const guides = (DB().fertilizerGuides || []).slice(0, 8);
  let html = `<div class="filter-tabs"><button class="filter-tab active" data-fert="all">All</button><button class="filter-tab" data-fert="Rice">Rice</button><button class="filter-tab" data-fert="Cotton">Cotton</button><button class="filter-tab" data-fert="Wheat">Wheat</button><button class="filter-tab" data-fert="Maize">Maize</button></div>`;
  html += `<div id="fert-list">`;
  guides.forEach(g => {
    html += `<div class="price-card fert-card" data-crop="${g.crop}" onclick="showToast('${g.crop}: ${g.npkDose} • ${g.schedule} • ${g.costPerHa}','info')">
      <div class="price-info"><div class="price-icon" style="background:var(--soft-green);color:var(--primary-green);"><i class="fas fa-leaf"></i></div>
        <div><div class="price-crop">${g.crop}</div><div style="font-size:10px;color:var(--text-muted);">${g.npkDose} • ${g.schedule}</div></div></div>
      <div style="text-align:right;"><span class="badge badge-green">${g.type}</span><div style="font-size:10px;color:var(--text-muted);">${g.costPerHa}</div></div>
    </div>`;
  });
  html += `</div>
    <div class="grid-2" style="margin-top:12px;">
      <div class="calc-card" onclick="showToast('NPK Calculator: For 1 acre Rice - Urea 55kg, DAP 25kg, MOP 15kg','info')"><i class="fas fa-calculator" style="font-size:24px;color:var(--primary-green);display:block;margin-bottom:6px;"></i><h4>NPK Calculator</h4></div>
      <div class="calc-card" onclick="showToast('Organic: Vermicompost 2t/ha, Neem cake 500kg/ha, Green manure for nitrogen.','success')"><i class="fas fa-seedling" style="font-size:24px;color:var(--success);display:block;margin-bottom:6px;"></i><h4>Organic Guide</h4></div>
      <div class="calc-card" onclick="showToast('Nearby shops: Krishi Seed Centre (2km), Bharat Beej Bhandar (4km)','info')"><i class="fas fa-store" style="font-size:24px;color:var(--primary-green);display:block;margin-bottom:6px;"></i><h4>Nearby Shops</h4></div>
      <div class="calc-card" onclick="showToast('Subsidy: 50% on organic fertilizers under PKVY. Apply at agriculture dept.','info')"><i class="fas fa-landmark" style="font-size:24px;color:var(--warning);display:block;margin-bottom:6px;"></i><h4>Subsidies</h4></div>
    </div>`;
  el.innerHTML = html;

  el.querySelectorAll('.filter-tab').forEach(tab => {
    tab.addEventListener('click', function() {
      el.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
      this.classList.add('active');
      const crop = this.dataset.fert;
      el.querySelectorAll('.fert-card').forEach(c => {
        c.style.display = crop === 'all' || c.dataset.crop === crop ? 'flex' : 'none';
      });
    });
  });
};
window.initFertilizerCenter = initFertilizerCenter;

/* ===== EQUIPMENT ===== */
function initEquipmentRental(containerId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const items = (DB().equipmentRentals || []).slice(0, 8);
  let html = `<div class="filter-tabs"><button class="filter-tab active" data-eq="all">All</button><button class="filter-tab" data-eq="Tractor">Tractors</button><button class="filter-tab" data-eq="Harvester">Harvesters</button><button class="filter-tab" data-eq="Drone">Drones</button></div>`;
  html += `<div id="equip-list" class="grid-2">`;
  items.forEach(e => {
    html += `<div class="feature-card equip-card" data-type="${e.type}" onclick="showToast('${e.name}: ${e.dailyRate} • ${e.distance} away • ⭐${e.rating}','info')">
      <i class="fas fa-tractor"></i>
      <h4>${e.name}</h4>
      <p>${e.dailyRate} • ${e.distance}</p>
      <span class="badge ${e.available?'badge-green':'badge-warning'}">${e.available?'Available':'Booked'}</span>
      <span style="font-size:11px;font-weight:600;color:var(--primary-green);margin-left:6px;">${e.rating}★</span>
      <button class="btn-primary btn-sm" style="margin-top:8px;width:100%;" onclick="event.stopPropagation();showToast('${e.name} booked for tomorrow! Confirmation sent.','success')">Book Now</button>
    </div>`;
  });
  html += `</div>`;
  el.innerHTML = html;

  el.querySelectorAll('.filter-tab').forEach(tab => {
    tab.addEventListener('click', function() {
      el.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
      this.classList.add('active');
      const type = this.dataset.eq;
      el.querySelectorAll('.equip-card').forEach(c => {
        c.style.display = type === 'all' || c.dataset.type === type ? 'block' : 'none';
      });
    });
  });
};
window.initEquipmentRental = initEquipmentRental;

/* ===== SEEDS ===== */
function initSeedCenter(containerId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const seeds = (DB().seedInventory || []).slice(0, 10);
  let html = `<div class="grid-2">`;
  seeds.forEach(s => {
    html += `<div class="feature-card" onclick="showToast('${s.name}: ${s.price} • Yield: ${s.yield} • ${s.duration} • ⭐${s.rating}','info')">
      <i class="fas fa-seedling"></i>
      <h4 style="font-size:12px;">${s.name}</h4>
      <p style="font-size:10px;">${s.variety} • ${s.price}</p>
      <p style="font-size:10px;color:var(--text-muted);">Yield: ${s.yield} • ${s.duration}</p>
      <span class="badge badge-green">${s.stock}</span>
      <span style="font-size:10px;color:var(--text-muted);margin-left:6px;">⭐${s.rating}</span>
      <button class="btn-primary btn-sm" style="margin-top:6px;width:100%;" onclick="event.stopPropagation();showToast('Ordering ${s.name} from ${s.dealer}...','success')">Order</button>
    </div>`;
  });
  html += `</div>
    <div class="grid-2" style="margin-top:12px;">
      <div class="calc-card" onclick="showToast('Seed rate: Rice 20kg/acre, Wheat 40kg/acre, Maize 8kg/acre, Cotton 2kg/acre','info')"><i class="fas fa-calculator" style="font-size:20px;color:var(--primary-green);display:block;margin-bottom:6px;"></i><h4>Seed Calculator</h4></div>
      <div class="calc-card" onclick="showToast('Store seeds below 25°C in airtight containers with silica gel.','info')"><i class="fas fa-warehouse" style="font-size:20px;color:var(--primary-green);display:block;margin-bottom:6px;"></i><h4>Storage Guide</h4></div>
    </div>`;
  el.innerHTML = html;
};
window.initSeedCenter = initSeedCenter;

/* ===== SOIL ===== */
function initSoilHealth(containerId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const soils = (DB().soilHealth || []).slice(0, 6);
  let html = `<div class="grid-2">`;
  soils.forEach(s => {
    const score = s.healthScore || 70;
    const color = score > 80 ? 'var(--primary-green)' : score > 60 ? 'var(--warning)' : 'var(--danger)';
    html += `<div class="feature-card" onclick="showToast('Plot ${s.plotId}: pH ${s.pH}, N:${s.nitrogen}, P:${s.phosphorus}, K:${s.potassium}','info')">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <i class="fas fa-earth-asia" style="color:var(--mud-brown);"></i>
        <span style="font-size:18px;font-weight:800;color:${color};">${score}%</span>
      </div>
      <h4>Plot ${s.plotId} • ${s.soilType}</h4>
      <p style="font-size:10px;color:var(--text-muted);">pH: ${s.pH} • OC: ${s.organicCarbon}</p>
      <div class="progress-bar"><div class="progress-fill" style="width:${score}%;background:${color};"></div></div>
      <span class="badge badge-green">${s.testDate}</span>
    </div>`;
  });
  html += `</div>
    <div class="calc-card" style="margin-top:12px;cursor:pointer;" onclick="showToast('${soils[0] ? soils[0].recommendation : 'Test soil regularly for best results'}','success')">
      <i class="fas fa-robot" style="color:var(--primary-green);margin-right:8px;"></i>
      <strong>AI Recommendation:</strong> ${soils[0] ? soils[0].recommendation : 'Maintain soil health'}
    </div>`;
  el.innerHTML = html;
};
window.initSoilHealth = initSoilHealth;

/* ===== MARKET PRICES ===== */
function initMarketPrices(containerId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const prices = (DB().marketPrices || []).slice(0, 15);
  let html = `<div class="search-bar"><i class="fas fa-search"></i><input type="text" placeholder="Search commodity..." oninput="filterPrices(this.value)" id="price-search"></div>`;
  html += `<div class="responsive-table"><table><thead><tr><th>Commodity</th><th>Price</th><th>Change</th><th>Mandi</th><th>Demand</th></tr></thead><tbody id="price-tbody">`;
  prices.forEach(p => {
    const up = p.trend === 'up';
    html += `<tr class="price-row" onclick="showToast('${p.commodity}: ₹${p.price}/${p.unit} at ${p.mandi}. MSP: ₹${p.msp}','info')">
      <td><strong>${p.commodity}</strong></td>
      <td style="font-weight:700;">₹${p.price.toLocaleString()}</td>
      <td style="color:${up?'var(--success)':'var(--danger)'};">${up?'▲':'▼'} ${p.change}</td>
      <td>${p.mandi}</td>
      <td><span class="badge ${p.demand==='High'?'badge-green':p.demand==='Medium'?'badge-warning':'badge-danger'}">${p.demand}</span></td>
    </tr>`;
  });
  html += `</tbody></table></div>
    <div style="display:flex;gap:8px;margin-top:12px;">
      <button class="btn-primary btn-sm" onclick="showToast('Price alerts set for your tracked crops!','success')"><i class="fas fa-bell"></i> Set Alert</button>
      <button class="btn-secondary btn-sm" onclick="showToast('MSP Kharif 2026: Rice ₹2,300, Cotton ₹7,100, Maize ₹2,100, Groundnut ₹5,700/qtl','info')"><i class="fas fa-landmark"></i> MSP Info</button>
    </div>`;
  el.innerHTML = html;
};
window.initMarketPrices = initMarketPrices;

function filterPrices(query) {
  const q = query.toLowerCase();
  document.querySelectorAll('.price-row').forEach(r => {
    r.style.display = r.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
}
window.filterPrices = filterPrices;

/* ===== CROP PROTECTION ===== */
function initCropProtection(containerId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const diseases = (DB().cropDiseases || []).slice(0, 10);
  let html = `<div class="filter-tabs"><button class="filter-tab active" data-dis="all">All</button><button class="filter-tab" data-dis="Fungal">Fungal</button><button class="filter-tab" data-dis="Pest">Pests</button><button class="filter-tab" data-dis="Viral">Viral</button></div>`;
  html += `<div id="disease-list">`;
  diseases.forEach(d => {
    html += `<div class="price-card disease-card" data-type="${d.type}" onclick="showToast('${d.disease}: ${d.organicSolution} | Prevention: ${d.prevention}','info')">
      <div class="price-info"><div class="price-icon" style="background:${d.severity==='High'?'var(--sun-soft)':'var(--sky-soft)'};color:${d.severity==='High'?'var(--danger)':'var(--primary-green)'};"><i class="fas fa-bug"></i></div>
        <div><div class="price-crop">${d.disease}</div><div style="font-size:10px;color:var(--text-muted);">${d.crop} • ${d.symptoms.substring(0,45)}...</div></div></div>
      <div style="text-align:right;"><span class="badge ${d.severity==='High'?'badge-danger':'badge-warning'}">${d.severity}</span>
        <div style="font-size:9px;color:var(--text-muted);">${d.type}</div>
        <span style="font-size:9px;color:var(--text-muted);">${d.season}</span>
      </div>
    </div>`;
  });
  html += `</div>
    <div class="grid-2" style="margin-top:12px;">
      <div class="calc-card" onclick="showToast('⚠️ Emergency: Fall Armyworm reported in nearby maize fields. Scout your fields immediately!','danger')"><i class="fas fa-exclamation-triangle" style="font-size:20px;color:var(--danger);display:block;margin-bottom:6px;"></i><h4>Emergency Alerts</h4></div>
      <div class="calc-card" onclick="showToast('Nearby agro-chemical stores: Krishi Pharmacy (3km), Agro Chem Centre (5km)','info')"><i class="fas fa-store" style="font-size:20px;color:var(--primary-green);display:block;margin-bottom:6px;"></i><h4>Medicine Stores</h4></div>
    </div>`;
  el.innerHTML = html;

  el.querySelectorAll('.filter-tab').forEach(tab => {
    tab.addEventListener('click', function() {
      el.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
      this.classList.add('active');
      const type = this.dataset.dis;
      el.querySelectorAll('.disease-card').forEach(c => {
        c.style.display = type === 'all' || c.dataset.type === type ? 'flex' : 'none';
      });
    });
  });
};
window.initCropProtection = initCropProtection;

/* ===== LIVESTOCK (Enhanced Management) ===== */
function initLivestockHealth(containerId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const animals = DB().livestock || [];
  const tabTitles = ["All","Cows","Buffalo","Goat","Chicken"];
  let activeTab = "all";

  const render = (filter) => {
    const filtered = filter === 'all' ? animals : animals.filter(a => a.type.toLowerCase() === filter);
    let html = `<div class="page-header"><h1><i class="fas fa-cow" style="color:var(--primary-green);"></i> Livestock Management</h1><span style="font-size:12px;color:var(--text-muted);">${animals.length} animals</span></div>`;
    html += `<div class="filter-tabs" id="ls-filter-tabs">${tabTitles.map((t,i) => `<button class="filter-tab ${i===0?'active':''}" data-ls="${t.toLowerCase()}">${t}</button>`).join('')}</div>`;

    // Stats row
    const healthy = animals.filter(a => a.health === 'Healthy').length;
    const totalYield = animals.reduce((sum, a) => sum + (parseInt(a.yield) || 0), 0);
    html += `<div class="grid-2" style="margin-bottom:12px;">
      <div class="stat-box"><i class="fas fa-heart" style="color:var(--primary-green);"></i><div class="stat-box-num">${healthy}/${animals.length}</div><div class="stat-box-label">Healthy</div></div>
      <div class="stat-box"><i class="fas fa-chart-line" style="color:var(--primary-green);"></i><div class="stat-box-num">${totalYield}${animals.some(a=>a.type==='Chicken')?' eggs':' L'}</div><div class="stat-box-label">Total Daily Yield</div></div>
    </div>`;

    // Animal cards
    html += `<div class="grid-2" id="ls-grid">`;
    filtered.slice(0, 12).forEach(a => {
      const hp = a.health === 'Healthy' ? 100 : a.health === 'Vaccination Due' ? 60 : 40;
      const hc = hp > 80 ? 'var(--primary-green)' : hp > 50 ? 'var(--warning)' : 'var(--danger)';
      html += `<div class="feature-card" onclick="showLivestockDetail(${a.id})" style="cursor:pointer;">
        <div style="display:flex;justify-content:space-between;">
          <i class="fas ${a.icon || 'fa-cow'}" style="font-size:24px;color:var(--mud-brown);"></i>
          <span class="badge ${a.health === 'Healthy' ? 'badge-green' : 'badge-warning'}">${a.health}</span>
        </div>
        <h4 style="font-size:13px;margin:4px 0 2px;">${a.name}</h4>
        <p style="font-size:10px;color:var(--text-muted);">${a.breed} • ${a.age}</p>
        <p style="font-size:16px;font-weight:800;color:var(--primary-green);">${a.yield}</p>
        <div style="display:flex;gap:4px;margin-top:4px;">
          <div style="flex:1;"><div class="progress-bar"><div class="progress-fill" style="width:${hp}%;background:${hc};"></div></div><span style="font-size:8px;color:var(--text-muted);">Health</span></div>
          <span style="font-size:9px;color:var(--text-muted);">Feed: ${a.feed}</span>
        </div>
        <div style="display:flex;gap:4px;margin-top:6px;">
          <button class="btn-primary btn-sm" style="flex:1;font-size:9px;" onclick="event.stopPropagation();showToast('Vaccination reminder set for ${a.name}!','success')">Vaccinate</button>
          <button class="btn-secondary btn-sm" style="font-size:9px;padding:4px 8px;" onclick="event.stopPropagation();showToast('Health record for ${a.name}: Last checkup - ${a.vaccineDate || 'N/A'}','info')">Records</button>
        </div>
      </div>`;
    });
    html += `</div>`;

    // Action buttons
    html += `<div style="display:flex;gap:6px;margin-top:12px;flex-wrap:wrap;">
      <button class="btn-primary btn-sm" onclick="showToast('Booking veterinarian for farm visit...','success')"><i class="fas fa-user-md"></i> Book Vet</button>
      <button class="btn-secondary btn-sm" onclick="showToast('Vaccination schedule: Cows 6mo, Buffalo 6mo, Goats 12mo, Chickens 45 days','info')"><i class="fas fa-syringe"></i> Schedule</button>
      <button class="btn-secondary btn-sm" onclick="showToast('Feed calculation: Cow 2% BW, Buffalo 2.5% BW, Goat 3% BW, Chicken 120g/day','info')"><i class="fas fa-calculator"></i> Feed Calc</button>
      <button class="btn-secondary btn-sm" onclick="showToast('Breeding recommendations: Best mating season Oct-Dec for dairy animals','info')"><i class="fas fa-heart"></i> Breeding</button>
      <button class="btn-secondary btn-sm" onclick="showToast('🐄 Livestock marketplace - Buy/Sell cattle coming soon!','info')"><i class="fas fa-store"></i> Marketplace</button>
    </div>`;
    return html;
  };

  el.innerHTML = render('all');

  el.addEventListener('click', function(e) {
    const tab = e.target.closest('[data-ls]');
    if (tab) {
      el.querySelectorAll('[data-ls]').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      el.innerHTML = render(tab.dataset.ls);
    }
  });
};
window.initLivestockHealth = initLivestockHealth;

function showLivestockDetail(id) {
  const a = (window.FarmDB && window.FarmDB.livestock || []).find(x => x.id === id);
  if (!a) return;
  const b = document.createElement('div'); b.className = 'modal-backdrop active'; b.onclick = function(e) { if (e.target === this) this.remove(); };
  b.innerHTML = `<div class="modal-box" style="max-width:500px;padding:24px;" onclick="event.stopPropagation()">
    <div style="display:flex;justify-content:space-between;margin-bottom:12px;">
      <h2>${a.name}</h2>
      <span style="font-size:22px;cursor:pointer;color:var(--text-muted);" onclick="this.closest('.modal-backdrop').remove()">&times;</span>
    </div>
    <div style="text-align:center;margin-bottom:16px;">
      <i class="fas ${a.icon || 'fa-cow'}" style="font-size:48px;color:var(--mud-brown);"></i>
      <h3 style="font-size:16px;margin-top:8px;">${a.breed}</h3>
    </div>
    <div class="grid-2" style="margin-bottom:12px;">
      <div class="stat-box"><div class="stat-box-num">${a.age || 'N/A'}</div><div class="stat-box-label">Age</div></div>
      <div class="stat-box"><div class="stat-box-num">${a.yield || 'N/A'}</div><div class="stat-box-label">Daily Yield</div></div>
      <div class="stat-box"><div class="stat-box-num">${a.feed || 'N/A'}</div><div class="stat-box-label">Feed</div></div>
      <div class="stat-box"><div class="stat-box-num">${a.vaccineDate || 'N/A'}</div><div class="stat-box-label">Last Vaccine</div></div>
    </div>
    <div style="display:flex;gap:8px;">
      <button class="btn-primary" style="flex:1;" onclick="showToast('Booking vet consultation for ${a.name}...','success')">Consult Vet</button>
      <button class="btn-secondary" onclick="showToast('Health record: ${a.health} • Weight: ${a.weight || '350 kg'} • Temp: Normal','info')">Health Check</button>
    </div>
  </div>`;
  document.body.appendChild(b);
}
window.showLivestockDetail = showLivestockDetail;

/* ===== GOVERNMENT SCHEMES (Enhanced) ===== */
function initGovSchemes(containerId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const schemes = DB().govSchemes || [];
  const cats = ["All","Central","State","Income Support","Subsidy","Insurance","Loan","Organic Farming","Livestock","Water","Energy","Mechanization","Development"];
  let html = `<div class="page-header"><h1><i class="fas fa-landmark" style="color:var(--primary-green);"></i> Government Schemes</h1><span style="font-size:12px;color:var(--text-muted);">${schemes.length} schemes available</span></div>`;
  html += `<div class="search-bar"><i class="fas fa-search"></i><input type="text" placeholder="Search schemes by name, category, benefit..." oninput="filterSchemes(this.value)" id="scheme-search"></div>`;
  html += `<div class="filter-tabs" id="scheme-filter-tabs">${cats.map((c,i) => `<button class="filter-tab ${i===0?'active':''}" data-scat="${c.toLowerCase()}">${c}</button>`).join('')}</div>`;
  html += `<div id="schemes-list" class="grid-2">`;
  schemes.forEach(s => {
    const sc = s.deadline && new Date(s.deadline) < new Date(Date.now()+86400000*15) ? 'badge-danger' : 'badge-green';
    html += `<div class="feature-card scheme-card" data-search="${s.name} ${s.category} ${s.type} ${s.benefit}" onclick="showSchemeDetail(${s.id})" style="cursor:pointer;">
      <div style="display:flex;justify-content:space-between;"><i class="fas ${s.type==='Insurance'?'fa-shield-halved':s.type==='Subsidy'?'fa-gift':s.type==='Loan'?'fa-hand-holding-usd':s.type==='Pension'?'fa-money-bill-wave':s.type==='Income Support'?'fa-wallet':'fa-landmark'}" style="font-size:22px;color:var(--primary-green);"></i><span class="${sc}">${s.status}</span></div>
      <h4 style="font-size:13px;margin:6px 0 3px;">${s.name}</h4>
      <p style="font-size:10px;color:var(--text-muted);">${s.category} • ${s.type || 'Scheme'}</p>
      <p style="font-size:11px;margin:4px 0;color:var(--text-secondary);">${s.description.substring(0,60)}...</p>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px;">
        <span style="font-size:14px;font-weight:800;color:var(--primary-green);">${s.benefit}</span>
        <span style="font-size:10px;color:var(--text-muted);">📅 ${s.deadline || 'Open'}</span>
      </div>
      <div style="display:flex;gap:4px;margin-top:6px;">
        <button class="btn-primary btn-sm" style="flex:1;font-size:10px;" onclick="event.stopPropagation();showToast('Opening ${s.name} application form...','success')">Apply Now</button>
        <button class="btn-secondary btn-sm" style="font-size:10px;padding:6px 8px;" onclick="event.stopPropagation();showToast('${s.name} saved to bookmarks','success')"><i class="far fa-bookmark"></i></button>
        <button class="btn-secondary btn-sm" style="font-size:10px;padding:6px 8px;" onclick="event.stopPropagation();showToast('Share link generated!','info')"><i class="fas fa-share-alt"></i></button>
      </div>
    </div>`;
  });
  html += `</div>`;
  el.innerHTML = html;

  // Filter tabs
  el.querySelectorAll('#scheme-filter-tabs .filter-tab').forEach(tab => {
    tab.addEventListener('click', function() {
      el.querySelectorAll('#scheme-filter-tabs .filter-tab').forEach(t => t.classList.remove('active'));
      this.classList.add('active');
      const cat = this.dataset.scat;
      el.querySelectorAll('.scheme-card').forEach(c => {
        const txt = c.dataset.search.toLowerCase();
        c.style.display = cat === 'all' || txt.includes(cat) ? '' : 'none';
      });
    });
  });
};
window.initGovSchemes = initGovSchemes;

function filterSchemes(query) {
  const q = query.toLowerCase();
  document.querySelectorAll('.scheme-card').forEach(s => {
    s.style.display = s.dataset.search.toLowerCase().includes(q) ? '' : 'none';
  });
}
window.filterSchemes = filterSchemes;

/* ===== LEARNING (Coursera-style) ===== */
function initLearningCenter() {
  const el = document.getElementById("learning-content");
  if (!el) return;
  const courses = DB().learningCourses || [];
  const cats = ["All","Beginner","Intermediate","Advanced","tech","soil","livestock","finance","water","pest","mechanization"];

  const courseCard = (c) => `
    <div class="feature-card" onclick="showCourseDetail(${c.id})" style="cursor:pointer;">
      <div style="display:flex;justify-content:space-between;"><i class="fas ${c.image || 'fa-graduation-cap'}" style="font-size:24px;color:var(--primary-green);"></i>
        <span class="badge ${c.level==='Beginner'?'badge-green':c.level==='Intermediate'?'badge-warning':'badge-danger'}">${c.level}</span>
      </div>
      <h4 style="font-size:13px;margin:6px 0 3px;">${c.title}</h4>
      <p style="font-size:10px;color:var(--text-muted);">${c.instructor || 'Expert'} • ⭐${c.rating} (${(c.students||0).toLocaleString()} students)</p>
      <p style="font-size:11px;color:var(--text-secondary);margin:4px 0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;">${(c.description||'').substring(0,80)}...</p>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px;">
        <span style="font-size:11px;color:var(--text-muted);">${c.duration || 'N/A'}</span>
        <span style="font-size:12px;font-weight:700;color:var(--primary-green);">${c.price || 'Free'}</span>
      </div>
      ${c.percent !== undefined && c.percent > 0 ? `<div style="margin-top:6px;"><div class="progress-bar"><div class="progress-fill" style="width:${c.percent}%"></div></div><span style="font-size:9px;color:var(--text-muted);">${c.percent}% complete</span></div>` : ''}
      <button class="btn-primary btn-sm" style="width:100%;margin-top:6px;" onclick="event.stopPropagation();showCourseDetail(${c.id})">${c.percent >= 100 ? 'Review' : c.percent > 0 ? 'Continue' : 'Start Course'}</button>
    </div>`;

  let html = `<div class="page-header"><h1><i class="fas fa-graduation-cap" style="color:var(--primary-green);"></i> Learning Center</h1><span style="font-size:12px;color:var(--text-muted);">${courses.length} courses</span></div>`;
  html += `<div class="filter-tabs" id="learn-filter-tabs">${cats.map((c,i) => `<button class="filter-tab ${i===0?'active':''}" data-lcat="${c.toLowerCase()}">${c.charAt(0).toUpperCase()+c.slice(1)}</button>`).join('')}</div>`;

  // Continue learning section
  const inProgress = courses.filter(c => c.percent > 0 && c.percent < 100);
  if (inProgress.length > 0) {
    html += `<h3 style="font-size:15px;margin:12px 0 8px;"><i class="fas fa-play-circle" style="color:var(--primary-green);"></i> Continue Learning</h3>`;
    html += `<div class="grid-2">${inProgress.map(courseCard).join('')}</div>`;
  }

  html += `<h3 style="font-size:15px;margin:12px 0 8px;"><i class="fas fa-book" style="color:var(--primary-green);"></i> All Courses</h3>`;
  html += `<div class="grid-2" id="all-courses-grid">${courses.map(courseCard).join('')}</div>`;
  el.innerHTML = html;

  el.querySelectorAll('#learn-filter-tabs .filter-tab').forEach(tab => {
    tab.addEventListener('click', function() {
      el.querySelectorAll('#learn-filter-tabs .filter-tab').forEach(t => t.classList.remove('active'));
      this.classList.add('active');
      const cat = this.dataset.lcat;
      const grid = document.getElementById('all-courses-grid');
      if (cat === 'all') { grid.innerHTML = courses.map(courseCard).join(''); return; }
      const filtered = courses.filter(c => c.level?.toLowerCase() === cat || c.category?.toLowerCase() === cat);
      grid.innerHTML = filtered.length > 0 ? filtered.map(courseCard).join('') : '<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--text-muted);">No courses in this category</div>';
    });
  });
}
window.initLearningCenter = initLearningCenter;

function showCourseDetail(id) {
  const c = (window.FarmDB && window.FarmDB.learningCourses || []).find(x => x.id === id);
  if (!c) return;
  const b = document.createElement('div'); b.className = 'modal-backdrop active'; b.onclick = function(e) { if (e.target === this) this.remove(); };
  const lessons = c.lessons || [];
  b.innerHTML = `<div class="modal-box" style="max-width:600px;max-height:90vh;overflow-y:auto;padding:24px;" onclick="event.stopPropagation()">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
      <div><span class="badge badge-green">${c.level}</span> <span class="badge badge-warning">⭐${c.rating}</span></div>
      <span style="font-size:22px;cursor:pointer;color:var(--text-muted);" onclick="this.closest('.modal-backdrop').remove()">&times;</span>
    </div>
    <h2 style="font-size:18px;margin-bottom:6px;">${c.title}</h2>
    <p style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">${c.instructor || 'Expert'} • ${(c.students||0).toLocaleString()} students enrolled</p>
    <p style="font-size:13px;color:var(--text-secondary);margin-bottom:12px;">${c.description || ''}</p>
    <div class="grid-3" style="margin-bottom:12px;">
      <div class="stat-box"><div class="stat-box-num" style="font-size:16px;">${c.duration || 'N/A'}</div><div class="stat-box-label">Duration</div></div>
      <div class="stat-box"><div class="stat-box-num" style="font-size:16px;">${c.lessons ? c.lessons.length : 0}</div><div class="stat-box-label">Lessons</div></div>
      <div class="stat-box"><div class="stat-box-num" style="font-size:16px;">${c.price || 'Free'}</div><div class="stat-box-label">Price</div></div>
    </div>
    ${c.certificate ? `<div style="padding:8px 12px;background:var(--sun-soft);border-radius:var(--radius-sm);margin-bottom:12px;font-size:12px;"><i class="fas fa-certificate" style="color:var(--warning);"></i> <strong>Certificate</strong> of completion included</div>` : ''}
    ${c.percent !== undefined ? `<div style="margin-bottom:12px;"><strong style="font-size:12px;">📊 Progress: ${c.percent}%</strong><div class="progress-bar" style="margin-top:4px;"><div class="progress-fill" style="width:${c.percent}%"></div></div></div>` : ''}
    <h4 style="font-size:14px;margin-bottom:8px;">📚 Lessons (${lessons.length})</h4>
    ${lessons.map((l,i) => `
      <div style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border-light);font-size:12px;">
        <div style="width:24px;height:24px;border-radius:50%;background:${l.completed ? 'var(--primary-green)' : 'var(--border-light)'};color:${l.completed ? 'white' : 'var(--text-muted)'};display:flex;align-items:center;justify-content:center;font-size:10px;flex-shrink:0;">${l.completed ? '<i class="fas fa-check"></i>' : i+1}</div>
        <div style="flex:1;"><strong>${l.title}</strong><div style="font-size:10px;color:var(--text-muted);">${l.duration || ''}</div></div>
        <button class="btn-primary btn-sm" style="font-size:9px;padding:4px 10px;" onclick="showToast('Playing ${l.title}...','info')">Watch</button>
      </div>
    `).join('')}
    <div style="display:flex;gap:8px;margin-top:16px;">
      <button class="btn-primary" style="flex:1;" onclick="showToast('Starting ${c.title} - lesson 1...','success')"><i class="fas fa-play"></i> ${c.percent > 0 ? 'Continue' : 'Start Learning'}</button>
      <button class="btn-secondary" onclick="showToast('Quiz feature: Test your knowledge!','info')"><i class="fas fa-question-circle"></i> Quiz</button>
    </div>
  </div>`;
  document.body.appendChild(b);
}
window.showCourseDetail = showCourseDetail;

/* ===== SUSTAINABILITY ===== */
function initSustainability() {
  const el = document.getElementById("sustainability-content");
  if (!el) return;
  const sd = DB().sustainabilityData || {};
  const insights = sd.waterUsageAnalytics || [];
  const maxUsage = Math.max(...insights.map(i => i.usage), 1);
  const initiatives = sd.initiatives || [];

  let html = `<div class="page-header"><h1><i class="fas fa-leaf" style="color:var(--primary-green);"></i> Sustainability Dashboard</h1><span style="font-size:12px;color:var(--text-muted);">Environmental Score: ${sd.environmentalScore || 0}/100</span></div>`;

  // Stats row
  html += `<div class="grid-2" style="margin-bottom:12px;">
    <div class="stat-box"><i class="fas fa-tint" style="color:var(--primary-green);"></i><div class="stat-box-num">${(sd.waterConserved || 0).toLocaleString()} L</div><div class="stat-box-label">Water Conserved</div></div>
    <div class="stat-box"><i class="fas fa-tree" style="color:var(--primary-green);"></i><div class="stat-box-num">${(sd.treesPlanted || 0).toLocaleString()}</div><div class="stat-box-label">Trees Planted</div></div>
    <div class="stat-box"><i class="fas fa-solar-panel" style="color:var(--primary-green);"></i><div class="stat-box-num">${sd.solarCapacity || 0} kW</div><div class="stat-box-label">Solar Capacity</div></div>
    <div class="stat-box"><i class="fas fa-seedling" style="color:var(--primary-green);"></i><div class="stat-box-num">${sd.organicArea || 0} acres</div><div class="stat-box-label">Organic Area</div></div>
  </div>`;

  // Environmental score gauge
  const sc = sd.environmentalScore || 0;
  html += `<div class="card-premium"><h4 style="margin-bottom:8px;"><i class="fas fa-chart-pie" style="color:var(--primary-green);"></i> Environmental Score</h4>
    <div style="display:flex;align-items:center;gap:16px;">
      <div style="width:80px;height:80px;border-radius:50%;background:conic-gradient(var(--primary-green) 0% ${sc}%, var(--border-light) ${sc}% 100%);display:flex;align-items:center;justify-content:center;">
        <div style="width:60px;height:60px;border-radius:50%;background:white;display:flex;align-items:center;justify-content:center;font-size:22px;font-weight:800;color:var(--primary-green);">${sc}%</div>
      </div>
      <div style="flex:1;"><p style="font-size:12px;color:var(--text-secondary);">Your farm's environmental sustainability score. Based on water conservation, renewable energy use, organic practices, and biodiversity.</p>
        <div style="display:flex;gap:8px;margin-top:6px;">
          <button class="btn-primary btn-sm" onclick="showToast('AI suggests: Plant 50 more trees and install solar pump to improve score.','success')">AI Suggestion</button>
        </div>
      </div>
    </div>
  </div>`;

  // Water usage chart
  if (insights.length > 0) {
    html += `<div class="card-premium"><h4 style="margin-bottom:8px;"><i class="fas fa-water" style="color:var(--primary-green);"></i> Water Usage (kL/month)</h4>
      <div style="display:flex;gap:6px;align-items:flex-end;height:100px;padding:8px 0;">`;
    insights.forEach(i => {
      const h = (i.usage / maxUsage) * 80;
      html += `<div style="flex:1;display:flex;flex-direction:column;align-items:center;height:100%;justify-content:flex-end;">
        <div style="width:100%;height:${h}px;background:var(--primary-green);border-radius:4px 4px 0 0;transition:height 0.5s;min-height:4px;"></div>
        <span style="font-size:8px;color:var(--text-muted);margin-top:4px;">${i.month}</span>
      </div>`;
    });
    html += `</div><div style="display:flex;justify-content:space-between;font-size:10px;color:var(--text-muted);">
      <span>🌧️ Rainfall: ${insights.map(i=>i.rainfall).join('mm, ')}mm</span>
    </div></div>`;
  }

  // Initiatives
  if (initiatives.length > 0) {
    html += `<div class="card-premium"><h4 style="margin-bottom:8px;"><i class="fas fa-tasks" style="color:var(--primary-green);"></i> Green Initiatives</h4>`;
    initiatives.forEach(inv => {
      html += `<div style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border-light);">
        <i class="fas ${inv.icon}" style="color:var(--primary-green);width:20px;"></i>
        <div style="flex:1;"><strong style="font-size:12px;">${inv.title}</strong><div style="font-size:10px;color:var(--text-muted);">${inv.impact}</div></div>
        <span class="badge ${inv.status === 'Completed' ? 'badge-green' : 'badge-warning'}">${inv.status}</span>
        <div style="width:60px;"><div class="progress-bar"><div class="progress-fill" style="width:${inv.progress}%"></div></div><span style="font-size:9px;color:var(--text-muted);">${inv.progress}%</span></div>
      </div>`;
    });
    html += `</div>`;
  }

  // AI Suggestions & Carbon footprint
  html += `<div class="grid-2">
    <div class="card-premium" onclick="showToast('Switch to solar pumps and organic farming to reduce carbon footprint.','info')" style="cursor:pointer;">
      <i class="fas fa-cloud" style="color:var(--primary-green);font-size:22px;display:block;margin-bottom:4px;"></i>
      <h4 style="font-size:13px;">Carbon Footprint</h4>
      <p style="font-size:11px;color:var(--text-secondary);">${sd.carbonFootprint || 0} kg CO₂/year</p>
      <p style="font-size:10px;color:var(--text-muted);">Reduce by 15% with solar adoption</p>
    </div>
    <div class="card-premium" onclick="showToast('AI recommends: Implement drip irrigation on 2 more plots to save 20% more water.','success')" style="cursor:pointer;">
      <i class="fas fa-robot" style="color:var(--primary-green);font-size:22px;display:block;margin-bottom:4px;"></i>
      <h4 style="font-size:13px;">AI Suggestion</h4>
      <p style="font-size:11px;color:var(--text-secondary);">Plant nitrogen-fixing trees along boundaries</p>
      <p style="font-size:10px;color:var(--text-muted);">Improves soil & biodiversity</p>
    </div>
  </div>`;

  el.innerHTML = html;
}
window.initSustainability = initSustainability;

/* ===== ENHANCED WORKERS ===== */
function initWorkersMarket(containerId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const workers = (DB().workers || []).slice(0, 15);
  const cats = ["All","Harvest Workers","Tractor Drivers","Machine Operators","Spraying Workers","Field Workers","Irrigation Workers","Livestock Workers","Drone Operators","Equipment Mechanics"];

  let html = `<div class="page-header"><h1><i class="fas fa-users" style="color:var(--primary-green);"></i> Workers Market</h1><span style="font-size:12px;color:var(--text-muted);">${workers.length} workers available</span></div>`;
  html += `<div class="search-bar"><i class="fas fa-search"></i><input type="text" placeholder="Search workers by name, skill, location..." oninput="filterWorkers(this.value)" id="worker-search"></div>`;
  html += `<div class="filter-tabs" id="worker-filter-tabs">${cats.map((c,i) => `<button class="filter-tab ${i===0?'active':''}" data-wcat="${c.toLowerCase().replace(/\s+/g,'-')}">${c}</button>`).join('')}</div>`;
  html += `<div id="workers-list">`;
  workers.forEach(w => {
    const skillStr = w.skills ? w.skills.join(', ') : w.skills || 'General Labor';
    html += `<div class="feature-card worker-item" data-search="${w.name} ${skillStr} ${w.location}" style="cursor:default;margin-bottom:8px;">
      <div style="display:flex;gap:12px;">
        <div style="width:48px;height:48px;border-radius:50%;background:var(--soft-green);display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:700;color:var(--primary-green);flex-shrink:0;">${w.name.charAt(0)}</div>
        <div style="flex:1;">
          <div style="display:flex;justify-content:space-between;">
            <h4 style="font-size:13px;">${w.name}</h4>
            <span style="font-size:12px;font-weight:700;color:var(--primary-green);">${w.dailyWage}</span>
          </div>
          <p style="font-size:10px;color:var(--text-muted);">${skillStr} • ${w.experience || 'N/A'}</p>
          <p style="font-size:10px;color:var(--text-muted);">📍 ${w.location} • ⭐${w.rating} (${w.jobsCompleted || 0} jobs) ${w.verified ? '✓ Verified' : ''}</p>
          <div style="display:flex;gap:8px;margin-top:6px;">
            <button class="btn-primary btn-sm" style="font-size:10px;" onclick="showToast('Hiring ${w.name} for tomorrow! ₹${(w.dailyWage||'500').replace(/[^0-9]/g,'')}/day. Confirmation sent.','success')"><i class="fas fa-handshake"></i> Hire</button>
            <button class="btn-secondary btn-sm" style="font-size:10px;" onclick="showToast('Calling ${w.name} at ${w.phone || '+91 98765XXXXX'}...','info')"><i class="fas fa-phone"></i> Call</button>
            <button class="btn-secondary btn-sm" style="font-size:10px;" onclick="showToast('Chat with ${w.name} - Feature coming soon!','info')"><i class="far fa-comment-dots"></i></button>
          </div>
        </div>
      </div>
    </div>`;
  });
  html += `</div>
    <div style="display:flex;gap:8px;margin-top:12px;">
      <button class="btn-primary" style="flex:1;font-size:11px;" onclick="showToast('Posting a new job listing for workers...','success')"><i class="fas fa-plus"></i> Post Job</button>
      <button class="btn-secondary" style="flex:1;font-size:11px;" onclick="showToast('Worker attendance logged for today. In time: 6:30 AM - Out time: 5:00 PM','info')"><i class="fas fa-clipboard-check"></i> Attendance</button>
    </div>`;
  el.innerHTML = html;

  // Filter tabs
  el.querySelectorAll('#worker-filter-tabs .filter-tab').forEach(tab => {
    tab.addEventListener('click', function() {
      el.querySelectorAll('#worker-filter-tabs .filter-tab').forEach(t => t.classList.remove('active'));
      this.classList.add('active');
      const cat = this.dataset.wcat;
      el.querySelectorAll('.worker-item').forEach(w => {
        const txt = w.dataset.search.toLowerCase();
        w.style.display = cat === 'all' || txt.includes(cat.replace(/-/g,' ')) ? '' : 'none';
      });
    });
  });
};
window.initWorkersMarket = initWorkersMarket;

function filterWorkers(query) {
  const q = query.toLowerCase();
  document.querySelectorAll('.worker-item').forEach(w => {
    w.style.display = w.dataset.search.toLowerCase().includes(q) ? '' : 'none';
  });
}
window.filterWorkers = filterWorkers;

function showSchemeDetail(id) {
  const s = (window.FarmDB && window.FarmDB.govSchemes || []).find(x => x.id === id);
  if (!s) return;
  const b = document.createElement('div'); b.className = 'modal-backdrop active'; b.onclick = function(e) { if (e.target === this) this.remove(); };
  const faqs = (s.faq || 'No FAQs available').split('Q:').filter(Boolean).map(f => { const parts = f.split('A:'); return parts.length>1 ? {q:'Q:'+parts[0],a:'A:'+parts[1]} : null; }).filter(Boolean);
  b.innerHTML = `<div class="modal-box" style="max-width:560px;max-height:85vh;overflow-y:auto;padding:24px;" onclick="event.stopPropagation()">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
      <h2 style="font-size:18px;">${s.name}</h2>
      <span style="font-size:22px;cursor:pointer;color:var(--text-muted);" onclick="this.closest('.modal-backdrop').remove()">&times;</span>
    </div>
    <span class="badge badge-green" style="margin-bottom:10px;">${s.category} • ${s.type || 'Scheme'}</span>
    <p style="font-size:13px;color:var(--text-secondary);margin-bottom:16px;">${s.description}</p>
    <div class="grid-2" style="margin-bottom:12px;">
      <div class="stat-box"><div class="stat-box-num" style="font-size:16px;">${s.benefit}</div><div class="stat-box-label">Benefit</div></div>
      <div class="stat-box"><div class="stat-box-num" style="font-size:16px;">📅 ${s.deadline || 'Open'}</div><div class="stat-box-label">Deadline</div></div>
    </div>
    <div style="margin-bottom:12px;padding:12px;background:var(--bg-card-soft);border-radius:var(--radius-md);">
      <strong style="font-size:12px;">✅ Eligibility</strong>
      <p style="font-size:11px;color:var(--text-secondary);margin-top:4px;">${s.eligibility}</p>
    </div>
    <div style="margin-bottom:12px;padding:12px;background:var(--bg-card-soft);border-radius:var(--radius-md);">
      <strong style="font-size:12px;">📋 Documents Required</strong>
      <p style="font-size:11px;color:var(--text-secondary);margin-top:4px;">${s.documents}</p>
    </div>
    <div style="margin-bottom:12px;">
      <strong style="font-size:12px;">🎯 Objective</strong>
      <p style="font-size:11px;color:var(--text-secondary);margin-top:4px;">${s.objective || 'Support farmers.'}</p>
    </div>
    <div style="margin-bottom:12px;">
      <strong style="font-size:12px;">📞 Contact</strong>
      <p style="font-size:11px;color:var(--text-secondary);margin-top:4px;">${s.contact || 'District Agriculture Office'}</p>
    </div>
    ${faqs.length > 0 ? `<div style="margin-bottom:12px;"><strong style="font-size:12px;">❓ FAQ</strong>${faqs.map(f => `<div style="margin-top:6px;padding:8px;background:var(--bg-card-soft);border-radius:var(--radius-sm);"><p style="font-size:11px;font-weight:600;">${f.q}</p><p style="font-size:11px;color:var(--text-secondary);">${f.a}</p></div>`).join('')}</div>` : ''}
    <div style="display:flex;gap:8px;margin-top:16px;">
      <button class="btn-primary" style="flex:1;" onclick="this.closest('.modal-backdrop').remove();showToast('Opening ${s.name} application form...','success')">Apply Now</button>
      <button class="btn-secondary" onclick="this.closest('.modal-backdrop').remove();showToast('${s.name} saved to bookmarks','success')">Save</button>
      <button class="btn-secondary" onclick="this.closest('.modal-backdrop').remove();showToast('Share link copied!','info')">Share</button>
    </div>
  </div>`;
  document.body.appendChild(b);
}
window.showSchemeDetail = showSchemeDetail;

})();
