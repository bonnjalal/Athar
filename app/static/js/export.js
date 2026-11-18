/**
 * Export data report logic:
 * Filters projects per community/group by year, month, custom date range, or all-time.
 * Propagates selected export/report language (?lang=) without mutating session locale.
 */

let activeFilterMode = "year";
let activeProjects = [];

function _t(key) {
    const args = Array.prototype.slice.call(arguments);
    if (window.atharI18n && window.atharI18n.t) {
        return window.atharI18n.t.apply(window.atharI18n, args);
    }
    return key;
}

const TYPE_KEY_LOOKUP = {
    "workshop": "athar-type-workshop",
    "edit-a-thon": "athar-type-edit-a-thon",
    "photo walk": "athar-type-photo-walk",
    "contest": "athar-type-contest",
    "contest / competition": "athar-type-contest",
    "glam": "athar-type-glam",
    "education program": "athar-type-education",
    "outreach": "athar-type-outreach",
    "campaign": "athar-type-campaign",
    "conference / meetup": "athar-type-conference",
    "hackathon": "athar-type-hackathon",
    "translation": "athar-type-translation",
    "exhibition": "athar-type-exhibition",
    "other": "athar-type-other"
};

const STATUS_KEY_LOOKUP = {
    "in progress": "athar-status-in-progress",
    "planned": "athar-status-planned",
    "completed": "athar-status-completed",
    "canceled": "athar-status-canceled",
    "cancelled": "athar-status-canceled"
};

function getCommunitySlug() {
    const select = document.getElementById("export-community");
    return select ? select.value : "";
}

function getSelectedExportLang() {
    const langSelect = document.getElementById("export-lang");
    return (langSelect && langSelect.value) ? langSelect.value : (window.ATHAR_LOCALE || "ar");
}

function getCommunityName() {
    const select = document.getElementById("export-community");
    if (!select || !select.selectedOptions.length) return "";
    return select.selectedOptions[0].text.split("(")[0].trim();
}

function setFilterMode(mode) {
    activeFilterMode = mode;

    const pills = document.querySelectorAll(".export-filter-pill");
    pills.forEach(pill => {
        pill.classList.toggle("is-active", pill.getAttribute("data-mode") === mode);
    });

    const panels = {
        "year": document.getElementById("panel-year"),
        "month": document.getElementById("panel-month"),
        "custom": document.getElementById("panel-custom"),
        "all": document.getElementById("panel-all")
    };

    Object.keys(panels).forEach(key => {
        if (panels[key]) {
            panels[key].style.display = (key === mode) ? "block" : "none";
        }
    });

    updateLivePreview();
}

function onCommunityChange() {
    updateLivePreview();
}

function buildQueryParams() {
    const params = new URLSearchParams();

    if (activeFilterMode === "year") {
        const yearVal = document.getElementById("filter-year")?.value;
        if (yearVal) {
            params.set("filter_type", "year");
            params.set("year", yearVal);
        }
    } else if (activeFilterMode === "month") {
        const yearVal = document.getElementById("filter-month-year")?.value;
        const monthVal = document.getElementById("filter-month-val")?.value;
        if (yearVal && monthVal) {
            params.set("filter_type", "month");
            params.set("year", yearVal);
            params.set("month", monthVal);
        }
    } else if (activeFilterMode === "custom") {
        const startVal = document.getElementById("filter-custom-start")?.value;
        const endVal = document.getElementById("filter-custom-end")?.value;
        params.set("filter_type", "custom");
        if (startVal) params.set("start_date", startVal);
        if (endVal) params.set("end_date", endVal);
    } else if (activeFilterMode === "all") {
        params.set("filter_type", "all");
    }

    const incProg = document.getElementById("include-in-progress");
    const incPlan = document.getElementById("include-planned");
    const incCanc = document.getElementById("include-canceled");

    if (incProg) params.set("include_in_progress", incProg.checked ? "1" : "0");
    if (incPlan) params.set("include_planned", incPlan.checked ? "1" : "0");
    if (incCanc) params.set("include_canceled", incCanc.checked ? "1" : "0");

    const exportLang = getSelectedExportLang();
    if (exportLang) {
        params.set("lang", exportLang);
    }

    return params;
}

function getFilterDescriptionText() {
    const commName = getCommunityName();
    let periodText = "";

    if (activeFilterMode === "year") {
        const yr = document.getElementById("filter-year")?.value || "";
        periodText = yr;
    } else if (activeFilterMode === "month") {
        const yr = document.getElementById("filter-month-year")?.value || "";
        const mSelect = document.getElementById("filter-month-val");
        const mText = mSelect?.selectedOptions[0]?.text || "";
        periodText = `${mText} ${yr}`;
    } else if (activeFilterMode === "custom") {
        const start = document.getElementById("filter-custom-start")?.value || "";
        const end = document.getElementById("filter-custom-end")?.value || "";
        periodText = (start || "...") + " — " + (end || "...");
    } else {
        periodText = _t("athar-export-mode-all");
    }

    const incProg = document.getElementById("include-in-progress")?.checked;
    const incPlan = document.getElementById("include-planned")?.checked;
    const incCanc = document.getElementById("include-canceled")?.checked;

    const statusParts = [_t("athar-status-completed")];
    if (incProg) statusParts.push(_t("athar-status-in-progress"));
    if (incPlan) statusParts.push(_t("athar-status-planned"));
    if (incCanc) statusParts.push(_t("athar-status-canceled"));

    return `${commName} | ${periodText} | ${statusParts.join(" + ")}`;
}

async function updateLivePreview() {
    const slug = getCommunitySlug();
    const badge = document.getElementById("preview-count-badge");
    const desc = document.getElementById("preview-filter-desc");
    const tbody = document.getElementById("preview-tbody");
    const tableContainer = document.getElementById("preview-table-container");
    const emptyState = document.getElementById("preview-empty-state");
    const directLink = document.getElementById("btn-direct-link");

    if (desc) {
        desc.textContent = getFilterDescriptionText();
    }

    if (!slug) {
        if (badge) badge.textContent = _t("athar-export-preview-count", 0);
        if (tbody) tbody.innerHTML = "";
        if (tableContainer) tableContainer.style.display = "none";
        if (emptyState) emptyState.style.display = "block";
        return;
    }

    const queryParams = buildQueryParams();
    const exportParams = new URLSearchParams(queryParams);
    exportParams.set("format", "csv");
    const exportUrl = `/api/${encodeURIComponent(slug)}/export?${exportParams.toString()}`;
    const reportUrl = `/${encodeURIComponent(slug)}/report?${queryParams.toString()}`;

    if (directLink) {
        directLink.href = exportUrl;
    }

    const printReportBtn = document.getElementById("btn-print-report");
    if (printReportBtn) {
        printReportBtn.href = reportUrl;
    }

    const detailedParams = new URLSearchParams(queryParams);
    detailedParams.set("detailed", "1");
    const detailedReportUrl = `/${encodeURIComponent(slug)}/report?${detailedParams.toString()}`;
    const printDetailedReportBtn = document.getElementById("btn-print-detailed-report");
    if (printDetailedReportBtn) {
        printDetailedReportBtn.href = detailedReportUrl;
    }

    if (badge) {
        badge.textContent = "...";
    }

    try {
        const apiUrl = `/api/${encodeURIComponent(slug)}/projects?${queryParams.toString()}`;
        const response = await fetch(apiUrl);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        const projects = Array.isArray(data) ? data : (data.projects || []);
        activeProjects = projects;

        if (badge) {
            badge.textContent = _t("athar-export-preview-count", projects.length);
        }

        if (projects.length === 0) {
            if (tableContainer) tableContainer.style.display = "none";
            if (emptyState) emptyState.style.display = "block";
        } else {
            if (tableContainer) tableContainer.style.display = "block";
            if (emptyState) emptyState.style.display = "none";

            if (tbody) {
                tbody.innerHTML = "";
                const previewRows = projects.slice(0, 10);
                previewRows.forEach((p, idx) => {
                    const tr = document.createElement("tr");

                    const rawType = (p.project_type || "").toLowerCase();
                    const typeKey = TYPE_KEY_LOOKUP[rawType];
                    const typeDisplay = typeKey ? _t(typeKey) : (p.project_type || _t("athar-type-default"));

                    const rawStatus = (p.status || "").toLowerCase();
                    const statusKey = STATUS_KEY_LOOKUP[rawStatus];
                    const statusDisplay = statusKey ? _t(statusKey) : (p.status || _t("athar-status-in-progress"));

                    const dateDisplay = p.start_date || (p.created_at ? String(p.created_at).slice(0, 10) : "—");
                    const displayTitle = p.localized_title || p.title || "";
                    const titleLang = p.localized_lang || p.primary_lang || "ar";

                    tr.innerHTML = `
                        <td style="text-align: center; font-size: 0.85rem;">${idx + 1}</td>
                        <td><strong><bdi lang="${escapeHtml(titleLang)}" dir="auto">${escapeHtml(displayTitle)}</bdi></strong></td>
                        <td><span class="project-type-badge">${escapeHtml(typeDisplay)}</span></td>
                        <td><code>${escapeHtml(p.target_wiki || "arwiki")}</code></td>
                        <td><span class="project-status project-status--${rawStatus.replace(/\s+/g, "-")}">${escapeHtml(statusDisplay)}</span></td>
                        <td class="export-date-cell">${escapeHtml(dateDisplay)}</td>
                    `;
                    tbody.appendChild(tr);
                });

                if (projects.length > 10) {
                    const extraTr = document.createElement("tr");
                    extraTr.innerHTML = `
                        <td colspan="6" class="export-extra-row-cell">
                            ${escapeHtml(_t("athar-export-extra-rows", projects.length - 10))}
                        </td>
                    `;
                    tbody.appendChild(extraTr);
                }
            }
        }
    } catch (err) {
        console.error("Preview error:", err);
        if (badge) badge.textContent = "!";
        if (emptyState) {
            emptyState.style.display = "block";
        }
        if (tableContainer) tableContainer.style.display = "none";
    }
}

function triggerCsvDownload() {
    const slug = getCommunitySlug();
    if (!slug) return;

    const queryParams = buildQueryParams();
    queryParams.set("format", "csv");
    const exportUrl = `/api/${encodeURIComponent(slug)}/export?${queryParams.toString()}`;
    window.location.href = exportUrl;
}

function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

document.addEventListener("DOMContentLoaded", () => {
    setFilterMode("year");
});
