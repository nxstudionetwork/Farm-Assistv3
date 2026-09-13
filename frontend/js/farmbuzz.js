(function () {
  'use strict';

  var FB = window.API && window.API.FarmBuzz;

  var LS_RECENT = 'fa-farmbuzz-recent-search';
  var CATEGORIES = ['Farming', 'Crop', 'Machinery', 'Market', 'Success Story', 'Question', 'Tip', 'Community', 'Other'];
  var SHORT_CATS = ['Farmer Techniques', 'Farmer Tricks', 'Farming Scenes', 'Farmer Life', 'Farming Comedy', 'Quick Knowledge', 'Educational', 'Expert Shorts'];

  var view = 'home';
  var me = null;
  var activeDetail = null;
  var activeShareId = null;
  var reportTargetId = null;
  var compType = 'post';
  var compKind = 'photo';
  var compFile = null;
  var compFileType = null;
  var compThumbUrl = null;
  var editEntryId = null;
  var taggedPeople = [];

  var shorts = [];
  var shortsOrig = [];
  var spIdx = 0;
  var spViewSent = {};
  var spDwellStart = {};
  var spWatchLast = {};
  var spEvQueue = {};
  var spEvTimer = null;
  var spIo = null;
  var WATCH_QUALIFY_MS = 1500;
  var WATCH_THROTTLE_MS = 5000;
  var spTimer = null;
  var spPaused = false;
  var spMuted = false;
  var spCommentsOpen = false;

  var storiesByAuthor = [];
  var stIx = 0;
  var stSIdx = 0;
  var stTimer = null;
  var stPaused = false;
  var stViewed = {};

  var searchActive = false;
  var searchSeq = 0;
  var meLoaded = false;
  var spWheelLock = false;
  var shortsPage = 1;
  var shortsGone = false;
  var moreMenuEl = null;

  function $(id) { return document.getElementById(id); }

  function esc(s) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(s == null ? '' : String(s)));
    return div.innerHTML;
  }

  function fmtNum(n) {
    n = Number(n) || 0;
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return String(n);
  }

  function fmtTime(v) {
    if (!v) return '';
    var s = String(v);
    var t = s.indexOf('T') === -1 ? s.replace(' ', 'T') + 'Z' : (s.length === 19 ? s + 'Z' : s);
    var d = new Date(t);
    if (isNaN(d.getTime())) return s;
    var diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 45) return 'just now';
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    if (diff < 604800) return Math.floor(diff / 86400) + 'd ago';
    return d.toLocaleDateString();
  }

  function authed() {
    return !!(localStorage.getItem('fa-auth-token'));
  }

  function guard(msg) {
    if (authed()) return true;
    showToast(msg || 'Please login to continue', 'warning');
    setTimeout(function () { window.location.href = 'login.html'; }, 800);
    return false;
  }

  function apiErr(e) {
    if (e && e.status === 401) {
      showToast('Session expired. Please login again.', 'danger');
      setTimeout(function () { window.location.href = 'login.html'; }, 800);
      return true;
    }
    if (e && e.status === 403) {
      showToast(e.message || 'You cannot perform this action', 'danger');
      return true;
    }
    if (e && e.status === 409) {
      showToast(e.message || 'This action was already completed', 'warning');
      return true;
    }
    showToast(e && e.message ? e.message : 'Something went wrong. Please try again.', 'danger');
    return true;
  }

  function avatarOf(authorish, size) {
    var u = authorish || {};
    if (u.profile_image) return u.profile_image;
    if (window.UserStore && window.UserStore.avatarFor) {
      return window.UserStore.avatarFor({ full_name: u.full_name || 'Farmer' });
    }
    return '';
  }

  function avatarImgHtml(authorish, cls, altAttr) {
    var alt = (authorish && authorish.full_name) || 'Farmer';
    return '<img class="' + (cls || '') + '" src="' + esc(avatarOf(authorish)) + '" alt="' + esc(alt) + '" loading="lazy">';
  }

  function isMine(d) {
    if (!d) return false;
    if (d.is_mine) return true;
    if (d.user_id && me && me.id && d.user_id === me.id) return true;
    return false;
  }

  function mediaTag(d, isShort) {
    var m = (d.media_type || 'text').toLowerCase();
    if (m === 'video') {
      var poster = d.thumbnail_url ? ' poster="' + esc(d.thumbnail_url) + '"' : '';
      return '<video class="fb-video-feed' + (isShort ? ' fb-short-media' : '') + '" src="' + esc(d.media_url) + '" preload="metadata" controls muted playsinline' + poster + '></video>';
    }
    if (m === 'image') {
      return '<img src="' + esc(d.media_url) + '" alt="' + esc(d.title || d.caption || 'Post media') + '" loading="lazy">';
    }
    return '<div class="fb-pad-media' + ((d.category === 'Tip') ? ' fb-pad-tip' : '') + '" aria-hidden="true"><i class="fas ' + ((d.category === 'Tip') ? 'fa-lightbulb' : 'fa-wheat-awn') + '"></i></div>';
  }

  function verif(d) {
    return (d && d.author && d.author.verified) ? ' <i class="fas fa-circle-check" title="Verified"></i>' : '';
  }

  function hashCaption(container, text) {
    container.querySelectorAll('.fb-hashtag').forEach(function (el) {
      el.addEventListener('click', function (e) {
        e.stopPropagation();
        openTagSearch(el.getAttribute('data-tag'));
      });
    });
  }

  var recents = [];
  try { recents = JSON.parse(localStorage.getItem(LS_RECENT) || '[]') || []; } catch (e) { recents = []; }

  function addRecent(q) {
    q = (q || '').trim();
    if (!q) return;
    recents = recents.filter(function (r) { return r.toLowerCase() !== q.toLowerCase(); });
    recents.unshift(q);
    recents = recents.slice(0, 5);
    try { localStorage.setItem(LS_RECENT, JSON.stringify(recents)); } catch (e) {}
  }

  function emptyHtml(icon, title, sub) {
    return '<div class="fb-empty"><i class="fas ' + (icon || 'fa-leaf') + '"></i><p>' + esc(title) + '</p>' +
      (sub ? '<p style="font-size:12px;margin-top:4px;">' + esc(sub) + '</p>' : '') + '</div>';
  }

  function toast(msg, type) {
    if (typeof window.showToast === 'function') window.showToast(msg, type || 'success');
  }

  /* ==========================================================================
     VIEW SWITCHING
  ========================================================================== */
  var VIEWS = ['home', 'shorts', 'trends', 'post', 'self'];

  function closeModals() {
    ['fbDetailModal', 'fbShareModal', 'fbFarmerModal', 'fbEditModal', 'fbReportModal', 'fbStoryCreateModal'].forEach(function (id) {
      document.getElementById(id).classList.remove('open');
    });
  }

  function switchView(name, opts) {
    opts = opts || {};
    if (VIEWS.indexOf(name) === -1) name = 'home';
    view = name;
    document.querySelectorAll('.fb-topnav button[data-view]').forEach(function (b) {
      b.classList.toggle('active', b.getAttribute('data-view') === name);
    });
    VIEWS.forEach(function (v) {
      var el = document.getElementById('fbView' + v.charAt(0).toUpperCase() + v.slice(1));
      el.classList.toggle('active', v === name);
    });
    window.scrollTo(0, 0);
    if (view === 'home') {
      if (searchActive) {
        performSearch($('fbSearchInput').value.trim());
      } else {
        renderHome();
      }
    } else if (view === 'shorts') {
      renderShorts(opts.category);
    } else if (view === 'trends') {
      renderTrends(opts.filter || 'all');
    } else if (view === 'post') {
      initComposer();
    } else if (view === 'self') {
      renderSelf(opts.tab || 'posts');
    }
    updateHash();
  }

  function updateHash() {
    try { history.replaceState(null, '', '#fb-' + view); } catch (e) {}
  }

  function readHash() {
    var h = window.location.hash || '';
    var m = h.match(/^#fb-(home|shorts|trends|post|self)/);
    return m ? m[1] : null;
  }

  /* ==========================================================================
     HOME
  ========================================================================== */
  function skelCard() {
    return '<div class="fb-skel-card">' +
      '<div class="fb-skel-head">' +
      '<div class="fb-skeleton fb-skel-av"></div>' +
      '<div class="fb-skel-head-lines"><div class="fb-skeleton fb-skel-line w60"></div><div class="fb-skeleton fb-skel-line w40"></div></div>' +
      '</div>' +
      '<div class="fb-skeleton fb-skel-media"></div>' +
      '<div class="fb-skel-row"><div class="fb-skeleton fb-skel-line w30"></div><div class="fb-skeleton fb-skel-line w20"></div></div>' +
      '<div class="fb-skel-body"><div class="fb-skeleton fb-skel-line w90"></div><div class="fb-skeleton fb-skel-line w70"></div></div>' +
      '</div>';
  }

  function renderHome() {
    $('fbHomePosts').innerHTML = skelCard() + skelCard() + skelCard();
    renderForYou();
    renderStoriesRow();
    renderShortsStrip();
    renderTips();
    renderHomePosts();
  }

  function renderForYou() {
    var el = $('fbForYou');
    var crops = [];
    if (me && me.crops) crops = me.crops;
    var farmName = '';
    try { farmName = localStorage.getItem('fa-selected-farm') || ''; } catch (e) {}
    var label = crops && crops.length && typeof crops === 'string' ? 'For You – ' + String(crops).split(/[,]/).slice(0, 2).join(' & ') : 'For You';
    var sub = 'Content matched to your farming profile';
    if (crops && ((typeof crops === 'string' && crops) || (Array.isArray(crops) && crops.length))) sub = 'Personalised feed based on your preferred crops';
    el.innerHTML = '<div class="fb-tip-card" style="margin-bottom:14px;border-color:var(--premium-green,#1B5E3F);">' +
      '<div class="fb-tip-icon" style="background:linear-gradient(135deg,#1B5E3F,#52B788);"><i class="fas fa-hand-point-up"></i></div>' +
      '<div class="fb-tip-body"><h5>' + esc(label) + '</h5><p>' + esc(sub) + (farmName ? ' · Farm: ' + esc(farmName) : '') + '</p></div></div>';
  }

  function renderStoriesRow() {
    var row = $('fbFarmersRow');
    loadStories().then(function (groups) {
      var html = '';
      html += '<div class="fb-farmer-pill" id="fbAddStoryPill" tabindex="0" role="button" aria-label="Create a story">' +
        '<div class="fb-fp-add"><i class="fas fa-plus"></i></div><span>Your Story</span></div>';
      groups.forEach(function (g) {
        var a = g.author;
        html += '<div class="fb-farmer-pill" data-story-author="' + esc(a.id) + '" tabindex="0" role="button" aria-label="View ' + esc(a.full_name) + ' stories">' +
          '<img class="fb-fp-avatar ring" src="' + esc(avatarOf(a)) + '" alt="' + esc(a.full_name) + '" loading="lazy">' +
          '<span>' + esc(String(a.full_name || 'Farmer').split(' ')[0]) + '</span></div>';
      });
      if (!groups.length) {
        html += '<div style="flex:1;min-width:200px;padding:10px 14px;color:var(--text-muted);font-size:12.5px;">No stories yet. Be the first to share a quick farm update!</div>';
      }
      row.innerHTML = html;
      var add = $('fbAddStoryPill');
      if (add) add.addEventListener('click', function () { openStoryCreate(); });
      row.querySelectorAll('[data-story-author]').forEach(function (el) {
        el.addEventListener('click', function () { openStoriesByAuthor(el.getAttribute('data-story-author')); });
      });
    }).catch(function () {
      row.innerHTML = '';
    });
  }

  function renderShortsStrip() {
    var strip = $('fbShortsStrip');
    if (!strip) return;
    FB.recommendedShorts({ limit: 8, page: 1 }).then(function (data) {
      var items = (data && data.items) || [];
      if (!items.length) {
        strip.innerHTML = '';
        strip.style.minHeight = '0';
        return;
      }
      strip.innerHTML = items.map(function (s) {
        var thumb = s.thumbnail_url || s.media_url || '';
        var inner = thumb
          ? '<img src="' + esc(thumb) + '" alt="' + esc(s.title || 'Short') + '" loading="lazy" onerror="this.parentNode.classList.add(\'no-image\');this.remove();">'
          : '';
        return '<div class="fb-strip-card' + (inner ? '' : ' no-image') + '" data-open-short="' + esc(s.id) + '">' +
          inner +
          '<span class="fb-strip-cat">' + esc(s.category || 'Short') + '</span>' +
          '<span class="fb-strip-play"><i class="fas fa-play"></i></span></div>';
      }).join('');
      bindStripClicks(strip);
    }).catch(function () {
      strip.innerHTML = '';
      strip.style.minHeight = '0';
    });
  }

  function bindStripClicks(container) {
    if (!container) return;
    container.querySelectorAll('[data-open-short]').forEach(function (el) {
      el.addEventListener('click', function () {
        var id = el.getAttribute('data-open-short');
        FB.recommendedShorts({ limit: 50, page: 1 }).then(function (data) {
          openSpById(id, (data && data.items) || []);
        }).catch(function () {});
      });
    });
  }

  function openSpById(id, items) {
    var list = items || [];
    var idx = list.findIndex(function (s) { return s.id === id; });
    if (idx >= 0) openSp(idx, list);
    else if (list.length) openSp(0, list);
  }

  function renderTips() {
    var el = $('fbTipList');
    FB.feed({ content_type: 'post', category: 'Tip', limit: 4, page: 1 }).then(function (data) {
      var items = (data && data.items) || [];
      if (!items.length) {
        el.innerHTML = emptyHtml('fa-lightbulb', 'No tips yet', 'Post a quick farming tip from the Post tab');
        return;
      }
      el.innerHTML = items.map(function (t) {
        var title = (t.title || t.caption || '').split('.')[0].slice(0, 70);
        return '<div class="fb-tip-card" data-open-post="' + esc(t.id) + '">' +
          '<div class="fb-tip-icon" style="background:linear-gradient(135deg,#1B5E3F,#52B788);"><i class="fas fa-lightbulb"></i></div>' +
          '<div class="fb-tip-body"><h5>' + esc(title) + '</h5><p>' + esc(t.caption || '').slice(0, 120) + '</p></div></div>';
      }).join('');
      bindTipClicks(el);
    }).catch(function () {
      el.innerHTML = emptyHtml('fa-lightbulb', 'Could not load tips');
    });
  }

  function bindTipClicks(container) {
    if (!container) return;
    container.querySelectorAll('[data-open-post]').forEach(function (el) {
      el.addEventListener('click', function () { openDetail(el.getAttribute('data-open-post')); });
    });
  }

  function renderHomePosts() {
    var el = $('fbHomePosts');
    FB.feed({ content_type: 'all', limit: 10, page: 1, sort: 'recent' }).then(function (data) {
      var items = (data && data.items) || [];
      if (!items.length) {
        el.innerHTML = emptyHtml('fa-wheat-awn', 'Nothing here yet', 'Be the first to share a farming update');
        return;
      }
      el.innerHTML = items.map(postCardHtml).join('');
      bindPostContainer(el, items);
    }).catch(function () {
      el.innerHTML = emptyHtml('fa-cloud', 'Could not load the feed', 'Check your connection and try again');
    });
  }

  /* ==========================================================================
     POST CARDS
  ========================================================================== */
  function postCardHtml(p) {
    var mine = isMine(p);
    var mediaClosed = '<div class="fb-post-media"><div class="fb-cat-chip">' + esc(p.category || 'Farming') + '</div>' +
      (p.content_type === 'short' ? '<span class="fb-short-badge">SHORT</span>' : '') +
      mediaTag(p) +
      '<div class="fb-media-overlay" data-open-post="' + esc(p.id) + '" role="button" aria-label="Open post"></div></div>';
    var mediaOpen = '<div class="fb-post-media' + (false ? ' fb-tall' : '') + '">' +
      '<div class="fb-cat-chip">' + esc(p.category || 'Farming') + '</div>' +
      (p.content_type === 'short' ? '<span class="fb-short-badge">SHORT</span>' : '') +
      mediaTag(p) +
      '<div class="fb-media-overlay" data-open-post="' + esc(p.id) + '" role="button" aria-label="Open post"></div></div>';
    var media = p.media_type === 'image' ? mediaOpen : mediaClosed;
    var loc = p.location ? '<div class="fb-post-loc"><i class="fas fa-location-dot"></i>' + esc(p.location) + '</div>' : '';
    var caption = p.caption ? '<div class="fb-post-caption"><b>' + esc(p.author.full_name) + '</b> ' +
      esc(p.caption).replace(/#([\w\u0900-\u097F]+)/g, '<span class="fb-hashtag" data-tag="#$1">#$1</span>') +
      '</div>' : '';
    var fc = p.media_type === 'image' ? ' inline' : '';
    var isShortCard = p.content_type === 'short';
    return '<article class="fb-post-card" data-post-id="' + esc(p.id) + '">' +
      '<div class="fb-post-head">' +
      '<img class="fb-avatar" src="' + esc(avatarOf(p.author)) + '" alt="' + esc(p.author.full_name) + '" data-farmer="' + esc(p.author.id) + '" loading="lazy">' +
      '<div class="fb-post-head-info" data-farmer="' + esc(p.author.id) + '"><b>' + esc(p.author.full_name) + verif(p) + '</b>' +
      '<small>' + esc(fmtTime(p.created_at)) + (p.author.farmer_id ? ' · ' + esc(p.author.farmer_id) : '') + '</small></div>' +
      (!mine && p.author.id !== (me && me.id) ? '<button class="fb-follow-btn' + (p.is_followed ? ' following' : '') + '" data-follow="' + esc(p.author.id) + '">' + (p.is_followed ? 'Following' : 'Follow') + '</button>' : '') +
      '<button class="fb-more-btn" data-more="' + esc(p.id) + '" aria-label="More options"><i class="fas fa-ellipsis-h"></i></button>' +
      '</div>' +
      media +
      '<div class="fb-post-actions">' +
      '<button class="fb-act' + (p.is_liked ? ' liked' : '') + '" data-like="' + esc(p.id) + '" aria-label="Like"><i class="fas ' + (p.is_liked ? 'fa-heart' : 'fa-heart') + '" data-act-icon="heart"></i>' + (isShortCard ? '' : '<span data-likes-count>' + fmtNum(p.likes_count) + '</span>') + '</button>' +
      '<button class="fb-act" data-comment="' + esc(p.id) + '" aria-label="Comment"><i class="fas fa-comment"></i>' + (isShortCard ? '' : '<span data-comment-count>' + fmtNum(p.comments_count) + '</span>') + '</button>' +
      '<button class="fb-act' + (p.is_saved ? ' saved' : '') + '" data-save="' + esc(p.id) + '" aria-label="Save"><i class="fas ' + (p.is_saved ? 'fa-bookmark' : 'fa-bookmark') + '" data-act-icon="bookmark"></i></button>' +
      '<button class="fb-act" data-share="' + esc(p.id) + '" aria-label="Share"><i class="fas fa-share-nodes"></i></button>' +
      '</div>' +
      '<div class="fb-post-body">' +
      (isShortCard ? '' : '<div class="fb-post-likes">' + fmtNum(p.likes_count) + ' likes</div>') +
      caption +
      loc +
      (isShortCard ? '' : '<div class="fb-post-comments" data-comment="' + esc(p.id) + '">View all ' + fmtNum(p.comments_count) + ' comments</div>') +
      '</div></article>';
  }

  function bindPostContainer(container, items, opts) {
    opts = opts || {};
    items.forEach(function (p) { cachePost(p); });
    container.querySelectorAll('[data-farmer]').forEach(function (el) {
      el.addEventListener('click', function () { openFarmer(el.getAttribute('data-farmer')); });
    });
    container.querySelectorAll('[data-follow]').forEach(function (el) {
      el.addEventListener('click', function () { toggleFollowFrom(el); });
    });
    container.querySelectorAll('[data-more]').forEach(function (el) {
      el.addEventListener('click', function (e) { openMoreMenu(el.getAttribute('data-more'), el); });
    });
    container.querySelectorAll('[data-like]').forEach(function (el) {
      el.addEventListener('click', function () { toggleLikeFrom(el); });
    });
    container.querySelectorAll('[data-save]').forEach(function (el) {
      el.addEventListener('click', function () { toggleSaveFrom(el); });
    });
    container.querySelectorAll('[data-comment]').forEach(function (el) {
      el.addEventListener('click', function () {
        openContent(postFromCache(el.getAttribute('data-comment')), opts.savedList);
      });
    });
    container.querySelectorAll('[data-share]').forEach(function (el) {
      el.addEventListener('click', function () { openShare(el.getAttribute('data-share')); });
    });
    container.querySelectorAll('[data-open-post]').forEach(function (el) {
      el.addEventListener('click', function () {
        openContent(postFromCache(el.getAttribute('data-open-post')), opts.savedList);
      });
    });
    hashCaption(container, '');
  }

  function openContent(item, savedList) {
    if (!item) return;
    if (item.content_type === 'short') {
      if (savedList && savedList.length) {
        for (var i = 0; i < savedList.length; i++) {
          if (savedList[i].id === item.id) { openSp(i, savedList); return; }
        }
      }
      openSp(0, [item]);
    } else {
      openDetail(item.id);
    }
  }

  function cachePost(p) {
    if (p && p.id) postCache[p.id] = p;
  }

  function postFromCache(id) {
    return postCache[id] || null;
  }

  function postEl(id) {
    return document.querySelector('[data-post-id="' + id + '"]');
  }

  function patchCounts(id, kind, value) {
    var p = postFromCache(id);
    if (p) {
      if (kind === 'likes') p.likes_count = value;
      if (kind === 'comments') p.comments_count = value;
      if (kind === 'saves') p.saves_count = value;
    }
    var card = postEl(id);
    if (!card) return;
    if (kind === 'likes') {
      var spans = card.querySelectorAll('[data-likes-count]');
      for (var i = 0; i < spans.length; i++) spans[i].textContent = fmtNum(value);
    }
    if (kind === 'comments') {
      var cs = card.querySelectorAll('[data-comment-count]');
      for (var j = 0; j < cs.length; j++) cs[j].textContent = fmtNum(value);
    }
  }

  function patchFlags(id, flag, value) {
    var p = postFromCache(id);
    if (p) p[flag] = value;
    var card = postEl(id);
    if (!card) return;
    if (flag === 'is_liked') {
      var btn = card.querySelector('[data-like="' + id + '"]');
      if (btn) btn.classList.toggle('liked', value);
    }
    if (flag === 'is_saved') {
      var sb = card.querySelector('[data-save="' + id + '"]');
      if (sb) sb.classList.toggle('saved', value);
    }
    if (flag === 'is_followed') {
      var f = card.querySelector('[data-follow]');
      if (f) {
        f.classList.toggle('following', value);
        f.textContent = value ? 'Following' : 'Follow';
      }
    }
  }

  var postCache = {};

  /* ==========================================================================
     ENGAGEMENT
  ========================================================================== */
  function toggleLikeFrom(el) {
    var id = el.getAttribute('data-like');
    if (!guard('Please login to like posts')) return;
    FB.like(id).then(function (data) {
      patchCounts(id, 'likes', data.likes_count);
      patchFlags(id, 'is_liked', !!data.is_liked);
      toast(data.message || (data.is_liked ? 'Liked' : 'Unliked'), data.is_liked ? 'success' : 'info');
    }).catch(apiErr);
  }

  function toggleSaveFrom(el) {
    var id = el.getAttribute('data-save');
    if (!guard('Please login to save posts')) return;
    FB.save(id).then(function (data) {
      patchCounts(id, 'saves', data.saves_count);
      patchFlags(id, 'is_saved', !!data.is_saved);
      toast(data.message || 'Saved');
    }).catch(apiErr);
  }

  function toggleFollowFrom(el) {
    var userId = el.getAttribute('data-follow');
    if (!guard('Please login to follow farmers')) return;
    FB.follow(userId).then(function (data) {
      var following = !!data.following;
      el.classList.toggle('following', following);
      el.textContent = following ? 'Following' : 'Follow';
      toast(data.message || (following ? 'Following' : 'Unfollowed'), following ? 'success' : 'info');
    }).catch(apiErr);
  }

  function openDetail(id) {
    if (!FB) return;
    closeModals();
    $('fbDetailModal').classList.add('open');
    $('fbDetailHead').innerHTML = '<div class="fb-skeleton" style="width:60%;height:40px;"></div>';
    $('fbDetailMedia').style.display = 'none';
    $('fbDetailMedia').innerHTML = '';
    $('fbDetailBody').innerHTML = '';
    $('fbDetailActions').innerHTML = '';
    $('fbDetailComments').innerHTML = '';
    $('fbDetailCommentInput').value = '';
    activeDetail = id;
    FB.getPost(id).then(function (post) {
      cachePost(post);
      activeDetailData = post;
      renderDetail(post);
      if (FB.view) FB.view(id).catch(function () {});
    }).catch(function (e) {
      $('fbDetailHead').innerHTML = emptyHtml('fa-circle-exclamation', 'Could not open post', (e && e.message) || '');
    });
  }

  var activeDetailData = null;

  function renderDetail(p) {
    var head = $('fbDetailHead');
    head.innerHTML =
      '<img class="fb-avatar" style="width:44px;height:44px;" src="' + esc(avatarOf(p.author)) + '" alt="' + esc(p.author.full_name) + '" data-dp-farmer="' + esc(p.author.id) + '">' +
      '<div class="fb-post-head-info"><b>' + esc(p.author.full_name) + verif(p) + '</b>' +
      '<small>' + esc(fmtTime(p.created_at)) + (p.author.farmer_id ? ' · ' + esc(p.author.farmer_id) : '') + '</small></div>';

    var media = $('fbDetailMedia');
    media.innerHTML = '';
    if (p.media_type && p.media_type !== 'text' && p.media_url) {
      media.style.display = 'block';
      if (p.media_type === 'video') {
        media.innerHTML = '<video class="fb-detail-media" controls preload="metadata" src="' + esc(p.media_url) + '"' + (p.thumbnail_url ? ' poster="' + esc(p.thumbnail_url) + '"' : '') + '></video>';
      } else {
        media.innerHTML = '<img class="fb-detail-media" src="' + esc(p.media_url) + '" alt="">';
      }
    } else {
      media.style.display = 'none';
    }

    var body = '<div class="fb-post-likes" style="margin:8px 0 5px;">' + fmtNum(p.likes_count) + ' likes · ' + fmtNum(p.views_count) + ' views</div>' +
      '<div class="fb-post-caption">' +
      (p.caption ? '<b>' + esc(p.author.full_name) + '</b> ' + esc(p.caption).replace(/#([\w\u0900-\u097F]+)/g, '<span class="fb-hashtag" data-tag="#$1">#$1</span>') + '<br>' : '') +
      (p.title ? '<small style="color:var(--text-dark,#173423);font-weight:700;">' + esc(p.title) + '</small><br>' : '') +
      (p.category ? '<small>Category: <b>' + esc(p.category) + '</b></small>' : '') +
      '</div>';
    if (p.location) body += '<div class="fb-post-loc"><i class="fas fa-location-dot"></i>' + esc(p.location) + '</div>';
    if (p.crop) body += '<div class="fb-post-loc" style="margin-top:3px;"><i class="fas fa-seedling"></i>' + esc(p.crop) + '</div>';
    $('fbDetailBody').innerHTML = body;

    $('fbDetailActions').innerHTML =
      '<button class="fb-act' + (p.is_liked ? ' liked' : '') + '" data-like="' + esc(p.id) + '"><i class="fas ' + (p.is_liked ? 'fa-heart' : 'fa-heart') + '"></i> Like (' + fmtNum(p.likes_count) + ')</button>' +
      '<button class="fb-act' + (p.is_saved ? ' saved' : '') + '" data-save="' + esc(p.id) + '"><i class="fas ' + (p.is_saved ? 'fa-bookmark' : 'fa-bookmark') + '"></i> Save</button>' +
      '<button class="fb-act" data-share="' + esc(p.id) + '"><i class="fas fa-share-nodes"></i> Share</button>' +
      (!isMine(p) && p.author.id !== (me && me.id) ? '<button class="fb-follow-btn' + (p.is_followed ? ' following' : '') + '" style="margin-left:auto;" data-follow="' + esc(p.author.id) + '">' + (p.is_followed ? 'Following' : 'Follow') + '</button>' : '');

    $('fbDetailCommentCount').textContent = fmtNum(p.comments_count);
    renderDetailComments(p.comments || []);

    hashCaption($('fbDetailBody'), '');
    var d = $('fbDetailModal');
    d.querySelectorAll('[data-dp-farmer]').forEach(function (el) {
      el.addEventListener('click', function () { openFarmer(el.getAttribute('data-dp-farmer')); });
    });
    d.querySelectorAll('[data-like]').forEach(function (el) {
      el.addEventListener('click', function () {
        var id = el.getAttribute('data-like');
        if (!guard('Please login to like posts')) return;
        FB.like(id).then(function (data) {
          el.classList.toggle('liked', !!data.is_liked);
          el.innerHTML = '<i class="fas ' + (data.is_liked ? 'fa-heart' : 'fa-heart') + '"></i> Like (' + fmtNum(data.likes_count) + ')';
          toast(data.message || 'Liked');
        }).catch(apiErr);
      });
    });
    d.querySelectorAll('[data-save]').forEach(function (el) {
      el.addEventListener('click', function () {
        var id = el.getAttribute('data-save');
        if (!guard('Please login to save posts')) return;
        FB.save(id).then(function (data) {
          el.classList.toggle('saved', !!data.is_saved);
          toast(data.message || 'Saved');
        }).catch(apiErr);
      });
    });
    d.querySelectorAll('[data-follow]').forEach(function (el) {
      el.addEventListener('click', function () {
        var uid = el.getAttribute('data-follow');
        if (!guard('Please login to follow farmers')) return;
        FB.follow(uid).then(function (data) {
          var f = !!data.following;
          el.classList.toggle('following', f);
          el.textContent = f ? 'Following' : 'Follow';
          toast(data.message || (f ? 'Following' : 'Unfollowed'));
        }).catch(apiErr);
      });
    });
    d.querySelectorAll('[data-share]').forEach(function (el) {
      el.addEventListener('click', function () { openShare(el.getAttribute('data-share')); });
    });
    $('fbDetailBody').addEventListener('click', function (e) {
      var tag = e.target.closest && e.target.closest('.fb-hashtag');
      if (tag) { e.stopPropagation(); openTagSearch(tag.getAttribute('data-tag')); }
    });
  }

  function renderDetailComments(list) {
    var el = $('fbDetailComments');
    if (!list.length) {
      el.innerHTML = '<div style="color:var(--text-muted);font-size:12.5px;padding:8px 0;">No comments yet. Be the first to respond.</div>';
      return;
    }
    el.innerHTML = list.map(function (c) {
      return '<div class="fb-comment-item" data-comment-row="' + esc(c.id) + '">' +
        '<img src="' + esc(avatarOf(c.author)) + '" alt="">' +
        '<div class="fb-c-body"><b>' + esc(c.author.full_name) + '</b><span>' + esc(c.content) + '</span>' +
        '<small>' + esc(fmtTime(c.created_at)) + (c.is_mine ? ' · You' : '') + '</small></div>' +
        (c.is_mine ? '<button class="fb-more-btn" data-del-comment="' + esc(c.id) + '" aria-label="Delete comment"><i class="fas fa-trash"></i></button>' : '') +
        '</div>';
    }).join('');
    el.querySelectorAll('[data-del-comment]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var cid = btn.getAttribute('data-del-comment');
        if (!confirm('Delete this comment?')) return;
        FB.deleteComment(activeDetail, cid).then(function () {
          toast('Comment deleted', 'info');
          openDetail(activeDetail);
          patchCounts(activeDetail, 'comments', Math.max(0, (postFromCache(activeDetail) ? postFromCache(activeDetail).comments_count : 1) - 1));
        }).catch(apiErr);
      });
    });
  }

  function addDetailComment() {
    var input = $('fbDetailCommentInput');
    var btn = $('fbDetailCommentBtn');
    var val = input.value.trim();
    if (!activeDetail || !val) return;
    if (!guard('Please login to comment')) return;
    if (btn && btn.disabled) return;
    setBtnBusy(btn, true, 'fa-paper-plane', 'fa-spinner fa-spin');
    FB.comment(activeDetail, { content: val }).then(function (data) {
      input.value = '';
      patchCounts(activeDetail, 'comments', (postFromCache(activeDetail) ? postFromCache(activeDetail).comments_count : 0) + 1);
      toast('Comment added');
      openDetail(activeDetail);
    }).catch(apiErr).then(function () {
      setBtnBusy(btn, false, 'fa-paper-plane', 'fa-spinner fa-spin');
    });
  }

  function setBtnBusy(btn, busy, iconClass, spinClass) {
    if (!btn) return;
    btn.disabled = busy;
    btn.classList.toggle('fb-btn-busy', busy);
    btn.innerHTML = busy
      ? '<i class="fas ' + spinClass + '"></i>'
      : '<i class="fas ' + iconClass + '"></i>';
  }

  /* ==========================================================================
     MORE MENU / EDIT / DELETE / REPORT
  ========================================================================== */
  function openMoreMenu(id, anchorEl) {
    closeMoreMenu();
    var p = postFromCache(id);
    if (!p) return;
    var mine = isMine(p);
    var items = [];
    items.push({ icon: 'fa-user', label: mine ? 'Open my profile' : 'View profile', fn: function () { openFarmer(p.author.id); } });
    if (!mine && p.author.id !== (me && me.id)) {
      items.push({ icon: 'fa-user-plus', label: p.is_followed ? 'Unfollow' : 'Follow', fn: function () { if (guard('Please login to follow farmers')) FB.follow(p.author.id).then(function (d) { patchFlags(id, 'is_followed', !!d.following); toast(d.message || ''); }).catch(apiErr); } });
    }
    items.push({ icon: 'fa-bookmark', label: p.is_saved ? 'Remove from saved' : 'Save post', fn: function () { if (guard('Please login to save posts')) FB.save(id).then(function (d) { patchFlags(id, 'is_saved', !!d.is_saved); patchCounts(id, 'saves', d.saves_count); toast(d.message || ''); }).catch(apiErr); } });
    items.push({ icon: 'fa-copy', label: 'Copy link', fn: function () { copyText(window.location.origin + '/farmbuzz.html?post=' + encodeURIComponent(p.post_id)); } });
    if (mine) {
      items.push({ icon: 'fa-pen', label: 'Edit', fn: function () { editPost(id); } });
      items.push({ icon: 'fa-trash', label: 'Delete', fn: function () { deletePostItem(id); } });
    } else {
      items.push({ icon: 'fa-flag', label: 'Report', fn: function () { openReport(p.id); } });
    }
    var x = anchorEl.getBoundingClientRect();
    var menu = document.createElement('div');
    menu.className = 'fb-more-menu';
    menu.style.cssText = 'position:fixed;z-index:120;top:' + (x.bottom + 6) + 'px;right:' + Math.max(8, window.innerWidth - x.right) + 'px;background:#fff;border:1px solid var(--border-light);border-radius:14px;box-shadow:0 10px 30px rgba(0,0,0,.18);padding:6px;min-width:190px;';
    menu.innerHTML = items.map(function (it, i) {
      return '<button class="fb-mm-item" data-i="' + i + '"><i class="fas ' + it.icon + '"></i> ' + esc(it.label) + '</button>';
    }).join('');
    menu.querySelectorAll('.fb-mm-item').forEach(function (b) {
      b.style.cssText = 'display:flex;width:100%;gap:10px;align-items:center;border:none;background:none;padding:10px 12px;font-size:13px;font-weight:600;color:#2c3a32;cursor:pointer;border-radius:10px;font-family:inherit;text-align:left;';
      b.addEventListener('mouseover', function () { b.style.background = '#f0f4f1'; });
      b.addEventListener('mouseout', function () { b.style.background = 'transparent'; });
      b.addEventListener('click', function () {
        var fn = items[Number(b.getAttribute('data-i'))].fn;
        closeMoreMenu();
        fn();
      });
    });
    moreMenuEl = menu;
    document.body.appendChild(menu);
    setTimeout(function () {
      document.addEventListener('click', closeMoreMenu, { once: true });
    }, 0);
  }

  function closeMoreMenu() {
    if (moreMenuEl) {
      moreMenuEl.remove();
      moreMenuEl = null;
    }
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { toast('Copied to clipboard!'); }, function () { toast('Could not copy', 'warning'); });
    } else {
      toast('Could not copy', 'warning');
    }
  }

  function editPost(id) {
    var p = postFromCache(id);
    if (!p) return;
    switchView('post');
    openComposerForEdit(p);
  }

  function deletePostItem(id) {
    if (!confirm('Delete this post? This cannot be undone.')) return;
    FB.deletePost(id).then(function () {
      toast('Post deleted', 'info');
      var card = postEl(id);
      if (card) card.remove();
      if (activeDetail === id) closeModals();
      if (view === 'self') renderSelf(lastSelfTab || 'posts');
    }).catch(apiErr);
  }

  function openReport(id) {
    if (!guard('Please login to report content')) return;
    reportTargetId = id;
    closeModals();
    $('fbReportModal').classList.add('open');
    $('fbReportDesc').value = '';
  }

  function submitReport() {
    if (!reportTargetId) return;
    var btn = $('fbReportBtn');
    var reason = $('fbReportReason').value;
    var desc = $('fbReportDesc').value.trim();
    if (!reason) { toast('Please select a report reason', 'warning'); return; }
    if (btn && btn.disabled) return;
    if (btn) btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Submitting...';
    FB.report(reportTargetId, { reason: reason, description: desc || null }).then(function (data) {
      toast((data && data.message) || 'Report submitted', 'success');
      closeModals();
    }).catch(apiErr).then(function () {
      if (btn) btn.innerHTML = '<i class="fas fa-flag"></i> Submit Report';
    });
  }

  /* ==========================================================================
     SHARE
  ========================================================================== */
  function openShare(id) {
    activeShareId = id;
    closeModals();
    $('fbShareModal').classList.add('open');
    var p = postFromCache(id);
    var shareText = (p && (p.caption || p.title)) ? p.caption || p.title : 'Check out this FarmBuzz post';
    var url = window.location.origin + '/farmbuzz.html?post=' + encodeURIComponent((p && p.post_id) || id);
    var enc = encodeURIComponent;
    var opts = [
      { icon: 'fa-brands fa-whatsapp', color: '#25D366', label: 'WhatsApp', href: 'https://wa.me/?text=' + enc(shareText + ' ' + url) },
      { icon: 'fa-brands fa-facebook-f', color: '#1877F2', label: 'Facebook', href: 'https://www.facebook.com/sharer/sharer.php?u=' + enc(url) },
      { icon: 'fa-brands fa-x-twitter', color: '#0F1419', label: 'X', href: 'https://twitter.com/intent/tweet?text=' + enc(shareText) + '&url=' + enc(url) },
      { icon: 'fa-brands fa-telegram', color: '#2AABEE', label: 'Telegram', href: 'https://t.me/share/url?url=' + enc(url) + '&text=' + enc(shareText) },
      { icon: 'fa-solid fa-copy', color: '#44524a', label: 'Copy text', fn: 'copy' },
      { icon: 'fa-solid fa-envelope', color: '#8B6F47', label: 'Email', href: 'mailto:?subject=' + enc('FarmBuzz post') + '&body=' + enc(shareText + ' ' + url) }
    ];
    $('fbShareGrid').innerHTML = opts.map(function (o, i) {
      var click = o.href ? '' : ' data-btn="' + i + '"';
      return '<button class="fb-share-opt"' + click + (o.href ? ' onclick="window.open(this.getAttribute(\'data-href\'),\'_blank\',\'noopener\')" data-href="' + esc(o.href) + '"' : '') + '>' +
        '<span class="fb-share-icon" style="background:' + o.color + ';"><i class="' + o.icon + '"></i></span><span>' + o.label + '</span></button>';
    }).join('');
    $('fbShareGrid').querySelectorAll('[data-btn]').forEach(function (b) {
      b.addEventListener('click', function () {
        var p2 = postFromCache(id);
        var t = (p2 && (p2.caption || p2.title)) ? (p2.caption || p2.title) : 'FarmBuzz post';
        if (b.getAttribute('data-btn') === '4') {
          copyText(t);
        }
      });
    });
  }

  function doShare() {
    if (!activeShareId) return;
    if (!guard('Please login to share')) return;
    FB.share(activeShareId).then(function (data) {
      patchCounts(activeShareId, 'shares', data.shares_count);
      toast((data && data.message) || 'Shared');
    }).catch(apiErr);
  }

  /* ==========================================================================
     SEARCH
  ========================================================================== */
  function openTagSearch(tag) {
    var input = $('fbSearchInput');
    if (!input) return;
    input.value = tag;
    activateSearch();
    performSearch(tag);
    switchView('home');
  }

  function bindSearchEvents() {
    var input = $('fbSearchInput');
    var clear = $('fbSearchClear');
    var debT = null;
    input.addEventListener('input', function () {
      clear.style.display = this.value ? 'block' : 'none';
      if (debT) clearTimeout(debT);
      debT = setTimeout(function () {
        var q = input.value.trim();
        if (q) {
          activateSearch();
          performSearch(q);
        } else {
          deactivateSearch();
          if (view === 'home') renderHome();
        }
      }, 350);
    });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        var q = input.value.trim();
        if (q) { activateSearch(); performSearch(q); }
      }
    });
    clear.addEventListener('click', function () {
      input.value = '';
      clear.style.display = 'none';
      deactivateSearch();
      if (view === 'home') renderHome();
    });
  }

  function activateSearch() { searchActive = true; document.body.classList.add('fb-searching'); }
  function deactivateSearch() { searchActive = false; document.body.classList.remove('fb-searching'); }

  function performSearch(q) {
    if (!q) { deactivateSearch(); return; }
    if (!FB) return;
    var seq = ++searchSeq;
    var target = $('fbHomePosts');
    target.innerHTML = '<div class="fb-skeleton fb-skel-card"></div>';
    addRecent(q);
    FB.search({ q: q, type: 'all', limit: 10 }).then(function (res) {
      if (seq !== searchSeq) return;
      var html = '';
      var farmers = (res && res.farmers) || [];
      var posts = (res && res.posts) || [];
      var shortsRes = (res && res.shorts) || [];
      var tags = (res && res.hashtags) || [];
      if (!(farmers.length || posts.length || shortsRes.length || tags.length)) {
        target.innerHTML = emptyHtml('fa-magnifying-glass', 'No results for "' + q + '"', 'Try a farmer name, #hashtag, crop or location');
        return;
      }
      html += '<div class="fb-search-type-head">Farmers</div>';
      html += farmers.length ? farmers.map(function (f) {
        return '<div class="fb-search-row" data-farmer="' + esc(f.id) + '"><img src="' + esc(avatarOf(f)) + '" alt="">' +
          '<div class="fb-sr-body"><b>' + esc(f.full_name) + '</b><small>' + esc(f.farmer_id) + '</small></div></div>';
      }).join('') : '<div style="font-size:12px;color:var(--text-muted);padding:4px 8px;">None found</div>';
      html += '<div class="fb-search-type-head">Posts</div>';
      html += posts.length ? posts.map(function (p) {
        return '<div class="fb-search-row" data-open-post="' + esc(p.id) + '">' + searchThumb(p) +
          '<div class="fb-sr-body"><b>' + esc((p.caption || p.title || 'Post').slice(0, 60)) + '</b><small>by ' + esc(p.author.full_name) + '</small></div></div>';
      }).join('') : '<div style="font-size:12px;color:var(--text-muted);padding:4px 8px;">None found</div>';
      html += '<div class="fb-search-type-head">Shorts</div>';
      html += shortsRes.length ? shortsRes.map(function (s) {
        return '<div class="fb-search-row" data-open-short-search="' + esc(s.id) + '">' + searchThumb(s) +
          '<div class="fb-sr-body"><b>' + esc((s.title || s.caption || 'Short').slice(0, 60)) + '</b><small>' + esc(s.author.full_name) + '</small></div></div>';
      }).join('') : '<div style="font-size:12px;color:var(--text-muted);padding:4px 8px;">None found</div>';
      html += '<div class="fb-search-type-head">#Hashtags</div>';
      html += tags.length ? tags.map(function (t) {
        return '<div class="fb-search-row" data-hashtag="' + esc('#' + t.tag) + '"><span class="fb-search-thumb" style="background:linear-gradient(135deg,#1B5E3F,#52B788);"><i class="fas fa-hashtag"></i></span>' +
          '<div class="fb-sr-body"><b>#' + esc(t.tag) + '</b><small>' + fmtNum(t.post_count) + ' posts</small></div></div>';
      }).join('') : '<div style="font-size:12px;color:var(--text-muted);padding:4px 8px;">None found</div>';

      html += '<div class="fb-search-type-head">Recent</div>' + recentChips();

      target.innerHTML = html;
      target.querySelectorAll('[data-farmer]').forEach(function (el) {
        el.addEventListener('click', function () { openFarmer(el.getAttribute('data-farmer')); });
      });
      target.querySelectorAll('[data-open-post]').forEach(function (el) {
        el.addEventListener('click', function () { openDetail(el.getAttribute('data-open-post')); });
      });
      target.querySelectorAll('[data-open-short-search]').forEach(function (el) {
        el.addEventListener('click', function (e) {
          var sid = el.getAttribute('data-open-short-search');
          FB.recommendedShorts({ limit: 50, page: 1 }).then(function (d) {
            openSpById(sid, (d && d.items) || []);
          }).catch(function () {});
        });
      });
      target.querySelectorAll('[data-hashtag]').forEach(function (el) {
        el.addEventListener('click', function () {
          var q2 = el.getAttribute('data-hashtag');
          $('fbSearchInput').value = q2;
          performSearch(q2);
        });
      });
    }).catch(function () {
      if (seq !== searchSeq) return;
      target.innerHTML = emptyHtml('fa-circle-exclamation', 'Search failed', 'Please try again');
    });
  }

  function searchThumb(p) {
    var img = p.media_url || p.thumbnail_url || '';
    if (img) return '<img src="' + esc(img) + '" alt="">';
    return '<span class="fb-search-thumb"><i class="fas fa-' + (p.content_type === 'short' ? 'clapperboard' : 'wheat-awn') + '"></i></span>';
  }

  function recentChips() {
    if (!recents.length) return '';
    return recents.map(function (r) {
      return '<span class="fb-recent-tag" data-recent="' + esc(r) + '"><i class="fas fa-clock-rotate-left"></i> ' + esc(r) + '</span>';
    }).join('');
  }

  function bindRecentChips(container) {
    if (!container) return;
    container.querySelectorAll('[data-recent]').forEach(function (el) {
      el.addEventListener('click', function () {
        var q = el.getAttribute('data-recent');
        $('fbSearchInput').value = q;
        performSearch(q);
      });
    });
  }

  /* ==========================================================================
     TRENDS
  ========================================================================== */
  function renderTrends(filter) {
    var chipsEl = $('fbTrendChips');
    var listEl = $('fbTrendList');
    listEl.innerHTML = '<div class="fb-skeleton" style="height:60px;"></div>';
    FB.trends().then(function (data) {
      var trends = (data && data.trends) || [];
      var hot = (data && data.hot_posts) || [];
      if (!trends.length) {
        listEl.innerHTML = emptyHtml('fa-fire', 'No trending topics yet');
        return;
      }
      var cats = ['all'].concat(Array.from(new Set(trends.map(function (t) { return t.category; }))).slice(0, 8));
      chipsEl.innerHTML = cats.map(function (c) {
        return '<button class="fb-chip' + (filter === c ? ' active' : '') + '" data-trend-cat="' + esc(c) + '">' + esc(c === 'all' ? 'All' : c.charAt(0).toUpperCase() + c.slice(1)) + '</button>';
      }).join('');
      chipsEl.querySelectorAll('[data-trend-cat]').forEach(function (b) {
        b.addEventListener('click', function () { renderTrends(b.getAttribute('data-trend-cat')); });
      });
      var shown = filter === 'all' ? trends : trends.filter(function (t) { return t.category === filter; });
      listEl.innerHTML = shown.map(function (t, i) {
        var colors = ['#1565C0', '#2D8659', '#d97706', '#40916C', '#7c3aed', '#C9A227', '#B23A48', '#1B5E3F'];
        var c = colors[i % colors.length];
        return '<div class="fb-trend-row" data-trend-q="' + esc(t.topic.charAt(0) === '#' ? t.topic : '#' + t.topic.replace(/\s+/g, '')) + '">' +
          '<div class="fb-trend-rank" style="background:' + c + ';">' + (i + 1) + '</div>' +
          '<div class="fb-trend-body"><div class="fb-trend-topic">' + esc(t.topic) + '</div>' +
          '<div class="fb-trend-desc">' + esc(t.description || '') + '</div>' +
          '<div class="fb-trend-meta"><span>' + esc(t.category) + '</span><span class="fb-trend-score">' + fmtNum(t.engagement_score) + ' engagement</span></div></div></div>';
      }).join('');
      if (hot.length) {
        listEl.insertAdjacentHTML('beforeend', '<div class="fb-section-head" style="margin-top:16px;"><h3><i class="fas fa-fire-flame-curved"></i> Hot Posts</h3></div>' + hot.map(postCardHtml).join(''));
        bindPostContainer(listEl, hot);
      }
      listEl.querySelectorAll('[data-trend-q]').forEach(function (el) {
        el.addEventListener('click', function () { openTagSearch(el.getAttribute('data-trend-q')); });
      });
    }).catch(function () {
      listEl.innerHTML = emptyHtml('fa-fire', 'Could not load trends', 'Please try again');
    });
  }

  /* ==========================================================================
     SHORTS
  ========================================================================== */
  function renderShorts(category) {
    var chipsEl = $('fbShortChips');
    var gridEl = $('fbShortsGrid');
    shortsPage = 1;
    shortsGone = false;
    gridEl.innerHTML = emptyHtml('fa-clapperboard', 'Loading shorts...');
    if (category === undefined) category = '';
    renderShortChips(chipsEl, category);
    fetchShorts(gridEl, category, true);
  }

  function renderShortChips(chipsEl, category) {
    var render = function (cats) {
      var list = ['all'].concat(cats.slice(0, 8));
      chipsEl.innerHTML = list.map(function (c) {
        return '<button class="fb-chip' + ((category || 'all') === c ? ' active' : '') + '" data-short-cat="' + esc(c) + '">' + esc(c === 'all' ? 'All' : c) + '</button>';
      }).join('');
      chipsEl.querySelectorAll('[data-short-cat]').forEach(function (b) {
        b.addEventListener('click', function () { renderShorts(b.getAttribute('data-short-cat')); });
      });
    };
    if (FB && FB.shortCategories) {
      FB.shortCategories().then(function (data) {
        var cats = (data && data.categories) || [];
        render(cats.length ? cats : SHORT_CATS);
      }).catch(function () { render(SHORT_CATS); });
    } else {
      render(SHORT_CATS);
    }
  }

  function fetchShorts(gridEl, category, fresh) {
    var params = { limit: 20, page: shortsPage };
    if (category && category !== 'all') params.category = category;
    FB.recommendedShorts(params).then(function (data) {
      if (fresh && $('fbShortsGrid') !== gridEl) return;
      var items = (data && data.items) || [];
      if (fresh) {
        shortsOrig = items.slice();
        if (!items.length) {
          gridEl.innerHTML = emptyHtml('fa-clapperboard', 'No shorts yet', 'Create a short from the Post tab and select the Short type');
          return;
        }
        gridEl.innerHTML = items.map(function (s) { return shortCardHtml(s); }).join('');
        bindShortGrid(gridEl, items);
      } else {
        if (!items.length) {
          shortsGone = true;
          var mo = gridEl.querySelector('.fb-load-more');
          if (mo) mo.remove();
          return;
        }
        gridEl.insertAdjacentHTML('beforeend', items.map(function (s) { return shortCardHtml(s); }).join(''));
        bindShortGrid(gridEl, items);
      }
      var more = gridEl.querySelector('.fb-load-more');
      if (items.length >= 20 && !shortsGone) {
        if (!more) {
          more = document.createElement('button');
          more.className = 'fb-load-more btn';
          more.textContent = 'Load more';
          more.style.margin = '16px auto';
          more.addEventListener('click', function () {
            if (more.disabled) return;
            shortsPage += 1;
            more.disabled = true;
            more.textContent = 'Loading...';
            fetchShorts(gridEl, category, false);
          });
          gridEl.appendChild(more);
        } else {
          more.disabled = false;
          more.textContent = 'Load more';
        }
      } else if (more) {
        more.remove();
      }
    }).catch(function () {
      if (fresh) {
        gridEl.innerHTML = emptyHtml('fa-circle-exclamation', 'Could not load shorts');
      } else {
        var mb = gridEl.querySelector('.fb-load-more');
        if (mb) { mb.disabled = false; mb.textContent = 'Load more'; }
      }
    });
  }

  function shortCardHtml(s) {
    var thumb = s.thumbnail_url || s.media_url || '';
    var inner = thumb
      ? '<img src="' + esc(thumb) + '" alt="' + esc(s.title || 'Short') + '" loading="lazy" onerror="this.parentNode.classList.add(\'no-image\');this.remove();">'
      : '';
    return '<div class="fb-short-card' + (inner ? '' : ' no-image') + '" data-short-id="' + esc(s.id) + '" role="button" tabindex="0" aria-label="Play short">' +
      inner +
      '<span class="fb-short-cat">' + esc(s.category || 'Short') + '</span>' +
      '<div class="fb-short-info"><b>' + esc(s.title || s.caption || '') + '</b>' +
      '<small>' + esc(s.author.full_name) + '</small></div></div>';
  }

  function bindShortGrid(gridEl, items) {
    gridEl.querySelectorAll('[data-short-id]').forEach(function (el) {
      el.addEventListener('click', function () {
        var id = el.getAttribute('data-short-id');
        var idx = items.findIndex(function (s) { return s.id === id; });
        openSp(Math.max(idx, 0), items);
      });
    });
    gridEl.querySelectorAll('[data-short-id]').forEach(function (el) {
      el.setAttribute('tabindex', '0');
      el.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') el.click();
      });
    });
  }

  function openSp(idx, list) {
    if (!list || !list.length) return;
    shorts = list;
    spIdx = Math.max(0, Math.min(idx, shorts.length - 1));
    spViewSent = {};
    spDwellStart = {};
    spWatchLast = {};
    spEvQueue = {};
    if (spEvTimer) { clearTimeout(spEvTimer); spEvTimer = null; }
    spPaused = false;
    var stage = $('fbSpStage');
    stage.style.scrollTop = 0;
    stage.innerHTML = '';
    shorts.forEach(function (s) {
      stage.appendChild(buildSpSlide(s));
    });
    $('fbShortsPlayer').classList.add('open');
    document.body.style.overflow = 'hidden';
    $('fbSpProgressFill').style.width = '0%';
    $('fbSpCounter').textContent = '1/' + shorts.length;
    if ('IntersectionObserver' in window) {
      if (spIo) spIo.disconnect();
      spIo = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (en.isIntersecting && en.intersectionRatio >= 0.5) return;
          var v = en.target.querySelector('video');
          if (v) v.pause();
        });
      }, { threshold: [0, 0.5] });
      shorts.forEach(function () { spIo.observe(stage.lastChild); });
    }
    requestAnimationFrame(function () {
      stage.scrollTop = spIdx * stage.clientHeight;
      activateSp(false);
    });
  }

  function buildSpSlide(s) {
    var slide = document.createElement('div');
    slide.className = 'fb-sp-slide';
    slide.dataset.spId = s.id;
    var mediaInner = '';
    if (s.media_type === 'video' && s.media_url) {
      mediaInner = '<video class="fb-sp-media" src="' + esc(s.media_url) + '" muted playsinline preload="auto"' +
        (s.thumbnail_url ? ' poster="' + esc(s.thumbnail_url) + '"' : '') + '></video>';
    } else if (s.media_url) {
      mediaInner = '<img class="fb-sp-media" src="' + esc(s.media_url) + '" alt="' + esc(s.title || 'Short') + '" draggable="false" onerror="this.onerror=null;this.style.display=\'none\';">';
    } else {
      var ph = s.thumbnail_url || '';
      mediaInner = ph
        ? '<img class="fb-sp-media" src="' + esc(ph) + '" alt="' + esc(s.title || 'Short') + '" draggable="false">'
        : '<div class="fb-sp-media fb-sp-plain" style="background:#101d15;">' +
          '<div style="position:absolute;left:16px;right:16px;bottom:26px;text-align:left;color:#fff;">' +
          '<div style="font-size:15px;font-weight:700;line-height:1.4;">' + esc(s.title || s.caption || 'Short') + '</div></div></div>';
    }
    var rail = spRailHtml(s);
    slide.innerHTML =
      '<div class="fb-sp-grad-top"></div>' +
      mediaInner +
      '<div class="fb-sp-vignette"></div>' +
      '<div class="fb-sp-loading"><i class="fas fa-spinner"></i></div>' +
      '<div class="fb-sp-info">' +
      '<div class="fb-sp-author">' + avatarImgHtml(s.author, '', '') +
      '<b>' + esc(s.author.full_name) + verif(s) + '</b>' +
      (s.author.id !== (me && me.id) ? '<button class="fb-sp-follow' + (s.is_followed ? ' following' : '') + '" data-sp-follow="' + esc(s.author.id) + '">' + (s.is_followed ? 'Following' : 'Follow') + '</button>' : '') +
      '</div>' +
      '<div class="fb-sp-title">' + esc(s.title || '') + '</div>' +
      '<div class="fb-sp-meta"><span><i class="fas fa-fire"></i> ' + esc(s.category || 'Short') + '</span></div>' +
      (s.caption ? '<div class="fb-sp-desc">' + esc(s.caption) + '</div>' : '') +
      '</div>' +
      rail;
    return slide;
  }

  function spRailHtml(s) {
    return '<div class="fb-sp-right" data-sp-rail>' +
      '<div class="fb-sp-avatar-ring">' + avatarImgHtml(s.author, '', '') + '</div>' +
      '<div class="fb-sp-rail" data-sp-act="like" role="button"><button class="fb-sp-rail-btn' + (s.is_liked ? ' liked' : '') + '"><i class="fas fa-heart" data-rail="like"></i></button><b></b></div>' +
      '<div class="fb-sp-rail" data-sp-act="comment" role="button"><button class="fb-sp-rail-btn"><i class="fas fa-comment"></i></button><b></b></div>' +
      '<div class="fb-sp-rail" data-sp-act="share" role="button"><button class="fb-sp-rail-btn"><i class="fas fa-share-nodes"></i></button><b></b></div>' +
      '<div class="fb-sp-rail" data-sp-act="save" role="button"><button class="fb-sp-rail-btn' + (s.is_saved ? ' saved' : '') + '"><i class="fas fa-bookmark" data-rail="save"></i></button><b></b></div>' +
      '<div class="fb-sp-rail" data-sp-act="mute" role="button"><button class="fb-sp-rail-btn"><i class="fas fa-volume-up" data-rail="mute"></i></button><b></b></div>' +
      '</div>';
  }

  function currentShort() {
    return shorts[spIdx];
  }

  function queueEv(id, type, dwell) {
    var e = spEvQueue[id] || { dwell: null };
    e[type] = true;
    if (dwell != null) e.dwell = Math.round(dwell);
    spEvQueue[id] = e;
  }

  function scheduleFlush() {
    if (spEvTimer) clearTimeout(spEvTimer);
    spEvTimer = setTimeout(flushEvQueue, 1200);
  }

  function flushEvQueue() {
    if (spEvTimer) { clearTimeout(spEvTimer); spEvTimer = null; }
    if (!authed()) { spEvQueue = {}; return; }
    var ids = Object.keys(spEvQueue);
    if (!ids.length) return;
    for (var i = 0; i < ids.length; i++) {
      var e = spEvQueue[ids[i]];
      var typ = e.skip ? 'skip' : e.complete ? 'complete' : e.replay ? 'replay' : e.qualified_view ? 'qualified_view' : e.watch ? 'watch' : null;
      if (!typ) continue;
      var payload = { event_type: typ };
      if (e.dwell != null) payload.watch_duration_ms = e.dwell;
      FB.recordEvent(ids[i], payload).catch(function () {});
    }
    spEvQueue = {};
  }

  function trackQualified(id, dwell) {
    if (!spViewSent[id]) {
      spViewSent[id] = true;
      if (FB.view && authed()) FB.view(id).catch(function () {});
    }
    queueEv(id, 'qualified_view', dwell);
    var now = Date.now();
    if (!spWatchLast[id] || now - spWatchLast[id] >= WATCH_THROTTLE_MS) {
      spWatchLast[id] = now;
      queueEv(id, 'watch', dwell);
    }
    scheduleFlush();
  }

  function trackSkip(id) {
    if (spViewSent[id]) return;
    queueEv(id, 'skip');
    scheduleFlush();
  }

  function trackComplete(id) {
    if (!spViewSent[id]) {
      spViewSent[id] = true;
      if (FB.view && authed()) FB.view(id).catch(function () {});
    }
    queueEv(id, 'complete');
    scheduleFlush();
  }

  function trackReplay(id) {
    if (!spViewSent[id]) {
      spViewSent[id] = true;
      if (FB.view && authed()) FB.view(id).catch(function () {});
    }
    queueEv(id, 'replay');
    scheduleFlush();
  }

  function settleSp(id) {
    if (!id) return;
    var start = spDwellStart[id];
    delete spDwellStart[id];
    if (start == null) return;
    var dwell = Date.now() - start;
    if (dwell >= WATCH_QUALIFY_MS) trackQualified(id, dwell);
    else trackSkip(id);
  }

  function activateSp(animate) {
    var stage = $('fbSpStage');
    var height = stage.clientHeight || (window.innerHeight);
    var next = Math.round(stage.scrollTop / height);
    next = Math.max(0, Math.min(next, shorts.length - 1));
    var prev = spIdx;
    spIdx = next;
    if (prev !== next) {
      $('fbSpCounter').textContent = (next + 1) + '/' + shorts.length;
      $('fbSpProgressFill').style.width = '0%';
      pauseSlides();
      settleSp(shorts[prev] && shorts[prev].id);
      flushEvQueue();
    }
    var s = currentShort();
    if (!s) return;
    spDwellStart[s.id] = Date.now();
    var slide = stage.children[spIdx];
    if (!slide) return;
    slide.classList.remove('loading');
    var v = slide.querySelector('video');
    if (v) {
      v.muted = spMuted;
      v.volume = spMuted ? 0 : 1;
      playCurrentVideo();
    }
    var img = slide.querySelector('img.fb-sp-media');
    if (img) {
      var timer = slide.__timer;
      if (timer) clearTimeout(timer);
      slide.__timer = setTimeout(function () {
        if (!spPaused && Math.abs(Math.round(stage.scrollTop / height) - spIdx) <= 0) {
          trackComplete(s.id);
          nextSp();
        }
      }, 6000);
    }
    startProgress();
    preloadAdjacent();
  }

  function preloadAdjacent() {
    var stage = $('fbSpStage');
    if (!stage || !shorts.length) return;
    for (var i = 0; i < shorts.length; i++) {
      var slide = stage.children[i];
      if (!slide) continue;
      var v = slide.querySelector('video');
      if (!v) continue;
      var dist = Math.abs(i - spIdx);
      if (dist <= 1) {
        if (v.getAttribute('preload') !== 'auto') {
          v.setAttribute('preload', 'auto');
          if (dist === 1 && v.readyState === 0) v.load();
        }
      } else if (v.getAttribute('preload') !== 'none') {
        v.setAttribute('preload', 'none');
        if (i !== spIdx) v.pause();
      }
    }
  }

  function playCurrentVideo() {
    var slide = $('fbSpStage').children[spIdx];
    if (!slide) return;
    var v = slide.querySelector('video');
    if (v) {
      slide.classList.add('loading');
      v.muted = spMuted;
      v.volume = spMuted ? 0 : 1;
      var tryPlay = function () {
        var pr = v.play();
        if (pr && pr.then) pr.then(function () { slide.classList.remove('loading'); }).catch(function () { slide.classList.remove('loading'); });
        else slide.classList.remove('loading');
      };
      if (v.readyState >= 2) { tryPlay(); }
      else {
        v.addEventListener('canplay', tryPlay, { once: true });
        v.load();
      }
    } else {
      slide.classList.remove('loading');
    }
  }

  function pauseSlides() {
    var stage = $('fbSpStage');
    var slides = stage.children;
    for (var i = 0; i < slides.length; i++) {
      var v = slides[i].querySelector('video');
      if (v) v.pause();
    }
    if (spTimer) { clearInterval(spTimer); spTimer = null; }
  }

  function startProgress() {
    if (spTimer) clearInterval(spTimer);
    var slide = $('fbSpStage').children[spIdx];
    if (!slide) return;
    var v = slide.querySelector('video');
    if (v) {
      var id = currentShort().id;
      spTimer = setInterval(function () {
        if (!v.duration || !v.currentTime) return;
        $('fbSpProgressFill').style.width = Math.min(100, (v.currentTime / v.duration) * 100) + '%';
        if (v.ended) { if (v.__done) return; v.__done = true; trackComplete(id); nextSp(); return; }
        else if (v.__lastT != null && v.currentTime < v.__lastT - 0.4) { trackReplay(id); }
        v.__lastT = v.currentTime;
      }, 200);
    }
  }

  function toggleSpPause() {
    var slide = $('fbSpStage').children[spIdx];
    if (!slide) return;
    var v = slide.querySelector('video');
    spPaused = !spPaused;
    if (v) {
      if (spPaused) v.pause(); else playCurrentVideo();
    } else if (spPaused) {
      if (slide.__timer) clearTimeout(slide.__timer);
    } else {
      nextSpTimer();
    }
    $('fbSpPaused').classList.toggle('show', spPaused);
  }

  function nextSpTimer() {
    var slide = $('fbSpStage').children[spIdx];
    if (slide && slide.__timer) { clearTimeout(slide.__timer); slide.__timer = null; }
    var t = setTimeout(function () { if (!spPaused) nextSp(); }, 6000);
    if (slide) slide.__timer = t;
  }

  function nextSp() {
    if (!shorts.length) return;
    var stage = $('fbSpStage');
    var height = stage.clientHeight || (window.innerHeight || 800);
    var target = Math.min(spIdx + 1, shorts.length - 1);
    stage.scrollTo({ top: target * height, behavior: 'smooth' });
  }

  function prevSp() {
    if (!shorts.length) return;
    var stage = $('fbSpStage');
    var height = stage.clientHeight;
    var target = Math.max(spIdx - 1, 0);
    stage.scrollTo({ top: target * height, behavior: 'smooth' });
  }

  function stopSp() {
    $('fbShortsPlayer').classList.remove('open');
    document.body.style.overflow = '';
    pauseSlides();
    spPaused = false;
    $('fbSpPaused').classList.remove('show');
    var s = currentShort();
    if (s) settleSp(s.id);
    flushEvQueue();
    if (spIo) { spIo.disconnect(); spIo = null; }
  }

  function handleSpAction(e) {
    var rail = e.target.closest('[data-sp-act]');
    if (!rail) return;
    var act = rail.getAttribute('data-sp-act');
    var s = currentShort();
    if (!s) return;
    if (act === 'like') {
      if (!guard('Please login to like shorts')) return;
      FB.like(s.id).then(function (d) {
        s.is_liked = !!d.is_liked; s.likes_count = d.likes_count;
        updateSpRail(s, 'like');
        toast(d.message || 'Liked');
      }).catch(apiErr);
    } else if (act === 'comment') {
      openSpComments();
    } else if (act === 'share') {
      openShare(s.id);
    } else if (act === 'save') {
      if (!guard('Please login to save shorts')) return;
      FB.save(s.id).then(function (d) {
        s.is_saved = !!d.is_saved; s.saves_count = d.saves_count;
        updateSpRail(s, 'save');
        toast(d.message || 'Saved');
      }).catch(apiErr);
    } else if (act === 'mute') {
      spMuted = !spMuted;
      var stage = $('fbSpStage');
      for (var i = 0; i < stage.children.length; i++) {
        var v = stage.children[i].querySelector('video');
        if (v) { v.muted = spMuted; v.volume = spMuted ? 0 : 1; }
      }
      var mb = stage.querySelector('[data-rail="mute"]');
      if (mb) mb.className = spMuted ? 'fas fa-volume-xmark' : 'fas fa-volume-up';
      toast(spMuted ? 'Sound muted' : 'Sound on', 'info');
    }
  }

  function updateSpRail(s, kind) {
    var stage = $('fbSpStage');
    var slide = stage.querySelector('.fb-sp-slide[data-sp-id="' + s.id + '"]');
    if (!slide) return;
    if (kind === 'like') {
      slide.querySelector('.fb-sp-rail[data-sp-act="like"] .fb-sp-rail-btn').classList.toggle('liked', !!s.is_liked);
    }
    if (kind === 'save') {
      slide.querySelector('.fb-sp-rail[data-sp-act="save"] .fb-sp-rail-btn').classList.toggle('saved', !!s.is_saved);
    }
  }

  function openSpComments() {
    var s = currentShort();
    if (!s) return;
    var panel = $('fbSpCommentsPanel');
    panel.style.display = 'block';
    spCommentsOpen = true;
    $('fbSpCommentTitle').textContent = 'Comments';
    $('fbSpCommentsList').innerHTML = '<div style="color:var(--text-muted);font-size:12.5px;padding:8px;">Loading...</div>';
    FB.comments(s.id).then(function (data) {
      var list = (data && data.items) || [];
      if (!list.length) {
        $('fbSpCommentsList').innerHTML = '<div style="color:var(--text-muted);font-size:12.5px;padding:8px;">No comments yet.</div>';
        return;
      }
      $('fbSpCommentsList').innerHTML = list.map(function (c) {
        return '<div class="fb-sp-comment">' + avatarImgHtml(c.author, '', '') +
          '<div class="fb-c-body"><b>' + esc(c.author.full_name) + '</b><span>' + esc(c.content) + '</span>' +
          '<small>' + esc(fmtTime(c.created_at)) + '</small></div></div>';
      }).join('');
    }).catch(function () {
      $('fbSpCommentsList').innerHTML = '<div style="color:var(--text-muted);font-size:12.5px;padding:8px;">Could not load comments.</div>';
    });
  }

  function addSpComment() {
    var s = currentShort();
    var input = $('fbSpCommentInput');
    var btn = $('fbSpCommentBtn');
    var val = input.value.trim();
    if (!s || !val) return;
    if (!guard('Please login to comment')) return;
    if (btn && btn.disabled) return;
    if (btn) btn.disabled = true;
    FB.comment(s.id, { content: val }).then(function () {
      input.value = '';
      s.comments_count = (s.comments_count || 0) + 1;
      $('fbSpCommentTitle').textContent = 'Comments';
      openSpComments();
      toast('Comment added');
    }).catch(apiErr).then(function () {
      if (btn) btn.disabled = false;
    });
  }

  /* ==========================================================================
     STORIES
  ========================================================================== */
  function loadStories() {
    return FB.stories().then(function (data) {
      var items = (data && data.items) || [];
      var order = [];
      var map = {};
      items.forEach(function (s) {
        var aid = s.user_id;
        if (!map[aid]) {
          map[aid] = { author: s.author, stories: [] };
          order.push(aid);
        }
        map[aid].stories.push(s);
      });
      storiesByAuthor = order.map(function (aid) { return map[aid]; });
      return storiesByAuthor;
    });
  }

  function openStoriesByAuthor(authorId) {
    var group = storiesByAuthor.find(function (g) { return g.author.id === authorId; });
    if (!group) return;
    stIx = storiesByAuthor.indexOf(group);
    stSIdx = 0;
    stPaused = false;
    $('fbStoriesPlayer').classList.add('open');
    document.body.style.overflow = 'hidden';
    renderStory();
  }

  function openStoryCreate() {
    if (!guard('Please login to share a story')) return;
    closeModals();
    $('fbStoryCreateModal').classList.add('open');
    resetStoryForm();
  }

  function resetStoryForm() {
    $('fbStCaptionInput').value = '';
    $('fbStFileInput').value = '';
    $('fbStPreview').style.display = 'none';
    $('fbStPreviewImg').style.display = 'none';
    $('fbStPreviewVideo').style.display = 'none';
    storyMediaData = null;
    $('fbStCharCount').textContent = '0 / 300 · Stories stay live for 24 hours';
  }

  var storyMediaData = null;

  function buildStoryStub(group) {
    return { author: group.author, stories: group.stories.slice(), stIdx: 0 };
  }

  function renderStory() {
    var group = storiesByAuthor[stIx];
    if (!group) { stopSt(); return; }
    var stories = group.stories;
    var idx = stSIdx;
    var total = stories.length;
    $('fbStAvatar').src = avatarOf(group.author);
    $('fbStName').textContent = group.author.full_name || 'Farmer';
    $('fbStTime').textContent = 'Story ' + (idx + 1) + ' of ' + total;
    $('fbStDelete').style.display = (group.author.id === (me && me.id)) ? 'inline-flex' : 'none';
    var bars = $('fbStBars');
    bars.innerHTML = stories.map(function (s, i) {
      return '<div class="fb-st-bar' + (i < idx ? ' done' : i === idx ? ' active' : '') + '"><span id="stBarFill-' + i + '"></span></div>';
    }).join('');
    var st = stories[idx];
    if (!stViewed[st.id]) {
      stViewed[st.id] = true;
      if (FB.storyView && authed()) FB.storyView(st.id).catch(function () {});
    }
    var media = $('fbStMedia');
    media.innerHTML = '';
    var capEl = $('fbStCaption');
    capEl.textContent = st.caption || '';
    capEl.style.display = (st.caption ? '' : 'none');
    if (st.media_type === 'video' && st.media_url) {
      var v = document.createElement('video');
      v.src = st.media_url;
      v.muted = stMuted;
      v.playsInline = true;
      v.loop = false;
      if (st.thumbnail_url) v.poster = st.thumbnail_url;
      media.appendChild(v);
      v.addEventListener('loadedmetadata', function () {
        var fill = $('stBarFill-' + idx);
        if (!fill) return;
        fill.style.transition = 'none';
        fill.style.width = '0%';
        requestAnimationFrame(function () {
          fill.style.transition = 'width ' + (v.duration || 10) + 's linear';
          fill.style.width = '100%';
        });
      });
      playStVideo(v);
      v.addEventListener('ended', function () { forwardSt(); });
    } else if (st.media_type === 'image' && st.media_url) {
      var img = document.createElement('img');
      img.src = st.media_url;
      img.alt = st.caption || 'Story';
      media.appendChild(img);
      startStBar(5);
    } else {
      var wrap = document.createElement('div');
      wrap.className = 'fb-st-text';
      wrap.innerHTML = '<i class="fas ' + (group.author.id === (me && me.id) ? 'fa-circle-user' : 'fa-wheat-awn') + '" style="' + (st.background_color ? 'color:' + esc(st.background_color) + ';' : '') + '"></i>' +
        '<p>' + esc(st.caption || '') + '</p>';
      media.appendChild(wrap);
      startStBar(6);
    }
    $('fbStMedia').classList.add('fb-st-show');
  }

  var stMuted = false;

  function playStVideo(v) {
    var pr = v.play();
    if (pr && pr.then) pr.catch(function () {});
  }

  function startStBar(seconds) {
    var idx = stSIdx;
    var fill = $('stBarFill-' + idx);
    if (!fill) return;
    fill.style.transition = 'none';
    fill.style.width = '0%';
    requestAnimationFrame(function () {
      fill.style.transition = 'width ' + seconds + 's linear';
      fill.style.width = '100%';
    });
    if (stTimer) clearTimeout(stTimer);
    stTimer = setTimeout(function () {
      if (!stPaused) forwardSt();
    }, seconds * 1000);
  }

  function stopSt() {
    $('fbStoriesPlayer').classList.remove('open');
    document.body.style.overflow = '';
    stPaused = false;
    if (stTimer) { clearTimeout(stTimer); stTimer = null; }
  }

  function backSt() {
    if (stSIdx > 0) {
      stSIdx--;
      renderStory();
    } else if (stIx > 0) {
      stIx--;
      stSIdx = storiesByAuthor[stIx].stories.length - 1;
      renderStory();
    }
  }

  function forwardSt() {
    var group = storiesByAuthor[stIx];
    if (!group) { stopSt(); return; }
    if (stSIdx < group.stories.length - 1) {
      stSIdx++;
      renderStory();
    } else if (stIx < storiesByAuthor.length - 1) {
      stIx++;
      stSIdx = 0;
      renderStory();
    } else {
      stopSt();
    }
  }

  function toggleStPause() {
    stPaused = !stPaused;
    var media = $('fbStMedia');
    var v = media.querySelector('video');
    if (v) {
      if (stPaused) v.pause(); else playStVideo(v);
    } else if (stTimer) {
      if (stPaused) clearTimeout(stTimer);
      else startStBar(6);
    }
  }

  /* ==========================================================================
     COMPOSER
  ========================================================================== */
  function initComposer() {
    if (!FB) return;
    if (me) {
      $('fbCompAvatar').src = avatarOf(me);
      $('fbCompName').textContent = me.full_name || 'You';
    } else if (window.UserStore && window.UserStore.getCurrentUser()) {
      var u = window.UserStore.getCurrentUser();
      $('fbCompAvatar').src = window.UserStore.avatarFor(u);
      $('fbCompName').textContent = u.full_name || 'You';
    }
    if (editEntryId) return;
    $('fbCaption').value = '';
    $('fbLocation').value = '';
    $('fbCrop').value = '';
    $('fbTags').value = '';
    $('fbCharCount').textContent = '0 / 2000';
    $('fbPostHint').innerHTML = '&nbsp;';
    compFile = null;
    compFileType = null;
    compThumbUrl = null;
    compKind = 'photo';
    taggedPeople = [];
    $('fbTagPeople').innerHTML = '';
    setKindActive('photo');
    $('fbMediaPreview').style.display = 'none';
    $('fbUploadProgress').style.display = 'none';
    var btn = $('fbPostBtn');
    btn.querySelector('span').textContent = 'Post to FarmBuzz';
    $('fbPostBtn').disabled = false;
  }

  function setKindActive(kind) {
    compKind = kind;
    document.querySelectorAll('#fbMediaPicker button').forEach(function (b) {
      b.classList.toggle('active', b.getAttribute('data-kind') === kind);
    });
  }

  function openComposerForEdit(p) {
    editEntryId = p.id;
    compType = p.content_type === 'short' ? 'short' : 'post';
    document.querySelectorAll('#fbCompType button').forEach(function (b) {
      b.classList.toggle('active', b.getAttribute('data-ctype') === compType);
    });
    $('fbCaption').value = p.caption || '';
    $('fbLocation').value = p.location || '';
    $('fbCrop').value = p.crop || '';
    var tagStr = ((p.hashtags || []).map(function (t) { return '#' + t; })).join(', ');
    $('fbTags').value = tagStr;
    $('fbCharCount').textContent = (p.caption || '').length + ' / 2000';
    compFileType = p.media_type;
    compThumbUrl = p.thumbnail_url || null;
    showComposerMedia(p.media_url, p.media_type === 'video' ? 'video' : (p.media_type === 'image' ? 'image' : null));
    var kind = p.media_type === 'video' ? 'video' : (p.media_type === 'image' ? 'photo' : 'text');
    setKindActive(kind);
    var btn = $('fbPostBtn');
    btn.querySelector('span').textContent = (p.content_type === 'short' ? 'Update Short' : 'Update Post');
    switchView('post');
  }

  function showComposerMedia(url, kind) {
    $('fbMediaPreview').style.display = 'block';
    if (kind === 'video') {
      $('fbPreviewVideo').style.display = 'block';
      $('fbPreviewVideo').src = url;
      $('fbPreviewImg').style.display = 'none';
    } else if (kind === 'image') {
      $('fbPreviewImg').style.display = 'block';
      $('fbPreviewImg').src = url;
      $('fbPreviewVideo').style.display = 'none';
      $('fbPreviewVideo').removeAttribute('src');
    } else {
      $('fbMediaPreview').style.display = 'none';
    }
  }

  function submitPost() {
    var caption = $('fbCaption').value.trim();
    if (!guard('Please login to post')) return;
    if (!caption && !compFile && !compThumbUrl) {
      $('fbPostHint').textContent = 'Add a caption or media first.';
      return;
    }
    var btn = $('fbPostBtn');
    btn.disabled = true;
    btn.querySelector('i').className = 'fas fa-circle-notch';
    var payload = function () {
      var p = {
        content_type: compType,
        caption: caption,
        location: $('fbLocation').value.trim() || null,
        crop: $('fbCrop').value.trim() || null,
        category: $('fbCategory').value,
        visibility: $('fbVisibility').value,
        hashtags: parseTags($('fbTags').value),
        tagged_users: taggedPeople,
        media_type: 'text'
      };
      if (compFileType === 'video') {
        p.media_type = 'video';
        p.media_url = compUploadedUrl;
        if (compKind === 'video' && compFile) p.media_type = 'video';
      } else if (compFileType === 'image') {
        p.media_type = 'image';
        p.media_url = compUploadedUrl;
      }
      return p;
    };
    var done = function (p) {
      var req = editEntryId ? FB.updatePost(editEntryId, {
        caption: p.caption, location: p.location, crop: p.crop, category: p.category, visibility: p.visibility, hashtags: p.hashtags
      }) : FB.createPost(p);
      return req;
    };
    if (compFile) {
      var kindQ = compFileType === 'video' ? 'video' : 'image';
      $('fbUploadProgress').style.display = 'block';
      $('fbUpFill').style.width = '45%';
      $('fbUpLabel').textContent = 'Uploading media...';
      FB.uploadMedia(compFile, kindQ).then(function (data) {
        compUploadedUrl = data.url;
        compFile = null;
        $('fbUpFill').style.width = '90%';
        $('fbUpLabel').textContent = 'Finishing...';
        var p = payload();
        return done(p);
      }).then(completePost).catch(function (e) {
        btn.disabled = false;
        btn.querySelector('i').className = 'fas fa-paper-plane';
        $('fbUploadProgress').style.display = 'none';
        apiErr(e);
      });
    } else {
      var p2 = payload();
      done(p2).then(completePost).catch(function (e) {
        btn.disabled = false;
        btn.querySelector('i').className = 'fas fa-paper-plane';
        apiErr(e);
      });
    }
  }

  var compUploadedUrl = null;

  function completePost(d) {
    var btn = $('fbPostBtn');
    btn.disabled = false;
    btn.querySelector('i').className = 'fas fa-paper-plane';
    $('fbUploadProgress').style.display = 'none';
    toast((d && d.message) || 'Published!');
    editEntryId = null;
    compUploadedUrl = null;
    initComposer();
    if (compType === 'short') switchView('shorts');
    else {
      switchView('home');
      if (!searchActive) renderHome();
    }
  }

  function parseTags(str) {
    var list = [];
    String(str || '').split(/[\s,;]+/).forEach(function (t) {
      t = t.trim().replace(/^#/, '');
      if (t && /^[\w\u0900-\u097F]+$/.test(t) && list.length < 20) list.push(t);
    });
    return list;
  }

  function bindComposerEvents() {
    document.querySelectorAll('#fbCompType button').forEach(function (b) {
      b.addEventListener('click', function () {
        compType = b.getAttribute('data-ctype');
        document.querySelectorAll('#fbCompType button').forEach(function (x) { x.classList.toggle('active', x === b); });
        if (compType === 'short') {
          $('fbPostBtn').querySelector('span').textContent = 'Publish Short';
        } else {
          $('fbPostBtn').querySelector('span').textContent = 'Post to FarmBuzz';
        }
      });
    });
    document.querySelectorAll('#fbMediaPicker button').forEach(function (b) {
      b.addEventListener('click', function () {
        var kind = b.getAttribute('data-kind');
        setKindActive(kind);
        if (kind === 'text') {
          compFile = null;
          compFileType = null;
          compThumbUrl = null;
          $('fbMediaPreview').style.display = 'none';
        } else {
          $('fbFileInput').click();
        }
      });
    });
    $('fbFileInput').addEventListener('change', function () {
      var f = this.files && this.files[0];
      if (!f) return;
      var isVid = f.type.indexOf('video') === 0;
      if (!isVid && f.type.indexOf('image') !== 0) {
        toast('Please choose an image or video file', 'warning');
        return;
      }
      compFile = f;
      compFileType = isVid ? 'video' : 'image';
      var url = URL.createObjectURL(f);
      showComposerMedia(url, compFileType);
      setKindActive(isVid ? 'video' : 'photo');
    });
    $('fbMediaRemove').addEventListener('click', function () {
      compFile = null;
      compFileType = null;
      compThumbUrl = null;
      $('fbFileInput').value = '';
      $('fbMediaPreview').style.display = 'none';
    });
    $('fbCaption').addEventListener('input', function () {
      $('fbCharCount').textContent = this.value.length + ' / 2000';
    });
    $('fbPostBtn').addEventListener('click', submitPost);
  }

  function bindTagPeople() {
    var wrap = $('fbTagPeople');
    var input = document.createElement('input');
    input.type = 'text';
    input.placeholder = 'Type a name and press Enter';
    input.style.cssText = 'flex:1;min-width:120px;border:1px dashed var(--border-light);background:#fafcfb;border-radius:20px;padding:6px 12px;font-size:11.5px;outline:none;font-family:inherit;';
    wrap.appendChild(input);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && input.value.trim()) {
        e.preventDefault();
        var name = input.value.trim();
        if (taggedPeople.indexOf(name) === -1 && taggedPeople.length < 10) {
          taggedPeople.push(name);
          var chip = document.createElement('button');
          chip.type = 'button';
          chip.className = 'fb-tag-chip on';
          chip.innerHTML = '<i class="fas fa-user"></i> ' + esc(name) + ' <i class="fas fa-xmark"></i>';
          chip.addEventListener('click', function () {
            taggedPeople = taggedPeople.filter(function (t) { return t !== name; });
            chip.remove();
          });
          wrap.insertBefore(chip, input);
        }
        input.value = '';
      }
    });
  }

  /* ==========================================================================
     SELF PROFILE
  ========================================================================== */
  var lastSelfTab = 'posts';

  function renderSelf(tab) {
    var tabName = tab || 'posts';
    lastSelfTab = tabName;
    var profileEl = $('fbSelfProfile');
    var contentEl = $('fbSelfContent');
    profileEl.innerHTML = '<div class="fb-skeleton" style="height:220px;"></div>';
    contentEl.innerHTML = '';
    if (!guard('Please login to view your profile')) {
      profileEl.innerHTML = emptyHtml('fa-user', 'Login to view your FarmBuzz profile');
      return;
    }
    var tabs = document.querySelectorAll('#fbSelfTabs button');
    tabs.forEach(function (b) { b.classList.toggle('active', b.getAttribute('data-tab') === tabName); });
    FB.profile().then(function (p) {
      me = p;
      meLoaded = true;
      profileEl.innerHTML = selfProfileHtml(p);
      renderSelfTab(tabName, contentEl, p);
      var editBtn = $('fbSelfEditBtn');
      if (editBtn) editBtn.addEventListener('click', function () { openEditProfile(); });
      var postBtn = $('fbSelfPostBtn');
      if (postBtn) postBtn.addEventListener('click', function () { switchView('post'); });
    }).catch(function () {
      profileEl.innerHTML = emptyHtml('fa-circle-exclamation', 'Could not load your profile', 'Please check your connection');
    });
  }

  function selfProfileHtml(p) {
    var tags = '';
    var cropStr = p.crops;
    if (typeof cropStr === 'string') cropStr = cropStr.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
    if (Array.isArray(cropStr) && cropStr.length) {
      tags = '<div class="fb-profile-tags">' + cropStr.slice(0, 6).map(function (c) { return '<span>' + esc(c) + '</span>'; }).join('') + '</div>';
    }
    var loc = p.farm_location ? '<div class="fb-profile-loc"><i class="fas fa-location-dot"></i>' + esc(p.farm_location) + '</div>' : '';
    var bio = p.bio ? '<div class="fb-profile-bio">' + esc(p.bio) + '</div>' : '';
    return '<div class="fb-profile-card">' +
      '<div class="fb-profile-cover"><i class="fas fa-seedling"></i></div>' +
      '<div class="fb-profile-main">' +
      '<div class="fb-profile-avatar-wrap"><img src="' + esc(avatarOf(p)) + '" alt="' + esc(p.full_name) + '"></div>' +
      '<div class="fb-profile-head"><h2>' + esc(p.full_name) + ' <i class="fas fa-circle-check" title="Verified"></i></h2>' +
      '<div class="fb-fid">' + esc(p.farmer_id) + '</div></div>' + loc + bio + tags +
      '<div class="fb-profile-stats">' +
      '<div class="fb-stat-box"><b>' + fmtNum(p.posts_count) + '</b><span>Posts</span></div>' +
      '<div class="fb-stat-box"><b>' + fmtNum(p.shorts_count) + '</b><span>Shorts</span></div>' +
      '<div class="fb-stat-box"><b>' + fmtNum(p.followers_count) + '</b><span>Followers</span></div>' +
      '<div class="fb-stat-box"><b>' + fmtNum(p.following_count) + '</b><span>Following</span></div>' +
      '<div class="fb-stat-box"><b>' + fmtNum(p.saved_count) + '</b><span>Saved</span></div>' +
      '</div>' +
      '<div class="fb-profile-btns">' +
      '<button class="btn btn-primary" id="fbSelfEditBtn" style="background:linear-gradient(135deg,#1B5E3F,#2D8659);border:none;color:#fff;"><i class="fas fa-user-pen"></i> Edit Profile</button>' +
      '<button class="btn" id="fbSelfPostBtn" style="border:1px solid var(--border-light);"><i class="fas fa-square-plus"></i> New Post</button>' +
      '</div></div></div>';
  }

  function renderSelfTab(tab, el, p) {
    if (tab === 'about') {
      el.innerHTML = '<div class="fb-profile-card" style="padding:16px;">' +
        '<div style="font-size:12.5px;color:#2c3a32;line-height:2;">' +
        '<div><b>Farming type:</b> ' + esc(p.farming_type || 'Not set') + '</div>' +
        '<div><b>Irrigation:</b> ' + esc(p.irrigation_type || 'Not set') + '</div>' +
        '<div><b>Experience:</b> ' + esc(p.farming_experience || 'Not set') + '</div>' +
        '<div><b>Location:</b> ' + esc(p.farm_location || 'Not set') + '</div>' +
        '<div><b>Crops:</b> ' + esc(Array.isArray(p.crops) ? p.crops.join(', ') : (p.crops || 'Not set')) + '</div></div></div>';
      return;
    }
    el.innerHTML = '<div class="fb-skeleton" style="height:200px;"></div>';
    if (tab === 'saved') {
      FB.saved({ limit: 50, page: 1 }).then(function (data) {
        var items = (data && data.items) || [];
        if (!items.length) { el.innerHTML = emptyHtml('fa-bookmark', 'No saved posts yet', 'Tap the bookmark icon on posts you like'); return; }
        var savedList = items.filter(function (x) { return x.content_type === 'short'; });
        el.innerHTML = items.map(postCardHtml).join('');
        bindPostContainer(el, items, { savedList: savedList });
      }).catch(function () { el.innerHTML = emptyHtml('fa-circle-exclamation', 'Could not load saved posts'); });
      return;
    }
    var content = tab === 'posts' ? 'post' : 'short';
    var minePosts = (Array.isArray(p.posts) ? p.posts : []).filter(function (x) { return x.content_type === content; });
    if (!minePosts.length) {
      el.innerHTML = emptyHtml(tab === 'posts' ? 'fa-file-lines' : 'fa-clapperboard', tab === 'posts' ? 'You have no posts yet' : 'You have no shorts yet', tab === 'posts' ? 'Share your first update from the Post tab' : 'Create a short using the Post tab (Short type)');
      return;
    }
    el.innerHTML = minePosts.map(postCardHtml).join('');
    bindPostContainer(el, minePosts);
  }

  function openEditProfile() {
    if (!me) return;
    $('fbEditAvatar').src = avatarOf(me);
    $('fbEditAvatarUrl').value = me.profile_image || '';
    $('fbEditBio').value = me.bio || '';
    $('fbEditLocation').value = me.farm_location || '';
    $('fbEditFarmingType').value = me.farming_type || '';
    closeModals();
    $('fbEditModal').classList.add('open');
  }

  function saveProfile() {
    if (!guard('Please login')) return;
    var btn = $('fbEditSave');
    var bio = $('fbEditBio').value.trim();
    if (bio.length > 300) { toast('Bio must be 300 characters or fewer', 'warning'); return; }
    if (btn && btn.disabled) return;
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...'; }
    var data = {
      bio: bio,
      farm_location: $('fbEditLocation').value.trim(),
      farming_type: $('fbEditFarmingType').value,
      profile_image: $('fbEditAvatarUrl').value.trim() || null
    };
    FB.updateProfile(data).then(function () {
      toast('Profile updated');
      closeModals();
      renderSelf(lastSelfTab);
    }).catch(apiErr).then(function () {
      if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-check"></i> Save Changes'; }
    });
  }

  /* ==========================================================================
     FARMER MODAL
  ========================================================================== */
  function openFarmer(userId) {
    if (!FB) return;
    closeModals();
    var modal = $('fbFarmerModal');
    modal.classList.add('open');
    $('fbFarmerBody').innerHTML = '<div class="fb-skeleton" style="height:220px;margin-top:14px;"></div>';
    FB.userProfile(userId).then(function (p) {
      var mine = me && me.id === p.id;
      var tags = '';
      var cropStr = p.crops;
      if (typeof cropStr === 'string') cropStr = cropStr.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
      if (Array.isArray(cropStr) && cropStr.length) {
        tags = '<div class="fb-profile-tags">' + cropStr.slice(0, 6).map(function (c) { return '<span>' + esc(c) + '</span>'; }).join('') + '</div>';
      }
      var postsHtml = '';
      if (p.posts && p.posts.length) {
        postsHtml = '<div style="font-size:12px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.4px;margin:12px 0 8px;">Recent posts</div>' +
          '<div class="fb-fp-posts">' + p.posts.slice(0, 9).map(function (pt) {
            if (pt.media_type === 'image' || pt.media_type === 'video') {
              var inner = pt.media_type === 'video'
                ? '<img src="' + esc(pt.thumbnail_url || '') + '" alt="" style="background:linear-gradient(135deg,#1B5E3F,#52B788);" onerror="this.style.display=\'none\';"><i class="fas fa-play" style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);color:#fff;text-shadow:0 1px 4px rgba(0,0,0,.6);"></i>'
                : '<img src="' + esc(pt.media_url) + '" alt="">';
              return '<div class="fb-fp-post" data-open-post="' + esc(pt.id) + '">' + inner + '</div>';
            }
            return '<div class="fb-fp-post" data-open-post="' + esc(pt.id) + '" style="display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#0F2E1E,#2D8659);"><i class="fas fa-wheat-awn" style="color:rgba(255,255,255,.6);font-size:16px;"></i></div>';
          }).join('') + '</div>';
      }
      var actions = '';
      if (mine) {
        actions = '<button class="btn btn-primary" id="fbFpEdit" style="background:linear-gradient(135deg,#1B5E3F,#2D8659);border:none;color:#fff;"><i class="fas fa-user-pen"></i> Edit Profile</button>';
      } else {
        actions = '<button class="btn btn-primary" id="fbFpFollow" data-uid="' + esc(p.id) + '" style="background:' + (p.is_followed ? 'linear-gradient(135deg,#44524a,#2c3a32);color:#fff;' : 'linear-gradient(135deg,#1B5E3F,#2D8659);') + ';border:none;color:#fff;"><i class="fas ' + (p.is_followed ? 'fa-user-minus' : 'fa-user-plus') + '"></i> ' + (p.is_followed ? 'Following' : 'Follow') + '</button>' +
          '<button class="btn" id="fbFpMsg" data-uid="' + esc(p.id) + '" style="border:1px solid var(--border-light);"><i class="fas fa-comment-dots"></i> Message</button>';
      }
      $('fbFarmerBody').innerHTML =
        '<div class="fb-fp-cover"></div>' +
        '<div class="fb-fp-main">' +
        '<img class="fb-fp-avatar" src="' + esc(avatarOf(p)) + '" alt="' + esc(p.full_name) + '">' +
        '<div class="fb-fp-head"><h3>' + esc(p.full_name) + (p.id === (me && me.id) ? ' <i class="fas fa-circle-check" style="color:#2D8659;font-size:14px;"></i>' : '') + '</h3>' +
        '<div class="fb-fp-meta">' + esc(p.farmer_id || '') + (p.farm_location ? ' · ' + esc(p.farm_location) : '') + '</div></div>' +
        (p.bio ? '<div class="fb-fp-bio">' + esc(p.bio) + '</div>' : '') +
        tags +
        '<div class="fb-fp-stats">' +
        '<div class="fb-fp-stat"><b>' + fmtNum(p.posts_count + p.shorts_count) + '</b><span>Posts</span></div>' +
        '<div class="fb-fp-stat"><b>' + fmtNum(p.followers_count) + '</b><span>Followers</span></div>' +
        '<div class="fb-fp-stat"><b>' + fmtNum(p.following_count) + '</b><span>Following</span></div>' +
        '</div>' +
        '<div class="fb-fp-actions">' + actions + '</div>' +
        postsHtml +
        '</div>';
      var eb = $('fbFpEdit');
      if (eb) eb.addEventListener('click', function () { closeModals(); openEditProfile(); });
      var fb = $('fbFpFollow');
      if (fb) fb.addEventListener('click', function () {
        if (!guard('Please login to follow farmers')) return;
        FB.follow(p.id).then(function (d) {
          p.is_followed = !!d.following;
          fb.style.background = p.is_followed ? 'linear-gradient(135deg,#44524a,#2c3a32)' : 'linear-gradient(135deg,#1B5E3F,#2D8659)';
          fb.innerHTML = '<i class="fas ' + (p.is_followed ? 'fa-user-minus' : 'fa-user-plus') + '"></i> ' + (p.is_followed ? 'Following' : 'Follow');
          toast(d.message || (p.is_followed ? 'Following' : 'Unfollowed'));
        }).catch(apiErr);
      });
      var mb2 = $('fbFpMsg');
      if (mb2) mb2.addEventListener('click', function () {
        window.location.href = 'messages.html?farmer=' + encodeURIComponent(p.id);
      });
      $('fbFarmerBody').querySelectorAll('[data-open-post]').forEach(function (el) {
        el.addEventListener('click', function () { openDetail(el.getAttribute('data-open-post')); });
      });
    }).catch(function () {
      $('fbFarmerBody').innerHTML = emptyHtml('fa-circle-exclamation', 'Could not load profile');
    });
  }

  /* ==========================================================================
     STORY CREATE
  ========================================================================== */
  function bindStoryEvents() {
    $('fbStAddMedia').addEventListener('click', function () { $('fbStFileInput').click(); });
    $('fbStFileInput').addEventListener('change', function () {
      var f = this.files && this.files[0];
      if (!f) return;
      var isVid = f.type.indexOf('video') === 0;
      if (!isVid && f.type.indexOf('image') !== 0) {
        toast('Choose an image or video file', 'warning');
        return;
      }
      storyMediaData = { file: f, type: isVid ? 'video' : 'image' };
      var url = URL.createObjectURL(f);
      $('fbStPreview').style.display = 'block';
      if (isVid) {
        $('fbStPreviewVideo').style.display = 'block';
        $('fbStPreviewVideo').src = url;
        $('fbStPreviewImg').style.display = 'none';
      } else {
        $('fbStPreviewImg').style.display = 'block';
        $('fbStPreviewImg').src = url;
        $('fbStPreviewVideo').style.display = 'none';
        $('fbStPreviewVideo').removeAttribute('src');
      }
    });
    $('fbStMediaRemove').addEventListener('click', function () {
      storyMediaData = null;
      $('fbStFileInput').value = '';
      $('fbStPreview').style.display = 'none';
    });
    $('fbStCaptionInput').addEventListener('input', function () {
      $('fbStCharCount').textContent = this.value.length + ' / 300 · Stories stay live for 24 hours';
    });
    $('fbStPostBtn').addEventListener('click', function () {
      if (!guard('Please login to post a story')) return;
      var caption = $('fbStCaptionInput').value.trim();
      var btn = $('fbStPostBtn');
      btn.disabled = true;
      var publish = function (payload) {
        FB.createStory(payload).then(function (d) {
          btn.disabled = false;
          toast((d && d.message) || 'Story published!');
          closeModals();
          resetStoryForm();
          renderStoriesRow();
        }).catch(function (e) {
          btn.disabled = false;
          apiErr(e);
        });
      };
      if (storyMediaData) {
        $('fbUpFill').style.width = '45%';
        $('fbUploadProgress').style.display = 'block';
        FB.uploadMedia(storyMediaData.file, storyMediaData.type === 'video' ? 'video' : 'image').then(function (data) {
          $('fbUpFill').style.width = '90%';
          publish({
            media_url: data.url,
            media_type: storyMediaData.type,
            caption: caption || null
          });
        }).catch(function (e) {
          btn.disabled = false;
          $('fbUploadProgress').style.display = 'none';
          apiErr(e);
        });
      } else {
        publish({ media_type: 'text', caption: caption });
      }
    });
    $('fbStClose').addEventListener('click', stopSt);
    $('fbStPrev').addEventListener('click', backSt);
    $('fbStNext').addEventListener('click', forwardSt);
    $('fbStMedia').addEventListener('click', function () { toggleStPause(); });
    $('fbStDelete').addEventListener('click', function () {
      var group = storiesByAuthor[stIx];
      if (!group || group.author.id !== (me && me.id)) return;
      var st = group.stories[stSIdx];
      if (!st) return;
      if (!confirm('Delete this story?')) return;
      FB.deleteStory(st.id).then(function () {
        toast('Story deleted', 'info');
        group.stories.splice(stSIdx, 1);
        if (!group.stories.length) {
          storiesByAuthor.splice(stIx, 1);
          stopSt();
          renderStoriesRow();
        } else {
          stSIdx = Math.min(stSIdx, group.stories.length - 1);
          renderStory();
        }
      }).catch(apiErr);
    });
    $('fbStMute').addEventListener('click', function () {
      stMuted = !stMuted;
      var v = $('fbStMedia').querySelector('video');
      if (v) { v.muted = stMuted; v.volume = stMuted ? 0 : 1; }
      this.querySelector('i').className = stMuted ? 'fas fa-volume-xmark' : 'fas fa-volume-up';
      toast(stMuted ? 'Sound muted' : 'Sound on', 'info');
    });
  }

  /* ==========================================================================
     EVENTS
  ========================================================================== */
  function bindEvents() {
    document.querySelectorAll('.fb-topnav button[data-view]').forEach(function (b) {
      b.addEventListener('click', function () { switchView(b.getAttribute('data-view')); });
    });
    document.querySelectorAll('.fb-link[data-goto]').forEach(function (b) {
      b.addEventListener('click', function () { switchView(b.getAttribute('data-goto')); });
    });
    document.querySelectorAll('.fb-link[data-hashtag]').forEach(function (b) {
      b.addEventListener('click', function () { openTagSearch(b.getAttribute('data-hashtag')); });
    });
    document.querySelectorAll('.fb-link[data-sugtag]').forEach(function (b) {
      b.addEventListener('click', function () {
        var cur = $('fbTags').value.trim();
        $('fbTags').value = cur ? cur + ', ' + b.getAttribute('data-sugtag') : b.getAttribute('data-sugtag');
      });
    });
    $('fbHomeBtn').addEventListener('click', function () { window.location.href = 'index.html'; });
    bindSearchEvents();
    bindComposerEvents();
    bindTagPeople();

    document.getElementById('fbSelfTabs').addEventListener('click', function (e) {
      var btn = e.target.closest('button');
      if (!btn) return;
      renderSelf(btn.getAttribute('data-tab'));
    });
    $('fbEditSave').addEventListener('click', saveProfile);
    $('fbReportBtn').addEventListener('click', submitReport);

    $('fbDetailCommentBtn').addEventListener('click', addDetailComment);
    $('fbDetailCommentInput').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') addDetailComment();
    });

    var stage = $('fbSpStage');
    var spScrollDebounce = null;
    stage.addEventListener('scroll', function () {
      if (spScrollDebounce) clearTimeout(spScrollDebounce);
      spScrollDebounce = setTimeout(function () { activateSp(true); }, 100);
    }, { passive: true });
    stage.addEventListener('wheel', function (e) {
      if (Math.abs(e.deltaY) < 8) return;
      e.preventDefault();
      if (spWheelLock) return;
      spWheelLock = true;
      setTimeout(function () { spWheelLock = false; }, 300);
      if (e.deltaY > 0) nextSp(); else prevSp();
    }, { passive: false });
    $('fbSpClose').addEventListener('click', stopSp);
    $('fbSpHome').addEventListener('click', function () { stopSp(); switchView('home'); });
    $('fbSpNext').addEventListener('click', nextSp);
    $('fbSpPrev').addEventListener('click', prevSp);
    stage.addEventListener('click', function (e) {
      var rail = e.target.closest('[data-sp-act]');
      if (rail) { handleSpAction(e); return; }
      var follow = e.target.closest('[data-sp-follow]');
      if (follow) {
        var uid = follow.getAttribute('data-sp-follow');
        if (!guard('Please login to follow farmers')) return;
        FB.follow(uid).then(function (d) {
          var f = !!d.following;
          follow.classList.toggle('following', f);
          follow.textContent = f ? 'Following' : 'Follow';
          toast(d.message || (f ? 'Following' : 'Unfollowed'));
        }).catch(apiErr);
        return;
      }
      var video = e.target.closest('video');
      if (video || e.target.closest('.fb-sp-slide')) toggleSpPause();
    });
    $('fbSpCommentBtn').addEventListener('click', addSpComment);
    $('fbSpCommentInput').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') addSpComment();
    });
    $('fbSpCloseComments').addEventListener('click', function () {
      $('fbSpCommentsPanel').style.display = 'none';
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        if ($('fbStoriesPlayer').classList.contains('open')) { stopSt(); return; }
        if ($('fbShortsPlayer').classList.contains('open')) { stopSp(); return; }
        closeModals();
        closeMoreMenu();
      }
      if (e.key === 'ArrowDown' && $('fbShortsPlayer').classList.contains('open')) { e.preventDefault(); nextSp(); }
      if (e.key === 'ArrowUp' && $('fbShortsPlayer').classList.contains('open')) { e.preventDefault(); prevSp(); }
      if ((e.key === 'ArrowRight') && $('fbShortsPlayer').classList.contains('open')) { e.preventDefault(); nextSp(); }
      if (e.key === 'ArrowLeft' && $('fbShortsPlayer').classList.contains('open')) { e.preventDefault(); prevSp(); }
      if ((e.key === ' ' || e.key === 'Spacebar') && $('fbShortsPlayer').classList.contains('open')) { e.preventDefault(); toggleSpPause(); }
      if (e.key === 'ArrowRight' && $('fbStoriesPlayer').classList.contains('open')) forwardSt();
      if (e.key === 'ArrowLeft' && $('fbStoriesPlayer').classList.contains('open')) backSt();
    });

    document.querySelectorAll('.fb-sheet-close[data-close]').forEach(function (btn) {
      btn.addEventListener('click', function () { document.getElementById(btn.getAttribute('data-close')).classList.remove('open'); });
    });
    document.querySelectorAll('.fb-modal-backdrop').forEach(function (bd) {
      bd.addEventListener('click', function (e) {
        if (e.target === bd) bd.classList.remove('open');
      });
    });
    $('fbCopyLink').addEventListener('click', function () {
      copyText(window.location.href.split('?')[0]);
      if (activeShareId) doShare();
    });
    window.addEventListener('hashchange', function () {
      var v = readHash();
      if (v) switchView(v);
    });
  }

  /* ==========================================================================
     INIT
  ========================================================================== */
  function init() {
    if (!FB) {
      $('fbHomePosts').innerHTML = emptyHtml('fa-plug', 'FarmBuzz API is unavailable', 'Make sure the Farm Assist backend is running');
      return;
    }
    bindEvents();
    bindStoryEvents();
    loadMe();
    var v = readHash();
    if (v) switchView(v);
    else switchView('home');
  }

  function loadMe() {
    if (!authed() || !FB) return;
    FB.profile().then(function (p) {
      me = p;
      meLoaded = true;
      if (view === 'home') renderForYou();
      if (view === 'self') renderSelf(lastSelfTab);
    }).catch(function () {});
  }

  var postQParam = null;
  try {
    postQParam = new URLSearchParams(window.location.search).get('post');
  } catch (e) {}

  init();

  if (postQParam) {
    FB && FB.feed({ limit: 1, page: 1, search: postQParam }).then(function (data) {
      var items = (data && data.items) || [];
      if (items.length) openDetail(items[0].id);
    }).catch(function () {});
  }
})();