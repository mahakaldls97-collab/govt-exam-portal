"""Exam sync runner.

Run locally or from GitHub Actions:
    python sync_runner.py --days 90

New records are inserted and matching records are updated in place. Old records
are kept unless their source post is confirmed deleted (404/410); those are
removed after the sync. Expired statuses are refreshed afterwards.
"""
import argparse
import json
import sys
from datetime import datetime, timedelta

from database import auto_cleanup_expired_exams, get_db, init_db
from extra_sources import sync_from_freejobalert, sync_from_rojgarresult
from sarkariresult_crawler import sync_from_sarkariresult
from source_cleanup import prune_removed_exams
from studygovthelp_scraper import sync_from_studygovthelp


def _count_exams():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM exams").fetchone()[0]
    conn.close()
    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90, help="fetch posts published in the last N days")
    parser.add_argument("--pages", type=int, default=10, help="WordPress API pages (max 20)")
    parser.add_argument("--per-page", type=int, default=100)
    parser.add_argument("--sarkari-limit", type=int, default=30, help="detail pages to deep-scrape")
    parser.add_argument("--include-sarkari", action="store_true", help="also scrape sarkariresult.com.cm (off by default)")
    parser.add_argument("--skip-sarkari", action="store_true", help="kept for backward compatibility; sarkari is already off by default")
    parser.add_argument("--skip-extra", action="store_true", help="skip RojgarResult and FreeJobAlert")
    parser.add_argument("--extra-days", type=int, default=90, help="lookback window for extra sources")
    parser.add_argument("--rr-pages", type=int, default=5, help="RojgarResult API pages (100 posts each)")
    parser.add_argument("--fja-limit", type=int, default=25, help="FreeJobAlert detail pages per run")
    parser.add_argument("--no-prune", action="store_true", help="keep exams even if their source post is deleted")
    parser.add_argument("--prune-dry-run", action="store_true", help="check deleted source posts without removing")
    parser.add_argument("--prune-limit", type=int, default=150, help="source URLs to re-check per source per run")
    args = parser.parse_args()

    run_sarkari = args.include_sarkari and not args.skip_sarkari
    run_extra = not args.skip_extra

    init_db()
    before = _count_exams()
    after_iso = (datetime.now() - timedelta(days=max(1, args.days))).strftime("%Y-%m-%dT%H:%M:%S")

    results = {}
    errors = []

    try:
        results["studygovthelp"] = sync_from_studygovthelp(
            pages=max(1, min(args.pages, 20)),
            per_page=max(1, min(args.per_page, 100)),
            after=after_iso,
        )
    except Exception as exc:
        errors.append(f"studygovthelp: {exc}")
        results["studygovthelp"] = {"status": "error", "message": str(exc)}

    if run_sarkari:
        try:
            results["sarkariresult"] = sync_from_sarkariresult(
                limit_deep_scrape=max(1, args.sarkari_limit)
            )
        except Exception as exc:
            errors.append(f"sarkariresult: {exc}")
            results["sarkariresult"] = {"status": "error", "message": str(exc)}

    if run_extra:
        try:
            results["rojgarresult"] = sync_from_rojgarresult(
                days=max(1, args.extra_days),
                pages=max(1, args.rr_pages),
            )
        except Exception as exc:
            errors.append(f"rojgarresult: {exc}")
            results["rojgarresult"] = {"status": "error", "message": str(exc)}

        try:
            results["freejobalert"] = sync_from_freejobalert(
                days=max(1, args.extra_days),
                limit=max(0, args.fja_limit),
            )
        except Exception as exc:
            errors.append(f"freejobalert: {exc}")
            results["freejobalert"] = {"status": "error", "message": str(exc)}

    seen_by_source = {}
    for source in ("studygovthelp", "rojgarresult", "freejobalert"):
        result = results.get(source) or {}
        seen_by_source[source] = result.pop("_seen_urls", [])

    pruned = {}
    if not args.no_prune:
        for source, seen_urls in seen_by_source.items():
            result = results.get(source) or {}
            if str(result.get("status", "")).upper() != "SUCCESS":
                pruned[source] = {
                    "status": "skipped",
                    "reason": f"sync status: {result.get('status', 'missing')}",
                }
                continue
            if not seen_urls:
                pruned[source] = {"status": "skipped", "reason": "no listing URLs"}
                continue
            try:
                pruned[source] = prune_removed_exams(
                    source,
                    seen_urls,
                    max_checks=max(0, args.prune_limit),
                    dry_run=args.prune_dry_run,
                )
            except Exception as exc:
                errors.append(f"cleanup {source}: {exc}")
                pruned[source] = {"status": "error", "message": str(exc)}

    cleanup = auto_cleanup_expired_exams()
    after = _count_exams()

    ok_sources = [
        name for name, result in results.items()
        if str(result.get("status", "")).lower() not in ("error", "partial")
    ]
    summary = {
        "status": "success" if ok_sources else "error",
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "exams_before": before,
        "exams_after": after,
        "cleanup": cleanup,
        "pruned": pruned,
        "sources": results,
        "errors": errors,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
