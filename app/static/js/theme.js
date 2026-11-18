/**
 * Athar Dynamic Dark/Light Theme Toggle
 * Persists user preference to localStorage ("athar-theme") and dispatches
 * "athar:themechange" so Chart.js and dynamic components re-theme cleanly.
 */
(function () {
    "use strict";

    function getCurrentTheme() {
        const current = document.documentElement.dataset.theme;
        return current === "dark" ? "dark" : "light";
    }

    function updateToggleButton(btn, theme) {
        if (!btn) return;
        const _t = typeof window._t === "function" ? window._t : (k) => k;
        const textSpan = btn.querySelector(".theme-toggle-text");
        const nextLabel = theme === "dark" ? _t("athar-theme-light") : _t("athar-theme-dark");
        if (textSpan && nextLabel && nextLabel !== "athar-theme-light" && nextLabel !== "athar-theme-dark") {
            textSpan.textContent = nextLabel;
        } else if (textSpan) {
            textSpan.textContent = theme === "dark" ? "Light" : "Dark";
        }
        btn.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
    }

    function applyTheme(theme) {
        const normalized = theme === "dark" ? "dark" : "light";
        document.documentElement.dataset.theme = normalized;
        try {
            localStorage.setItem("athar-theme", normalized);
        } catch (err) {
            // Ignore private-browsing or restricted storage failures
        }
        const btn = document.getElementById("theme-toggle-btn");
        updateToggleButton(btn, normalized);
        window.dispatchEvent(new CustomEvent("athar:themechange", { detail: { theme: normalized } }));
    }

    document.addEventListener("DOMContentLoaded", () => {
        const btn = document.getElementById("theme-toggle-btn");
        updateToggleButton(btn, getCurrentTheme());
        if (btn) {
            btn.addEventListener("click", () => {
                const nextTheme = getCurrentTheme() === "dark" ? "light" : "dark";
                applyTheme(nextTheme);
            });
        }
    });

    window.AtharTheme = {
        getCurrentTheme,
        applyTheme,
    };
})();

