/* Default theme: change "dark" to "light" on the next line to switch the whole site. A reader's saved choice (toggle in the header) overrides it. */
const DEFAULT_THEME = "dark";
(function () {
  let theme = DEFAULT_THEME;
  try { const saved = localStorage.getItem("qer-theme"); if (saved === "light" || saved === "dark") theme = saved; } catch (e) { /* storage unavailable: the default applies */ }
  document.documentElement.setAttribute("data-theme", theme);
  const meta = document.querySelector('meta[name="color-scheme"]');
  if (meta) meta.setAttribute("content", theme);
})();
