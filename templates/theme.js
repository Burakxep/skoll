// Shared by every Sköll page. Runs in <head>: apply the saved theme before
// paint (falling back to the system setting), then wire the #theme button.
(function () {
  var root = document.documentElement;
  var t = null;
  try { t = localStorage.getItem("skoll.theme"); } catch (e) {}
  if (t !== "light" && t !== "dark") {
    t = matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }
  root.dataset.theme = t;

  function sync() {
    var dark = root.dataset.theme === "dark";
    var t = window.skollT || function (k) { return k === "theme.light" ? "Light" : "Dark"; };
    document.getElementById("theme-icon").textContent = dark ? "☀" : "☾";
    document.getElementById("theme-label").textContent = t(dark ? "theme.light" : "theme.dark");
  }
  document.addEventListener("skoll:lang", function () {
    if (document.getElementById("theme")) sync();
  });
  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("theme");
    if (btn) {
      btn.onclick = function () {
        root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
        try { localStorage.setItem("skoll.theme", root.dataset.theme); } catch (e) {}
        sync();
      };
      sync();
    }

    // Settings popover: holds the language switch + theme toggle.
    var sb = document.getElementById("settings-btn");
    var pop = document.getElementById("settings-pop");
    if (sb && pop) {
      var setOpen = function (open) {
        pop.hidden = !open;
        sb.setAttribute("aria-expanded", open ? "true" : "false");
      };
      sb.onclick = function (e) {
        e.stopPropagation();
        setOpen(pop.hidden);
      };
      document.addEventListener("click", function (e) {
        if (!pop.hidden && !pop.contains(e.target) && e.target !== sb) setOpen(false);
      });
      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && !pop.hidden) { setOpen(false); sb.focus(); }
      });
    }
  });
})();
