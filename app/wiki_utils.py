"""
Wikimedia project normalization, validation, sanitization, and URL generation.
Ensures strict security against SSRF, open-redirects, XSS, and broken hostnames.
"""
from datetime import date, datetime
import json
import logging
import re
from urllib.parse import quote, urlparse, urlunparse

import bleach
from bleach.linkifier import Linker
import requests
from flask import current_app
from sqlalchemy import func

logger = logging.getLogger(__name__)

# Whitelisted Wikimedia root domains for target_wiki (must strictly end with one of these)
ALLOWED_WIKIMEDIA_DOMAINS = (
    "wikipedia.org",
    "wikimedia.org",
    "wikidata.org",
    "wikisource.org",
    "wiktionary.org",
    "wikibooks.org",
    "wikiquote.org",
    "wikivoyage.org",
    "wikinews.org",
    "wikiversity.org",
    "mediawiki.org",
    "wikifunctions.org",
)

# Extended host whitelist for optional activity page links (wiki_link)
ALLOWED_ACTIVITY_LINK_DOMAINS = ALLOWED_WIKIMEDIA_DOMAINS + (
    "wmcloud.org",
    "wmflabs.org",
    "toolforge.org",
)

# Canonical cross-wiki campaign presets (separated from topic tags)
PRESET_CAMPAIGNS = (
    "Wiki Loves Ramadan",
    "Wiki Loves Monuments",
    "Wiki Loves Africa",
    "Wiki Loves Earth",
    "Wiki Loves Folklore",
    "1Lib1Ref",
    "Feminism and Folklore",
    "WikiGap",
    "SheSaid",
    "CEE Spring",
    "WikiForHumanRights",
)

STANDARD_ACTIVITY_TYPES = (
    "Workshop",
    "Edit-a-thon",
    "Photo Walk",
    "Contest",
    "Contest / Competition",
    "GLAM",
    "Education Program",
    "Outreach",
    "Campaign",
    "Conference / Meetup",
    "Hackathon",
    "Translation",
    "Exhibition",
)

LANG_CODE_REGEX = re.compile(r"^[a-z]{2,12}(-[a-z0-9]{2,12})*$")
ALLOWED_DESCRIPTION_TAGS = ["p", "b", "i", "strong", "em", "ul", "ol", "li", "a", "br"]
ALLOWED_DESCRIPTION_ATTRS = {"a": ["href", "title"]}
MAX_TRANSLATION_LANGUAGES = 20
MAX_TRANSLATED_TITLE_LEN = 255
MAX_TRANSLATED_DESC_LEN = 10240
MAX_TRANSLATED_RESULT_LEN = 4096


def _set_noopener_rel(attrs, new=False):
    if (None, "href") in attrs:
        attrs[(None, "rel")] = "noopener noreferrer"
    return attrs


_REL_LINKER = Linker(
    callbacks=[_set_noopener_rel],
    url_re=re.compile(r"(?!x)x"),
    parse_email=False,
)

# Canonical special project mappings: alias -> (canonical_code, domain)
SPECIAL_WIKI_MAP = {
    "commons": ("commonswiki", "commons.wikimedia.org"),
    "commonswiki": ("commonswiki", "commons.wikimedia.org"),
    "wikidata": ("wikidatawiki", "www.wikidata.org"),
    "wikidatawiki": ("wikidatawiki", "www.wikidata.org"),
    "meta": ("metawiki", "meta.wikimedia.org"),
    "metawiki": ("metawiki", "meta.wikimedia.org"),
    "species": ("specieswiki", "species.wikimedia.org"),
    "specieswiki": ("specieswiki", "species.wikimedia.org"),
    "incubator": ("incubatorwiki", "incubator.wikimedia.org"),
    "incubatorwiki": ("incubatorwiki", "incubator.wikimedia.org"),
    "mediawiki": ("mediawikiwiki", "www.mediawiki.org"),
    "mediawikiwiki": ("mediawikiwiki", "www.mediawiki.org"),
    "wikifunctions": ("wikifunctionswiki", "www.wikifunctions.org"),
    "wikifunctionswiki": ("wikifunctionswiki", "www.wikifunctions.org"),
    "sourceswiki": ("sourceswiki", "wikisource.org"),
    # Arabic names gracefully normalized to canonical projects
    "ويكيبيديا": ("arwiki", "ar.wikipedia.org"),
    "ويكيبيديا العربية": ("arwiki", "ar.wikipedia.org"),
    "ويكيبيديا المغربية": ("arywiki", "ary.wikipedia.org"),
    "دارجة": ("arywiki", "ary.wikipedia.org"),
    "كومنز": ("commonswiki", "commons.wikimedia.org"),
    "ويكيميديا كومنز": ("commonswiki", "commons.wikimedia.org"),
    "ويكي بيانات": ("wikidatawiki", "www.wikidata.org"),
    "ميتا": ("metawiki", "meta.wikimedia.org"),
    "ميتا-ويكي": ("metawiki", "meta.wikimedia.org"),
}

# Regex for MediaWiki dbnames like arwiki, enwiki, arywiki, zghwiki, arwikisource, etc.
DBNAME_REGEX = re.compile(
    r"^([a-z]{2,12}(?:-[a-z0-9]{2,12})*)"
    r"(wiki|wikisource|wiktionary|wikibooks|wikiquote|wikivoyage|wikinews|wikiversity)$"
)


def is_allowed_wikimedia_host(hostname: str, allowed_domains=ALLOWED_WIKIMEDIA_DOMAINS) -> bool:
    """Check if hostname belongs strictly to an allowed domain suffix."""
    if not hostname:
        return False
    hostname = hostname.lower().strip().rstrip(".")
    if not hostname:
        return False
    return any(hostname == d or hostname.endswith("." + d) for d in allowed_domains)


def validate_activity_wiki_url(raw_url: str | None) -> str | None:
    """
    Validate and normalize an optional activity page link (wiki_link).
    Allows official Wikimedia project domains plus wmcloud.org, wmflabs.org, and toolforge.org.
    Returns None when raw_url is empty/blank; never auto-generates URLs.
    """
    if raw_url is None:
        return None
    val = str(raw_url).strip()
    if not val:
        return None

    if "\\" in val or any(ord(c) < 32 or ord(c) == 127 or c.isspace() for c in val):
        raise ValueError("Invalid characters or whitespace in activity URL.")

    if val.lower().startswith("http://"):
        val = "https://" + val[7:]
    elif "://" not in val:
        lead = val.split("/", 1)[0]
        if "." in lead and ":" not in lead and not val.startswith("//"):
            val = "https://" + val

    if len(val) > 1024:
        raise ValueError("Activity URL must not exceed 1024 characters.")

    parsed = urlparse(val)
    if parsed.scheme.lower() != "https":
        raise ValueError("Activity URL must use HTTPS.")

    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Credentials are not allowed in activity URL.")

    try:
        explicit_port = parsed.port
    except ValueError as exc:
        raise ValueError("Malformed port in activity URL.") from exc

    if explicit_port is not None or ":" in (parsed.netloc or ""):
        raise ValueError("Explicit ports are not allowed in activity URL.")

    hostname = (parsed.hostname or "").lower().rstrip(".")
    if not hostname or not is_allowed_wikimedia_host(hostname, allowed_domains=ALLOWED_ACTIVITY_LINK_DOMAINS):
        raise ValueError(
            "Activity URL host must belong to Wikimedia, wmcloud.org, wmflabs.org, or toolforge.org."
        )

    return urlunparse(("https", hostname, parsed.path, parsed.params, parsed.query, parsed.fragment))


def normalize_wiki_target(raw_input: str, default: str = "arwiki") -> tuple[str, str]:
    """
    Validates and transforms user-supplied wiki identifier into (canonical_code, canonical_url).
    """
    if not raw_input:
        raw_input = default

    val = str(raw_input).strip()
    val_clean = re.sub(r"^https?://", "", val).strip().rstrip("/")
    lower_val = val_clean.lower()

    if lower_val in SPECIAL_WIKI_MAP:
        code, domain = SPECIAL_WIKI_MAP[lower_val]
        return code, f"https://{domain}"

    if is_allowed_wikimedia_host(val_clean):
        parts = val_clean.split(".")
        if len(parts) >= 3 and parts[-2] == "wikipedia":
            code = f"{parts[0]}wiki"
        elif "commons" in parts[0]:
            code = "commonswiki"
        elif "wikidata" in parts:
            code = "wikidatawiki"
        else:
            code = val_clean
        return code, f"https://{val_clean}"

    m = DBNAME_REGEX.match(lower_val)
    if m:
        lang, project_family = m.groups()
        if project_family == "wiki":
            domain = f"{lang}.wikipedia.org"
        else:
            domain = f"{lang}.{project_family}.org"
        return lower_val, f"https://{domain}"

    raise ValueError(
        f"Invalid Wikimedia project identifier: '{raw_input}'. "
        "Allowed examples: arwiki, commons, wikidata, arywiki, enwiki, metawiki."
    )


def resolve_wiki_url(raw_input: str, default: str = "arwiki") -> str:
    """Safe helper that returns canonical URL, falling back safely to default on error."""
    try:
        _, url = normalize_wiki_target(raw_input, default)
        return url
    except ValueError:
        return "https://ar.wikipedia.org"


def sanitize_plain_text(val: str | None) -> str:
    """Strip all HTML tags and attributes from plain-text inputs."""
    if val is None:
        return ""
    return bleach.clean(str(val), tags=[], attributes={}, strip=True).strip()


def sanitize_rich_html(val: str | None) -> str:
    """Sanitize rich HTML descriptions while enforcing rel='noopener noreferrer' on links."""
    if val is None:
        return ""
    cleaned = bleach.clean(
        str(val).strip(),
        tags=ALLOWED_DESCRIPTION_TAGS,
        attributes=ALLOWED_DESCRIPTION_ATTRS,
        protocols=["http", "https"],
        strip=True,
    )
    if "<a" in cleaned.lower():
        cleaned = _REL_LINKER.linkify(cleaned)
    return cleaned


def validate_lang_code(raw_code: str | None) -> str:
    """Validate and normalize BCP-47 / Wikimedia language codes."""
    code = str(raw_code or "").strip().lower()
    if not code or not LANG_CODE_REGEX.match(code):
        raise ValueError(f"Invalid language code: '{raw_code}'.")
    return code


def sanitize_translations_dict(raw_translations, primary_lang: str = "ar") -> dict | None:
    """
    Validate and sanitize Project.translations dictionary.
    Removes any key duplicating primary_lang, caps language count at 20,
    sanitizes HTML in description and strips HTML in plain-text fields.
    """
    if raw_translations is None or raw_translations == "":
        return None
    if not isinstance(raw_translations, dict):
        raise ValueError("Translations payload must be a JSON object mapping language codes.")

    norm_primary = validate_lang_code(primary_lang or "ar")
    cleaned_map = {}

    for raw_lang, entry in raw_translations.items():
        if not isinstance(entry, dict):
            continue
        lang_code = validate_lang_code(raw_lang)
        if lang_code == norm_primary:
            continue

        title_val = sanitize_plain_text(entry.get("title"))[:MAX_TRANSLATED_TITLE_LEN]
        desc_val = sanitize_rich_html(entry.get("description"))[:MAX_TRANSLATED_DESC_LEN]
        summary_val = sanitize_plain_text(entry.get("results_summary"))[:MAX_TRANSLATED_RESULT_LEN]
        notes_val = sanitize_plain_text(entry.get("results_notes"))[:MAX_TRANSLATED_RESULT_LEN]

        if not any((title_val, desc_val, summary_val, notes_val)):
            continue

        if len(cleaned_map) >= MAX_TRANSLATION_LANGUAGES:
            raise ValueError(f"Maximum of {MAX_TRANSLATION_LANGUAGES} translation languages allowed.")

        cleaned_map[lang_code] = {
            "title": title_val,
            "description": desc_val,
            "results_summary": summary_val,
            "results_notes": notes_val,
        }

    return cleaned_map or None


def sanitize_project_text_fields(
    title: str | None = None,
    description: str | None = "",
    results_summary: str | None = "",
    results_notes: str | None = "",
    winners=None,
    primary_lang: str = "ar",
    translations=None,
    require_title: bool = True,
) -> dict:
    """
    Shared XSS sanitization helper for web_bp, api_bp, and MinT translation proxy.
    """
    clean_primary = validate_lang_code(primary_lang or "ar")
    clean_title = sanitize_plain_text(title)
    if require_title and not clean_title:
        raise ValueError("Activity title cannot be empty.")
    if len(clean_title) > MAX_TRANSLATED_TITLE_LEN:
        raise ValueError("Activity title exceeds 255 characters.")

    clean_description = sanitize_rich_html(description)[:MAX_TRANSLATED_DESC_LEN]
    clean_summary = sanitize_plain_text(results_summary)[:MAX_TRANSLATED_RESULT_LEN]
    clean_notes = sanitize_plain_text(results_notes)[:MAX_TRANSLATED_RESULT_LEN]

    clean_winners = []
    if isinstance(winners, list):
        for w in winners:
            cw = sanitize_plain_text(w)
            if cw and cw not in clean_winners:
                clean_winners.append(cw)

    clean_translations = sanitize_translations_dict(translations, primary_lang=clean_primary)

    return {
        "title": clean_title,
        "description": clean_description,
        "results_summary": clean_summary,
        "results_notes": clean_notes,
        "winners": clean_winners,
        "primary_lang": clean_primary,
        "translations": clean_translations,
    }


ACTIVITY_TYPE_ARABIC = {
    "Workshop": "ورشة تدريبية",
    "Edit-a-thon": "ماراثون تحرير",
    "Photo Walk": "جولة تصوير",
    "Contest": "مسابقة ومنافسة",
    "Contest / Competition": "مسابقة ومنافسة",
    "GLAM": "شراكة ثقافية",
    "Education Program": "برنامج تعليمي",
    "Outreach": "برنامج توعوي",
    "Campaign": "حملة محتوى",
    "Conference / Meetup": "مؤتمر أو لقاء",
    "Hackathon": "فعالية برمجية",
    "Translation": "حملة ترجمة",
    "Exhibition": "معرض وتوثيق",
    "Other": "نشاط مخصص",
}

STATUS_ARABIC = {
    "In Progress": "جارية",
    "in progress": "جارية",
    "Planned": "مخططة",
    "planned": "مخططة",
    "Completed": "مكتملة",
    "completed": "مكتملة",
    "Canceled": "ملغاة",
    "canceled": "ملغاة",
    "Cancelled": "ملغاة",
    "cancelled": "ملغاة",
}


def translate_activity_type(val: str, lang: str | None = None) -> str:
    try:
        from app.i18n import translate_type_for_lang
        return translate_type_for_lang(val, lang=lang)
    except ImportError:
        if not val:
            return "نشاط مجتمعي"
        return ACTIVITY_TYPE_ARABIC.get(val, val)


def translate_status(val: str, lang: str | None = None) -> str:
    try:
        from app.i18n import translate_status_for_lang
        return translate_status_for_lang(val, lang=lang)
    except ImportError:
        if not val:
            return "جارية"
        return STATUS_ARABIC.get(val, val)


def determine_project_status(
    start_date=None,
    end_date=None,
    requested_status=None,
    current_status=None,
) -> str:
    """
    Determine project status based on dates and explicit override.
    - Normalizes 'Canceled' / 'Cancelled' / 'ملغي' / 'ملغاة' to 'Canceled'.
    - Preserves existing 'Canceled' status when requested_status is 'auto' or omitted.
    """
    today = date.today()

    if isinstance(start_date, str) and start_date.strip():
        try:
            start_date = datetime.strptime(start_date.strip(), "%Y-%m-%d").date()
        except ValueError:
            start_date = None
    elif isinstance(start_date, datetime):
        start_date = start_date.date()

    if isinstance(end_date, str) and end_date.strip():
        try:
            end_date = datetime.strptime(end_date.strip(), "%Y-%m-%d").date()
        except ValueError:
            end_date = None
    elif isinstance(end_date, datetime):
        end_date = end_date.date()

    if requested_status and requested_status not in ("auto", "Auto", ""):
        low = str(requested_status).strip().lower()
        if low in ("canceled", "cancelled", "ملغي", "ملغاة"):
            return "Canceled"
        if low in ("completed", "مكتملة", "منتهية", "finished"):
            return "Completed"
        if low in ("planned", "مخططة", "قادمة", "in the future"):
            return "Planned"
        if low in ("in progress", "جارية", "قيد التنفيذ", "running"):
            return "In Progress"
        return str(requested_status).strip()

    if current_status and str(current_status).strip().lower() in ("canceled", "cancelled"):
        return "Canceled"

    if end_date and end_date < today:
        return "Completed"
    if start_date and start_date > today:
        return "Planned"
    if start_date and start_date <= today:
        if end_date and end_date < today:
            return "Completed"
        return "In Progress"
    if end_date and end_date >= today:
        return "In Progress"

    return "In Progress"


def build_xtools_user_url(wiki_code: str, username: str) -> str:
    """Construct an outbound URL to XTools Edit Counter for a given user and wiki."""
    clean_code = (wiki_code or "arwiki").strip()
    try:
        clean_code, _ = normalize_wiki_target(clean_code)
    except ValueError:
        pass
    clean_user = (username or "").strip().replace(" ", "_")
    return f"https://xtools.wmcloud.org/ec/{clean_code}/{quote(clean_user)}"


def verify_wikimedia_username(raw_username: str) -> dict:
    """
    Verify a Wikimedia username locally first, then against Meta-Wiki CentralAuth globaluserinfo.
    Raises RuntimeError when the Wikimedia API request fails so callers can distinguish
    upstream outages (HTTP 503) from missing accounts.
    """
    from app.models import User

    cleaned = (raw_username or "").replace("_", " ").strip()
    if not cleaned:
        raise ValueError("Username is required.")

    local_user = User.query.filter(func.lower(User.username) == cleaned.lower()).first()
    if local_user:
        return {
            "exists": True,
            "username": local_user.username,
            "source": "local",
        }

    url = "https://meta.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "meta": "globaluserinfo",
        "guiuser": cleaned,
        "format": "json",
    }
    ua = current_app.config.get("USER_AGENT", "Athar/1.0 (https://athar.toolforge.org)")
    try:
        resp = requests.get(url, params=params, headers={"User-Agent": ua}, timeout=5)
        if resp.status_code != 200:
            logger.warning("CentralAuth check HTTP %s for username=%r", resp.status_code, cleaned)
            raise RuntimeError(f"Wikimedia CentralAuth returned HTTP {resp.status_code}.")
        gui = resp.json().get("query", {}).get("globaluserinfo", {})
    except requests.RequestException as exc:
        logger.warning("CentralAuth request failed for username=%r: %s", cleaned, exc)
        raise RuntimeError("Wikimedia CentralAuth lookup failed.") from exc

    if not gui or "missing" in gui:
        return {"exists": False, "username": cleaned}

    canonical_name = gui.get("name", cleaned)
    return {
        "exists": True,
        "username": canonical_name,
        "id": gui.get("id"),
        "home": gui.get("home", ""),
        "source": "wikimedia",
    }


MAX_PROJECT_TAGS = 20

RESERVED_SLUGS = frozenset({
    "user",
    "project",
    "export",
    "api",
    "auth",
    "static",
    "admin",
    "activities",
    "login",
    "logout",
    "oauth",
    "add-community",
    "lang",
})


def is_reserved_slug(slug: str) -> bool:
    """Check if a slug collides with core system routes."""
    return (slug or "").lower().strip() in RESERVED_SLUGS


def normalize_tag(raw_tag: str) -> str:
    """Normalize a tag string: strip leading '#', collapse whitespace, lowercase, max 64 chars."""
    if not raw_tag:
        return ""
    cleaned = sanitize_plain_text(raw_tag).lstrip("#").strip()
    cleaned = re.sub(r"\s+", " ", cleaned).lower()
    return cleaned[:64]


def parse_tags_input(raw_tags) -> list[str]:
    """Parse comma/newline-separated string or list of tags into deduplicated normalized tags (<= 20)."""
    if raw_tags is None or raw_tags == "":
        return []
    if isinstance(raw_tags, str):
        items = re.split(r"[\r\n,]+", raw_tags)
    elif isinstance(raw_tags, (list, tuple)):
        items = list(raw_tags)
    else:
        raise ValueError("Tags must be a comma-separated string or JSON list.")

    normalized = []
    seen = set()
    for item in items:
        tag = normalize_tag(str(item))
        if tag and tag not in seen:
            seen.add(tag)
            normalized.append(tag)

    if len(normalized) > MAX_PROJECT_TAGS:
        raise ValueError(f"Maximum of {MAX_PROJECT_TAGS} tags allowed per activity.")
    return normalized


def _parse_iso_date(date_str):
    if date_str is None:
        return None
    text_val = str(date_str).strip()
    if not text_val:
        return None
    try:
        return datetime.strptime(text_val, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _parse_name_list(raw_val, split_lines=False):
    if raw_val is None:
        return []
    if isinstance(raw_val, list):
        items = [str(x).strip() for x in raw_val]
    elif isinstance(raw_val, str):
        pattern = r"[\r\n,]+" if split_lines else r","
        items = [x.strip() for x in re.split(pattern, raw_val)]
    else:
        return []

    deduped = []
    for item in items:
        cleaned = item.replace("_", " ").strip() if split_lines else item.strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped


def _parse_results_payload(data):
    """Parse either form-encoded results_* fields or API JSON results dict with XSS sanitization."""
    has_form_results = any(
        k in data
        for k in (
            "results_summary",
            "results_notes",
            "results_winners",
            "results_articles_created",
            "results_articles_improved",
            "results_files_uploaded",
        )
    )
    if has_form_results:
        summary = sanitize_plain_text(data.get("results_summary", ""))[:MAX_TRANSLATED_RESULT_LEN]
        notes = sanitize_plain_text(data.get("results_notes", ""))[:MAX_TRANSLATED_RESULT_LEN]
        winners_raw = data.get("results_winners", "")
        winners = [sanitize_plain_text(w) for w in _parse_name_list(winners_raw, split_lines=True)]
        winners = [w for w in winners if w]

        def _safe_int(key):
            try:
                return max(0, int(data.get(key) or 0))
            except (ValueError, TypeError):
                return 0

        articles_created = _safe_int("results_articles_created")
        articles_improved = _safe_int("results_articles_improved")
        files_uploaded = _safe_int("results_files_uploaded")

        if not any((summary, winners, articles_created, articles_improved, files_uploaded, notes)):
            return None
        return {
            "summary": summary,
            "winners": winners,
            "metrics": {
                "articles_created": articles_created,
                "articles_improved": articles_improved,
                "files_uploaded": files_uploaded,
            },
            "notes": notes,
        }

    raw_results = data.get("results")
    if not isinstance(raw_results, dict):
        return None

    sanitized_results = dict(raw_results)
    if "summary" in sanitized_results:
        sanitized_results["summary"] = sanitize_plain_text(sanitized_results.get("summary"))[:MAX_TRANSLATED_RESULT_LEN]
    if "notes" in sanitized_results:
        sanitized_results["notes"] = sanitize_plain_text(sanitized_results.get("notes"))[:MAX_TRANSLATED_RESULT_LEN]
    if isinstance(sanitized_results.get("winners"), list):
        sanitized_results["winners"] = [
            sanitize_plain_text(w) for w in sanitized_results["winners"] if sanitize_plain_text(w)
        ]
    return sanitized_results


def parse_and_validate_project_payload(
    data,
    *,
    existing_project=None,
    require_dates=True,
    date_calc_when_not_canceled=False,
    partial=False,
) -> dict:
    """
    Shared payload parser, validator, and sanitizer for Project creation/editing
    across web_bp forms and api_bp JSON/form endpoints.
    Raises ValueError with an explanatory message on validation errors.
    """
    parsed = {}

    # 1. Title
    if not partial or "title" in data:
        clean_title = sanitize_plain_text(data.get("title"))
        if not clean_title:
            raise ValueError("Activity title is required.")
        if len(clean_title) > MAX_TRANSLATED_TITLE_LEN:
            raise ValueError("Activity title must not exceed 255 characters.")
        parsed["title"] = clean_title

    # 2. Primary language & translations
    if not partial or "primary_lang" in data:
        raw_primary = data.get("primary_lang") or (existing_project.primary_lang if existing_project else "ar")
        parsed["primary_lang"] = validate_lang_code(raw_primary)

    active_primary_lang = parsed.get(
        "primary_lang",
        existing_project.primary_lang if existing_project else "ar",
    )

    if "translations" in data or "translations_json" in data or not partial:
        raw_tr = None
        if "translations_json" in data:
            tr_str = (data.get("translations_json") or "").strip()
            if tr_str:
                try:
                    raw_tr = json.loads(tr_str)
                except (ValueError, TypeError) as exc:
                    raise ValueError("Invalid JSON format in translations payload.") from exc
        elif "translations" in data:
            raw_tr = data.get("translations")
        parsed["translations"] = sanitize_translations_dict(raw_tr, primary_lang=active_primary_lang)
    elif partial and "primary_lang" in parsed and existing_project and existing_project.translations:
        parsed["translations"] = sanitize_translations_dict(
            existing_project.translations,
            primary_lang=active_primary_lang,
        )

    # 3. Description
    if not partial or "description" in data:
        parsed["description"] = sanitize_rich_html(data.get("description", ""))[:MAX_TRANSLATED_DESC_LEN]

    # 4. Project Type
    if not partial or "project_type" in data or "custom_project_type" in data:
        fallback_type = existing_project.project_type if existing_project else "Workshop"
        raw_type = sanitize_plain_text(data.get("project_type") or fallback_type)
        custom_type = sanitize_plain_text(data.get("custom_project_type", ""))[:64]
        if raw_type == "Other" and custom_type:
            parsed["project_type"] = custom_type
        elif raw_type == "Other":
            parsed["project_type"] = "Other"
        else:
            parsed["project_type"] = (raw_type or fallback_type)[:64]

    # 5. Target Wiki
    if not partial or "target_wiki" in data:
        fallback_wiki = existing_project.target_wiki if existing_project else "arwiki"
        raw_wiki = data.get("target_wiki")
        if raw_wiki is None or not str(raw_wiki).strip():
            raw_wiki = fallback_wiki
        target_wiki, _ = normalize_wiki_target(str(raw_wiki).strip())
        parsed["target_wiki"] = target_wiki

    # 6. Optional Wiki Link
    if not partial or "wiki_link" in data:
        parsed["wiki_link"] = validate_activity_wiki_url(data.get("wiki_link"))

    # 7. Campaign
    if not partial or "campaign" in data:
        campaign_clean = sanitize_plain_text(data.get("campaign"))[:128]
        parsed["campaign"] = campaign_clean or None

    # 8. Tags (omit on partial update when 'tags' is absent so existing tags stay untouched)
    if not partial or "tags" in data:
        parsed["tags"] = parse_tags_input(data.get("tags"))

    # 9. Dates
    eff_start = existing_project.start_date if existing_project else None
    eff_end = existing_project.end_date if existing_project else None

    if not partial or "start_date" in data:
        eff_start = _parse_iso_date(data.get("start_date"))
        parsed["start_date"] = eff_start
    if not partial or "end_date" in data:
        eff_end = _parse_iso_date(data.get("end_date"))
        parsed["end_date"] = eff_end

    if require_dates and (not eff_start or not eff_end):
        raise ValueError("تاريخ بدء النشاط وتاريخ انتهائه إلزاميان لتسجيل النشاط.")
    if eff_start and eff_end and eff_end < eff_start:
        raise ValueError("تاريخ انتهاء النشاط لا يمكن أن يكون قبل تاريخ البدء.")

    # 10. Status
    curr_status = existing_project.status if existing_project else None
    if date_calc_when_not_canceled:
        raw_status = str(data.get("status") or "").strip()
        if raw_status.lower() in ("canceled", "cancelled", "ملغي", "ملغاة"):
            parsed["status"] = "Canceled"
        else:
            parsed["status"] = determine_project_status(eff_start, eff_end, "auto")
    else:
        if "status" in data:
            parsed["status"] = determine_project_status(
                eff_start, eff_end, data.get("status"), current_status=curr_status
            )
        elif not partial or "start_date" in data or "end_date" in data:
            parsed["status"] = determine_project_status(
                eff_start, eff_end, "auto", current_status=curr_status
            )

    # 11. Contest, Organizers, Jury, Participants, Results
    if not partial or "is_contest" in data:
        raw_contest = data.get("is_contest")
        if isinstance(raw_contest, str):
            parsed["is_contest"] = raw_contest.strip().lower() in ("1", "true", "yes", "on")
        else:
            parsed["is_contest"] = bool(raw_contest)

    eff_contest = parsed.get(
        "is_contest",
        existing_project.is_contest if existing_project else False,
    )

    if not partial or "co_organizers" in data:
        parsed["co_organizers"] = _parse_name_list(data.get("co_organizers"))
    if not partial or "jury_members" in data or "is_contest" in data:
        if "jury_members" in data:
            parsed["jury_members"] = _parse_name_list(data.get("jury_members")) if eff_contest else []
        elif not partial:
            parsed["jury_members"] = []
        elif not eff_contest:
            parsed["jury_members"] = []

    if not partial or "participants" in data:
        parsed["participants"] = _parse_name_list(data.get("participants"), split_lines=True)

    has_results_input = (
        not partial
        or "results" in data
        or any(
            k in data
            for k in (
                "results_summary",
                "results_notes",
                "results_winners",
                "results_articles_created",
                "results_articles_improved",
                "results_files_uploaded",
            )
        )
    )
    if has_results_input:
        parsed["results"] = _parse_results_payload(data)

    return parsed
