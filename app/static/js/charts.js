document.addEventListener("DOMContentLoaded", () => {
    const membersElement = document.getElementById("totalMembers");
    const projectsElement = document.getElementById("totalProjects");
    const editsElement = document.getElementById("totalEdits");

    const activityCanvas = document.getElementById("activityChart");
    const overviewCanvas = document.getElementById("overviewChart");
    const errorElement = document.getElementById("statsError");

    let activityChart = null;
    let overviewChart = null;
    let lastStats = null;

    function _t(key) {
        if (window.atharI18n && window.atharI18n.t) {
            return window.atharI18n.t.apply(window.atharI18n, arguments);
        }
        return key;
    }

    function getThemeColors() {
        const cs = getComputedStyle(document.documentElement);
        return {
            text: cs.getPropertyValue("--athar-text").trim() || "#202122",
            muted: cs.getPropertyValue("--athar-text-muted").trim() || "#54595d",
            grid: cs.getPropertyValue("--athar-border-subtle").trim() || "#eaecf0"
        };
    }

    function getCommunitySlug() {
        const dashboardEl = document.querySelector("[data-community-slug]");
        if (dashboardEl && dashboardEl.dataset.communitySlug) {
            return dashboardEl.dataset.communitySlug;
        }
        const pathParts = window.location.pathname.split("/").filter(Boolean);
        if (!pathParts.length) return null;
        return decodeURIComponent(pathParts[pathParts.length - 1]);
    }

    function showError(message) {
        if (errorElement) {
            errorElement.textContent = message;
            errorElement.hidden = false;
            errorElement.style.display = "block";
        }
    }

    function clearError() {
        if (errorElement) {
            errorElement.textContent = "";
            errorElement.hidden = true;
            errorElement.style.display = "none";
        }
    }

    function destroyCharts() {
        if (activityChart) {
            activityChart.destroy();
            activityChart = null;
        }
        if (overviewChart) {
            overviewChart.destroy();
            overviewChart = null;
        }
    }

    const TYPE_KEYS = {
        "Workshop": "athar-type-workshop",
        "Edit-a-thon": "athar-type-edit-a-thon",
        "Photo Walk": "athar-type-photo-walk",
        "Contest": "athar-type-contest",
        "Contest / Competition": "athar-type-contest",
        "GLAM": "athar-type-glam",
        "Education Program": "athar-type-education",
        "Outreach": "athar-type-outreach",
        "Campaign": "athar-type-campaign",
        "Conference / Meetup": "athar-type-conference",
        "Hackathon": "athar-type-hackathon",
        "Translation": "athar-type-translation",
        "Exhibition": "athar-type-exhibition",
        "Other": "athar-type-other"
    };

    const ACTIVITY_COLORS = {
        "Workshop": "#10b981",
        "Edit-a-thon": "#06b6d4",
        "Photo Walk": "#f59e0b",
        "Contest": "#8b5cf6",
        "Contest / Competition": "#8b5cf6",
        "GLAM": "#ec4899",
        "Education Program": "#3b82f6",
        "Outreach": "#3b82f6",
        "Campaign": "#f97316",
        "Conference / Meetup": "#6366f1",
        "Hackathon": "#14b8a6",
        "Translation": "#eab308",
        "Exhibition": "#a855f7",
        "Other": "#64748b"
    };

    function renderCharts(stats) {
        if (!stats || typeof Chart === "undefined") return;
        const theme = getThemeColors();
        const activities = stats.activities_by_type ?? {};
        const activityLabels = Object.keys(activities);
        const activityValues = Object.values(activities);
        const displayLabels = activityLabels.map(l => TYPE_KEYS[l] ? _t(TYPE_KEYS[l]) : l);

        if (activityCanvas) {
            if (activityChart) activityChart.destroy();
            activityChart = new Chart(activityCanvas, {
                type: "bar",
                data: {
                    labels: displayLabels,
                    datasets: [{
                        label: _t("athar-js-charts-label-count"),
                        data: activityValues,
                        backgroundColor: activityLabels.map(label => ACTIVITY_COLORS[label] || "#64748b"),
                        borderRadius: 5,
                        borderSkipped: false
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        x: {
                            ticks: { color: theme.muted },
                            grid: { color: theme.grid }
                        },
                        y: {
                            beginAtZero: true,
                            ticks: { precision: 0, color: theme.muted },
                            grid: { color: theme.grid }
                        }
                    }
                }
            });
        }

        if (overviewCanvas) {
            if (overviewChart) overviewChart.destroy();
            overviewChart = new Chart(overviewCanvas, {
                type: "doughnut",
                data: {
                    labels: [_t("athar-dashboard-kpi-members"), _t("athar-tab-activities")],
                    datasets: [{
                        data: [
                            stats.total_community_member ?? 0,
                            stats.total_project_member ?? 0
                        ],
                        backgroundColor: ["#0ea5e9", "#f59e0b"],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            labels: { color: theme.text }
                        }
                    }
                }
            });
        }
    }

    async function loadStats() {
        const communitySlug = getCommunitySlug();
        if (!communitySlug) {
            showError(_t("athar-js-stats-error"));
            if (membersElement) membersElement.textContent = "—";
            if (projectsElement) projectsElement.textContent = "—";
            if (editsElement) editsElement.textContent = "—";
            destroyCharts();
            return;
        }

        clearError();
        try {
            const response = await fetch(`/api/${encodeURIComponent(communitySlug)}/stats`);
            if (!response.ok) {
                throw new Error(`Failed to load stats (${response.status})`);
            }

            const stats = await response.json();
            lastStats = stats;

            if (membersElement) {
                const members = stats.total_members ?? stats.total_community_member ?? 0;
                membersElement.textContent = Number(members).toLocaleString();
            }
            if (projectsElement) {
                const projects = stats.total_projects ?? stats.total_project_member ?? 0;
                projectsElement.textContent = Number(projects).toLocaleString();
            }
            if (editsElement) {
                const edits = stats.total_edits ?? stats.total_edits_member_comm ?? 0;
                editsElement.textContent = Number(edits).toLocaleString();
            }

            renderCharts(stats);
        } catch (error) {
            console.error("Dashboard stats error:", error);
            showError(_t("athar-js-stats-error"));
        }
    }

    window.addEventListener("athar:themechange", () => {
        if (lastStats) renderCharts(lastStats);
    });

    loadStats();
});
