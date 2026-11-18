"""
app/i18n.py

Translatewiki.net banana-i18n JSON catalog loader, CLDR plural evaluator,
request locale resolver, and Jinja/Python translation helpers.
"""
from datetime import datetime
import json
from pathlib import Path
import re
from flask import current_app, g, has_app_context, has_request_context, request, session

I18N_ROOT = Path(__file__).resolve().parent.parent / "i18n"

RTL_LOCALES = frozenset(
    {"ar", "arc", "arz", "ary", "ckb", "dv", "fa", "glk", "he", "ku", "lrc", "mzn", "nqo", "pnb", "ps", "sd", "ug", "ur", "yi"}
)

LOCALE_LABELS = {
    "ar": "العربية",
    "en": "English",
    "fr": "Français",
}

LOCALE_CODE_PATTERN = re.compile(r"^[a-z0-9]{2,12}(?:-[a-z0-9]{2,12})*$")
PLURAL_PATTERN = re.compile(r"\{\{PLURAL:\$(\d+)\|([^{}]+)\}\}", re.IGNORECASE)
PARAM_PATTERN = re.compile(r"\$(\d+)")

TYPE_KEY_MAP = {
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
    "other": "athar-type-other",
}

STATUS_KEY_MAP = {
    "in progress": "athar-status-in-progress",
    "planned": "athar-status-planned",
    "completed": "athar-status-completed",
    "canceled": "athar-status-canceled",
    "cancelled": "athar-status-canceled",
}

_CATALOG_CACHE: dict[str, dict[str, dict[str, str]]] = {}
_SUPPORTED_LOCALES: list[str] = []


def _load_all_catalogs():
    global _CATALOG_CACHE, _SUPPORTED_LOCALES
    cache = {"ui": {}, "reports": {}}
    for domain in ("ui", "reports"):
        domain_dir = I18N_ROOT / domain
        if not domain_dir.is_dir():
            continue
        for json_file in sorted(domain_dir.glob("*.json")):
            code = json_file.stem.lower()
            if code == "qqq" or not LOCALE_CODE_PATTERN.match(code):
                continue
            with open(json_file, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            cache[domain][code] = {k: v for k, v in raw.items() if k != "@metadata" and isinstance(v, str)}

    _CATALOG_CACHE = cache
    discovered = sorted(cache.get("ui", {}).keys())
    _SUPPORTED_LOCALES = discovered or ["ar", "en"]


_load_all_catalogs()


def get_supported_locales() -> list[str]:
    return list(_SUPPORTED_LOCALES)


def is_supported_locale(lang: str | None) -> bool:
    if not lang:
        return False
    val = str(lang).strip().lower()
    return bool(LOCALE_CODE_PATTERN.match(val) and val in _SUPPORTED_LOCALES)


def locale_dir(lang: str | None = None) -> str:
    code = (lang or current_locale()).strip().lower().split("-")[0]
    return "rtl" if code in RTL_LOCALES else "ltr"


def locale_label(lang: str) -> str:
    return LOCALE_LABELS.get(lang, lang.upper())


def resolve_request_locale() -> str:
    default_lang = "ar"
    if has_app_context():
        default_lang = current_app.config.get("DEFAULT_LOCALE", "ar") or "ar"

    if has_request_context():
        override = getattr(g, "report_lang", None)
        if override and is_supported_locale(override):
            return override
        sess_lang = session.get("lang")
        if sess_lang and is_supported_locale(sess_lang):
            return sess_lang.strip().lower()

    return default_lang if is_supported_locale(default_lang) else "ar"


def current_locale() -> str:
    return resolve_request_locale()


def activate_report_lang_from_request() -> str:
    """
    Inspect optional '?lang=' query parameter on printable report and CSV routes.
    Sets g.report_lang for the current request WITHOUT mutating session['lang'].
    Raises ValueError if '?lang=' was explicitly given with an unsupported or invalid code.
    """
    raw_lang = request.args.get("lang")
    if raw_lang is not None and str(raw_lang).strip() != "":
        clean = str(raw_lang).strip().lower()
        if not is_supported_locale(clean):
            raise ValueError(f"Unsupported or invalid language parameter: '{raw_lang}'.")
        g.report_lang = clean
        return clean
    return resolve_request_locale()


def _cldr_plural_index(lang: str, n: float) -> int:
    base = (lang or "en").strip().lower().split("-")[0]
    try:
        num = abs(int(n))
    except (ValueError, TypeError):
        num = 0

    if base == "ar":
        if num == 0:
            return 0  # zero
        if num == 1:
            return 1  # one
        if num == 2:
            return 2  # two
        mod100 = num % 100
        if 3 <= mod100 <= 10:
            return 3  # few
        if 11 <= mod100 <= 99:
            return 4  # many
        return 5      # other

    if base == "fr":
        return 0 if num in (0, 1) else 1

    # Default (English & standard 2-form locales)
    return 0 if num == 1 else 1


def _pick_plural_form(forms_raw: str, lang: str, num_val: float) -> str:
    parts = forms_raw.split("|")
    explicit_map = {}
    positional = []

    for part in parts:
        m = re.match(r"^=?(\d+)=(.*)$", part)
        if m:
            explicit_map[int(m.group(1))] = m.group(2)
        else:
            positional.append(part)

    try:
        n_int = int(num_val)
    except (ValueError, TypeError):
        n_int = 0

    if n_int in explicit_map:
        return explicit_map[n_int]

    if not positional:
        return forms_raw

    idx = _cldr_plural_index(lang, num_val)
    if idx < len(positional):
        return positional[idx]
    return positional[-1]


def format_message(template: str, lang: str, *args) -> str:
    """Apply banana-i18n {{PLURAL:$N|...}} and $N positional substitutions."""
    if not template:
        return ""

    def _replace_plural(match):
        arg_idx = int(match.group(1)) - 1
        forms_str = match.group(2)
        num_val = args[arg_idx] if 0 <= arg_idx < len(args) else 0
        return _pick_plural_form(forms_str, lang, num_val)

    rendered = PLURAL_PATTERN.sub(_replace_plural, template)

    def _replace_param(match):
        arg_idx = int(match.group(1)) - 1
        if 0 <= arg_idx < len(args):
            return str(args[arg_idx])
        return match.group(0)

    return PARAM_PATTERN.sub(_replace_param, rendered)


def _lookup_key(domain: str, key: str, lang: str) -> str | None:
    domain_map = _CATALOG_CACHE.get(domain, {})
    if lang in domain_map and key in domain_map[lang]:
        return domain_map[lang][key]
    if "en" in domain_map and key in domain_map["en"]:
        return domain_map["en"][key]
    return None


def _(key: str, *args, lang: str | None = None) -> str:
    """Translate a key from the 'ui' message group."""
    target_lang = (lang.strip().lower() if lang and is_supported_locale(lang) else resolve_request_locale())
    template = _lookup_key("ui", key, target_lang)
    if template is None:
        return key
    return format_message(template, target_lang, *args)


def _r(key: str, *args, lang: str | None = None) -> str:
    """Translate a key from the 'reports' message group, falling back to 'ui'."""
    target_lang = (lang.strip().lower() if lang and is_supported_locale(lang) else resolve_request_locale())
    template = _lookup_key("reports", key, target_lang)
    if template is None:
        template = _lookup_key("ui", key, target_lang)
    if template is None:
        return key
    return format_message(template, target_lang, *args)


def translate_type_for_lang(val: str | None, lang: str | None = None) -> str:
    if not val:
        return _("athar-type-default", lang=lang)
    key = TYPE_KEY_MAP.get(str(val).strip().lower())
    if key:
        return _(key, lang=lang)
    return str(val)


def translate_status_for_lang(val: str | None, lang: str | None = None) -> str:
    if not val:
        return _("athar-status-in-progress", lang=lang)
    key = STATUS_KEY_MAP.get(str(val).strip().lower())
    if key:
        return _(key, lang=lang)
    return str(val)


def format_relative_time(dt: datetime | None, lang: str | None = None) -> str:
    if not dt:
        return _("athar-time-unavailable", lang=lang)
    diff = datetime.utcnow() - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return _("athar-time-now", lang=lang)
    minutes = seconds // 60
    if minutes < 60:
        return _("athar-time-minutes", minutes, lang=lang)
    hours = minutes // 60
    if hours < 24:
        return _("athar-time-hours", hours, lang=lang)
    days = hours // 24
    if days == 1:
        return _("athar-time-yesterday", lang=lang)
    if days < 30:
        return _("athar-time-days", days, lang=lang)
    months = days // 30
    return _("athar-time-months", months, lang=lang)


def get_client_catalog(lang: str | None = None) -> dict:
    """Return active locale UI message bundle for window.ATHAR_I18N client helpers."""
    target = (lang.strip().lower() if lang and is_supported_locale(lang) else resolve_request_locale())
    merged = dict(_CATALOG_CACHE.get("ui", {}).get("en", {}))
    merged.update(_CATALOG_CACHE.get("ui", {}).get(target, {}))
    return merged

