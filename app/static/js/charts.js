
document.addEventListener("DOMContentLoaded", () => {
    const membersElement = document.getElementById("totalMembers");
    const projectsElement = document.getElementById("totalProjects");
    const editsElement = document.getElementById("totalEdits");

    const activityCanvas = document.getElementById("activityChart");
    const overviewCanvas = document.getElementById("overviewChart");
    const errorElement = document.getElementById("statsError");

    let activityChart = null;
    let overviewChart = null;

    function getCommunitySlug() {
        const pathParts = window.location.pathname
            .split("/")
            .filter(Boolean);

        return pathParts.length
            ? pathParts[pathParts.length - 1]
            : null;
    }

    function showError(message) {
        if (errorElement) {
            errorElement.textContent = message;
            errorElement.hidden = false;
        }
    }

    function clearError() {
        if (errorElement) {
            errorElement.textContent = "";
            errorElement.hidden = true;
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

    async function loadStats() {
        const communitySlug = getCommunitySlug();

        if (!communitySlug) {
            showError("Community slug not found in URL.");

            if (membersElement) membersElement.textContent = "—";
            if (projectsElement) projectsElement.textContent = "—";
            if (editsElement) editsElement.textContent = "—";

            destroyCharts();
            return;
        }

        clearError();

        try {
            const response = await fetch(
                `/api/${encodeURIComponent(communitySlug)}/stats`
            );

            if (!response.ok) {
                throw new Error(`Failed to load stats (${response.status})`);
            }

            const stats = await response.json();

            if (membersElement) {
                membersElement.textContent =
                    stats.total_community_member ?? 0;
            }

            if (projectsElement) {
                projectsElement.textContent =
                    stats.total_project_member ?? 0;
            }

            if (editsElement) {
                editsElement.textContent =
                    stats.total_edits_member_comm ?? 0;
            }

            // Bar chart: projects by type
            const activities = stats.activities_by_type ?? {};
            const activityLabels = Object.keys(activities);
            const activityValues = Object.values(activities);

            const activityColors = {
                "Contest / Competition": "#8b5cf6",
                "Edit-a-thon": "#06b6d4",
                "Photo Walk": "#f59e0b",
                "Workshop": "#10b981"
            };

            if (activityCanvas) {
                if (activityChart) {
                    activityChart.destroy();
                }

                activityChart = new Chart(activityCanvas, {
                    type: "bar",
                    data: {
                        labels: activityLabels,
                        datasets: [{
                            label: "Number of projects",
                            data: activityValues,
                            backgroundColor: activityLabels.map(
                                label => activityColors[label] || "#64748b"
                            ),
                            borderRadius: 5,
                            borderSkipped: false
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                display: false
                            }
                        },
                        scales: {
                            y: {
                                beginAtZero: true,
                                ticks: {
                                    precision: 0
                                }
                            }
                        }
                    }
                });
            }

            // Doughnut chart: community members vs projects
            if (overviewCanvas) {
                if (overviewChart) {
                    overviewChart.destroy();
                }

                overviewChart = new Chart(overviewCanvas, {
                    type: "doughnut",
                    data: {
                        labels: ["Community members", "Projects"],
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
                        maintainAspectRatio: false
                    }
                });
            }
        } catch (error) {
            console.error("Dashboard stats error:", error);
            showError("Could not load dashboard statistics.");
        }
    }

    loadStats();
});
