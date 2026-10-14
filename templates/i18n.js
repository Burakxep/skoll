// Shared TR|EN switch. Pages are rendered in English by Python; every
// translatable element carries data-i18n="key" (+ data-vars='{...}' for
// placeholders), data-i18n-ph (placeholder) or data-i18n-aria (aria-label).
// window.SKOLL_I18N is the same dictionary Python used (templates/i18n.json).
(function () {
  var dict = window.SKOLL_I18N || { en: {} };
  var lang = null;
  try { lang = localStorage.getItem("skoll.lang"); } catch (e) {}
  if (!dict[lang]) {
    lang = /^tr\b/i.test(navigator.language || "") ? "tr" : "en";
  }

  function t(key, vars) {
    var s = (dict[lang] && dict[lang][key]) || dict.en[key] || key;
    return s.replace(/\{(\w+)\}/g, function (m, k) {
      return vars && vars[k] !== undefined ? vars[k] : m;
    });
  }
  window.skollT = t;
  window.skollLang = function () { return lang; };

  function vars(el) {
    try { return JSON.parse(el.dataset.vars || "{}"); } catch (e) { return {}; }
  }

  function apply() {
    document.documentElement.lang = lang;
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      el.textContent = t(el.dataset.i18n, vars(el));
    });
    document.querySelectorAll("[data-i18n-ph]").forEach(function (el) {
      el.placeholder = t(el.dataset.i18nPh);
    });
    document.querySelectorAll("[data-i18n-aria]").forEach(function (el) {
      el.setAttribute("aria-label", t(el.dataset.i18nAria));
    });
    document.querySelectorAll("[data-i18n-title]").forEach(function (el) {
      el.title = t(el.dataset.i18nTitle, vars(el));
    });
    document.querySelectorAll(".lang-btn").forEach(function (b) {
      b.setAttribute("aria-pressed", b.dataset.lang === lang ? "true" : "false");
    });
    document.dispatchEvent(new CustomEvent("skoll:lang", { detail: lang }));
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".lang-btn").forEach(function (b) {
      b.onclick = function () {
        lang = b.dataset.lang;
        try { localStorage.setItem("skoll.lang", lang); } catch (e) {}
        apply();
      };
    });
    apply();
  });
})();
