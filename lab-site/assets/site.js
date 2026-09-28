(function () {
  'use strict';
  // Remember the chosen language for the root redirect (the root page sends visitors to /en/ by default).
  try {
    var l = document.documentElement.getAttribute('lang');
    if (l === 'en' || l === 'pl') { document.querySelectorAll('.seg a').forEach(function (a) {
      a.addEventListener('click', function () { try { localStorage.setItem('lab-lang', a.getAttribute('hreflang')); } catch (e) {} }); }); }
  } catch (e) {}

  // Theme toggle: cycles light and dark, stored per browser. Without a stored choice the OS setting applies.
  var btn = document.querySelector('.theme');
  if (btn) btn.addEventListener('click', function () {
    var root = document.documentElement;
    var cur = root.getAttribute('data-theme');
    var dark = cur ? cur === 'dark' : (window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches);
    var next = dark ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem('lab-theme', next); } catch (e) {}
  });

  // Copy buttons (BibTeX). Falls back to selecting the text when the clipboard is not available.
  document.querySelectorAll('.copy').forEach(function (b) {
    b.addEventListener('click', function () {
      var el = document.getElementById(b.getAttribute('data-target'));
      if (!el) return;
      var text = el.textContent;
      var done = function () { var old = b.textContent; b.textContent = b.getAttribute('data-done'); setTimeout(function () { b.textContent = old; }, 1600); };
      var select = function () { var r = document.createRange(); r.selectNodeContents(el); var s = getSelection(); s.removeAllRanges(); s.addRange(r); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, select); else select();
    });
  });

  // Dossier contents: on wide screens the list is always open; on narrow ones it starts collapsed.
  var toc = document.querySelector('.tocd');
  if (toc && window.matchMedia) {
    var sync = function () { toc.open = window.matchMedia('(min-width: 1000px)').matches; };
    sync(); matchMedia('(min-width: 1000px)').addEventListener('change', sync);
  }
})();
