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
})();