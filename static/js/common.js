/* LitReview v2 — shared utilities (theme, data helpers) */
(function () {
  function applyTheme() {
    const d = localStorage.theme === 'dark' ||
      (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.classList.toggle('dark', d);
  }
  applyTheme();
  window.toggleTheme = function () {
    document.documentElement.classList.toggle('dark');
    localStorage.theme = document.documentElement.classList.contains('dark') ? 'dark' : 'light';
  };
  window.loadData = function () {
    return fetch('/data/reviews.json').then(function (r) {
      if (!r.ok) throw new Error('data unreachable');
      return r.json();
    });
  };
  window.areaName = function (areas, id) {
    var a = areas.find(function (x) { return x.id === id; });
    return a ? a.name : id;
  };
  window.escapeHtml = function (s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  /* minimal markdown renderer for the submit form preview (no external deps) */
  window.renderMarkdown = function (src) {
    var lines = src.replace(/\t/g, '    ').split('\n');
    var html = '', inCode = false, inList = false, inNum = false, para = [];
    function flushPara() {
      if (para.length) { html += '<p>' + para.join(' ') + '</p>'; para = []; }
    }
    function closeList() {
      if (inList) { html += '</ul>'; inList = false; }
      if (inNum) { html += '</ol>'; inNum = false; }
    }
    function inline(t) {
      return t
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/\*([^*]+)\*/g, '<em>$1</em>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    }
    lines.forEach(function (raw) {
      var line = raw.trimEnd();
      var m;
      if (line.trim().startsWith('```')) {
        flushPara(); closeList();
        if (inCode) { html += '</code></pre>'; inCode = false; }
        else { html += '<pre><code>'; inCode = true; }
        return;
      }
      if (inCode) { html += escapeHtml(line) + '\n'; return; }
      if ((m = line.match(/^(#{1,6})\s+(.*)/))) {
        flushPara(); closeList();
        var lv = m[1].length;
        html += '<h' + lv + '>' + inline(m[2]) + '</h' + lv + '>';
        return;
      }
      if ((m = line.match(/^\s*[-*+]\s+(.*)/))) {
        flushPara();
        if (!inList) { closeList(); html += '<ul>'; inList = true; }
        html += '<li>' + inline(m[1]) + '</li>';
        return;
      }
      if ((m = line.match(/^\s*\d+[.)]\s+(.*)/))) {
        flushPara();
        if (!inNum) { closeList(); html += '<ol>'; inNum = true; }
        html += '<li>' + inline(m[1]) + '</li>';
        return;
      }
      if (line.trim() === '') { flushPara(); closeList(); return; }
      if (/^>/.test(line.trim())) {
        flushPara(); closeList();
        html += '<blockquote>' + inline(line.trim().replace(/^>\s?/, '')) + '</blockquote>';
        return;
      }
      if (line.trim().startsWith('---')) { flushPara(); closeList(); html += '<hr>'; return; }
      closeList();
      para.push(inline(line));
    });
    flushPara(); closeList();
    if (inCode) html += '</code></pre>';
    return html;
  };

  /* reveal titles on load: split by words and stagger-animate each up */
  function initRevealTitles() {
    document.querySelectorAll('.reveal-title').forEach(function (el) {
      var lines = el.innerHTML.split(/\s*<br\s*\/?>\s*/gi);
      var wordIndex = 0;
      el.innerHTML = lines.map(function (line) {
        var words = (line || '&nbsp;').trim().split(/\s+/);
        var wordSpans = words.map(function (word) {
          var delay = (wordIndex++ * 0.05).toFixed(3) + 's';
          return '<span class="reveal-word"><span class="reveal-text" style="transition-delay:' + delay + '">' + word + '</span></span>';
        }).join(' ');
        return '<span class="reveal-line">' + wordSpans + '</span>';
      }).join('');
      requestAnimationFrame(function () {
        el.classList.add('is-visible');
      });
    });
  }

  /* scroll-triggered animations (data-effect + data-delay like xuemin.org) */
  var scrollObserver;
  function observeScrollAnimate(el) {
    if (!el || el.classList.contains('scroll-observed')) return;
    el.classList.add('scroll-observed');
    if (!scrollObserver) {
      scrollObserver = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            var target = entry.target;
            var effect = target.dataset.effect || 'fadeIn';
            var delay = target.dataset.delay || '0s';
            target.style.animationDelay = delay;
            target.style.animationName = effect;
            target.classList.add('animated');
            scrollObserver.unobserve(target);
          }
        });
      }, { threshold: 0.15, rootMargin: '0px 0px -40px 0px' });
    }
    scrollObserver.observe(el);
  }
  window.observeScrollAnimate = observeScrollAnimate;

  function initScrollAnimations() {
    document.querySelectorAll('.scroll-animate').forEach(observeScrollAnimate);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      initRevealTitles();
      initScrollAnimations();
    });
  } else {
    initRevealTitles();
    initScrollAnimations();
  }
})();