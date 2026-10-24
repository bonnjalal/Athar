
document.addEventListener("DOMContentLoaded", () => {
    const communitySelect = document.getElementById("list-comm");
    const form = document.getElementById("dashboard-filters");
    const results = document.getElementById("filter-results");

    if (!communitySelect || !form || !results) {
        console.error("Missing community select, filters form, or results.");
        return;
    }

    const startDate = document.getElementById("start-date");
    const endDate = document.getElementById("end-date");
    const activityType = document.getElementById("activity-type");
    const projectStatus = document.getElementById("project-status");
    const resetButton = document.getElementById("reset-filters");

    let allProjects = [];
    let filteredMode = false;
    let requestId = 0;

    
    function escapeHtml(text) {
        if (!text) return "";
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    const modal = document.getElementById("project-details-modal");
    const modalCloseBtn = document.getElementById("modal-close-btn");
    const modalFooterCloseBtn = document.getElementById("modal-footer-close-btn");

    function closeModal() {
        if (modal) {
            modal.style.display = "none";
            modal.setAttribute("aria-hidden", "true");
            document.body.classList.remove("modal-open");
        }
    }

    function openProjectModal(project) {
        if (!modal) return;

        const titleEl = document.getElementById("modal-project-title");
        const typeEl = document.getElementById("modal-project-type");
        const statusEl = document.getElementById("modal-project-status");
        const contestBadgeEl = document.getElementById("modal-contest-badge");
        const commEl = document.getElementById("modal-community-name");
        const targetWikiEl = document.getElementById("modal-target-wiki");
        const leadEl = document.getElementById("modal-lead-organizer");
        const coOrgsItem = document.getElementById("modal-co-orgs-item");
        const coOrgsEl = document.getElementById("modal-co-organizers");
        const datesEl = document.getElementById("modal-dates");
        const juryItem = document.getElementById("modal-jury-item");
        const juryEl = document.getElementById("modal-jury-members");
        const descEl = document.getElementById("modal-project-description");
        const editLink = document.getElementById("modal-edit-link");
        const directLink = document.getElementById("modal-direct-link");

        const title = project.title || project.name || "مشروع بدون عنوان";
        if (titleEl) titleEl.textContent = title;

        const statusMap = {
            "in progress": "جارية",
            "planned": "مخططة",
            "completed": "مكتملة"
        };
        const rawStatus = project.status || "In Progress";
        const statusDisplay = statusMap[rawStatus.toLowerCase()] || rawStatus;
        if (statusEl) {
            statusEl.textContent = statusDisplay;
            statusEl.className = `project-status project-status--${rawStatus.toLowerCase().replace(/\s+/g, "-")}`;
        }

        const typeMap = {
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
        const rawType = project.project_type || project.type || "نشاط مجتمعي";
        const typeDisplay = typeMap[rawType.toLowerCase()] || rawType;
        if (typeEl) {
            typeEl.textContent = typeDisplay;
            typeEl.style.display = "inline-block";
        }

    const WIKI_MAP = {
        'commons': 'https://commons.wikimedia.org',
        'commonswiki': 'https://commons.wikimedia.org',
        'wikidata': 'https://www.wikidata.org',
        'wikidatawiki': 'https://www.wikidata.org',
        'meta': 'https://meta.wikimedia.org',
        'metawiki': 'https://meta.wikimedia.org',
        'species': 'https://species.wikimedia.org',
        'specieswiki': 'https://species.wikimedia.org',
        'incubator': 'https://incubator.wikimedia.org',
        'incubatorwiki': 'https://incubator.wikimedia.org',
        'mediawiki': 'https://www.mediawiki.org',
        'mediawikiwiki': 'https://www.mediawiki.org',
        'wikifunctions': 'https://www.wikifunctions.org',
        'wikifunctionswiki': 'https://www.wikifunctions.org',
        'sourceswiki': 'https://wikisource.org',
        'ويكيبيديا': 'https://ar.wikipedia.org',
        'كومنز': 'https://commons.wikimedia.org',
        'ويكي بيانات': 'https://www.wikidata.org'
    };

    function resolveWikiUrl(input) {
        if (!input) return 'https://ar.wikipedia.org';
        const clean = String(input).trim().toLowerCase().replace(/^https?:\/\//, '').replace(/\/$/, '');
        if (WIKI_MAP[clean]) return WIKI_MAP[clean];
        if (clean.endsWith('.wikipedia.org') || clean.endsWith('.wikimedia.org') || clean.endsWith('.wikidata.org') || clean.endsWith('.wikisource.org') || clean.endsWith('.wiktionary.org') || clean.endsWith('.wikibooks.org') || clean.endsWith('.wikiquote.org') || clean.endsWith('.wikivoyage.org') || clean.endsWith('.wikinews.org') || clean.endsWith('.wikiversity.org') || clean.endsWith('.mediawiki.org') || clean.endsWith('.wikifunctions.org')) {
            return 'https://' + clean;
        }
        const m = clean.match(/^([a-z]{2,12}(?:-[a-z0-9]{2,12})*)(wiki|wikisource|wiktionary|wikibooks|wikiquote|wikivoyage|wikinews|wikiversity)$/);
        if (m) {
            const lang = m[1];
            const fam = m[2];
            return fam === 'wiki' ? `https://${lang}.wikipedia.org` : `https://${lang}.${fam}.org`;
        }
        return 'https://ar.wikipedia.org';
    }

    if (contestBadgeEl) {
        contestBadgeEl.style.display = project.is_contest ? "inline-block" : "none";
    }

    const commName = project.community_name || project.community || communitySelect.selectedOptions[0]?.textContent || "غير محدد";
    if (commEl) commEl.textContent = commName;

    if (targetWikiEl) {
        const wikiUrl = project.target_wiki_url || resolveWikiUrl(project.target_wiki);
        const wikiLabel = project.target_wiki || "arwiki";
        targetWikiEl.innerHTML = `<a href="${escapeHtml(wikiUrl)}" target="_blank" rel="noopener" style="color: #36c; text-decoration: underline;">${escapeHtml(wikiLabel)} (${escapeHtml(wikiUrl)})</a>`;
    }

        if (leadEl) {
            leadEl.textContent = project.lead_organizer || "غير محدد";
        }

        const coOrgs = Array.isArray(project.co_organizers) ? project.co_organizers : (project.co_organizers ? [project.co_organizers] : []);
        if (coOrgsItem && coOrgsEl) {
            if (coOrgs.length > 0) {
                coOrgsItem.style.display = "flex";
                coOrgsEl.textContent = coOrgs.join("، ");
            } else {
                coOrgsItem.style.display = "none";
            }
        }

        const dates = [];
        if (project.start_date) dates.push(`من: ${project.start_date}`);
        if (project.end_date) dates.push(`إلى: ${project.end_date}`);
        if (project.created_at) dates.push(`أُضيف: ${String(project.created_at).slice(0, 10)}`);
        if (datesEl) {
            datesEl.textContent = dates.length ? dates.join(" | ") : "غير محدد";
        }

        const jury = Array.isArray(project.jury_members) ? project.jury_members : [];
        if (juryItem && juryEl) {
            if (project.is_contest && jury.length > 0) {
                juryItem.style.display = "flex";
                juryEl.textContent = jury.join("، ");
            } else {
                juryItem.style.display = "none";
            }
        }

        if (descEl) {
            descEl.innerHTML = project.description || "<em>لا توجد تفاصيل إضافية مسجلة لهذا النشاط.</em>";
        }

        if (editLink) {
            if (project.id) {
                editLink.href = `/project/${project.id}/edit`;
                editLink.style.display = "inline-flex";
            } else {
                editLink.style.display = "none";
            }
        }

        if (directLink) {
            if (project.id) {
                directLink.href = `/project/${project.id}`;
                directLink.style.display = "inline-flex";
            } else {
                directLink.style.display = "none";
            }
        }

        modal.style.display = "flex";
        modal.setAttribute("aria-hidden", "false");
        document.body.classList.add("modal-open");
    }

    if (modalCloseBtn) modalCloseBtn.addEventListener("click", closeModal);
    if (modalFooterCloseBtn) modalFooterCloseBtn.addEventListener("click", closeModal);
    if (modal) {
        modal.addEventListener("click", (e) => {
            if (e.target === modal) closeModal();
        });
    }
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && modal && modal.style.display !== "none") {
            closeModal();
        }
    });

function displayProjects(projects) {
    results.replaceChildren();

    if (projects.length === 0) {
        results.textContent = "لم يتم العثور على أي أنشطة تطابق معايير التصفية.";
        return;
    }

    const grid = document.createElement("div");
    grid.className = "projects-grid";

    projects.forEach(project => {
        const card = document.createElement("div");
        card.className = "project-card clickable-project-card";
        card.setAttribute("role", "button");
        card.setAttribute("tabindex", "0");
        card.setAttribute("aria-label", `عرض تفاصيل: ${project.title || "النشاط"}`);

        const title = document.createElement("h3");
        title.className = "project-card-title";
        title.textContent =
            project.title || project.name || project.project || "نشاط بدون عنوان";

        const badges = document.createElement("div");
        badges.className = "project-badges-wrap";

        const status = document.createElement("span");
        const statusMap = {
            "in progress": "جارية",
            "planned": "مخططة",
            "completed": "مكتملة"
        };
        const rawStatus = project.status || "In Progress";
        const statusDisplay = statusMap[rawStatus.toLowerCase()] || rawStatus;
        status.className = `project-status project-status--${rawStatus.toLowerCase().replace(/\s+/g, "-")}`;
        status.textContent = statusDisplay;
        badges.appendChild(status);

        const project_type = document.createElement("span");
        project_type.className = "project-type-badge";
        const typeMap = {
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
        const rawType = project.project_type || project.type || "نشاط مجتمعي";
        project_type.textContent = typeMap[rawType.toLowerCase()] || rawType;
        badges.appendChild(project_type);

        if (project.is_contest) {
            const contestBadge = document.createElement("span");
            contestBadge.className = "project-contest-badge";
            contestBadge.textContent = "مسابقة";
            badges.appendChild(contestBadge);
        }

        const meta = document.createElement("div");
        meta.className = "project-card-meta";

        const community = document.createElement("p");
        community.className = "project-community";
        const commName =
            project.community_name ||
            project.community ||
            communitySelect.selectedOptions[0]?.textContent ||
            "غير محدد";
        community.textContent = `المجتمع: ${commName}`;
        meta.appendChild(community);

        if (project.target_wiki) {
            const wiki = document.createElement("p");
            wiki.className = "project-wiki";
            wiki.textContent = `المشروع: ${project.target_wiki}`;
            meta.appendChild(wiki);
        }

        const footer = document.createElement("div");
        footer.className = "project-card-footer";
        const cta = document.createElement("span");
        cta.className = "project-card-cta";
        cta.textContent = "عرض التفاصيل";
        footer.appendChild(cta);

        card.append(title, badges, meta, footer);

        card.addEventListener("click", () => openProjectModal(project));
        card.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                openProjectModal(project);
            }
        });

        grid.appendChild(card);
    });

    results.appendChild(grid);

    document.dispatchEvent(
        new CustomEvent("dashboard:filtered", {
            detail: { projects }
        })
    );
}


    async function loadCommunities() {
        const response = await fetch("/api/communities");

        if (!response.ok) {
            throw new Error(`Communities API: HTTP ${response.status}`);
        }

        const data = await response.json();
        const communities = Array.isArray(data)
            ? data
            : data.communities;

        if (!Array.isArray(communities)) {
            throw new Error("Invalid communities response");
        }

        communitySelect.replaceChildren(
            new Option("اختر المجتمع", "")
        );

        communities.forEach(community => {
            communitySelect.add(
                new Option(community.name, community.slug)
            );
        });
    }

    async function loadProjects() {
        const slug = communitySelect.value;
        const currentRequest = ++requestId;

        allProjects = [];
        filteredMode = false;
        displayProjects([]);

        if (!slug) {
            results.textContent = "اختر المجتمع لعرض أنشطته.";
            return;
        }

        results.textContent = "جاري تحميل الأنشطة...";

        try {
            const response = await fetch(
                `/api/${encodeURIComponent(slug)}/projects`
            );

            if (!response.ok) {
                throw new Error(`Projects API: HTTP ${response.status}`);
            }

            const data = await response.json();

            if (currentRequest !== requestId) return;

            allProjects = Array.isArray(data)
                ? data
                : data.projects;

            if (!Array.isArray(allProjects)) {
                throw new Error("Invalid projects response");
            }

            // Initial display: ALL projects, no filters applied.
            displayProjects(allProjects);
        } catch (error) {
            if (currentRequest === requestId) {
                console.error(error);
                results.textContent = `حدث خطأ أثناء تحميل البيانات: ${error.message}`;
            }
        }
    }

    

function normalize(value) {
    return String(value ?? "")
        .toLowerCase()
        .trim()
        .replace(/[-_]+/g, " ")
        .replace(/\s+/g, " ")
        .replace(/s$/, "");
}

function applyFilters() {
    const start = startDate?.value || "";
    const end = endDate?.value || "";
    const selectedType = activityType?.value || "";
    const selectedStatus = projectStatus?.value || "";

    const filteredProjects = allProjects.filter(project => {
        const projectDate = String(
            project.date ??
            project.start_date ??
            project.startDate ??
            ""
        ).slice(0, 10);

        const projectType =
            project.type ??
            project.activity_type ??
            project.project_type ??
            project.activityType ??
            "";

        const projectState =
            project.status ??
            project.project_status ??
            "";

        if (start && (!projectDate || projectDate < start)) {
            return false;
        }

        if (end && (!projectDate || projectDate > end)) {
            return false;
        }

        if (selectedType) {
            const normSelected = normalize(selectedType);
            const normProject = normalize(projectType);

            if (normSelected === "other") {
                const standardTypes = [
                    "workshop", "edit a thon", "photo walk", "contest",
                    "glam", "education program", "outreach", "campaign",
                    "conference meetup", "hackathon", "translation", "exhibition"
                ];
                const isStandard = standardTypes.some(t => normProject.includes(t) || t.includes(normProject));
                if (isStandard && normProject !== "other") {
                    return false;
                }
            } else {
                const matchExact = normProject === normSelected;
                const matchPrefix = normProject.startsWith(normSelected) || normSelected.startsWith(normProject);
                if (!matchExact && !matchPrefix) {
                    return false;
                }
            }
        }

        if (
            selectedStatus &&
            normalize(projectState) !== normalize(selectedStatus)
        ) {
            return false;
        }

        return true;
    });

    console.log("Selected type:", selectedType);
    console.log("Projects before filter:", allProjects.length);
    console.log("Projects after filter:", filteredProjects.length);

    displayProjects(filteredProjects);
}



    form.addEventListener("submit", event => {
        event.preventDefault();
        applyFilters();
    });

    if (resetButton) {
        resetButton.addEventListener("click", () => {
            form.reset();
            filteredMode = false;
            displayProjects(allProjects);
        });
    }

    communitySelect.addEventListener("change", loadProjects);

    loadCommunities()
        .then(() => {
            const currentSlug = document.querySelector("[data-community-slug]")?.dataset.communitySlug;
            if (currentSlug) {
                communitySelect.value = currentSlug;
            }
            if (communitySelect.value) {
                loadProjects();
            } else {
                results.textContent = "اختر المجتمع لعرض أنشطته.";
            }
        })
        .catch(error => {
            console.error(error);
            results.textContent = "تعذر تحميل قائمة المجتمعات.";
        });
});
