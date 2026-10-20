(() => {
  "use strict";

  const storageKey = "guia-pessoal-theme";
  let savedTheme = null;
  try {
    savedTheme = window.localStorage.getItem(storageKey);
  } catch (_error) {
    // The theme still works for this page when storage is unavailable.
  }

  const systemPrefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const initialTheme = savedTheme === "light" || savedTheme === "dark"
    ? savedTheme
    : (systemPrefersDark ? "dark" : "light");

  function applyTheme(theme, persist) {
    document.documentElement.dataset.theme = theme;
    const themeColor = document.querySelector('meta[name="theme-color"]');
    if (themeColor) themeColor.content = theme === "dark" ? "#111820" : "#e4e9ef";
    const toggle = document.getElementById("theme-toggle");
    if (toggle) {
      const darkModeActive = theme === "dark";
      toggle.textContent = darkModeActive ? "☀️ Modo claro" : "🌙 Modo escuro";
      toggle.setAttribute("aria-label", darkModeActive ? "Ativar modo claro" : "Ativar modo escuro");
      toggle.setAttribute("aria-pressed", String(darkModeActive));
    }
    if (persist) {
      try {
        window.localStorage.setItem(storageKey, theme);
      } catch (_error) {
        // Keep the selected theme for this page if storage is unavailable.
      }
    }
  }

  applyTheme(initialTheme, false);
  document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.getElementById("theme-toggle");
    if (!toggle) return;
    toggle.addEventListener("click", () => {
      const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      applyTheme(nextTheme, true);
    });
    applyTheme(document.documentElement.dataset.theme || initialTheme, false);
  });
})();
