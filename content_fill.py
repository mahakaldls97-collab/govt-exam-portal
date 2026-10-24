"""Backfill missing or vague exam fields by re-reading the stored source article.

Every synced exam keeps its full source HTML in content_html, so fields the
scrapers missed (vacancy counts, dates, fees, direct links) can be recovered
without touching the network. Only empty or placeholder values are replaced, and
a value is written only when it is concrete - nothing is ever invented.
"""

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from data_quality import parse_date

VAGUE_TOKENS = {
    "", "-", "--", "na", "n/a", "n.a.", "none", "tbd", "to be decided",
    "various posts", "as per schedule", "as per notification", "as per rules",
    "as per advertisement", "check official portal", "check official notification",
    "check notification", "notify later", "notified later", "to be notified",
    "after examination", "before examination", "coming soon", "not mentioned",
    "information not available", "available soon", "declared", "updates",
    "10th / 12th / graduate or relevant qualification as per post",
    "selection will be held as per the official notification",
}

DATE_FIELDS = (
    "notification_date", "apply_start_date", "apply_last_date",
    "fee_last_date", "correction_last_date", "admit_card_date",
    "exam_date", "result_date",
)

LABEL_PATTERNS = {
    "total_vacancies": r"(total|no\.?|number).*(vacanc|post)|vacanc|रिक्तियां|कुल पद|पद संख्या|total recruitment",
    "apply_start_date": r"(application|apply|online|form|आवेदन|रजिस्ट्रेशन).*(start|begin|प्रारंभ|शुरू)|(start|begin).*date",
    "apply_last_date": r"(last|final|closing|अंतिम).*(date|apply|आवेदन|तिथि)|date of closing|आवेदन की अंतिम",
    "fee_last_date": r"(fee|payment|शुल्क).*(last|final) *(date|तिथि)?|last date.*fee",
    "correction_last_date": r"correction.*(last|date)|संशोधन.*(अंतिम|तिथि)",
    "admit_card_date": r"(admit card|pre[- ]admit|hall ticket|एडमिट कार्ड|परीक्षा पत्र).*(date|तिथि|तारीख|issue|available|कब)|चुन परीक्षा पत्र",
    "exam_date": r"(exam|examination|written|cbe|cbt|interview|परीक्षा|इंटरव्यू|मेगा).*?(date|तारीख|तिथि|schedule)|date of (exam|test|interview)|परीक्षा की तारीख",
    "result_date": r"(result|merit list|selected candidate|रिजल्ट|परिणाम).*(date|तारीख|तिथि|declared|घोषित)|राजपत्रित",
    "fee_general": r"(application|apply|processing|exam|recovery).*(fee|charges|शुल्क|रुपये)|फीस|शुल्क",
    "min_age": r"(min|minimum|lower).*(age|आयु)|age.*(min|minimum)|न्यूनतम आयु|आयु सीमा|age limit|आयु",
    "max_age": r"(max|maximum|upper).*(age|आयु)|age.*(max|maximum)|अधिकतम आयु|आयु सीमा|age limit|आयु",
    "pay_level": r"pay level|pay scale|वेतन ंश|pay matrix|level.*cpc",
    "advt_no": r"advertis.*(no|number)|advt\.? *no|क्रमांक",
    "link_official_website": r"official (website|portal|site)|आधिकारिक वेबसाइट|वेबसाइट",
    "link_notification_pdf": r"(official |o/o )?notification|advertisement pdf|नोटिफिकेशन|आधिकारिक पत्र",
    "link_apply_online": r"(apply|registration|online form|आवेदन|रजिस्ट्रेशन).*(online|here|click|link)?|click here.*apply|apply",
    "link_admit_card": r"admit card|pre[- ]admit|hall ticket|एडमिट कार्ड",
    "link_answer_key": r"answer key|response sheet|rebuttal|उत्तर कुंजी",
    "link_result": r"result|merit list|selected list|रिजल्ट|परिणाम",
}

LINK_FIELDS = (
    "link_official_website", "link_notification_pdf", "link_apply_online",
    "link_admit_card", "link_answer_key", "link_result",
)

# Prose fields (eligibility, selection process) are left alone on purpose: a wrong
# specific sentence reads like fact, while the generic wording is honestly vague.
VAGUE_TARGET_FIELDS = tuple(LABEL_PATTERNS) + (
    "total_vacancies", "notification_date", "apply_start_date", "apply_last_date",
    "fee_last_date", "correction_last_date", "admit_card_date", "exam_date",
    "result_date", "fee_general", "fee_reserved", "min_age", "max_age",
)

AGGREGATOR_HOSTS = (
    "vacancy", "sarkari", "jobalert", "result", "recruitmentresult", "examresult",
    "scholarship", "admission", "khabar", "newsonair", "testbook", "jagran",
    "news18", "amar ujala", "quikr", "indeed", "timesjob", "shiksha", "collegedunia",
)
OFFICIAL_HOST_HINTS = (".gov.in", ".nic.in", ".edu.in", ".ac.in", ".gov", "nabard", "ibps",
                        "sbi.co.in", "pnbfls.com", "canbank", "unionbank", "indianbank",
                        "parikshasaarthi", "nta", "upsc", "ssc", "rbi", "isro", "drdo")

_TEXT_FALLBACK = {
    "total_vacancies": r"total (?:no\.? of )?(?:vacanc(?:y|ies)|posts?)\s*[:\-–]\s*([\d,]{1,9})",
    "apply_last_date": r"(?:last date|अंतिम तिथि|closing date)\s*(?:to apply|के लिए)?\s*[:\-–]?\s*([^\n<]{4,40})",
    "apply_start_date": r"(?:start date|आवेदन प्रारंभ|application begin)\s*[:\-–]?\s*([^\n<]{4,40})",
    "exam_date": r"(?:exam(?:ination)? date|date of exam|परीक्षा तिथि|परीक्षा की तारीख)\s*[:\-–]?\s*([^\n<]{4,40})",
    "admit_card_date": r"(?:admit card|pre[- ]admit card) (?:date|issue)\s*[:\-–]?\s*([^\n<]{4,40})",
    "result_date": r"result date\s*[:\-–]?\s*([^\n<]{4,40})",
    "fee_general": r"(?:application|examination) fee\s*[:\-–]?\s*(?:rs\.?|₹|rupees)?\s*([\d,]{1,7})",
    "min_age": r"age limit\s*[:\-–]?\s*(\d{2})\s*(?:-|to|से)\s*\d{2,3}",
    "max_age": r"age limit\s*[:\-–]?\s*\d{2}\s*(?:-|to|से)\s*(\d{2,3})",
    "advt_no": r"advertisement no\.?\s*[:\-–]?\s*([A-Za-z0-9/\- ]{4,40})",
}


def is_vague(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip().strip(":- ").lower()
    if not text:
        return True
    if text in VAGUE_TOKENS:
        return True
    return any(token in text for token in (
        "as per notification", "as per rules", "as per schedule", "not mentioned",
        "check official", "विस्तृत जानकारी नोटिफिकेशन", "आधिकारिक अधिसूचना",
    ))


def _clean(value, limit=90):
    text = re.sub(r"\s+", " ", str(value or "")).strip().strip(":-–| ")
    return text[:limit].rstrip()


def _specific(field, raw):
    """Return a trustworthy value for this field, or '' when the text is not concrete."""
    value = _clean(raw)
    if not value:
        return ""
    if field in DATE_FIELDS:
        parsed = parse_date(value)
        return parsed.isoformat() if parsed else ""
    if field == "total_vacancies":
        number = re.search(r"\d[\d,]*", value)
        if not number:
            return ""
        total = int(number.group(0).replace(",", ""))
        if total <= 0 or total > 500000:
            return ""
        return f"{total:,} Posts"
    if field in ("fee_general", "fee_reserved"):
        rupees = re.search(r"(?:rs\.?|₹|rupees)\s*([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s*(?:rs\.?|₹)", value, re.I)
        if not rupees:
            return ""
        amount = (rupees.group(1) or rupees.group(2)).replace(",", "")
        if float(amount) > 100000:
            return ""
        return f"Rs. {amount}/"
    if field == "advt_no":
        if re.fullmatch(r"(19|20)\d\d", value) or not re.search(r"\d", value):
            return ""
        return value if len(value) >= 5 else ""
    if field == "pay_level" and not re.search(r"level|cpc|pay scale|वेतन ंश", value, re.I):
        return ""
    if field == "min_age":
        ages = [int(a) for a in re.findall(r"\b(\d{2})\b", value) if 15 <= int(a) <= 42]
        return f"{min(ages)} Years" if ages else ""
    if field == "max_age":
        ages = [int(a) for a in re.findall(r"\b(\d{2,3})\b", value) if 17 <= int(a) <= 70]
        return f"{max(ages)} Years" if ages else ""
    if field.startswith("link_"):
        return value if value.lower().startswith(("http://", "https://")) else _bare_domain(value)
    if is_vague(value):
        return ""
    return value


def _bare_domain(text):
    match = re.search(r"\b(?:https?://)?([a-z0-9][a-z0-9.\-]*\.(?:gov\.in|nic\.in|org|com|in|net)\b[a-z0-9./\-]*)",
                      text.lower())
    if not match:
        return ""
    domain = match.group(1)
    return domain if domain.startswith("http") else f"https://{domain}"


def _table_pairs(soup):
    pairs = []
    for tr in soup.select("tr"):
        cells = [_clean(td.get_text(" ", strip=True), 160) for td in tr.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if len(cells) == 2:
            pairs.append((cells[0], cells[1]))
        elif len(cells) == 3 and _clean(cells[2], 160):
            pairs.append((cells[0], cells[2]))
    return pairs


def _sum_post_wise_vacancies(soup):
    total = 0
    for table in soup.select("table"):
        header = [c.get_text(" ", strip=True).lower()
                  for tr in table.select("tr")[:2] for c in tr.find_all(["th", "td"])]
        if not any(re.search(r"vacanc|रिक्त|no\.? of post|total post|^posts?$", h) for h in header):
            continue
        seen = set()
        subtotal = 0
        for tr in table.select("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            label = cells[1] if len(cells) >= 3 else cells[0]
            number = re.fullmatch(r"\+?([\d,]{1,7})", cells[-1].replace(" ", ""))
            if not number or not label:
                continue
            key = (label.lower(), number.group(1))
            if key in seen:
                continue
            seen.add(key)
            subtotal += int(number.group(1).replace(",", ""))
        if subtotal and total == 0:
            total = subtotal
    return f"{total:,} Posts" if total and total <= 500000 else ""


def _score_link(href, text, field):
    lowered = (href or "").lower()
    if not lowered.startswith(("http://", "https://")):
        return -1
    if "studygovthelp" in lowered or "rojgarresult" in lowered or "freejobalert" in lowered:
        return -1
    host = urlparse(lowered).netloc
    official = any(hint in host for hint in OFFICIAL_HOST_HINTS)
    if not official and any(token in host for token in AGGREGATOR_HOSTS):
        return -1
    score = 40 if official else 12
    if field == "link_notification_pdf" and lowered.endswith(".pdf"):
        score += 30
    if any(word in (text or "").lower() for word in ("click", "here", "check", "download", "apply", "official")):
        score += 8
    if text:
        score += 5
    return score


def _links(soup):
    found = {}
    for anchor in soup.select("a[href]"):
        href = (anchor.get("href") or "").strip()
        text = anchor.get_text(" ", strip=True)[:80]
        haystack = f"{text} {href}".lower()
        for field, pattern in (("link_notification_pdf", r"notification|advertis|अधिसूचना"),
                               ("link_apply_online", r"apply|registration|online form|आवेदन"),
                               ("link_admit_card", r"admit card|pre admit|एडमिट"),
                               ("link_answer_key", r"answer key|response sheet|rebuttal|उत्तर कुंजी"),
                               ("link_result", r"result|merit|रिजल्ट"),
                               ("link_official_website", r"official (website|portal)|आधिकारिक वेबसाइट")):
            if not re.search(pattern, haystack):
                continue
            score = _score_link(href, text, field)
            if score < 0:
                continue
            if found.get(field, ("", -1))[1] < score:
                found[field] = (href, score)
    return {field: value[0] for field, value in found.items()}


def extract_from_content(content_html):
    if not content_html or len(content_html) < 200:
        return {}
    soup = BeautifulSoup(content_html, "html.parser")
    pairs = _table_pairs(soup)
    filled = {}

    for field, pattern in LABEL_PATTERNS.items():
        if field not in VAGUE_TARGET_FIELDS:
            continue
        for label, value in pairs:
            if not re.search(pattern, label.lower(), re.I):
                continue
            candidate = _specific(field, value)
            if candidate and (field not in filled or not is_vague(filled[field])):
                filled[field] = candidate
                break

    text = soup.get_text("\n", strip=True)
    for field, pattern in _TEXT_FALLBACK.items():
        if filled.get(field) and not is_vague(filled[field]):
            continue
        match = re.search(pattern, text, re.I)
        if match:
            candidate = _specific(field, match.group(1) if match.groups() else match.group(0))
            if candidate:
                filled[field] = candidate

    if not filled.get("total_vacancies") or is_vague(filled.get("total_vacancies", "")):
        summed = _sum_post_wise_vacancies(soup)
        if summed:
            filled["total_vacancies"] = summed

    for field, href in _links(soup).items():
        filled.setdefault(field, href)
    return filled


def fill_exam(exam):
    """Return the fields that should be written for one exam row."""
    recovered = extract_from_content(exam.get("content_html") or "")
    payload = {}
    for field, value in recovered.items():
        current = exam.get(field)
        if field in DATE_FIELDS:
            if current and not is_vague(current) and parse_date(current):
                continue
        elif not is_vague(current):
            continue
        if value and str(value).strip() != str(current or "").strip():
            payload[field] = value
    return payload


_TITLE_VACANCY = re.compile(
    r"\b(\d{1,3}(?:,\d{3})+|\d{2,6})\b([\s\w\u0900-\u097F,()/.\-]{0,28}?)\b(?:posts?|vacanc\w*|seats?|पद|पदों|रिक्तियां)\b", re.I)
_TITLE_VACANCY_FOR = re.compile(r"\b(?:for|of|के लिए)\s*(\d{1,3}(?:,\d{3})+|\d{2,6})\b\s*(?:posts?|seats?|पद|vacanc)?", re.I)
_MULTIPLIERS = (("हजार", 1000), ("thousand", 1000), ("लाख", 100000), ("lakh", 100000))
_SLUG_VACANCY = re.compile(r"-(\d{2,6})(?:-\d{1,3})?$")
_YEAR_RANGE = range(1900, 2101)


def vacancy_from_heading(title, slug):
    """Read a post count the source itself put in the headline or slug."""
    numbers = []
    for match in _TITLE_VACANCY.finditer(str(title or "")):
        value = next((g for g in match.groups() if g), "")
        gap = (match.group(2) or "").lower()
        number = int(value.replace(",", ""))
        for token, factor in _MULTIPLIERS:
            if token in gap:
                number *= factor
                break
        numbers.append(number)
    for match in _TITLE_VACANCY_FOR.finditer(str(title or "")):
        numbers.append(int(match.group(1).replace(",", "")))
    if not numbers:
        match = _SLUG_VACANCY.search(str(slug or ""))
        if match:
            numbers.append(int(match.group(1)))
    for number in numbers:
        if number in _YEAR_RANGE or number > 500000:
            continue
        return f"{number:,} Posts"
    return ""


_TIME_RANGE = re.compile(r"\(\s*\d{1,2}[:.]\d{2}\s*[APap]\.?[Mm]\.?\s*(?:to|-|–)\s*\d{1,2}[:.]\d{2}\s*[APap]\.?[Mm]\.?\s*\)")
_DMY = re.compile(r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}")
_MULTI_DATE = re.compile(r"\b(?:to|से|tak|तक)\b|[-–]", re.I)


def _single_date(raw):
    """Parse only when the text is one date; ranges like "12 July to 18 July 2026" stay as written."""
    text = str(raw).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return None
    if _DMY.fullmatch(text):
        return parse_date(text)
    stripped = _TIME_RANGE.sub(" ", text)
    if _MULTI_DATE.search(stripped) and re.search(r"\d", stripped):
        return None
    return parse_date(text)


def normalize_dates(conn, apply_changes=True):
    """Rewrite free-text dates ("13 नवंबर 2026", "20-03-2026") as ISO so filters and sorting work."""
    changed = 0
    for field in DATE_FIELDS:
        for exam_id, raw in conn.execute(
                f"select id, {field} from exams where coalesce({field},'') != ''"):
            parsed = _single_date(raw)
            if not parsed:
                continue
            changed += 1
            if apply_changes:
                conn.execute(f"update exams set {field} = ? where id = ?", (parsed.isoformat(), exam_id))
    if apply_changes:
        conn.commit()
    return changed


def run_fill(conn, apply_changes=True, limit=None):
    columns = ", ".join(f"e.{f}" for f in VAGUE_TARGET_FIELDS)
    sql = (f"select e.id, e.slug, e.title, e.status, e.content_html, {columns} "
           "from exams e where e.status != 'Archived' and length(coalesce(e.content_html,'')) > 200")
    if limit:
        sql += f" limit {int(limit)}"
    rows = [dict(zip([d[0] for d in conn.execute(sql).description], row))
            for row in conn.execute(sql)]
    stats = {"exams": len(rows), "filled": 0, "fields": {}}
    for row in rows:
        payload = fill_exam(row)
        if is_vague(row.get("total_vacancies")) and not payload.get("total_vacancies"):
            heading = vacancy_from_heading(row.get("title"), row.get("slug"))
            if heading:
                payload["total_vacancies"] = heading
        if not payload:
            continue
        stats["filled"] += 1
        for field, value in payload.items():
            stats["fields"][field] = stats["fields"].get(field, 0) + 1
        if apply_changes:
            assignments = ", ".join(f"{f} = ?" for f in payload)
            conn.execute(f"update exams set {assignments} where id = ?",
                         list(payload.values()) + [row["id"]])
    if apply_changes:
        conn.commit()
    stats["dates_normalized"] = normalize_dates(conn, apply_changes)
    return stats
