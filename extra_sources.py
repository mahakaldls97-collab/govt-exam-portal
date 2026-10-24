"""Pan-India exam sources: RojgarResult (WordPress REST) and FreeJobAlert (RSS).

Both sources are turned into concise, original summaries with attribution. The
database is only updated through the normal create/update helpers, so running a
sync never clears existing records.
"""

import html as html_lib
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

import requests
from bs4 import BeautifulSoup

from database import create_exam, get_db, init_db, log_sync, update_exam
from data_quality import (
    CANONICAL_STATUSES,
    clean_text,
    clean_title,
    clean_url,
    dedupe_key,
    detect_state,
    ensure_slug,
    is_junk_title,
    normalize_record,
    parse_date,
)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
RR_API = "https://rojgarresult.com/wp-json/wp/v2/posts"
FJA_RSS = "https://www.freejobalert.com/feed/"
SOURCE_LABELS = {"rojgarresult": "RojgarResult", "freejobalert": "FreeJobAlert"}

DATE_FIELDS = (
    "notification_date",
    "apply_start_date",
    "apply_last_date",
    "fee_last_date",
    "correction_last_date",
    "admit_card_date",
    "exam_date",
    "result_date",
)
LINK_FIELDS = (
    "link_apply_online",
    "link_notification_pdf",
    "link_admit_card",
    "link_answer_key",
    "link_result",
    "link_official_website",
)
PLACEHOLDER_VALUES = {
    "",
    "-",
    "n/a",
    "na",
    "not specified",
    "as per notification",
    "check official notification",
    "check official portal",
    "as per schedule",
    "after examination",
    "various",
    "various posts",
}
UNIVERSITY_RESULT_RE = re.compile(
    r"\b(b\.?tech|b\.?arch|m\.?tech|mba|bba|bca|mca|b\.?sc|b\.?com|b\.?a)\b.*"
    r"\b(result|semester|admit card)\b",
    re.I,
)
UNIVERSITY_EXAM_RE = re.compile(
    r"\buniversity\b.*\b(result|semester|admit card|date\s*sheet)\b", re.I
)


def _get(url, **kwargs):
    headers = dict(kwargs.pop("headers", {}) or {})
    headers.setdefault("User-Agent", USER_AGENT)
    kwargs.setdefault("timeout", (10, 20))
    return requests.get(url, headers=headers, **kwargs)


def _clean_val(value, limit=500):
    text = clean_text(value, limit)
    if text.lower().strip(" .") in PLACEHOLDER_VALUES:
        return ""
    return text


def _add_text(facts, key, text, limit):
    text = _clean_val(text, limit)
    if not text or len(text) < 20:
        return
    current = facts.get(key, "")
    if text.lower() in current.lower():
        return
    combined = f"{current} {text}".strip()
    facts[key] = combined[:limit]


def _prepare_soup(html_text):
    soup = BeautifulSoup(html_text or "", "html.parser")
    for tag in soup.find_all(["script", "style", "noscript", "iframe", "ins", "form"]):
        tag.decompose()
    bad_markers = (
        "sharedaddy",
        "jp-relatedposts",
        "post-navigation",
        "comments-area",
        "author-box",
        "related-posts",
        "newsletter",
        "social-share",
        "adsbygoogle",
        "sidebar",
    )
    for tag in soup.find_all(["div", "aside", "section", "header", "footer", "nav", "ul"]):
        if getattr(tag, "attrs", None) is None:
            continue
        classes = [str(item).lower() for item in (tag.get("class") or [])]
        ident = (tag.get("id") or "").lower()
        if "sidebar" in classes or any(
            marker in cls for cls in classes for marker in bad_markers if marker != "sidebar"
        ) or any(marker in ident for marker in ("comment", "sidebar", "related-post")):
            tag.decompose()
    return soup


def _scope(soup):
    for selector in (".entry-content", ".post-content", ".article-content", "article", "main"):
        node = soup.select_one(selector)
        if node:
            return node
    return soup


def _section_text(scope, phrases, max_chars=700):
    for heading in scope.find_all(["h2", "h3", "h4"]):
        heading_text = heading.get_text(" ", strip=True).lower()
        if not any(phrase in heading_text for phrase in phrases):
            continue
        parts = []
        total = 0
        for element in heading.next_elements:
            if getattr(element, "name", None) in ("h2", "h3", "h4"):
                break
            if getattr(element, "name", None) not in ("p", "li"):
                continue
            text = _clean_val(element.get_text(" ", strip=True), max_chars)
            if len(text) < 20 or text in parts:
                continue
            low = text.lower()
            if any(word in low for word in ("telegram", "whatsapp", "join our", "free job alert")):
                continue
            parts.append(text)
            total += len(text)
            if total >= max_chars:
                break
        if parts:
            return " ".join(parts)[:max_chars]
    return ""


PHYSICAL_WORDS = (
    "height", "weight", "chest", "running", "long jump", "shot put",
    "physical standard", "physical measurement", "physical efficiency",
)


def _age_range(value):
    ranges = re.findall(r"(\d{2})\s*(?:-|–|to)\s*(\d{2})", value)
    if not ranges:
        return None
    low = min(int(item[0]) for item in ranges)
    highs = {int(item[1]) for item in ranges}
    if len(highs) == 1:
        max_age = f"{highs.pop()} Years"
    else:
        max_age = f"As per post (up to {max(highs)} Years)"
    note = f"Post-wise age limit: {value}" if len(ranges) > 1 else ""
    return f"{low} Years", max_age, note


def _is_fee_value(value):
    low = value.lower()
    if any(unit in low for unit in (" cm", " kg", "minute", "marks", "questions")):
        return False
    return bool(re.search(r"\d", low)) or any(word in low for word in ("nil", "free", "exempt"))


def _extract_facts(scope):
    facts = {
        "board": "",
        "post_name": "",
        "vacancies": "",
        "mode": "",
        "advt_no": "",
        "status": "",
        "location": "",
        "official_site": "",
        "pay_level": "",
        "apply_start": "",
        "apply_last": "",
        "fee_last": "",
        "correction_last": "",
        "admit_date": "",
        "exam_date": "",
        "result_date": "",
        "notification": "",
        "fee_general": "",
        "fee_reserved": "",
        "min_age": "",
        "max_age": "",
        "age_as_on": "",
        "age_relaxation": "",
        "salary_selection": "",
        "eligibility": "",
        "selection": "",
        "how_to_apply": "",
    }

    for table in scope.find_all("table"):
        table_text = clean_text(table.get_text(" ", strip=True), 600).lower()
        heading = table.find_previous(["h2", "h3", "h4"])
        heading_text = clean_text(heading.get_text(" ", strip=True), 160).lower() if heading else ""
        fee_context = "fee" in table_text or "fee" in heading_text

        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"], recursive=False)
            if len(cells) < 2:
                continue
            values = [_clean_val(cell.get_text(" ", strip=True), 700) for cell in cells]
            key = values[0].lower().strip(" :.-")
            value = values[1]
            if not key or not value:
                continue
            low_value = value.lower()
            if low_value in (
                "details", "date", "date and time", "total post", "total posts",
                "click here", "link", "no. of posts", "educational qualification",
                "age limit", "pay level",
            ):
                continue
            if key in ("s. no.", "s.no.", "s no.", "sno") or (
                key in ("post name", "post names")
                and low_value in ("educational qualification", "age limit", "pay level")
            ):
                continue

            # Post-wise vacancy rows end with the eligibility text.
            if (
                len(values) >= 3
                and re.fullmatch(r"[\d,]+", value)
                and len(values[2]) > 25
            ):
                _add_text(facts, "eligibility", values[2], 700)
                continue

            if any(k in key for k in ("organization", "organisation", "conducting authority", "recruiting body")) and not facts["board"]:
                facts["board"] = value
            elif key in ("post name", "post names", "posts", "name of post", "name of the post"):
                if not facts["post_name"]:
                    facts["post_name"] = value
            elif (
                any(k in key for k in ("total vacancy", "total vacancies", "total post", "number of post", "no of post", "no. of post"))
                or key in ("vacancies", "vacancy")
            ):
                if not facts["vacancies"]:
                    facts["vacancies"] = value
            elif ("advertisement" in key or key.startswith("advt")) and re.search(
                r"\b(?:no|number)\b", key
            ):
                facts["advt_no"] = value
            elif key in ("status", "notice status", "application status", "posting status"):
                # Only a wording the portal itself uses is accepted, so a page
                # writing "Notified"/"Online" here cannot corrupt the badge.
                if value.strip().title() in CANONICAL_STATUSES:
                    facts["status"] = value.strip().title()
            elif "application mode" in key:
                facts["mode"] = value
            elif key in ("job location", "location", "job posting"):
                facts["location"] = value
            elif "official website" in key or "official site" in key:
                facts["official_site"] = clean_url(value)
            elif "selection process" in key or "selection procedure" in key:
                facts["selection"] = facts["selection"] or value
            elif "salary" in key or "pay scale" in key or "pay level" in key or key == "pay":
                facts["salary_selection"] = facts["salary_selection"] or value
                facts["pay_level"] = facts["pay_level"] or value
            elif "minimum age" in key or "min age" in key:
                facts["min_age"] = facts["min_age"] or value
            elif "maximum age" in key or "max age" in key:
                facts["max_age"] = facts["max_age"] or value
            elif "age relaxation" in key:
                facts["age_relaxation"] = facts["age_relaxation"] or value
            elif "age calculation" in key or "age as on" in key or "as on date" in key:
                facts["age_as_on"] = facts["age_as_on"] or value
            elif key in ("age limit", "age criteria") or "age limit" in key:
                parsed_age = _age_range(value)
                if parsed_age:
                    facts["min_age"] = facts["min_age"] or parsed_age[0]
                    facts["max_age"] = facts["max_age"] or parsed_age[1]
                    facts["age_relaxation"] = facts["age_relaxation"] or parsed_age[2]
            elif "age" in key and any(k in key for k in ("relax", "category")):
                facts["age_relaxation"] = facts["age_relaxation"] or value
            elif "fee" in key and "last date" in key:
                facts["fee_last"] = facts["fee_last"] or value
            elif "correction" in key:
                facts["correction_last"] = facts["correction_last"] or value
            elif "admit card" in key or "call letter" in key:
                facts["admit_date"] = facts["admit_date"] or value
            elif "result" in key and ("date" in key or "declared" in key):
                facts["result_date"] = facts["result_date"] or value
            elif "walk-in" in key or "walk in" in key or "interview date" in key:
                facts["exam_date"] = facts["exam_date"] or value
            elif "exam date" in key or "examination date" in key or "date of exam" in key:
                facts["exam_date"] = facts["exam_date"] or value
            elif "registration start" in key or (
                "start date" in key and any(k in key for k in ("registration", "application", "apply"))
            ):
                facts["apply_start"] = facts["apply_start"] or value
            elif "last date" in key and any(
                k in key for k in ("registration", "application", "apply", "submission", "closing")
            ):
                if any(k in key for k in ("fee", "payment", "submission")):
                    facts["fee_last"] = facts["fee_last"] or value
                    if not facts["apply_last"]:
                        facts["apply_last"] = value
                else:
                    facts["apply_last"] = facts["apply_last"] or value
            elif key == "last date" or "closing date" in key:
                facts["apply_last"] = facts["apply_last"] or value
            elif "notification date" in key or key == "notification" or "post date" in key or "advertisement date" in key:
                facts["notification"] = facts["notification"] or value
            elif (
                fee_context
                and _is_fee_value(value)
                and not any(word in key for word in PHYSICAL_WORDS)
                and any(k in key for k in ("general", "obc", "ews", "ur", "sc", "st", "female", "reserved", "others"))
            ):
                if any(k in key for k in ("general", "obc", "ews", "ur")) and not facts["fee_general"]:
                    facts["fee_general"] = value
                elif not facts["fee_reserved"]:
                    facts["fee_reserved"] = value

    facts["eligibility"] = facts["eligibility"] or _section_text(
        scope, ("educational qualification", "qualification", "eligibility", "who can apply"), 700
    )
    facts["selection"] = _section_text(scope, ("selection process", "selection procedure"), 500)
    if not facts["selection"] and "selection procedure" in facts["salary_selection"].lower():
        split = re.split(r"selection\s+procedure\s*[:\-]?", facts["salary_selection"], maxsplit=1, flags=re.I)
        if len(split) > 1:
            facts["selection"] = _clean_val(split[1], 500)
    facts["how_to_apply"] = _section_text(scope, ("how to apply", "application procedure"), 700)
    return facts


def _extract_links(scope):
    links = {key: "" for key in ("apply", "notification", "official", "admit", "answer", "result")}
    for anchor in scope.find_all("a", href=True):
        href = clean_url(anchor.get("href"))
        if not href:
            continue
        text = clean_text(anchor.get_text(" ", strip=True)).lower()
        row = anchor.find_parent("tr")
        context = text
        if row is not None:
            context = f"{text} {clean_text(row.get_text(' ', strip=True)).lower()}"
        if any(word in context for word in ("whatsapp", "telegram", "youtube", "instagram", "facebook", "twitter")):
            continue
        if not links["apply"] and any(
            k in context
            for k in (
                "apply online", "online form", "apply here", "application link",
                "apply now", "apply link", "registration link", "online application",
            )
        ):
            links["apply"] = href
        if not links["notification"] and ("notification" in context or "advertisement" in context) and any(
            k in context for k in ("download", "pdf", "click here", "link")
        ):
            links["notification"] = href
        if not links["admit"] and any(k in context for k in ("admit card", "call letter", "exam city")):
            links["admit"] = href
        if not links["answer"] and "answer key" in context:
            links["answer"] = href
        if not links["result"] and any(k in context for k in ("result", "score card", "scorecard", "merit list")):
            links["result"] = href
        if not links["official"] and ("official website" in context or "official site" in context):
            links["official"] = href
    return links


def _date_value(value):
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else ""


def _display_date(value):
    parsed = parse_date(value)
    if parsed:
        return parsed.strftime("%d %b %Y")
    return clean_text(value, 40)


def _is_university_result(title):
    if UNIVERSITY_RESULT_RE.search(title):
        return True
    if UNIVERSITY_EXAM_RE.search(title) and not any(
        word in title.lower() for word in ("recruitment", "vacancy", "bharti")
    ):
        return True
    return False


def _build_content(data, source_name, source_url):
    label = SOURCE_LABELS.get(source_name, source_name)
    title = clean_text(data.get("title"), 220)
    board = clean_text(data.get("board_name"), 160) or "The recruiting authority"
    status = data.get("status") or "Applications Open"
    vacancy = clean_text(data.get("total_vacancies"), 60)
    state = clean_text(data.get("state"), 60) or "All India"
    post_name = clean_text(data.get("post_name"), 120)
    last_date = data.get("apply_last_date")
    last_text = ""
    if parse_date(last_date):
        last_text = f" The last date to apply is {_display_date(last_date)}."

    if status == "Result":
        lead = (
            f"{board} has declared the result for {title}. Candidates can check the "
            "scorecard, merit list or cut-off details through the official link below."
        )
    elif status == "Admit Card":
        lead = (
            f"{board} has released the admit card or exam-city information for {title}. "
            "Download the call letter from the official link below."
        )
    elif status == "Answer Key":
        lead = (
            f"{board} has published the answer key for {title}. Candidates can download "
            "the provisional answer key and check the objection process."
        )
    elif status == "Applications Closed":
        lead = (
            f"The application window for {title} has closed. The next updates will be the "
            "admit card, exam date and result."
        )
    elif status == "Upcoming":
        lead = (
            f"{board} is expected to release the notification for {title}. Bookmark this "
            "page for the latest dates, vacancy details and official link."
        )
    else:
        lead = (
            f"Applications are open for {title}.{last_text} Candidates should verify "
            "eligibility, age limit and fee before applying through the official portal."
        )

    def table(rows, headers=None):
        body = []
        if headers:
            body.append(
                "<tr><th class=\"bg-slate-100 p-2.5 font-bold text-slate-800 border border-slate-200\">"
                + "</th><th class=\"bg-slate-100 p-2.5 font-bold text-slate-800 border border-slate-200\">".join(
                    html_lib.escape(str(h)) for h in headers
                )
                + "</th></tr>"
            )
        for key, value in rows:
            if not value:
                continue
            body.append(
                "<tr>"
                f"<td class=\"p-2.5 text-slate-700 border border-slate-200 font-semibold\">{html_lib.escape(str(key))}</td>"
                f"<td class=\"p-2.5 text-slate-700 border border-slate-200\">{html_lib.escape(str(value))}</td>"
                "</tr>"
            )
        if not body:
            return ""
        return (
            "<div class=\"overflow-x-auto my-3\"><table class=\"w-full text-xs sm:text-sm text-left "
            "border-collapse border border-slate-200 rounded-xl overflow-hidden\">"
            + "".join(body)
            + "</table></div>"
        )

    parts = [f"<p class=\"text-xs sm:text-sm text-slate-700 leading-relaxed mb-3\">{html_lib.escape(lead)}</p>"]

    quick_rows = [
        ("Recruiting Board", board),
        ("Post Name", post_name),
        ("Total Vacancies", vacancy if vacancy.lower() not in PLACEHOLDER_VALUES else ""),
        ("Job Location", state),
        ("Application Mode", clean_text(data.get("fee_payment_mode"), 80) and "Online"),
        ("Advertisement No.", clean_text(data.get("advt_no"), 80)),
    ]
    quick_table = table(quick_rows, ("Particulars", "Details"))
    if quick_table:
        parts.append("<h2 class=\"text-base sm:text-lg font-black text-slate-900 mt-6 mb-2 pb-1 border-b border-slate-100\">Recruitment Overview</h2>")
        parts.append(quick_table)

    date_rows = []
    for label_text, field in (
        ("Notification Date", "notification_date"),
        ("Application Start", "apply_start_date"),
        ("Last Date to Apply", "apply_last_date"),
        ("Fee Payment Last Date", "fee_last_date"),
        ("Correction Last Date", "correction_last_date"),
        ("Admit Card Date", "admit_card_date"),
        ("Exam Date", "exam_date"),
        ("Result Date", "result_date"),
    ):
        value = data.get(field)
        if parse_date(value):
            date_rows.append((label_text, _display_date(value)))
    date_table = table(date_rows, ("Event", "Date"))
    if date_table:
        parts.append("<h2 class=\"text-base sm:text-lg font-black text-slate-900 mt-6 mb-2 pb-1 border-b border-slate-100\">Important Dates</h2>")
        parts.append(date_table)

    fee_rows = []
    general = clean_text(data.get("fee_general"), 80)
    reserved = clean_text(data.get("fee_reserved"), 80)
    if general and general.lower() not in PLACEHOLDER_VALUES:
        fee_rows.append(("General / OBC / EWS", general))
    if reserved and reserved.lower() not in PLACEHOLDER_VALUES:
        fee_rows.append(("SC / ST / Reserved", reserved))
    fee_table = table(fee_rows, ("Category", "Fee"))
    if fee_table:
        parts.append("<h2 class=\"text-base sm:text-lg font-black text-slate-900 mt-6 mb-2 pb-1 border-b border-slate-100\">Application Fee</h2>")
        parts.append(fee_table)

    eligibility = clean_text(data.get("eligibility_criteria"), 700)
    if eligibility and len(eligibility) > 30:
        parts.append("<h2 class=\"text-base sm:text-lg font-black text-slate-900 mt-6 mb-2 pb-1 border-b border-slate-100\">Eligibility Criteria</h2>")
        parts.append(f"<p class=\"text-xs sm:text-sm text-slate-700 leading-relaxed mb-3\">{html_lib.escape(eligibility)}</p>")

    selection = clean_text(data.get("selection_process"), 500)
    if selection and len(selection) > 20:
        parts.append("<h2 class=\"text-base sm:text-lg font-black text-slate-900 mt-6 mb-2 pb-1 border-b border-slate-100\">Selection Process</h2>")
        parts.append(f"<p class=\"text-xs sm:text-sm text-slate-700 leading-relaxed mb-3\">{html_lib.escape(selection)}</p>")

    if status in ("Applications Open", "Upcoming", "Applications Closed"):
        steps = [
            "Read the official notification and confirm eligibility, age limit and application fee.",
            "Open the official application portal and register with a valid mobile number and email.",
            "Fill the application form carefully and upload the required documents.",
            "Pay the application fee, submit the form and download the acknowledgement.",
        ]
        parts.append("<h2 class=\"text-base sm:text-lg font-black text-slate-900 mt-6 mb-2 pb-1 border-b border-slate-100\">How to Apply</h2>")
        parts.append("<ol class=\"list-decimal list-inside space-y-1 text-xs sm:text-sm text-slate-700 mb-3\">" + "".join(
            f"<li>{html_lib.escape(step)}</li>" for step in steps
        ) + "</ol>")
    elif status in ("Admit Card", "Result", "Answer Key"):
        parts.append("<h2 class=\"text-base sm:text-lg font-black text-slate-900 mt-6 mb-2 pb-1 border-b border-slate-100\">How to Download</h2>")
        parts.append(
            "<ol class=\"list-decimal list-inside space-y-1 text-xs sm:text-sm text-slate-700 mb-3\">"
            "<li>Open the official link given on this page.</li>"
            "<li>Enter your registration number, roll number or date of birth as required.</li>"
            "<li>Download the document and verify your name, post and other details.</li>"
            "</ol>"
        )

    source_href = html_lib.escape(clean_url(source_url) or source_url or "", quote=True)
    parts.append(
        "<p class=\"text-xs text-slate-500 leading-relaxed mt-6 pt-3 border-t border-slate-100\">"
        f"Source: <a href=\"{source_href}\" target=\"_blank\" rel=\"nofollow noopener\" class=\"text-indigo-600 font-semibold\">{html_lib.escape(label)}</a> "
        "(third-party update). This page is a concise summary; verify all details on the official portal before applying. "
        "अधिक जानकारी के लिए आधिकारिक वेबसाइट देखें।"
        "</p>"
    )
    return "".join(parts)[:14000]


def _parse_item(title, html_text, source_url, post_date, source_name):
    title = clean_title(title)
    soup = _prepare_soup(html_text)
    scope = _scope(soup)
    facts = _extract_facts(scope)
    links = _extract_links(scope)

    board = facts["board"] or ""
    state = detect_state(title, "All India")
    if state == "All India" and board:
        state = detect_state(board, "All India")
    if state == "All India" and facts["location"]:
        state = detect_state(facts["location"], "All India")

    notification_date = _date_value(facts["notification"]) or post_date or ""
    apply_last = _date_value(facts["apply_last"])
    apply_start = _date_value(facts["apply_start"])
    exam_date = _date_value(facts["exam_date"])
    result_date = _date_value(facts["result_date"])
    admit_date = _date_value(facts["admit_date"])
    fee_last = _date_value(facts["fee_last"])
    correction_last = _date_value(facts["correction_last"])

    min_age = facts["min_age"] or "As per notification"
    max_age = facts["max_age"] or "As per rules"
    eligibility = facts["eligibility"] or "10th / 12th / Graduate or relevant qualification as per the official notification."
    selection = facts["selection"] or "Selection will be held as per the official notification."
    post_name = facts["post_name"] or title[:90]

    short = (
        f"{board or 'The recruiting authority'} has released an update for {title}. "
        "Check important dates, vacancy, eligibility, fee and official links."
    )

    data = {
        "title": title,
        "slug": ensure_slug(title),
        "category": "",
        "board_name": board[:160],
        "total_vacancies": facts["vacancies"] or "Various Posts",
        "short_description": short[:320],
        "status": facts["status"],
        "notification_date": notification_date,
        "apply_start_date": apply_start,
        "apply_last_date": apply_last,
        "fee_last_date": fee_last,
        "correction_last_date": correction_last,
        "admit_card_date": admit_date,
        "exam_date": exam_date,
        "result_date": result_date,
        "fee_general": facts["fee_general"] or "As per notification",
        "fee_reserved": facts["fee_reserved"] or "As per notification",
        "fee_payment_mode": "Online (Debit/Credit Card, Net Banking, UPI)",
        "min_age": min_age,
        "max_age": max_age,
        "age_as_on": facts["age_as_on"],
        "age_relaxation": facts["age_relaxation"] or "As per government rules.",
        "eligibility_criteria": eligibility,
        "selection_process": selection,
        "syllabus_summary": "Detailed syllabus and exam pattern are available in the official notification.",
        "how_to_apply": "Read the official notification, complete the online form, upload documents, pay the fee and submit the application.",
        "link_apply_online": links["apply"],
        "link_notification_pdf": links["notification"],
        "link_admit_card": links["admit"],
        "link_answer_key": links["answer"],
        "link_result": links["result"],
        "link_official_website": links["official"] or facts["official_site"],
        "state": state,
        "is_auto_synced": 1,
        "source_url": clean_url(source_url) or source_url,
        "content_html": "",
        "short_title": title[:70],
        "post_name": post_name[:160],
        "department": board[:120],
        "advt_no": facts["advt_no"],
        "pay_level": facts["pay_level"][:80],
        "keywords": f"{title}, {board}, {state} govt jobs, {source_name}",
    }

    normalized = normalize_record(data, cap_content=False)
    normalized["content_html"] = _build_content(normalized, source_name, source_url)
    return normalized


GENERIC_PHRASES = (
    "online form",
    "apply online",
    "application form",
    "last date",
    "direct link",
    "click here",
    "download",
    "notification",
    "recruitment",
    "bharti",
    "vacancy",
    "vacancies",
    "admit card",
    "answer key",
    "score card",
    "scorecard",
    "merit list",
    "cut off",
    "cutoff",
    "exam date",
    "exam pattern",
    "syllabus",
    "result",
    "latest",
    "update",
    "revised",
    "declared",
    "final",
    "post",
    "posts",
    "government",
    "govt",
    "jobs",
    "job",
)
STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "are", "was", "will",
    "has", "have", "had", "into", "over", "under", "about", "after", "before",
    "india", "all", "new", "not", "out", "here", "now", "today", "check", "link",
    "form", "online", "ke", "ki", "ka", "me", "mein", "se", "tak", "aur",
    "भर्ती", "ऑनलाइन", "फॉर्म", "आवेदन", "अंतिम", "तिथि", "परिणाम", "रिजल्ट",
    "एडमिट", "कार्ड", "उत्तर", "कुंजी", "सिलेबस", "पद", "पदों", "नोटिफिकेशन",
    "लिंक", "डाउनलोड", "करें", "के", "लिए", "में", "की", "का",
}


def _title_core(title):
    text = clean_title(title).lower()
    years = frozenset(re.findall(r"\b20\d{2}\b", text))
    text = re.sub(r"\b20\d{2}\b", " ", text)
    for phrase in GENERIC_PHRASES:
        text = text.replace(phrase, " ")
    text = re.sub(r"[^a-z0-9\u0900-\u097f]+", " ", text)
    tokens = {
        token
        for token in text.split()
        if len(token) > 1 and not token.isdigit() and token not in STOPWORDS
    }
    # Hindi titles are usually translations of the same English post; keeping
    # both scripts in the set inflates it and hides duplicates.
    latin_tokens = {
        token for token in tokens
        if not any("\u0900" <= char <= "\u097f" for char in token)
    }
    if latin_tokens:
        tokens = latin_tokens
    return frozenset(tokens), years


class ExamIndex:
    def __init__(self):
        self.rows = []
        self.by_source = {}
        self.by_slug = {}
        connection = get_db()
        cursor = connection.execute("SELECT * FROM exams")
        for record in cursor.fetchall():
            row = dict(record)
            core, years = _title_core(row.get("title", ""))
            row["_core"] = core
            row["_years"] = years
            row["_kind"] = dedupe_key(row.get("title", "")).split(":", 1)[0]
            self.rows.append(row)
            if row.get("source_url"):
                self.by_source[row["source_url"]] = row
            self.by_slug[row.get("slug", "")] = row
        connection.close()

    def exact(self, slug=None, source_url=None):
        if source_url and source_url in self.by_source:
            return self.by_source[source_url]
        if slug and slug in self.by_slug:
            return self.by_slug[slug]
        return None

    def similar(self, title, state):
        core, years = _title_core(title)
        if len(core) < 2:
            return None
        kind = dedupe_key(title).split(":", 1)[0]
        for row in self.rows:
            if row.get("status") == "Archived":
                continue
            if row["_kind"] != kind:
                continue
            if row.get("state") != state:
                continue
            if years and row["_years"] and not (years & row["_years"]):
                continue
            other = row["_core"]
            if len(other) < 2:
                continue
            intersection = core & other
            if not intersection:
                continue
            union = core | other
            if len(intersection) / len(union) >= 0.72:
                return row
            if core <= other or other <= core:
                return row
        return None

    def add(self, exam_id, data):
        row = dict(data)
        row["id"] = exam_id
        core, years = _title_core(row.get("title", ""))
        row["_core"] = core
        row["_years"] = years
        row["_kind"] = dedupe_key(row.get("title", "")).split(":", 1)[0]
        self.rows.append(row)
        if row.get("source_url"):
            self.by_source[row["source_url"]] = row
        self.by_slug[row.get("slug", "")] = row


def _merge_match(row, data):
    existing = row
    payload = {}
    generic_boards = {
        "",
        "Central Government",
        "State Government",
        f"{existing.get('state')} Government",
    }
    if existing.get("board_name") in generic_boards and data.get("board_name") not in generic_boards:
        payload["board_name"] = data["board_name"]
    if existing.get("state") == "All India" and data.get("state") not in (None, "", "All India"):
        payload["state"] = data["state"]
    if existing.get("category") in ("", "Others", "State") and data.get("category") not in ("", "Others", "State"):
        payload["category"] = data["category"]
    if existing.get("total_vacancies") in ("", "Various Posts") and data.get("total_vacancies") not in ("", "Various Posts"):
        payload["total_vacancies"] = data["total_vacancies"]

    for field in DATE_FIELDS:
        new_date = parse_date(data.get(field))
        old_date = parse_date(existing.get(field))
        if new_date and new_date != old_date and field != "notification_date":
            payload[field] = data[field]
    if not parse_date(existing.get("notification_date")) and parse_date(data.get("notification_date")):
        payload["notification_date"] = data["notification_date"]

    rank = {
        "Upcoming": 1,
        "Applications Open": 2,
        "Applications Closed": 3,
        "Admit Card": 4,
        "Answer Key": 5,
        "Result": 6,
        "Archived": 7,
    }
    if data.get("status") and data["status"] != existing.get("status"):
        if rank.get(data["status"], 0) >= rank.get(existing.get("status"), 0):
            payload["status"] = data["status"]

    for field in LINK_FIELDS:
        if not existing.get(field) and data.get(field):
            payload[field] = data[field]
    if len(existing.get("content_html") or "") < 1200 and len(data.get("content_html") or "") > len(
        existing.get("content_html") or ""
    ):
        payload["content_html"] = data["content_html"]
    for field in ("eligibility_criteria", "selection_process", "how_to_apply", "short_description"):
        if len(existing.get(field) or "") < 40 and len(data.get(field) or "") > len(existing.get(field) or ""):
            payload[field] = data[field]
    if not existing.get("post_name") and data.get("post_name"):
        payload["post_name"] = data["post_name"]
    if not existing.get("department") and data.get("department"):
        payload["department"] = data["department"]
    if not existing.get("source_url") and data.get("source_url"):
        payload["source_url"] = data["source_url"]

    if not payload:
        return False
    payload["is_auto_synced"] = 1
    update_exam(existing["id"], payload)
    existing.update(payload)
    return True


def _stats():
    return {
        "items_found": 0,
        "items_added": 0,
        "items_updated": 0,
        "skipped_junk": 0,
        "skipped_duplicates": 0,
        "skipped_limit": 0,
        "errors": 0,
        "seen_urls": set(),
    }


def _process_record(index, title, html_text, source_url, post_date, source_name, stats):
    title = clean_title(title)
    if not title or is_junk_title(title) or _is_university_result(title):
        stats["skipped_junk"] += 1
        return
    source_url = clean_url(source_url) or source_url

    existing = index.exact(source_url=source_url)
    if existing and existing.get("status") == "Archived":
        stats["skipped_duplicates"] += 1
        return

    data = _parse_item(title, html_text, source_url, post_date, source_name)
    if not data.get("title"):
        stats["skipped_junk"] += 1
        return

    match = existing or index.exact(slug=data["slug"]) or index.similar(data["title"], data["state"])
    if match:
        if match.get("status") == "Archived":
            stats["skipped_duplicates"] += 1
        elif _merge_match(match, data):
            stats["items_updated"] += 1
        else:
            stats["skipped_duplicates"] += 1
        return

    base_slug = data["slug"]
    counter = 2
    while data["slug"] in index.by_slug:
        data["slug"] = f"{base_slug}-{counter}"
        counter += 1
    exam_id = create_exam(data)
    index.add(exam_id, data)
    stats["items_added"] += 1
    print(f"  [+] {source_name}: {data['title']} [{data['state']}]")


def _finish(source_name, stats):
    label = SOURCE_LABELS.get(source_name, source_name)
    status = "SUCCESS" if stats["items_found"] and stats["errors"] == 0 else ("PARTIAL" if stats["items_added"] or stats["items_updated"] else "ERROR")
    message = (
        f"{label} sync: {stats['items_found']} posts examined, {stats['items_added']} new, "
        f"{stats['items_updated']} updated, {stats['skipped_junk']} junk skipped, "
        f"{stats['skipped_duplicates']} duplicates skipped."
    )
    if stats["errors"]:
        message += f" {stats['errors']} item errors."
    log_sync(status, stats["items_found"], stats["items_added"], message)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")
    return {
        "status": status,
        "items_found": stats["items_found"],
        "items_added": stats["items_added"],
        "items_updated": stats["items_updated"],
        "skipped_junk": stats["skipped_junk"],
        "skipped_duplicates": stats["skipped_duplicates"],
        "skipped_limit": stats["skipped_limit"],
        "errors": stats["errors"],
        "message": message,
        "_seen_urls": sorted(stats.get("seen_urls", [])),
    }


def sync_from_rojgarresult(days=90, pages=5, per_page=100):
    init_db()
    stats = _stats()
    index = ExamIndex()
    after = (datetime.now() - timedelta(days=max(1, days))).strftime("%Y-%m-%dT%H:%M:%S")
    pages = max(1, min(int(pages), 10))
    per_page = max(1, min(int(per_page), 100))

    for page in range(1, pages + 1):
        try:
            response = _get(
                RR_API,
                params={"page": page, "per_page": per_page, "after": after},
            )
        except Exception as exc:
            stats["errors"] += 1
            print(f"[ROJGARRESULT] Page {page} request failed: {exc}")
            break
        if response.status_code == 400 and page > 1:
            break
        if response.status_code != 200:
            stats["errors"] += 1
            print(f"[ROJGARRESULT] Page {page} returned {response.status_code}")
            break
        try:
            posts = response.json()
        except Exception as exc:
            stats["errors"] += 1
            print(f"[ROJGARRESULT] Invalid JSON on page {page}: {exc}")
            break
        if not isinstance(posts, list) or not posts:
            break

        stats["items_found"] += len(posts)
        total_pages = int(response.headers.get("X-WP-TotalPages") or pages)
        for post in posts:
            try:
                title = clean_text((post.get("title") or {}).get("rendered", ""), 220)
                content = (post.get("content") or {}).get("rendered", "")
                link = (post.get("link") or "").strip()
                if link:
                    stats["seen_urls"].add(link)
                post_date = (post.get("date") or "")[:10]
                _process_record(index, title, content, link, post_date, "rojgarresult", stats)
            except Exception as exc:
                stats["errors"] += 1
                print(f"  [!] RojgarResult item failed: {exc}")
        if page >= total_pages:
            break

    return _finish("rojgarresult", stats)


def sync_from_freejobalert(days=90, limit=25):
    init_db()
    stats = _stats()
    index = ExamIndex()
    cutoff = (datetime.now() - timedelta(days=max(1, days))).date()
    detail_fetches = 0

    try:
        response = _get(FJA_RSS)
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except Exception as exc:
        stats["errors"] += 1
        print(f"[FREEJOBALERT] Feed failed: {exc}")
        return _finish("freejobalert", stats)

    items = root.findall(".//item")
    for item in items:
        title = clean_text(item.findtext("title") or "", 220)
        link = (item.findtext("link") or "").strip()
        if link:
            stats["seen_urls"].add(link)
        raw_date = item.findtext("pubDate") or ""
        published = None
        try:
            published = parsedate_to_datetime(raw_date).date()
        except Exception:
            pass
        if published and published < cutoff:
            continue
        stats["items_found"] += 1
        if not title or not link or is_junk_title(title) or _is_university_result(title):
            stats["skipped_junk"] += 1
            continue
        clean_link = clean_url(link) or link
        if index.exact(source_url=clean_link):
            stats["skipped_duplicates"] += 1
            continue
        if detail_fetches >= max(0, int(limit)):
            stats["skipped_limit"] += 1
            continue
        detail_fetches += 1
        try:
            detail = _get(link)
            detail.raise_for_status()
            time.sleep(0.8)
            soup = _prepare_soup(detail.text)
            meta = soup.find("meta", attrs={"property": "og:title"})
            page_title = meta.get("content") if meta else ""
            if not page_title:
                heading = soup.find("h1")
                page_title = heading.get_text(" ", strip=True) if heading else title
            _process_record(
                index,
                page_title or title,
                detail.text,
                link,
                published.isoformat() if published else "",
                "freejobalert",
                stats,
            )
        except Exception as exc:
            stats["errors"] += 1
            print(f"  [!] FreeJobAlert detail failed: {exc}")

    return _finish("freejobalert", stats)
