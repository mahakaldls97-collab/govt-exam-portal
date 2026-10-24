"""Broadcast newly added exams to the Telegram channel.

Runs inside the scheduled sync: any exam that has never been announced gets one
post (Hindi title, status, direct link to our own exam page) and is recorded in
`telegram_posts` so it is never repeated. Without bot credentials it reports
what it would send instead of failing the sync.
"""

import argparse
import os
import sqlite3
from datetime import datetime

import requests

from database import get_db, init_db
from data_quality import parse_date

API = "https://api.telegram.org/bot{token}/{method}"
DEFAULT_BASE_URL = "https://govt-exam-portal-three.vercel.app"
PER_RUN_LIMIT = 15

STATUS_LINE = {
    "Applications Open": "🟢 Apply Online Chalu Hai",
    "Upcoming": "🔵 Jald Aane Wala Notification",
    "Applications Closed": "⚪ Application Band",
    "Admit Card": "🎫 Admit Card / Exam City",
    "Answer Key": " Answer Key",
    "Result": "✅ Result",
    "Syllabus": "📖 Syllabus / Exam Pattern",
}

ENSURE_TABLE = """
create table if not exists telegram_posts (
    exam_id integer primary key,
    slug text not null,
    posted_at text not null,
    message_id integer,
    status text not null
)
"""


def _esc(text):
    return (str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def render_message(exam, base_url):
    title = _esc(exam.get("title") or exam.get("slug"))
    status = STATUS_LINE.get(exam.get("status"), "📌 Update")
    board = _esc(exam.get("board_name") or exam.get("department") or "")
    link = f"{base_url.rstrip('/')}/exam/{exam.get('slug')}"
    lines = [f"<b>{title}</b>", "", status]
    if board:
        lines.append(f"🏛️ {board}")
    vacancies = str(exam.get("total_vacancies") or "").strip()
    if vacancies and vacancies.lower() not in ("various posts", "post wise"):
        lines.append(f"👉 Total Posts: {vacancies}")
    last_date = _display(exam.get("apply_last_date"))
    if exam.get("status") in ("Applications Open", "Upcoming") and last_date \
            and "official" not in last_date.lower() and "as per" not in last_date.lower():
        lines.append(f"⏳ Last Date: {last_date}")
    lines += ["", "👇👇 Complete details yahan check karein", f'<a href="{link}">{link}</a>']
    return "\n".join(lines)


def ensure_table(conn):
    conn.execute(ENSURE_TABLE)
    conn.commit()


def _display(value):
    parsed = parse_date(str(value or ""))
    return parsed.strftime("%d %b %Y") if parsed else str(value or "").strip()


def pending_exams(conn, limit=PER_RUN_LIMIT):
    # Closed applications are stale news on a channel, so they are not announced.
    sql = ("select e.* from exams e left join telegram_posts p on p.exam_id = e.id "
           "where p.exam_id is null and e.status not in ('Archived', 'Applications Closed') "
           "order by e.notification_date desc, e.id desc limit ?")
    rows = [dict(r) for r in conn.execute(sql, (int(limit),))]
    return rows


def bootstrap_existing(conn):
    """Mark everything already in the DB as announced so the first run does not flood."""
    ensure_table(conn)
    count = conn.execute("select count(*) from telegram_posts").fetchone()[0]
    if count:
        return 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = list(conn.execute("select id, slug from exams where status != 'Archived'"))
    conn.executemany("insert or ignore into telegram_posts (exam_id, slug, posted_at, status) "
                     "values (?, ?, ?, 'skipped_backlog')",
                     [(r[0], r[1], now) for r in rows])
    conn.commit()
    return len(rows)


def _send(token, chat_id, text):
    response = requests.post(
        API.format(token=token, method="sendMessage"),
        data={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": "false"},
        timeout=45,
    )
    payload = {}
    try:
        payload = response.json()
    except ValueError:
        payload = {"ok": False, "description": response.text[:200]}
    return response.status_code, payload


def broadcast(conn=None, token=None, chat_id=None, base_url=DEFAULT_BASE_URL,
              limit=PER_RUN_LIMIT, dry_run=False):
    own_conn = conn is None
    conn = conn or get_db()
    ensure_table(conn)
    bootstrapped = bootstrap_existing(conn)
    pending = pending_exams(conn, limit)
    result = {"bootstrapped": bootstrapped, "pending": len(pending),
              "sent": 0, "failed": 0, "skipped": 0, "messages": []}
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")

    for exam in pending:
        text = render_message(exam, base_url)
        result["messages"].append(text)
        if dry_run or not token or not chat_id:
            result["skipped"] += 1
            continue
        code, payload = _send(token, chat_id, text)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if payload.get("ok"):
            result["sent"] += 1
            conn.execute("insert or replace into telegram_posts (exam_id, slug, posted_at, message_id, status) "
                         "values (?, ?, ?, ?, 'sent')",
                         (exam["id"], exam["slug"], now, payload["result"].get("message_id")))
        else:
            result["failed"] += 1
            conn.execute("insert or replace into telegram_posts (exam_id, slug, posted_at, status) "
                         "values (?, ?, ?, ?)",
                         (exam["id"], exam["slug"], now, f"error {code}: {payload.get('description', '')[:80]}"))
        conn.commit()

    if own_conn:
        conn.close()
    if not token or not chat_id:
        result["note"] = "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set - nothing was sent."
    return result


def main():
    parser = argparse.ArgumentParser(description="Announce new exams on Telegram")
    parser.add_argument("--dry-run", action="store_true", help="print messages without sending")
    parser.add_argument("--limit", type=int, default=PER_RUN_LIMIT)
    parser.add_argument("--base-url", default=os.environ.get("SITE_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--test", action="store_true", help="send one sample post to the channel")
    args = parser.parse_args()

    init_db()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if args.test:
        sample = {"title": "Test Post - SarkariNexus 360", "slug": "sarkari-nexus-360-test",
                  "status": "Applications Open", "board_name": "Test", "total_vacancies": "",
                  "apply_last_date": ""}
        code, payload = _send(token, chat_id, render_message(sample, args.base_url))
        print("HTTP", code, payload.get("ok"), payload.get("description", ""))
        return

    result = broadcast(token=token, chat_id=chat_id, base_url=args.base_url,
                       limit=args.limit, dry_run=args.dry_run)
    print(f"backlog marked: {result['bootstrapped']}, pending: {result['pending']}, "
          f"sent: {result['sent']}, failed: {result['failed']}, skipped: {result['skipped']}")
    if result.get("note"):
        print(result["note"])
    for message in result["messages"][:3]:
        print("-" * 60)
        print(message)


if __name__ == "__main__":
    main()
