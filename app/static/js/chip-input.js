(function (window) {
    const activeInstances = [];

    function normalizeTagValue(raw) {
        if (!raw) return "";
        return String(raw)
            .replace(/<[^>]*>/g, "")
            .trim()
            .replace(/^#+/, "")
            .replace(/\s+/g, " ")
            .toLowerCase()
            .slice(0, 64);
    }

    function setupChipInput(config) {
        const container = document.getElementById(config.containerId);
        const chipsList = document.getElementById(config.chipsId);
        const input = document.getElementById(config.inputId);
        const hidden = document.getElementById(config.hiddenId);
        const feedback = config.feedbackId ? document.getElementById(config.feedbackId) : null;

        if (!container || !chipsList || !input || !hidden) return null;

        const mode = config.mode || "wikimedia_user";
        const maxItems = config.maxItems || (mode === "tag" ? 20 : 100);
        let items = [];
        let pendingPromise = null;

        function setFeedback(msg, type) {
            if (!feedback) return;
            feedback.textContent = msg;
            feedback.className = "cdx-chip-feedback " + (type ? "is-" + type : "");
            if (type === "error") {
                container.classList.add("is-error");
            } else {
                container.classList.remove("is-error");
            }
        }

        function sync() {
            hidden.value = items.join(",");
        }

        function render() {
            chipsList.innerHTML = "";
            items.forEach((value, index) => {
                const chip = document.createElement("span");
                chip.className = mode === "tag" ? "cdx-chip cdx-chip--tag" : "cdx-chip";
                chip.textContent = value;

                const removeBtn = document.createElement("button");
                removeBtn.type = "button";
                removeBtn.className = "cdx-chip-remove";
                removeBtn.innerHTML = "&times;";
                removeBtn.setAttribute("aria-label", "Remove " + value);
                removeBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    items.splice(index, 1);
                    render();
                    setFeedback("", "");
                    input.focus();
                });

                chip.appendChild(removeBtn);
                chipsList.appendChild(chip);
            });
            sync();
        }

        if (hidden.value && hidden.value.trim()) {
            hidden.value.split(",").forEach((raw) => {
                const val = mode === "tag" ? normalizeTagValue(raw) : raw.trim();
                if (val && !items.some((x) => x.toLowerCase() === val.toLowerCase())) {
                    if (items.length < maxItems) items.push(val);
                }
            });
            render();
        }

        function addTagSynchronously(raw) {
            const val = normalizeTagValue(raw);
            if (!val) {
                input.value = "";
                return false;
            }
            if (items.some((x) => x.toLowerCase() === val.toLowerCase())) {
                setFeedback(`"${val}" مضاف مسبقاً.`, "error");
                input.value = "";
                return false;
            }
            if (items.length >= maxItems) {
                setFeedback(`الحد الأقصى هو ${maxItems} وسماً للنشاط الواحد.`, "error");
                return false;
            }
            items.push(val);
            render();
            input.value = "";
            setFeedback("", "");
            return true;
        }

        async function verifyAndAddUser(rawName) {
            const username = String(rawName || "").trim().replace(/^,+|,+$/g, "");
            if (!username) return;

            if (items.some((x) => x.toLowerCase() === username.toLowerCase())) {
                setFeedback(`المستخدم "${username}" مضاف مسبقاً في القائمة.`, "error");
                return;
            }

            setFeedback(`جاري التحقق من حساب "${username}" في ويكيميديا...`, "loading");

            const runCheck = (async () => {
                try {
                    const resp = await fetch(`/api/check-user?username=${encodeURIComponent(username)}`);
                    const data = await resp.json();
                    if (data.exists) {
                        const canonicalName = data.username || username;
                        if (!items.some((x) => x.toLowerCase() === canonicalName.toLowerCase())) {
                            items.push(canonicalName);
                            render();
                        }
                        input.value = "";
                        setFeedback(`تم التحقق من الحساب "${canonicalName}" وإضافته بنجاح.`, "success");
                        setTimeout(() => {
                            if (feedback && feedback.classList.contains("is-success")) {
                                setFeedback("", "");
                            }
                        }, 2500);
                    } else {
                        setFeedback(`المستخدم "${username}" غير مسجل في ويكيميديا. يرجى التأكد من الاسم.`, "error");
                    }
                } catch (_err) {
                    setFeedback("تعذر التحقق من الحساب حالياً، يرجى المحاولة لاحقاً.", "error");
                } finally {
                    pendingPromise = null;
                }
            })();

            pendingPromise = runCheck;
            return runCheck;
        }

        function addItem(raw) {
            if (mode === "tag") {
                return addTagSynchronously(raw);
            }
            if (!pendingPromise) {
                return verifyAndAddUser(raw);
            }
            return pendingPromise;
        }

        container.addEventListener("click", (e) => {
            if (e.target !== input && !e.target.classList.contains("cdx-chip-remove")) {
                input.focus();
            }
        });

        input.addEventListener("focus", () => container.classList.add("is-focused"));
        input.addEventListener("blur", () => {
            container.classList.remove("is-focused");
            if (mode === "tag" && input.value.trim()) {
                addTagSynchronously(input.value);
            }
        });

        input.addEventListener("input", () => {
            if (container.classList.contains("is-error")) {
                container.classList.remove("is-error");
                if (feedback && feedback.classList.contains("is-error")) {
                    feedback.textContent = "";
                }
            }
        });

        input.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === ",") {
                e.preventDefault();
                addItem(input.value);
            } else if (e.key === "Backspace" && input.value === "" && items.length > 0) {
                items.pop();
                render();
                setFeedback("", "");
            }
        });

        input.addEventListener("paste", (e) => {
            const pasteData = (e.clipboardData || window.clipboardData).getData("text");
            if (pasteData && pasteData.includes(",")) {
                e.preventDefault();
                const parts = pasteData.split(",").map((s) => s.trim()).filter(Boolean);
                parts.forEach((part) => {
                    if (mode === "tag") {
                        addTagSynchronously(part);
                    } else {
                        verifyAndAddUser(part);
                    }
                });
            }
        });

        const instance = {
            flush: async function () {
                if (mode === "tag" && input.value.trim()) {
                    addTagSynchronously(input.value);
                } else if (mode === "wikimedia_user" && input.value.trim() && !pendingPromise) {
                    await verifyAndAddUser(input.value);
                }
                if (pendingPromise) {
                    await pendingPromise;
                }
            },
        };
        activeInstances.push(instance);
        return instance;
    }

    async function flushAll() {
        for (const inst of activeInstances) {
            await inst.flush();
        }
    }

    window.AtharChipInput = {
        setup: setupChipInput,
        flushAll: flushAll,
    };
})(window);

