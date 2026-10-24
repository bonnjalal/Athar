/**
 * Export data report logic:
 * Filters projects per community/group by year, month, custom date range, or all-time.
 * Provides real-time preview and direct CSV download.
 */

let activeFilterMode = "year";
let activeProjects = [];

const TYPE_TRANSLATIONS = {
    "workshop": "ورشة تدريبية",
    "edit-a-thon": "ماراثون تحرير",
    "photo walk": "جولة تصوير",
    "contest": "مسابقة ومنافسة",
    "glam": "شراكة ثقافية",
    "education program": "برنامج تعليمي",
    "outreach": "برنامج توعوي",
    "campaign": "حملة محتوى",
    "conference / meetup": "مؤتمر أو لقاء",
    "hackathon": "فعالية برمجية",
    "translation": "حملة ترجمة",
    "exhibition": "معرض وتوثيق",
    "other": "نشاط مخصص"
};

const STATUS_TRANSLATIONS = {
    "in progress": "جارية",
    "planned": "مخططة",
    "completed": "مكتملة"
};

function getCommunitySlug() {
    const select = document.getElementById("export-community");
    return select ? select.value : "";
}

function getCommunityName() {
    const select = document.getElementById("export-community");
    if (!select || !select.selectedOptions.length) return "";
    return select.selectedOptions[0].text.split("(")[0].trim();
}

function setFilterMode(mode) {
    activeFilterMode = mode;

    // Update pill buttons
    const pills = document.querySelectorAll(".export-filter-pill");
    pills.forEach(pill => {
        if (pill.getAttribute("data-mode") === mode) {
            pill.classList.add("is-active");
        } else {
            pill.classList.remove("is-active");
        }
    });

    // Toggle panels
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
    const slug = getCommunitySlug();

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

    return params;
}

function getFilterDescriptionText() {
    const commName = getCommunityName();
    let periodText = "";

    if (activeFilterMode === "year") {
        const yr = document.getElementById("filter-year")?.value || "";
        periodText = `سنة ${yr}`;
    } else if (activeFilterMode === "month") {
        const yr = document.getElementById("filter-month-year")?.value || "";
        const mSelect = document.getElementById("filter-month-val");
        const mText = mSelect?.selectedOptions[0]?.text || "";
        periodText = `${mText} ${yr}`;
    } else if (activeFilterMode === "custom") {
        const start = document.getElementById("filter-custom-start")?.value || "";
        const end = document.getElementById("filter-custom-end")?.value || "";
        if (start && end) {
            periodText = `الفترة من ${start} إلى ${end}`;
        } else if (start) {
            periodText = `ابتداءً من ${start}`;
        } else if (end) {
            periodText = `حتى تاريخ ${end}`;
        } else {
            periodText = "فترة مخصصة (غير محددة بعد)";
        }
    } else {
        periodText = "كافة الأنشطة (بدون قيد زمني)";
    }

    return `المجموعة: ${commName} | ${periodText}`;
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
        if (badge) badge.textContent = "اختر مجتمعاً";
        if (tbody) tbody.innerHTML = "";
        if (tableContainer) tableContainer.style.display = "none";
        if (emptyState) emptyState.style.display = "block";
        return;
    }

    const queryParams = buildQueryParams();
    const exportParams = new URLSearchParams(queryParams);
    exportParams.set("format", "csv");
    const exportUrl = `/api/${encodeURIComponent(slug)}/export?${exportParams.toString()}`;

    if (directLink) {
        directLink.href = exportUrl;
    }

    if (badge) {
        badge.textContent = "جاري التحقق...";
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
            badge.textContent = `${projects.length} نشاط مطابق`;
        }

        if (projects.length === 0) {
            if (tableContainer) tableContainer.style.display = "none";
            if (emptyState) emptyState.style.display = "block";
        } else {
            if (tableContainer) tableContainer.style.display = "block";
            if (emptyState) emptyState.style.display = "none";

            if (tbody) {
                tbody.innerHTML = "";
                // Show up to 10 rows for preview
                const previewRows = projects.slice(0, 10);
                previewRows.forEach((p, idx) => {
                    const tr = document.createElement("tr");

                    const rawType = (p.project_type || "").toLowerCase();
                    const typeDisplay = TYPE_TRANSLATIONS[rawType] || p.project_type || "نشاط مجتمعي";

                    const rawStatus = (p.status || "").toLowerCase();
                    const statusDisplay = STATUS_TRANSLATIONS[rawStatus] || p.status || "جارية";

                    const dateDisplay = p.start_date || (p.created_at ? String(p.created_at).slice(0, 10) : "—");

                    tr.innerHTML = `
                        <td style="text-align: center; color: #72777d; font-size: 0.85rem;">${idx + 1}</td>
                        <td><strong>${escapeHtml(p.title || "نشاط بدون عنوان")}</strong></td>
                        <td><span class="project-type-badge">${escapeHtml(typeDisplay)}</span></td>
                        <td><code>${escapeHtml(p.target_wiki || "arwiki")}</code></td>
                        <td><span class="project-status project-status--${rawStatus.replace(/\\s+/g, '-')}">${escapeHtml(statusDisplay)}</span></td>
                        <td style="color: #54595d; direction: ltr; text-align: right;">${escapeHtml(dateDisplay)}</td>
                    `;
                    tbody.appendChild(tr);
                });

                if (projects.length > 10) {
                    const extraTr = document.createElement("tr");
                    extraTr.innerHTML = `
                        <td colspan="6" style="text-align: center; color: #54595d; font-style: italic; background: #fafafa; padding: 8px;">
                            ... و ${projects.length - 10} أنشطة إضافية سيتم تضمينها في ملف الـ CSV
                        </td>
                    `;
                    tbody.appendChild(extraTr);
                }
            }
        }
    } catch (err) {
        console.error("Preview error:", err);
        if (badge) badge.textContent = "خطأ في التحميل";
        if (emptyState) {
            emptyState.textContent = "حدث خطأ أثناء تحميل بيانات المعاينة.";
            emptyState.style.display = "block";
        }
        if (tableContainer) tableContainer.style.display = "none";
    }
}

function triggerCsvDownload() {
    const slug = getCommunitySlug();
    if (!slug) {
        alert("يرجى اختيار المجتمع أولاً.");
        return;
    }

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
    // Set default filter mode
    setFilterMode("year");
});
