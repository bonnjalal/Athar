
var communitiesSelect = document.getElementById("communities");

async function chargeComm() {
    if (!communitiesSelect) return;

    try {
        const response = await fetch("/api/communities");

        if (!response.ok) {
            throw new Error(
                `Failed to load communities (${response.status})`
            );
        }

        const data = await response.json();
        const communities = Array.isArray(data)
            ? data
            : data.communities;

        if (!Array.isArray(communities)) {
            throw new Error("Unexpected communities API response");
        }

        communitiesSelect.replaceChildren();

        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "اختر المجتمع";
        communitiesSelect.appendChild(placeholder);

        communities.forEach((community) => {
            const option = document.createElement("option");
            option.value = community.slug;
            option.textContent = community.name;
            communitiesSelect.appendChild(option);
        });
    } catch (error) {
        console.error("Error loading communities:", error);
    }
}

document.getElementById('export-comm-btn').addEventListener('click', ()=>{
    window.location.href(`/api/${communities.value}`);
})

document.addEventListener("DOMContentLoaded", chargeComm);
