"""
Wikimedia project normalization, validation, and URL generation.
Ensures strict security against SSRF, open-redirects, and broken hostnames.
"""
import re
from urllib.parse import urlparse

# Whitelisted Wikimedia root domains (must strictly end with one of these)
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
    "wikifunctions.org"
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


def is_allowed_wikimedia_host(hostname: str) -> bool:
    """Check if hostname belongs strictly to an official Wikimedia domain."""
    if not hostname:
        return False
    hostname = hostname.lower().strip()
    return any(hostname == d or hostname.endswith("." + d) for d in ALLOWED_WIKIMEDIA_DOMAINS)


def normalize_wiki_target(raw_input: str, default: str = "arwiki") -> tuple[str, str]:
    """
    Validates and transforms user-supplied wiki identifier into (canonical_code, canonical_url).
    Examples:
      'arwiki' -> ('arwiki', 'https://ar.wikipedia.org')
      'commons' -> ('commonswiki', 'https://commons.wikimedia.org')
      'wikidata' -> ('wikidatawiki', 'https://www.wikidata.org')
      'ar.wikipedia.org' -> ('arwiki', 'https://ar.wikipedia.org')
    Raises:
      ValueError if the input is untrusted, invalid, or non-Wikimedia.
    """
    if not raw_input:
        raw_input = default

    val = str(raw_input).strip()
    # Strip protocol and trailing slashes if user pasted full URL
    val_clean = re.sub(r"^https?://", "", val).strip().rstrip("/")
    lower_val = val_clean.lower()

    # 1. Check special alias dictionary
    if lower_val in SPECIAL_WIKI_MAP:
        code, domain = SPECIAL_WIKI_MAP[lower_val]
        return code, f"https://{domain}"

    # 2. Check full domain format (e.g. ar.wikipedia.org)
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

    # 3. Check MediaWiki dbname format (e.g. arwiki, arywiki, enwiki, frwiki, arwikisource)
    m = DBNAME_REGEX.match(lower_val)
    if m:
        lang, project_family = m.groups()
        if project_family == "wiki":
            domain = f"{lang}.wikipedia.org"
        else:
            domain = f"{lang}.{project_family}.org"
        return lower_val, f"https://{domain}"

    # 4. Strict security validation: reject anything that doesn't match
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
    "Other": "نشاط مخصص"
}

STATUS_ARABIC = {
    "In Progress": "جارية",
    "in progress": "جارية",
    "Planned": "مخططة",
    "planned": "مخططة",
    "Completed": "مكتملة",
    "completed": "مكتملة"
}


def translate_activity_type(val: str) -> str:
    if not val:
        return "نشاط مجتمعي"
    return ACTIVITY_TYPE_ARABIC.get(val, val)


def translate_status(val: str) -> str:
    if not val:
        return "جارية"
    return STATUS_ARABIC.get(val, val)


def determine_project_status(start_date=None, end_date=None, requested_status=None) -> str:
    """
    Determine the project status based on starting and ending dates:
    - 'Completed' (finished) if the ending date is in the past (end_date < today)
    - 'Planned' (in the future) if the starting date is in the future (start_date > today)
    - 'In Progress' (running) if active: start_date <= today and (not end_date or end_date >= today)
    If requested_status is explicitly given (not 'auto'), it is honored as a manual override.
    """
    from datetime import date, datetime
    today = date.today()

    # Parse date if string
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

    # If explicit manual override is specified (not 'auto' and not empty)
    if requested_status and requested_status not in ("auto", "Auto", ""):
        low = str(requested_status).strip().lower()
        if low in ("completed", "مكتملة", "منتهية", "finished"):
            return "Completed"
        if low in ("planned", "مخططة", "قادمة", "in the future"):
            return "Planned"
        if low in ("in progress", "جارية", "قيد التنفيذ", "running"):
            return "In Progress"
        return requested_status

    # If status is 'auto' (or omitted), determine status dynamically based on dates:
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

