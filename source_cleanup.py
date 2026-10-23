"""Remove exams whose source post has been deleted at the source.

A post missing from the recent WordPress/RSS listing is only a candidate:
the listing covers a limited window, so every candidate URL is checked and
removed only when the source itself returns 404/410 (or a clear not-found page).
"""

import argparse
import json
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import requests

from database import get_db, init_db

IST = timezone(timedelta(hours=5, minutes=30))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

SOURCE_DOMAINS = {
    "studygovthelp": "studygovthelp.in",
    "rojgarresult": "rojgarresult.com",
    "freejobalert": "freejobalert.com",
}
WP_ENDPOINTS = {
    "studygovthelp": ("https://studygovthelp.in/wp-json/wp/v2/posts", 10),
    "rojgarresult": ("https://rojgarresult.com/wp-json/wp/v2/posts", 5),
}
FJA_RSS = "https://www.freejobalert.com/feed/"

MIN_SEEN_URLS = 5
DEFAULT_MAX_CHECKS = 150
CHECK_WORKERS = 6
CHECK_COOLDOWN_HOURS = 6
REMOVED_MARKERS = (
    "404 not found", "404 - not found", "page not found", "post not found",
    "page you are looking for", "page you're looking for", "page does not exist",
    "page doesn't exist", "content not found", "no longer available", "nothing found",
)


def _norm_url(url):
    if not url:
        return ""
    try:
        parts = urlsplit(str(url).strip())
    except ValueError:
        return str(url).strip().lower()
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/+", "/", parts.path or "/").rstrip("/") or "/"
    return f"{host}{path}".lower()


def _page_says_removed(html):
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    heading = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    head = " ".join(match.group(1) for match in (title, heading) if match)
    head = re.sub(r"<[^>]+>", " ", head)
    head = re.sub(r"\s+", " ", head).lower()
    return any(marker in head for marker in REMOVED_MARKERS)


def _check_url(url):
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=(6, 12),
            allow_redirects=True,
        )
        status = response.status_code
        final_url = response.url
        body = response.text[:250000] if status == 200 else ""
        response.close()
    except Exception:
        return "unverified", 0
    if status in (404, 410):
        return "removed", status
    if status != 200:
        return "unverified", status

    # WordPress often redirects deleted permalinks to the homepage with a 200.
    original_host = urlsplit(url).netloc.lower().removeprefix("www.")
    final_host = urlsplit(final_url).netloc.lower().removeprefix("www.")
    original_path = (urlsplit(url).path or "/").rstrip("/") or "/"
    final_path = (urlsplit(final_url).path or "/").rstrip("/") or "/"
    if original_host == final_host and original_path != "/" and final_path == "/":
        return "removed", status
    if _page_says_removed(body):
        return "removed", status
    return "kept", status


def collect_seen_urls(source_key, days=90):
    """Fetch the current source listing (no detail pages, no DB writes)."""
    if source_key == "freejobalert":
        response = requests.get(
            FJA_RSS, headers={"User-Agent": USER_AGENT}, timeout=(10, 30)
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
        return {
            link.strip()
            for item in root.findall(".//item")
            for link in [item.findtext("link") or ""]
            if link.strip()
        }

    api_url, max_pages = WP_ENDPOINTS[source_key]
    after = (datetime.now() - timedelta(days=max(1, days))).strftime("%Y-%m-%dT%H:%M:%S")
    seen = set()
    for page in range(1, max_pages + 1):
        response = requests.get(
            api_url,
            params={"page": page, "per_page": 100, "after": after},
            headers={"User-Agent": USER_AGENT},
            timeout=(10, 40),
        )
        if response.status_code == 400:
            break
        response.raise_for_status()
        posts = response.json()
        if not isinstance(posts, list) or not posts:
            break
        for post in posts:
            link = (post.get("link") or "").strip()
            if link:
                seen.add(link)
        total_pages = int(response.headers.get("X-WP-TotalPages") or max_pages)
        if page >= total_pages:
            break
    return seen


def prune_removed_exams(source_key, seen_urls, max_checks=DEFAULT_MAX_CHECKS, dry_run=False):
    domain = SOURCE_DOMAINS.get(source_key)
    if not domain:
        return {"status": "skipped", "reason": f"unknown source: {source_key}"}

    seen = {_norm_url(url) for url in (seen_urls or ()) if url}
    if len(seen) < MIN_SEEN_URLS:
        return {
            "status": "skipped",
            "reason": f"source listing returned only {len(seen)} URLs",
            "seen": len(seen),
        }

    conn = get_db()
    try:
        rows = [
            dict(row) for row in conn.execute(
                "SELECT id, title, source_url, updated_at, "
                "COALESCE(source_checked_at, '') AS checked_at "
                "FROM exams WHERE source_url LIKE ?",
                (f"%{domain}%",),
            ).fetchall()
        ]
    finally:
        conn.close()

    unseen = [row for row in rows if _norm_url(row["source_url"]) not in seen]
    if not unseen:
        return {
            "status": "success", "source": source_key, "seen": len(seen),
            "source_records": len(rows), "unseen": 0, "checked": 0,
            "deleted": 0, "kept": 0, "unverified": 0, "remaining": 0,
            "dry_run": dry_run, "deleted_titles": [],
        }

    # A listing that suddenly covers less than a third of our records is more
    # likely a partial response than a real mass deletion; leave data untouched.
    if len(seen) < 50 and len(unseen) > len(rows) * 0.7:
        return {
            "status": "skipped",
            "reason": "source listing looks incomplete",
            "seen": len(seen), "source_records": len(rows), "unseen": len(unseen),
        }

    cutoff = (datetime.now(IST) - timedelta(hours=CHECK_COOLDOWN_HOURS)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    candidates = [row for row in unseen if not row["checked_at"] or row["checked_at"] < cutoff]
    candidates.sort(key=lambda row: row["updated_at"] or "", reverse=True)
    candidates.sort(key=lambda row: row["checked_at"] or "")
    remaining = max(0, len(candidates) - max(0, int(max_checks)))
    candidates = candidates[: max(0, int(max_checks))]

    checked_rows = []
    with ThreadPoolExecutor(max_workers=CHECK_WORKERS) as pool:
        futures = {pool.submit(_check_url, row["source_url"]): row for row in candidates}
        for future in as_completed(futures):
            outcome, http_status = future.result()
            checked_rows.append((futures[future], outcome, http_status))

    removed = sum(1 for _, outcome, _ in checked_rows if outcome == "removed")
    kept = sum(1 for _, outcome, _ in checked_rows if outcome == "kept")
    unverified = sum(1 for _, outcome, _ in checked_rows if outcome == "unverified")
    deleted_titles = [row["title"] for row, outcome, _ in checked_rows if outcome == "removed"]

    if removed >= 10 and removed > len(checked_rows) * 0.5:
        return {
            "status": "skipped",
            "reason": "too many 404s at once; possible site-wide URL change",
            "seen": len(seen), "source_records": len(rows), "unseen": len(unseen),
            "checked": len(checked_rows), "would_delete": removed,
            "kept": kept, "unverified": unverified, "dry_run": dry_run,
            "deleted_titles": deleted_titles[:20],
        }

    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    if not dry_run and checked_rows:
        conn = get_db()
        try:
            for row, outcome, _ in checked_rows:
                if outcome == "removed":
                    conn.execute("DELETE FROM faqs WHERE exam_id = ?", (row["id"],))
                    conn.execute("DELETE FROM exams WHERE id = ?", (row["id"],))
                else:
                    conn.execute(
                        "UPDATE exams SET source_checked_at = ? WHERE id = ?",
                        (now, row["id"]),
                    )
            conn.commit()
        finally:
            conn.close()

    return {
        "status": "success",
        "source": source_key,
        "seen": len(seen),
        "source_records": len(rows),
        "unseen": len(unseen),
        "checked": len(checked_rows),
        "deleted": 0 if dry_run else removed,
        "would_delete": removed if dry_run else 0,
        "kept": kept,
        "unverified": unverified,
        "remaining": remaining,
        "dry_run": dry_run,
        "deleted_titles": deleted_titles[:20],
    }


def main():
    parser = argparse.ArgumentParser(description="Remove exams deleted at their source")
    parser.add_argument(
        "--source",
        choices=["all", "studygovthelp", "rojgarresult", "freejobalert"],
        default="all",
    )
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--max-checks", type=int, default=DEFAULT_MAX_CHECKS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    init_db()
    sources = list(SOURCE_DOMAINS) if args.source == "all" else [args.source]
    summary = {}
    for source in sources:
        try:
            seen = collect_seen_urls(source, days=args.days)
            summary[source] = prune_removed_exams(
                source, seen, max_checks=args.max_checks, dry_run=args.dry_run
            )
        except Exception as exc:
            summary[source] = {"status": "error", "message": str(exc)}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
