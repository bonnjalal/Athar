
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
        const dashboardEl = document.querySelector("[data-community-slug]");
        if (dashboardEl && dashboardEl.dataset.communitySlug) {
            return dashboardEl.dataset.communitySlug;
        }

        const pathParts = window.location.pathname
            .split("/")
            .filter(Boolean);

        if (!pathParts.length) return null;
        return decodeURIComponent(pathParts[pathParts.length - 1]);
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
            showError("معرّف المجتمع غير محدد في الرابط.");

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

            // Bar chart: projects by type
            const activities = stats.activities_by_type ?? {};
            const activityLabels = Object.keys(activities);
            const activityValues = Object.values(activities);

            const activityLabelsArabic = {
                "Workshop": "ورشات تدريبية",
                "Edit-a-thon": "ماراثونات تحرير",
                "Photo Walk": "جولات تصوير",
                "Contest": "مسابقات",
                "Contest / Competition": "مسابقات",
                "GLAM": "شراكات ثقافية",
                "Education Program": "برامج تعليمية",
                "Outreach": "برامج توعوية",
                "Campaign": "حملات محتوى",
                "Conference / Meetup": "مؤتمرات ولقاءات",
                "Hackathon": "فعاليات برمجية",
                "Translation": "حملات ترجمة",
                "Exhibition": "معارض",
                "Other": "أخرى"
            };

            const displayLabels = activityLabels.map(l => activityLabelsArabic[l] || l);

            const activityColors = {
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

            if (activityCanvas) {
                if (activityChart) {
                    activityChart.destroy();
                }

                activityChart = new Chart(activityCanvas, {
                    type: "bar",
                    data: {
                        labels: displayLabels,
                        datasets: [{
                            label: "عدد الأنشطة",
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
                        labels: ["أعضاء المجتمع", "الأنشطة"],
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
            showError("تعذر تحميل إحصائيات لوحة القيادة.");
        }
    }

    loadStats();
});
