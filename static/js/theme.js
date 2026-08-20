(function () {
    const STORAGE_KEY = 'theme-preference';
    const THEMES = {
        LIGHT: 'light',
        DARK: 'dark'
    };

    const root = document.documentElement;
    const mediaQuery = window.matchMedia
        ? window.matchMedia('(prefers-color-scheme: dark)')
        : null;

    function normalizeTheme(value) {
        if (value === THEMES.LIGHT || value === THEMES.DARK) {
            return value;
        }
        return null;
    }

    function readSavedTheme() {
        try {
            return normalizeTheme(localStorage.getItem(STORAGE_KEY));
        } catch (error) {
            return null;
        }
    }

    function getSystemTheme() {
        return mediaQuery && mediaQuery.matches ? THEMES.DARK : THEMES.LIGHT;
    }

    function getCurrentTheme() {
        return normalizeTheme(root.getAttribute('data-theme')) || readSavedTheme() || getSystemTheme();
    }

    function getNextTheme(currentTheme) {
        return currentTheme === THEMES.DARK ? THEMES.LIGHT : THEMES.DARK;
    }

    function updateToggleButtons(currentTheme) {
        const nextTheme = getNextTheme(currentTheme);
        const nextLabel = nextTheme === THEMES.DARK
            ? 'Switch to dark theme'
            : 'Switch to light theme';

        document.querySelectorAll('[data-theme-toggle]').forEach(function (button) {
            button.setAttribute('aria-label', nextLabel);
            button.setAttribute('title', nextLabel);
            button.setAttribute('data-theme-next', nextTheme);

            const icon = button.querySelector('.theme-toggle-icon');
            if (icon) {
                icon.textContent = currentTheme === THEMES.DARK ? '☀' : '🌙';
            }
        });
    }

    function applyTheme(theme, options) {
        const settings = options || {};
        const resolvedTheme = normalizeTheme(theme) || THEMES.LIGHT;

        root.setAttribute('data-theme', resolvedTheme);
        root.style.colorScheme = resolvedTheme;
        updateToggleButtons(resolvedTheme);

        if (settings.persist) {
            try {
                localStorage.setItem(STORAGE_KEY, resolvedTheme);
            } catch (error) {
                // Ignore localStorage failures (private mode, disabled storage, etc.)
            }
        }
    }

    function toggleTheme() {
        const currentTheme = getCurrentTheme();
        const nextTheme = getNextTheme(currentTheme);
        applyTheme(nextTheme, { persist: true });
    }

    function bindToggleButtons() {
        document.querySelectorAll('[data-theme-toggle]').forEach(function (button) {
            if (button.dataset.themeBound === '1') {
                return;
            }

            button.dataset.themeBound = '1';
            button.addEventListener('click', toggleTheme);
        });
    }

    function initTheme() {
        const initialTheme = normalizeTheme(root.getAttribute('data-theme')) || readSavedTheme() || getSystemTheme();
        applyTheme(initialTheme, { persist: false });
        bindToggleButtons();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTheme);
    } else {
        initTheme();
    }

    if (mediaQuery) {
        const onSystemThemeChange = function (event) {
            if (readSavedTheme()) {
                return;
            }
            applyTheme(event.matches ? THEMES.DARK : THEMES.LIGHT, { persist: false });
        };

        if (mediaQuery.addEventListener) {
            mediaQuery.addEventListener('change', onSystemThemeChange);
        } else if (mediaQuery.addListener) {
            mediaQuery.addListener(onSystemThemeChange);
        }
    }
})();
