/**
 * Compact Wikimedia-Commons-style Multilingual Activity Translation Panel
 * - Searchable language-code comboboxes across all 590+ Wikimedia / MinT languages
 *   (loaded immediately from wikimedia-languages.js and kept fresh via GET /api/languages)
 * - Supports both Title/Description (#translation-panel-root) and
 *   Results Summary/Notes (#results-translation-panel-root) sharing #translations_json
 * - Optional corner "Auto-translate with MinT" button per language card
 */
(function () {
    "use strict";

    const LANG_CODE_REGEX = /^[a-z]{2,12}(-[a-z0-9]{2,12})*$/;
    const MAX_LANGUAGES = 20;

    let languageCatalog = Array.isArray(window.ATHAR_WIKIMEDIA_LANGUAGES) && window.ATHAR_WIKIMEDIA_LANGUAGES.length
        ? window.ATHAR_WIKIMEDIA_LANGUAGES.slice()
        : [["ar", "العربية", "Arabic"], ["en", "English"], ["fr", "Français", "French"], ["es", "Español", "Spanish"]];

    const langNameByCode = {};
    function rebuildLangMap() {
        languageCatalog.forEach((row) => {
            if (!Array.isArray(row) || !row[0]) return;
            const code = String(row[0]).toLowerCase();
            langNameByCode[code] = row[1] || code;
        });
    }
    rebuildLangMap();

    // Shared translation state keyed by language code:
    // state[code] = { title, description, results_summary, results_notes, _panels: { main: bool, results: bool } }
    let state = {};
    const mountedPanels = [];

    function msg(key, fallback) {
        if (typeof window._t === "function") {
            const val = window._t(key);
            if (val && val !== key) return val;
        }
        return fallback;
    }

    function msgFormat(key, arg1, fallback) {
        if (typeof window._t === "function") {
            const val = window._t(key, arg1);
            if (val && val !== key) return val;
        }
        return fallback;
    }

    function getPrimaryLang() {
        const hidden = document.getElementById("primary_lang");
        return hidden ? String(hidden.value || "ar").trim().toLowerCase() : "ar";
    }

    function formatLangLabel(code) {
        const c = String(code || "").trim().toLowerCase();
        const name = langNameByCode[c];
        return name && name !== c ? `${c} — ${name}` : c;
    }

    function ensureLangEntry(code) {
        if (!state[code]) {
            state[code] = { _panels: { main: false, results: false } };
        }
        if (!state[code]._panels) {
            state[code]._panels = { main: false, results: false };
        }
        return state[code];
    }

    function syncToHidden() {
        const hidden = document.getElementById("translations_json");
        if (!hidden) return;
        const primary = getPrimaryLang();
        const cleaned = {};
        let count = 0;

        Object.keys(state).forEach((rawCode) => {
            if (count >= MAX_LANGUAGES) return;
            const code = String(rawCode || "").trim().toLowerCase();
            if (!code || code === primary || !LANG_CODE_REGEX.test(code)) return;
            const entry = state[rawCode] || {};
            const cleanedEntry = {};
            ["title", "description", "results_summary", "results_notes"].forEach((field) => {
                const v = typeof entry[field] === "string" ? entry[field].trim() : "";
                if (v) cleanedEntry[field] = v;
            });
            if (Object.keys(cleanedEntry).length > 0) {
                cleaned[code] = cleanedEntry;
                count += 1;
            }
        });

        hidden.value = Object.keys(cleaned).length > 0 ? JSON.stringify(cleaned) : "{}";
    }

    function filterLanguages(query, excludedCodes) {
        const q = String(query || "").trim().toLowerCase();
        const excluded = new Set(excludedCodes || []);
        const codeExact = [];
        const codePrefix = [];
        const nameMatch = [];

        languageCatalog.forEach((row) => {
            const code = String(row[0] || "").toLowerCase();
            if (!code || excluded.has(code)) return;
            const autonym = String(row[1] || code);
            const enName = String(row[2] || "");

            if (!q) {
                codePrefix.push(row);
                return;
            }
            if (code === q) {
                codeExact.push(row);
            } else if (code.startsWith(q)) {
                codePrefix.push(row);
            } else if (
                code.includes(q) ||
                autonym.toLowerCase().includes(q) ||
                (enName && enName.toLowerCase().includes(q))
            ) {
                nameMatch.push(row);
            }
        });

        return codeExact.concat(codePrefix, nameMatch).slice(0, 40);
    }

    function setupLangCombobox({ inputEl, menuEl, excludedProvider, onSelect, clearOnSelect }) {
        if (!inputEl || !menuEl) return null;
        let activeIdx = -1;

        function closeMenu() {
            menuEl.hidden = true;
            activeIdx = -1;
        }

        function chooseCode(code) {
            const norm = String(code || "").trim().toLowerCase();
            if (!norm || !LANG_CODE_REGEX.test(norm)) return false;
            closeMenu();
            onSelect(norm);
            if (clearOnSelect) {
                inputEl.value = "";
            }
            return true;
        }

        function renderMenu() {
            const query = inputEl.value.trim().toLowerCase();
            const excluded = excludedProvider ? excludedProvider() : [];
            const matches = filterLanguages(query, excluded);
            menuEl.innerHTML = "";
            activeIdx = -1;

            matches.forEach((row) => {
                const code = String(row[0]);
                const autonym = String(row[1] || code);
                const enName = row[2] ? String(row[2]) : "";

                const btn = document.createElement("button");
                btn.type = "button";
                btn.className = "lang-combobox-option";
                btn.dataset.langCode = code;

                const codeSpan = document.createElement("span");
                codeSpan.className = "lang-option-code";
                codeSpan.textContent = code;

                const nameSpan = document.createElement("span");
                nameSpan.className = "lang-option-name";
                nameSpan.textContent = enName ? `${autonym} (${enName})` : autonym;

                btn.appendChild(codeSpan);
                btn.appendChild(nameSpan);
                btn.addEventListener("mousedown", (e) => {
                    e.preventDefault();
                    chooseCode(code);
                });
                menuEl.appendChild(btn);
            });

            if (matches.length === 0 && query) {
                if (LANG_CODE_REGEX.test(query) && !excluded.includes(query)) {
                    const fallbackBtn = document.createElement("button");
                    fallbackBtn.type = "button";
                    fallbackBtn.className = "lang-combobox-option lang-combobox-option--custom";
                    fallbackBtn.dataset.langCode = query;
                    fallbackBtn.textContent = msgFormat(
                        "athar-form-lang-no-match",
                        query,
                        `Press Enter to add "${query}"`
                    );
                    fallbackBtn.addEventListener("mousedown", (e) => {
                        e.preventDefault();
                        chooseCode(query);
                    });
                    menuEl.appendChild(fallbackBtn);
                }
            }

            menuEl.hidden = menuEl.children.length === 0;
        }

        inputEl.addEventListener("focus", () => {
            if (!clearOnSelect) {
                inputEl.select();
            }
            renderMenu();
        });

        inputEl.addEventListener("input", renderMenu);

        inputEl.addEventListener("keydown", (e) => {
            const options = Array.from(menuEl.querySelectorAll(".lang-combobox-option"));
            if (e.key === "ArrowDown") {
                if (menuEl.hidden) renderMenu();
                e.preventDefault();
                activeIdx = Math.min(activeIdx + 1, options.length - 1);
                options.forEach((opt, i) => opt.classList.toggle("is-highlighted", i === activeIdx));
                if (options[activeIdx]) options[activeIdx].scrollIntoView({ block: "nearest" });
            } else if (e.key === "ArrowUp") {
                e.preventDefault();
                activeIdx = Math.max(activeIdx - 1, 0);
                options.forEach((opt, i) => opt.classList.toggle("is-highlighted", i === activeIdx));
                if (options[activeIdx]) options[activeIdx].scrollIntoView({ block: "nearest" });
            } else if (e.key === "Enter") {
                e.preventDefault();
                if (activeIdx >= 0 && options[activeIdx]) {
                    chooseCode(options[activeIdx].dataset.langCode);
                } else {
                    const typed = inputEl.value.trim().toLowerCase();
                    if (LANG_CODE_REGEX.test(typed) && chooseCode(typed)) return;
                    if (options.length > 0) chooseCode(options[0].dataset.langCode);
                }
            } else if (e.key === "Escape") {
                closeMenu();
            }
        });

        inputEl.addEventListener("blur", () => {
            setTimeout(() => {
                closeMenu();
                if (!clearOnSelect) {
                    const typed = inputEl.value.trim().toLowerCase();
                    if (LANG_CODE_REGEX.test(typed)) {
                        onSelect(typed);
                    } else {
                        inputEl.value = formatLangLabel(getPrimaryLang());
                    }
                }
            }, 120);
        });

        return { renderMenu, closeMenu };
    }

    function mountTranslationPanel({
        rootId,
        listId,
        openBtnId,
        pickerRowId,
        filterInputId,
        menuId,
        cancelBtnId,
        panelKey,
        fieldSpecs,
    }) {
        const root = document.getElementById(rootId);
        const listEl = document.getElementById(listId);
        const openPickerBtn = document.getElementById(openBtnId);
        const pickerRow = document.getElementById(pickerRowId);
        const targetFilterInput = document.getElementById(filterInputId);
        const targetMenu = document.getElementById(menuId);
        const cancelPickerBtn = document.getElementById(cancelBtnId);
        if (!root || !listEl) return null;

        function isLangVisibleInPanel(langCode) {
            const entry = state[langCode];
            if (!entry) return false;
            if (entry._panels && entry._panels[panelKey]) return true;
            return fieldSpecs.some((spec) => typeof entry[spec.key] === "string" && entry[spec.key].trim().length > 0);
        }

        function collectSourceValues() {
            const out = {};
            fieldSpecs.forEach((spec) => {
                const srcEl = document.getElementById(spec.sourceInputId);
                const val = srcEl ? String(srcEl.value || "").trim() : "";
                if (val) out[spec.key] = val;
            });
            return out;
        }

        function renderCards() {
            const primary = getPrimaryLang();
            listEl.innerHTML = "";

            Object.keys(state).forEach((langCode) => {
                if (langCode === primary) {
                    delete state[langCode];
                    return;
                }
                if (!isLangVisibleInPanel(langCode)) return;
                const entry = ensureLangEntry(langCode);
                entry._panels[panelKey] = true;

                const card = document.createElement("div");
                card.className = "translation-card";
                card.dataset.langCode = langCode;
                card.dataset.panel = panelKey;

                const header = document.createElement("div");
                header.className = "translation-card-header";

                const badge = document.createElement("span");
                badge.className = "translation-card-lang-badge";
                badge.textContent = formatLangLabel(langCode);

                const actions = document.createElement("div");
                actions.className = "translation-card-actions";

                const mintBtn = document.createElement("button");
                mintBtn.type = "button";
                mintBtn.className = "cdx-button cdx-button--quiet translation-mint-btn";
                mintBtn.textContent = msg("athar-form-auto-translate-mint", "Auto-translate with MinT");

                const removeBtn = document.createElement("button");
                removeBtn.type = "button";
                removeBtn.className = "translation-remove-btn";
                removeBtn.setAttribute("aria-label", msg("athar-form-remove-language", "Remove"));
                removeBtn.title = msg("athar-form-remove-language", "Remove");
                removeBtn.textContent = "\u00d7";
                removeBtn.addEventListener("click", () => {
                    fieldSpecs.forEach((spec) => {
                        delete entry[spec.key];
                    });
                    entry._panels[panelKey] = false;
                    const stillActive = (entry._panels.main || entry._panels.results) ||
                        ["title", "description", "results_summary", "results_notes"].some(
                            (k) => typeof entry[k] === "string" && entry[k].trim().length > 0
                        );
                    if (!stillActive) {
                        delete state[langCode];
                    }
                    renderCards();
                    syncToHidden();
                });

                actions.appendChild(mintBtn);
                actions.appendChild(removeBtn);
                header.appendChild(badge);
                header.appendChild(actions);
                card.appendChild(header);

                const statusEl = document.createElement("div");
                statusEl.className = "translation-mint-status";
                statusEl.setAttribute("aria-live", "polite");
                statusEl.hidden = true;
                card.appendChild(statusEl);

                const controls = {};
                fieldSpecs.forEach((spec) => {
                    const group = document.createElement("div");
                    group.className = "translation-field-row";
                    const fieldId = `tr_${panelKey}_${langCode}_${spec.key}`;
                    const labelText = msg(spec.labelKey, spec.fallbackLabel);

                    const input = document.createElement(spec.multiline ? "textarea" : "input");
                    input.id = fieldId;
                    input.className = spec.multiline ? "cdx-textarea" : "cdx-text-input";
                    input.dir = "auto";
                    input.lang = langCode;
                    input.placeholder = `${labelText} (${langCode})`;
                    input.setAttribute("aria-label", `${labelText} (${langCode})`);
                    if (spec.multiline) {
                        input.rows = spec.rows || 3;
                    } else {
                        input.type = "text";
                        input.maxLength = 255;
                    }
                    input.value = entry[spec.key] || "";
                    input.addEventListener("input", () => {
                        entry[spec.key] = input.value;
                        syncToHidden();
                    });

                    group.appendChild(input);
                    card.appendChild(group);
                    controls[spec.key] = input;
                });

                mintBtn.addEventListener("click", async () => {
                    const translateUrl = root.dataset.translateUrl || "/project/translate";
                    const sourceFields = collectSourceValues();
                    if (Object.keys(sourceFields).length === 0) {
                        statusEl.hidden = false;
                        statusEl.className = "translation-mint-status translation-mint-status--warn";
                        statusEl.textContent = msg("athar-form-mint-error", "Please enter source text first.");
                        return;
                    }

                    const hasExisting = fieldSpecs.some(
                        (spec) => String((controls[spec.key] && controls[spec.key].value) || "").trim().length > 0
                    );
                    if (hasExisting) {
                        const confirmText = msg(
                            "athar-form-mint-confirm-overwrite",
                            "Overwrite existing text in this language with MinT pre-translation?"
                        );
                        if (!window.confirm(confirmText)) return;
                    }

                    mintBtn.disabled = true;
                    statusEl.hidden = false;
                    statusEl.className = "translation-mint-status";
                    statusEl.textContent = msg("athar-form-mint-loading", "Translating with MinT...");

                    try {
                        const csrfMeta = document.querySelector('meta[name="csrf-token"]');
                        const csrfToken = csrfMeta ? csrfMeta.getAttribute("content") : "";
                        const resp = await fetch(translateUrl, {
                            method: "POST",
                            headers: {
                                "Content-Type": "application/json",
                                "X-CSRFToken": csrfToken || "",
                                "X-Requested-With": "XMLHttpRequest",
                            },
                            body: JSON.stringify({
                                source_lang: getPrimaryLang(),
                                target_lang: langCode,
                                fields: sourceFields,
                            }),
                        });

                        let data = {};
                        try {
                            data = await resp.json();
                        } catch (e) {
                            data = {};
                        }

                        if (!resp.ok) {
                            if (resp.status === 400 && data.manual_only) {
                                statusEl.className = "translation-mint-status translation-mint-status--warn";
                                statusEl.textContent = msg(
                                    "athar-form-mint-manual-only",
                                    "Manual entry only (MinT pair unavailable)"
                                );
                            } else {
                                statusEl.className = "translation-mint-status translation-mint-status--err";
                                statusEl.textContent = data.error || msg(
                                    "athar-form-mint-error",
                                    "Auto-translation unavailable; please enter manually."
                                );
                            }
                            return;
                        }

                        const returned = (data && data.fields) || {};
                        fieldSpecs.forEach((spec) => {
                            if (typeof returned[spec.key] === "string") {
                                entry[spec.key] = returned[spec.key];
                                if (controls[spec.key]) controls[spec.key].value = returned[spec.key];
                            }
                        });

                        syncToHidden();
                        statusEl.className = "translation-mint-status translation-mint-status--ok";
                        statusEl.textContent = msg(
                            "athar-form-mint-success",
                            "Translated via MinT. Please review before saving."
                        );
                    } catch (err) {
                        statusEl.className = "translation-mint-status translation-mint-status--err";
                        statusEl.textContent = msg(
                            "athar-form-mint-error",
                            "Auto-translation unavailable; please enter manually."
                        );
                    } finally {
                        mintBtn.disabled = false;
                    }
                });

                listEl.appendChild(card);
            });
        }

        function addPanelLanguage(rawCode) {
            const code = String(rawCode || "").trim().toLowerCase();
            const primary = getPrimaryLang();
            if (!code || !LANG_CODE_REGEX.test(code) || code === primary) {
                return false;
            }
            if (!state[code] && Object.keys(state).length >= MAX_LANGUAGES) return false;
            const entry = ensureLangEntry(code);
            entry._panels[panelKey] = true;
            renderCards();
            syncToHidden();
            const firstSpec = fieldSpecs[0];
            if (firstSpec) {
                const focusEl = document.getElementById(`tr_${panelKey}_${code}_${firstSpec.key}`);
                if (focusEl) focusEl.focus();
            }
            return true;
        }

        function closeTargetPicker() {
            if (pickerRow) pickerRow.hidden = true;
            if (openPickerBtn) openPickerBtn.hidden = false;
            if (targetFilterInput) targetFilterInput.value = "";
            if (targetMenu) targetMenu.hidden = true;
        }

        if (openPickerBtn && pickerRow && targetFilterInput) {
            setupLangCombobox({
                inputEl: targetFilterInput,
                menuEl: targetMenu,
                excludedProvider: () => {
                    const already = Object.keys(state).filter((c) => isLangVisibleInPanel(c));
                    return [getPrimaryLang()].concat(already);
                },
                clearOnSelect: true,
                onSelect: (chosenCode) => {
                    closeTargetPicker();
                    addPanelLanguage(chosenCode);
                },
            });

            openPickerBtn.addEventListener("click", () => {
                openPickerBtn.hidden = true;
                pickerRow.hidden = false;
                targetFilterInput.focus();
            });
        }

        if (cancelPickerBtn) {
            cancelPickerBtn.addEventListener("click", closeTargetPicker);
        }

        renderCards();
        return { renderCards, addLanguage: addPanelLanguage };
    }

    function renderAllPanels() {
        mountedPanels.forEach((p) => {
            if (p && typeof p.renderCards === "function") p.renderCards();
        });
    }

    async function refreshLiveLanguageCatalog() {
        try {
            const resp = await fetch("/api/languages");
            if (!resp.ok) return;
            const liveList = await resp.json();
            if (!Array.isArray(liveList) || liveList.length === 0) return;

            const byCode = {};
            languageCatalog.forEach((r) => {
                if (Array.isArray(r) && r[0]) byCode[String(r[0]).toLowerCase()] = r;
            });
            liveList.forEach((r) => {
                if (Array.isArray(r) && r[0]) {
                    const c = String(r[0]).toLowerCase();
                    if (!byCode[c]) byCode[c] = r;
                }
            });
            languageCatalog = Object.values(byCode);
            rebuildLangMap();
        } catch (err) {
            // Silently retain pre-bundled 590-language Wikimedia catalog
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        const mainRoot = document.getElementById("translation-panel-root");
        if (!mainRoot) return;

        const hidden = document.getElementById("translations_json");
        if (hidden && hidden.value) {
            try {
                const parsed = JSON.parse(hidden.value);
                if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
                    state = parsed;
                    Object.keys(state).forEach((k) => {
                        const e = ensureLangEntry(k);
                        if (e.title || e.description) e._panels.main = true;
                        if (e.results_summary || e.results_notes) e._panels.results = true;
                    });
                }
            } catch (err) {
                state = {};
            }
        }

        const primaryHidden = document.getElementById("primary_lang");
        const primaryPicker = document.getElementById("primary_lang_picker");
        const primaryMenu = document.getElementById("primary_lang_menu");
        if (primaryHidden && primaryPicker) {
            primaryPicker.value = formatLangLabel(primaryHidden.value || "ar");
            setupLangCombobox({
                inputEl: primaryPicker,
                menuEl: primaryMenu,
                excludedProvider: () => [],
                clearOnSelect: false,
                onSelect: (chosenCode) => {
                    primaryHidden.value = chosenCode;
                    primaryPicker.value = formatLangLabel(chosenCode);
                    if (state[chosenCode]) delete state[chosenCode];
                    renderAllPanels();
                    syncToHidden();
                },
            });
        }

        const mainPanel = mountTranslationPanel({
            rootId: "translation-panel-root",
            listId: "translation-cards-list",
            openBtnId: "open-lang-picker-btn",
            pickerRowId: "translation-lang-picker-row",
            filterInputId: "target-lang-filter",
            menuId: "target-lang-menu",
            cancelBtnId: "cancel-lang-picker-btn",
            panelKey: "main",
            fieldSpecs: [
                { key: "title", sourceInputId: "title", labelKey: "athar-form-translated-title", fallbackLabel: "Title", multiline: false },
                { key: "description", sourceInputId: "description", labelKey: "athar-form-translated-description", fallbackLabel: "Description", multiline: true, rows: 3 },
            ],
        });
        if (mainPanel) mountedPanels.push(mainPanel);

        const resultsPanel = mountTranslationPanel({
            rootId: "results-translation-panel-root",
            listId: "results-translation-cards-list",
            openBtnId: "open-results-lang-picker-btn",
            pickerRowId: "results-lang-picker-row",
            filterInputId: "results-target-lang-filter",
            menuId: "results-target-lang-menu",
            cancelBtnId: "cancel-results-lang-picker-btn",
            panelKey: "results",
            fieldSpecs: [
                { key: "results_summary", sourceInputId: "results_summary", labelKey: "athar-form-translated-summary", fallbackLabel: "Summary", multiline: true, rows: 2 },
                { key: "results_notes", sourceInputId: "results_notes", labelKey: "athar-form-translated-notes", fallbackLabel: "Notes", multiline: true, rows: 2 },
            ],
        });
        if (resultsPanel) mountedPanels.push(resultsPanel);

        syncToHidden();
        refreshLiveLanguageCatalog();
    });

    window.AtharTranslationPanel = {
        syncToHidden,
        addLanguage: (code) => (mountedPanels[0] ? mountedPanels[0].addLanguage(code) : false),
        getState: () => state,
    };
})();
