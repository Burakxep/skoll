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
    // dark theme shows a sun (switch to light); light shows a moon (switch to dark)
    var sun = '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.2"/>'
      + '<path d="M12 2.5v2.4M12 19.1v2.4M21.5 12h-2.4M4.9 12H2.5M18.4 5.6l-1.7 1.7'
      + 'M7.3 16.7l-1.7 1.7M18.4 18.4l-1.7-1.7M7.3 7.3 5.6 5.6"/></svg>';
    var moon = '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">'
      + '<path d="M20 14.6A8 8 0 1 1 9.4 4a6.3 6.3 0 0 0 10.6 10.6z"/></svg>';
    document.getElementById("theme-icon").innerHTML = dark ? sun : moon;
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
