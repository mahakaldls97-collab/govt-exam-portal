"""State PSC notice boards read from the commissions' own websites.

Two commissions publish every notice on their homepage with the full wording in
the link itself: UPPSC (Uttar Pradesh) and MPPSC (Madhya Pradesh). Aggregators
carry only the big advertisements, so district slips, document verification
notices, answer keys and interview dates from these boards never reach the
portal. This module adds exactly what the notice board states.

Nothing is inferred: a notice without a date on the page is stored without a
date, and office housekeeping (tenders, equipment, bids) is dropped.
"""

import re
from datetime import date, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from database import init_db
from data_quality import clean_text, clean_title, parse_date
from extra_sources import (
    SOURCE_LABELS,
    ExamIndex,
    _finish,
    _get,
    _process_record,
    _stats,
)

SITES = {
    "uppsc": {
        "label": "UPPSC",
        "url": "https://uppsc.up.nic.in/",
        "board": "Uttar Pradesh Public Service Commission (UPPSC)",
        "state": "Uttar Pradesh",
        # Its Open_PDF_DB.aspx links only serve the PDF once the board has set
        # its session cookie, so a visitor arriving from elsewhere gets the
        # homepage. Link the board itself instead of a dead-looking token URL.
        "direct_pdf": False,
    },
    "mppsc": {
        "label": "MPPSC",
        "board": "Madhya Pradesh Public Service Commission (MPPSC)",
        "state": "Madhya Pradesh",
        "url": "https://www.mppsc.mp.gov.in/",
        "direct_pdf": True,
    },
}

# Hindi titles on these boards embed zero-width joiners inside words, which
# silently breaks substring matching unless they are stripped first.
_INVISIBLE = re.compile(r"[\u200b-\u200f\u202c\ufeff]")

# Ordered: the first matching phrase decides how the notice is filed.
KIND_PHRASES = (
    ("Answer Key", ("answer key", "उत्तर कुंजी", "आंसर की")),
    ("Result", ("result", "परिणाम", "उत्तीर्ण", "merit list", "selected candidates")),
    ("Admit Card", (
        "admit card", "call letter", "district information slip", "district slip",
        "e-admit", "पत्र", "साक्षात्कार", "interview", "document verification",
        "अभिलेख", "preliminary", "viva",
    )),
    ("Exam Date", ("exam date", "examination date", "time table", "schedule", "date sheet")),
    ("Recruitment", (
        "advertisement", "vigyapti", "विज्ञप्ति", "recruitment", "भर्ती", "पद",
        "online form", "आवेदन", "notification", "corrigendum", "advt", "सूचना",
    )),
)

# Office housekeeping and administrative orders, not exam events.
OFF_TOPIC = (
    "tender", "bid", "photocopier", "toner", "stationery", "shutter", "kiosk",
    "carpet", "furniture", "vehicle", "licensing", "gem", "निविदा", "निरस्त",
    "transfer", "posting of", "vacation", "holiday",
)

# The commission's own wording, kept for the "Notice Type" fact.
STAGE_PHRASES = (
    ("Corrigendum", ("corrigendum", "सংশोधन")),
    ("Document Verification", ("document verification", "अभिलेख")),
    ("District Information Slip", ("district information slip", "district slip")),
    ("Interview", ("interview", "साक्षात्कार")),
    ("Answer Key", ("answer key", "उत्तर कुंजी", "आंसर की")),
    ("Result", ("result", "परिणाम")),
    ("Admit Card", ("admit card", "call letter", "e-admit")),
    ("Recruitment Advertisement", ("advertisement", "recruitment", "भर्ती", "विज्ञप्ति")),
)

_DATE_IN_TITLE = re.compile(
    r"[,:\s-]*(?:दिनांक|dated|दिवसांक|dt\.?|date)\s*[:\-]?\s*(\d{1,2}[/.-]\d{1,2}[/.-]\d{4})",
    re.I,
)
_DATE_IN_FILENAME = re.compile(r"dated[_-]?(\d{1,2}[_-]\d{1,2}[_-]\d{4})", re.I)
_ADVT_NO = re.compile(
    r"(?:advt|advertisement|क्रमांक|क्र\.?)[.\s]{0,2}"
    r"(?:no|number|संख्या)?[.\s:/\-]{0,3}"
    r"([A-Z][A-Z0-9]*(?:[-/][A-Z0-9]+){1,3}[-/]\d{4}|\d{1,4}/\d{1,4})",
    re.I,
)
_LEAD_NOISE = re.compile(
    r"^(?:notice|सूचना|विज्ञप्ति|result|परिणाम|advertisement|corrected|important|of)\s*"
    r"(?:regarding|regd\.?|of|for|में|के\s*संदर्भ\s*में|संबंधी|सन्दर्भ)?\s*[:\-\s]*",
    re.I,
)
# "ADVT. NO. D-6/E-1/2025, Food Safety…" reads better with the number in its own
# field, and the number survives in the advt_no column and the table.
_ADVT_LEAD = re.compile(
    r"^advt\.?\s*(?:no|number)?\.?\s*[:\-]?\s*"
    r"[A-Z][A-Z0-9]*(?:[-/][A-Z0-9]+){1,3}[-/]\d{4}\s*[,:\-\s]*",
    re.I,
)
_KEEP_UPPER = {
    "advt", "no", "nos", "uppsc", "mppsc", "psc", "sc", "st", "obc", "ews", "pwd",
    "up", "mp", "cbi", "ias", "ifs", "pcs", "te", "sts", "mts", "gd", "si", "ao",
    "po", "so", "ito", "pto", "rto", "deo", "ae", "je",
}


def _plain(text):
    """Lowercase for matching, with the invisible marks these boards insert."""
    return _INVISIBLE.sub("", text or "").lower()


def _readable_case(text):
    """Calm an ALL-CAPS notice title without breaking post codes and acronyms."""
    words = []
    for word in (text or "").split():
        core = word.strip("().,:;/-")
        if not core or any(c.isdigit() for c in core):
            words.append(word)
        elif "." in core or core.lower() in _KEEP_UPPER:
            words.append(word)
        elif word.isupper() and len(word) > 1:
            words.append(word.capitalize())
        else:
            words.append(word)
    return " ".join(words)


def _classify(raw_title):
    text = _plain(raw_title)
    if any(word in text for word in OFF_TOPIC):
        return None
    for kind, phrases in KIND_PHRASES:
        if any(phrase in text for phrase in phrases):
            return kind
    return None


def _stage(raw_title, kind):
    text = _plain(raw_title)
    for label, phrases in STAGE_PHRASES:
        if any(phrase in text for phrase in phrases):
            return label
    return kind


def _notice_date(raw_title, url):
    for pattern, source in ((_DATE_IN_TITLE, _plain(raw_title)), (_DATE_IN_FILENAME, url.lower())):
        match = pattern.search(source)
        if not match:
            continue
        parsed = parse_date(match.group(1).replace("_", "/").replace("-", "/"))
        if parsed:
            return parsed.isoformat()
    return ""


def _display_title(raw_title):
    text = _INVISIBLE.sub("", re.sub(r"\s+", " ", raw_title or "")).strip(" .·-")
    text = _DATE_IN_TITLE.sub("", text).strip(" ,:-.")
    text = _LEAD_NOISE.sub("", text)
    text = _ADVT_LEAD.sub("", text)
    text = re.sub(r"\s*[/|]\s*$", "", text)
    return clean_title(_readable_case(text))


def _advt_year(advt_no):
    """The year the commission gave the advertisement, from its own number."""
    matches = re.findall(r"(\d{4})", advt_no or "")
    return int(matches[-1]) if matches else 0


def _uppsc_items(html_text, site_url):
    soup = BeautifulSoup(html_text or "", "html.parser")
    items = []
    for anchor in soup.find_all("a", href=True):
        if "Open_PDF_DB" not in (anchor.get("href") or ""):
            continue
        title = clean_text(anchor.get("title") or anchor.get_text(" ", strip=True), 240)
        if title:
            items.append((title, urljoin(site_url, anchor["href"])))
    return items


def _mppsc_items(html_text, site_url):
    soup = BeautifulSoup(html_text or "", "html.parser")
    items = []
    for anchor in soup.find_all("a", href=True):
        if not re.search(r"\.pdf(\?|$)", anchor.get("href") or "", re.I):
            continue
        title = clean_text(anchor.get("title") or anchor.get_text(" ", strip=True), 240)
        if title:
            items.append((title, urljoin(site_url, anchor["href"])))
    return items


EXTRACTORS = {"uppsc": _uppsc_items, "mppsc": _mppsc_items}

# The wording of this anchor decides which button the portal files the PDF
# under, so each kind carries the phrase the link classifier looks for.
_LINK_LABEL = {
    "Recruitment": "Advertisement",
    "Admit Card": "Admit Card",
    "Answer Key": "Answer Key",
    "Result": "Result",
    "Exam Date": "Exam Date",
}


def _notice_html(site, kind, stage, subject, notice_url, notice_date, advt_no, status=""):
    """A page holding only what the notice board stated about this item."""
    text = clean_text(subject, 240)
    rows = [
        f"<tr><td>Organization</td><td>{site['board']}</td></tr>",
        f"<tr><td>Job Location</td><td>{site['state']}</td></tr>",
        f"<tr><td>Notice Type</td><td>{stage}</td></tr>",
    ]
    if status:
        rows.append(f"<tr><td>Status</td><td>{status}</td></tr>")
    if notice_date:
        rows.append(f"<tr><td>Notification Date</td><td>{notice_date}</td></tr>")
    if advt_no:
        rows.append(f"<tr><td>Advertisement Number</td><td>{clean_text(advt_no, 40)}</td></tr>")
    rows.append(f"<tr><td>Official Website</td><td>{site['url']}</td></tr>")
    if site.get("direct_pdf"):
        label = _LINK_LABEL.get(kind, kind)
        link_html = f'<p><a href="{notice_url}">Download {label} {stage} PDF</a></p>'
    else:
        link_html = f'<p><a href="{site["url"]}">Open {site["label"]} notice board</a></p>'
    return (
        f"<article><h1>{text}</h1><p>{text}</p>"
        f"<table>{''.join(rows)}</table>"
        f"{link_html}</article>"
    )


def sync_from_psc(site_key, days=120, limit=60):
    """Read one commission's homepage notice board into the portal."""
    site = SITES[site_key]
    SOURCE_LABELS[site_key] = site["label"]
    init_db()
    stats = _stats()
    index = ExamIndex()
    oldest = date.today() - timedelta(days=max(1, int(days)))

    try:
        response = _get(site["url"], verify=False)
        response.raise_for_status()
    except Exception as exc:
        stats["errors"] += 1
        print(f"[{site['label']}] Notice board failed: {exc}")
        return _finish(site_key, stats)

    items = EXTRACTORS[site_key](response.text, site["url"])
    stats["items_found"] = len(items)
    if not items:
        stats["errors"] += 1
        print(f"[{site['label']}] No notice links found.")
        return _finish(site_key, stats)

    filed = 0
    off_topic = 0
    too_old = 0
    posted = set()
    for raw_title, url in items:
        stats["seen_urls"].add(url)
        kind = _classify(raw_title)
        if not kind:
            off_topic += 1
            stats["skipped_junk"] += 1
            continue
        notice_date = _notice_date(raw_title, url)
        if notice_date and parse_date(notice_date) and parse_date(notice_date) < oldest:
            too_old += 1
            continue
        if filed >= max(0, int(limit)):
            stats["skipped_limit"] += 1
            continue
        subject = _display_title(raw_title)
        if not subject:
            stats["skipped_junk"] += 1
            continue
        advt = _ADVT_NO.search(_plain(raw_title))
        advt_no = advt.group(1).upper() if advt else ""
        marker = (kind, advt_no.replace(" ", ""), _plain(subject))
        if marker in posted:
            # The board repeats one notice under several anchors; the same
            # advertisement and stage posted twice is the same item.
            stats["skipped_duplicates"] += 1
            continue
        posted.add(marker)
        status = ""
        if kind == "Recruitment" and not notice_date:
            year = _advt_year(advt_no)
            if year and year < date.today().year:
                # These boards print no dates, but an advertisement numbered for
                # an earlier year cannot still be accepting forms.
                status = "Applications Closed"
        filed += 1
        _process_record(
            index,
            clean_title(f"{site['label']} {kind}: {subject}"),
            _notice_html(
                site, kind, _stage(raw_title, kind), subject, url,
                notice_date, advt_no, status,
            ),
            url,
            notice_date,
            site_key,
            stats,
        )

    print(
        f"[{site['label']}] {len(items)} notices on the board, {filed} filed, "
        f"{off_topic} office notices ignored, {too_old} older than {days} days."
    )
    return _finish(site_key, stats)


def sync_from_state_pscs(days=120, limit=60):
    """Run every state commission board configured above."""
    return {key: sync_from_psc(key, days=days, limit=limit) for key in SITES}
