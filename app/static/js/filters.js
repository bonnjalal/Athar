document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("dashboard-filters");
    if (!form) return;

    // Trim empty query inputs prior to bookmarkable GET submission
    form.addEventListener("submit", () => {
        const inputs = form.querySelectorAll("input, select");
        inputs.forEach((el) => {
            if (!el.name) return;
            if (!String(el.value || "").trim()) {
                el.disabled = true;
            }
        });
    });
});
