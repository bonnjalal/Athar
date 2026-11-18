(function (window) {
    const AR_ORDER = ["zero", "one", "two", "few", "many", "other"];
    const TWO_ORDER = ["one", "other"];

    function getPluralIndex(locale, n) {
        const num = Math.abs(parseInt(n, 10) || 0);
        const base = String(locale || "en").split("-")[0].toLowerCase();
        if (typeof Intl !== "undefined" && Intl.PluralRules) {
            try {
                const cat = new Intl.PluralRules(base).select(num);
                const order = base === "ar" ? AR_ORDER : TWO_ORDER;
                const idx = order.indexOf(cat);
                if (idx >= 0) return idx;
            } catch (_e) {
                // Fallback below
            }
        }
        if (base === "ar") {
            if (num === 0) return 0;
            if (num === 1) return 1;
            if (num === 2) return 2;
            const mod100 = num % 100;
            if (mod100 >= 3 && mod100 <= 10) return 3;
            if (mod100 >= 11 && mod100 <= 99) return 4;
            return 5;
        }
        return num === 1 ? 0 : 1;
    }

    function pickPluralForm(formsRaw, locale, numVal) {
        const parts = formsRaw.split("|");
        const explicit = {};
        const positional = [];
        for (const p of parts) {
            const m = p.match(/^=?(\d+)=(.*)$/);
            if (m) {
                explicit[parseInt(m[1], 10)] = m[2];
            } else {
                positional.push(p);
            }
        }
        const nInt = parseInt(numVal, 10) || 0;
        if (Object.prototype.hasOwnProperty.call(explicit, nInt)) {
            return explicit[nInt];
        }
        if (!positional.length) return formsRaw;
        const idx = getPluralIndex(locale, nInt);
        return idx < positional.length ? positional[idx] : positional[positional.length - 1];
    }

    function t(key) {
        const args = Array.prototype.slice.call(arguments, 1);
        const catalog = window.ATHAR_I18N || {};
        const locale = window.ATHAR_LOCALE || "ar";
        const template = Object.prototype.hasOwnProperty.call(catalog, key) ? catalog[key] : key;

        let out = String(template).replace(/\{\{PLURAL:\$(\d+)\|([^{}]+)\}\}/gi, function (_, idxStr, formsRaw) {
            const idx = parseInt(idxStr, 10) - 1;
            const val = idx >= 0 && idx < args.length ? args[idx] : 0;
            return pickPluralForm(formsRaw, locale, val);
        });

        out = out.replace(/\$(\d+)/g, function (match, idxStr) {
            const idx = parseInt(idxStr, 10) - 1;
            return idx >= 0 && idx < args.length ? String(args[idx]) : match;
        });

        return out;
    }

    window.atharI18n = { t: t };
})(window);

