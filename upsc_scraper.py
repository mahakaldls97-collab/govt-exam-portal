"""UPSC official notices, read from the upsc.gov.in "What's New" listing.

The commission's own site is the only place that publishes its recruitment
notices, interview schedules and result announcements before aggregators pick
them up. Two rules shape this scraper:

* Only facts that are actually on the page are stored. When the listing title
  carries a post count or a department, those are used; nothing else is
  guessed, so dates stay blank until the notice page itself can be read.
* Some networks can reach the upsc.gov.in homepage but not its notice pages —
  every deep URL answers with the homepage shell. Those pages are detected by
  their final URL and treated as "listing only" instead of parsed as content.
"""

import re
import time
from urllib.parse import quote, unquote, urlparse

from bs4 import BeautifulSoup

from database import init_db
from data_quality import clean_text, clean_title
from extra_sources import (
    SOURCE_LABELS,
    ExamIndex,
    _finish,
    _get,
    _process_record,
    _stats,
)

SOURCE = "upsc"
SOURCE_LABELS[SOURCE] = "UPSC Official"

HOME_URL = "https://upsc.gov.in/en"
SITE_ROOT = "https://upsc.gov.in/"
LISTING_PATH = "whats-new"
IGNORED_TEXTS = {"view all", "view all »", "read more", "more"}

_VACANCY_IN_TITLE = re.compile(
    r"\b(\d{1,3}(?:,\d{3})+|\d{1,4})\s*(?:posts?|vacanc\w*|seats?)\b", re.I
)
_POST_THEN_PLACE = re.compile(
    r"\bposts?\s+of\s+(?P<post>.+?)(?:\s+(?:in|at|for|of)\s+(?P<place>.+?))?\s*$",
    re.I,
)
_NOTICE_KIND = re.compile(r"^(?P<kind>[A-Za-z][A-Za-z ()&\-]{2,48}?):\s*\S")

# UPSC labels an announcement its own way; the portal files announcements by
# what a candidate can do with them. The original wording survives in the
# "Notice Type" row, so nothing is lost by renaming for display.
_KIND_TITLES = {
    "notice": "Recruitment Notice: {rest}",
    "written result": "Written Result: {rest}",
    "final result": "Final Result: {rest}",
    "result": "Result: {rest}",
    "marks of recommended candidates": "Result: Marks of Recommended Candidates - {rest}",
    "interview schedule": "Admit Card: Interview Schedule - {rest}",
    "interview details": "Admit Card: Interview Details - {rest}",
    "examination time table": "Exam Date: {rest}",
    "exam time table": "Exam Date: {rest}",
}


def _presentation_title(raw_title):
    """Rewrite an UPSC prefix into the wording the portal categorises by."""
    match = _NOTICE_KIND.match(raw_title)
    if not match:
        return f"UPSC {raw_title}"
    kind = match.group("kind").strip().lower()
    rest = raw_title[match.end("kind"):].lstrip(":").strip()
    template = _KIND_TITLES.get(kind)
    if not template or not rest:
        return f"UPSC {raw_title}"
    return f"UPSC {template.format(rest=rest)}"


def _absolute(href):
    """Build a fetchable UPSC URL even when the href holds raw spaces."""
    href = (href or "").strip()
    if not href:
        return ""
    if href.startswith("http"):
        return href
    path = unquote(href if href.startswith("/") else f"/{href}")
    return SITE_ROOT.rstrip("/") + quote(path, safe="/-._~()&,'=%")


def _listing_items(html_text):
    """Return (title, url) pairs from the What's New block, in page order."""
    soup = BeautifulSoup(html_text or "", "html.parser")
    items = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        if LISTING_PATH not in anchor["href"]:
            continue
        title = clean_text(anchor.get_text(" ", strip=True), 220)
        if not title or title.lower().strip(" »>") in IGNORED_TEXTS:
            continue
        url = _absolute(anchor["href"])
        if not url or url.lower() in seen:
            continue
        seen.add(url.lower())
        items.append((title, url))
    return items


def _is_homepage_shell(response, requested_url):
    """True when UPSC answered with its homepage instead of the notice page."""
    try:
        final_path = urlparse(response.url or requested_url).path
    except Exception:
        return True
    requested_path = urlparse(requested_url).path
    if final_path.rstrip("/") == requested_path.rstrip("/"):
        return False
    return final_path.rstrip("/") in ("", "/", "/en", "/index.php", "/hi")


def _listing_html(raw_title, notice_url):
    """A small page holding only what the listing title states."""
    body = clean_text(raw_title, 220)
    rows = [
        "<tr><td>Organization</td><td>Union Public Service Commission (UPSC)</td></tr>"
    ]
    vacancy = _VACANCY_IN_TITLE.search(body)
    if vacancy:
        rows.append(
            f"<tr><td>Total Vacancy</td><td>{int(vacancy.group(1).replace(',', '')):,} Posts</td></tr>"
        )
    post_match = _POST_THEN_PLACE.search(body)
    if post_match and post_match.group("post"):
        rows.append(
            f"<tr><td>Post Name</td><td>{clean_text(post_match.group('post'), 160)}</td></tr>"
        )
    if post_match and post_match.group("place"):
        rows.append(
            f"<tr><td>Job Location</td><td>{clean_text(post_match.group('place'), 160)}</td></tr>"
        )
    kind = _NOTICE_KIND.match(body)
    if kind:
        rows.append(
            f"<tr><td>Notice Type</td><td>{clean_text(kind.group('kind'), 60)}</td></tr>"
        )
    rows.append(f"<tr><td>Official Website</td><td>{SITE_ROOT}</td></tr>")
    return (
        f"<article><h1>{body}</h1>"
        f"<p>{body}</p>"
        f"<table>{''.join(rows)}</table>"
        f'<p><a href="{notice_url}">Official notice on upsc.gov.in</a></p></article>'
    )


def _detail_html(url, stats):
    """Fetch a notice page; return its HTML, or "" when the site withholds it."""
    try:
        response = _get(url)
        response.raise_for_status()
    except Exception as exc:
        stats["errors"] += 1
        print(f"  [!] UPSC detail failed: {exc}")
        return ""
    if _is_homepage_shell(response, url):
        return ""
    return response.text or ""


def sync_from_upsc(limit=25, fetch_details=True):
    """Add UPSC's own announcements; the listing page carries no dates."""
    init_db()
    stats = _stats()
    index = ExamIndex()
    limit = max(0, int(limit))
    detail_fetches = 0

    try:
        response = _get(HOME_URL)
        response.raise_for_status()
    except Exception as exc:
        stats["errors"] += 1
        print(f"[UPSC] Listing failed: {exc}")
        return _finish(SOURCE, stats)

    items = _listing_items(response.text)
    stats["items_found"] = len(items)
    if not items:
        stats["errors"] += 1
        print("[UPSC] No notice links found on the listing page.")
        return _finish(SOURCE, stats)

    shell_only = 0
    listing_fallback = 0
    for raw_title, url in items:
        stats["seen_urls"].add(url)
        title = clean_title(_presentation_title(raw_title))
        html_text = ""
        attempted = detail_fetches < limit
        if attempted:
            detail_fetches += 1
            html_text = _detail_html(url, stats) if fetch_details else ""
            time.sleep(0.6)
        if not html_text:
            if attempted:
                shell_only += 1
            else:
                listing_fallback += 1
            html_text = _listing_html(raw_title, url)
        _process_record(index, title, html_text, url, "", SOURCE, stats)

    if shell_only:
        print(
            f"[UPSC] {shell_only} notice page(s) not readable from this network — "
            "stored with the facts stated in the listing title."
        )
    if listing_fallback:
        print(f"[UPSC] {listing_fallback} notice page(s) left for the next run (detail limit).")
    return _finish(SOURCE, stats)
