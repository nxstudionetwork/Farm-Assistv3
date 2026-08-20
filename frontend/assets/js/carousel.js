/* ========================================================================
   FARM ASSIST - CAROUSEL COMPONENT (vanilla JS)
   Features:
     - Auto-slide with pause on hover / touch / focus / reduced-motion
     - Swipe (touch + pointer) and arrow-key navigation
     - Prev / Next arrows, dots, progress counter ("1/5")
     - Screen-reader friendly (aria-live, aria-hidden slides)
   Usage:
     Carousel.init(document.getElementById('hero-carousel'), {
       autoplay: true,
       autoplayMs: 1100,
       loop: true,
       onSlideChange: function(index, total) {}
     });
   ======================================================================== */
(function (global) {
  'use strict';

  var REDUCED = false;
  try {
    REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch (e) {}

  function Carousel() {
    this.root = null;
    this.track = null;
    this.slides = [];
    this.dots = [];
    this.prevBtn = null;
    this.nextBtn = null;
    this.counter = null;
    this.current = 0;
    this.total = 0;
    this.opts = {};
    this.timer = null;
    this.paused = false;
    this.touchX = 0;
    this.touchY = 0;
    this.live = null;
  }

  Carousel.prototype.init = function (root, options) {
    if (!root) return;
    this.root = root;
    this.opts = options || {};
    this.opts.autoplay = this.opts.autoplay !== undefined ? this.opts.autoplay : true;
    this.opts.autoplayMs = this.opts.autoplayMs || 1100;
    this.opts.loop = this.opts.loop !== undefined ? this.opts.loop : true;
    this.track = root.querySelector('.fa-carousel-track');
    this.slides = Array.prototype.slice.call(root.querySelectorAll('.fa-carousel-slide'));
    this.total = this.slides.length;
    if (!this.track || this.total < 2) return;

    this.counter = root.querySelector('.fa-carousel-progress');
    this.prevBtn = root.querySelector('.fa-carousel-arrow.prev');
    this.nextBtn = root.querySelector('.fa-carousel-arrow.next');
    this.live = root.querySelector('.fa-carousel-live');

    this._buildDots();
    this._setAria();
    this._bind();
    this.goTo(0, true);

    if (this.opts.autoplay && !REDUCED) this._start();
  };

  /* ---- Dots ---------------------------------------------------------- */
  Carousel.prototype._buildDots = function () {
    var self = this;
    var container = this.root.querySelector('.fa-carousel-dots');
    if (!container) return;
    this.slides.forEach(function (s, i) {
      var d = document.createElement('button');
      d.type = 'button';
      d.className = 'fa-carousel-dot' + (i === 0 ? ' active' : '');
      d.setAttribute('aria-label', 'Go to slide ' + (i + 1));
      d.addEventListener('click', function () {
        self._pause();
        self.goTo(i);
        self._resume();
      });
      container.appendChild(d);
      self.dots.push(d);
    });
  };

  /* ---- ARIA ---------------------------------------------------------- */
  Carousel.prototype._setAria = function () {
    this.root.setAttribute('role', 'region');
    this.root.setAttribute('aria-roledescription', 'carousel');
    if (!this.root.getAttribute('aria-label')) {
      this.root.setAttribute('aria-label', 'Agriculture highlights');
    }
    this.slides.forEach(function (s, i) {
      if (!s.getAttribute('role')) s.setAttribute('role', 'group');
      s.setAttribute('aria-roledescription', 'slide');
      s.setAttribute('aria-label', 'Slide ' + (i + 1) + ' of ' + this.total);
    }, this);
    if (this.counter && !this.counter.getAttribute('aria-live')) {
      this.counter.setAttribute('aria-live', 'polite');
    }
  };

  /* ---- Navigation ---------------------------------------------------- */
  Carousel.prototype.goTo = function (index, instant) {
    if (this.total < 2) return;
    if (this.opts.loop) {
      index = (index + this.total) % this.total;
    } else {
      index = Math.max(0, Math.min(this.total - 1, index));
    }
    this.current = index;
    var offset = -index * 100;
    this.track.style.transform = 'translateX(' + offset + '%)';
    if (instant) this.track.style.transition = 'none';
    this._updateUI();
    var self = this;
    if (instant) {
      requestAnimationFrame(function () {
        self.track.style.transition = '';
      });
    }
    if (this.opts.onSlideChange) this.opts.onSlideChange(index, this.total);
  };

  Carousel.prototype.next = function () {
    this._pause();
    this.goTo(this.current + 1);
    this._resume();
  };

  Carousel.prototype.prev = function () {
    this._pause();
    this.goTo(this.current - 1);
    this._resume();
  };

  Carousel.prototype._updateUI = function () {
    this.slides.forEach(function (s, i) {
      s.setAttribute('aria-hidden', i === this.current ? 'false' : 'true');
    }, this);
    if (this.dots.length) {
      this.dots.forEach(function (d, i) {
        d.classList.toggle('active', i === this.current);
      }, this);
    }
    if (this.counter) {
      this.counter.textContent = (this.current + 1) + '/' + this.total;
    }
    if (this.live) {
      this.live.textContent = 'Slide ' + (this.current + 1) + ' of ' + this.total;
    }
    if (this.prevBtn && !this.opts.loop) this.prevBtn.disabled = this.current === 0;
    if (this.nextBtn && !this.opts.loop) this.nextBtn.disabled = this.current === this.total - 1;
  };

  /* ---- Autoplay ------------------------------------------------------ */
  Carousel.prototype._start = function () {
    var self = this;
    this._clearTimer();
    this.timer = setInterval(function () {
      if (!self.paused && !document.hidden) self.goTo(self.current + 1);
    }, this.opts.autoplayMs);
  };

  Carousel.prototype._clearTimer = function () {
    if (this.timer) { clearInterval(this.timer); this.timer = null; }
  };

  Carousel.prototype._pause = function () {
    this.paused = true;
  };

  Carousel.prototype._resume = function () {
    var self = this;
    this.paused = false;
    this._clearTimer();
    if (this.opts.autoplay && !REDUCED) {
      // Resume on the next tick so rapid clicks don't race the interval
      setTimeout(function () { self._start(); }, 10);
    }
  };

  /* ---- Events -------------------------------------------------------- */
  Carousel.prototype._bind = function () {
    var self = this;

    if (this.prevBtn) this.prevBtn.addEventListener('click', function () { self.prev(); });
    if (this.nextBtn) this.nextBtn.addEventListener('click', function () { self.next(); });

    // Pause autoplay while the user interacts (hover / focus)
    this.root.addEventListener('mouseenter', function () { self.paused = true; });
    this.root.addEventListener('mouseleave', function () { self.paused = false; });
    this.root.addEventListener('focusin', function () { self.paused = true; });
    this.root.addEventListener('focusout', function () { self.paused = false; });

    // Keyboard arrow navigation
    this.root.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowLeft') { e.preventDefault(); self.prev(); }
      if (e.key === 'ArrowRight') { e.preventDefault(); self.next(); }
    });

    // Swipe support (touch)
    this.root.addEventListener('touchstart', function (e) {
      if (e.touches.length !== 1) return;
      self.touchX = e.touches[0].clientX;
      self.touchY = e.touches[0].clientY;
      self.paused = true;
    }, { passive: true });

    this.root.addEventListener('touchend', function (e) {
      if (self.touchX === 0 && self.touchY === 0) return;
      var dx = e.changedTouches[0].clientX - self.touchX;
      var dy = e.changedTouches[0].clientY - self.touchY;
      if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) {
        if (dx < 0) self.next(); else self.prev();
      }
      self.touchX = 0;
      self.touchY = 0;
      setTimeout(function () { self.paused = false; }, 200);
    }, { passive: true });

    // Pointer-based swipe for mouse / pen
    this.root.addEventListener('pointerdown', function (e) {
      self._pStart = { x: e.clientX, y: e.clientY, t: Date.now() };
    });
    this.root.addEventListener('pointerup', function (e) {
      if (!self._pStart) return;
      var dx = e.clientX - self._pStart.x;
      var dy = e.clientY - self._pStart.y;
      if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) && (Date.now() - self._pStart.t) < 700) {
        if (dx < 0) self.next(); else self.prev();
      }
      self._pStart = null;
    });

    document.addEventListener('visibilitychange', function () {
      if (document.hidden) self._clearTimer();
      else if (!self.paused && self.opts.autoplay && !REDUCED) self._start();
    });
  };

  Carousel.prototype.destroy = function () {
    this._clearTimer();
  };

  global.Carousel = Carousel;
  global.FACarousel = {
    init: function (root, options) {
      var c = new Carousel();
      c.init(root, options);
      return c;
    }
  };

})(window);
