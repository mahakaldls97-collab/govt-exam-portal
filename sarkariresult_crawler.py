import re
import html
import time
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from database import get_db, exam_exists, create_exam, update_exam, log_sync, init_db
from data_quality import (
    clean_title, ensure_slug, is_junk_title, normalize_record, dedupe_key, parse_date, clean_url,
)

BASE_URL = "https://sarkariresult.com.cm/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# State detection rules
STATE_DETECTION_RULES = {
    'Rajasthan': ['rajasthan', 'rsmssb', 'rpsc', 'reet', 'safai karmchari', 'raj ', 'jaipur', 'jodhpur'],
    'Uttar Pradesh': ['uttar pradesh', 'up ', 'upsssc', 'uppsc', 'upessc', 'uptet', 'uppbpb', 'lucknow', 'up tgt', 'up pgt', 'lekhpal', 'upcisb', 'anganwadi'],
    'Bihar': ['bihar', 'bpsc', 'bssc', 'bpssc', 'bcece', 'bseb', 'patna', 'deled', 'vidhan parishad'],
    'Madhya Pradesh': ['madhya pradesh', 'mp ', 'mppsc', 'mpesb', 'vyapam', 'bhopal', 'krashi vistar'],
    'Haryana': ['haryana', 'hssc', 'hpsc', 'htet', 'panchkula'],
    'Delhi': ['delhi', 'dsssb', 'delhi high court'],
    'Maharashtra': ['maharashtra', 'mpsc', 'mumbai', 'pune'],
    'Gujarat': ['gujarat', 'gpsc', 'gsssb'],
    'Punjab': ['punjab', 'ppsc', 'psssb'],
    'Uttarakhand': ['uttarakhand', 'ukpsc', 'uksssc', 'utet'],
    'Jharkhand': ['jharkhand', 'jssc', 'jpsc'],
    'Chhattisgarh': ['chhattisgarh', 'cgpsc', 'cgvyapam'],
    'West Bengal': ['west bengal', 'wbpsc', 'kolkata'],
    'Odisha': ['odisha', 'ossc', 'opsc'],
    'All India': ['ssc', 'upsc', 'railway', 'rrb', 'ibps', 'sbi', 'bank', 'nta', 'ugc net', 'csir', 'air force', 'army', 'navy', 'bsf', 'crpf', 'isro', 'india post', 'gds', 'ctet', 'afcat', 'nda', 'cds', 'iob', 'emrs']
}

def detect_state_for_title(title: str) -> str:
    t = title.lower()
    for state, keywords in STATE_DETECTION_RULES.items():
        if state == 'All India':
            continue
        if any(kw in t for kw in keywords):
            return state
    # Default to All India for central / general exams
    return 'All India'

def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text).strip('-')
    return text[:90]

def fetch_url(url: str, timeout: int = 20) -> str:
    resp = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return resp.text

def parse_sarkariresult_home():
    """
    Parses the homepage of sarkariresult.com.cm and returns categorized items:
    - Results
    - Admit Cards
    - Latest Jobs
    - Answer Key
    - Trending Highlights
    """
    print(f"[CRAWLER] Fetching homepage from {BASE_URL}...")
    html_content = fetch_url(BASE_URL)
    
    categories = {
        'Results': [],
        'Admit Card': [],
        'Latest Jobs': [],
        'Answer Key': [],
        'Trending': []
    }
    
    # 1. Parse Trending highlight grid boxes
    trending_matches = re.findall(r'<p[^>]+class=[\'"][^\'"]*gb-headline[^\'"]*[\'"][^>]*>\s*<a[^>]+href=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</a>', html_content)
    for link, raw_title in trending_matches:
        clean_title = re.sub(r'<[^>]+>', '', raw_title).replace('&#8211;', '-').strip()
        if len(clean_title) > 5 and not any(k in clean_title.lower() for k in ['meditation', 'whatsapp', 'tools', 'view more']):
            categories['Trending'].append({
                'title': clean_title,
                'link': link,
                'category': 'Latest Jobs',
                'status': 'Applications Open',
                'is_featured': 1
            })

    # 2. Extract column containers
    section_pattern = re.compile(
        r'<p[^>]+class=[\'"][^\'"]*gb-headline-text[\'"][^>]*>\s*(Results|Admit Cards|Latest Jobs|Answer Key)\s*</p>\s*<ul[^>]*>(.*?)</ul>',
        re.DOTALL | re.IGNORECASE
    )
    
    for match in section_pattern.finditer(html_content):
        sec_name = match.group(1).strip()
        list_html = match.group(2)
        
        # Standardize category name
        std_cat = 'Results'
        std_status = 'Result'
        if 'admit' in sec_name.lower():
            std_cat = 'Admit Card'
            std_status = 'Admit Card'
        elif 'latest' in sec_name.lower() or 'jobs' in sec_name.lower():
            std_cat = 'Latest Jobs'
            std_status = 'Applications Open'
        elif 'answer' in sec_name.lower():
            std_cat = 'Answer Key'
            std_status = 'Answer Key'
            
        items = re.findall(r'<a[^>]+class=[\'"]wp-block-latest-posts__post-title[\'"][^>]*href=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</a>', list_html)
        for link, raw_title in items:
            clean_title = re.sub(r'<[^>]+>', '', raw_title).replace('&#8211;', '-').replace('&amp;', '&').strip()
            clean_title = html.unescape(clean_title)
            
            categories[std_cat].append({
                'title': clean_title,
                'link': link,
                'category': std_cat,
                'status': std_status,
                'is_featured': 0
            })
            
    total_found = sum(len(v) for v in categories.values())
    print(f"[CRAWLER] Homepage parsed successfully! Found {total_found} items across categories.")
    return categories

DATE_TOKEN = r"(\d{1,2}\s+[A-Za-z]{3,9},?\s+\d{4}|\d{1,2}[./-]\d{1,2}[./-]\d{4})"

def _labeled_date(text, labels):
    for label in labels:
        m = re.search(rf"{label}[^\d\n]{{0,90}}{DATE_TOKEN}", text, re.I)
        if m and parse_date(m.group(1)):
            return m.group(1)
    return ""

def extract_details_from_page(url: str, fallback_title: str):
    """Extract only facts explicitly present on the page. No invented dates or fees."""
    try:
        page_html = fetch_url(url, timeout=20)
    except Exception as e:
        print(f"[CRAWLER] Could not fetch detail page {url}: {e}")
        return None

    soup = BeautifulSoup(page_html, 'html.parser')
    for tag in soup(['script', 'style', 'noscript', 'iframe']):
        tag.decompose()
    text = soup.get_text("\n", strip=True)

    apply_url = notif_url = official_website = admit_url = result_url = answer_url = ""
    fallback_gov_url = ""

    for anchor in soup.find_all('a', href=True):
        href = clean_url(anchor.get('href'))
        if not href:
            continue
        label = anchor.get_text(" ", strip=True).lower()
        host = href.lower()
        if ('.gov.in' in host or '.nic.in' in host) and not fallback_gov_url:
            fallback_gov_url = href
        if not official_website and 'official website' in label:
            official_website = href
        elif not apply_url and ('apply online' in label or 'online form' in label or 'application form' in label):
            apply_url = href
        elif not notif_url and ('notification' in label or 'download' in label and 'pdf' in label):
            notif_url = href
        elif not admit_url and ('admit card' in label or 'hall ticket' in label):
            admit_url = href
        elif not answer_url and ('answer key' in label or 'response sheet' in label):
            answer_url = href
        elif not result_url and ('result' in label or 'score card' in label or 'merit list' in label):
            result_url = href

    if not official_website:
        official_website = fallback_gov_url

    apply_start = _labeled_date(text, (
        'online application start', 'application begin', 'application start',
        'start date', 'apply start', 'registration start', 'आवेदन प्रारंभ', 'आवेदन शुरू',
    ))
    apply_last = _labeled_date(text, (
        'online application last date', 'last date to apply', 'last date for apply',
        'last date', 'closing date', 'form last date', 'अंतिम तिथि',
    ))
    exam_date = _labeled_date(text, ('exam date', 'examination date', 'cbt date', 'परीक्षा तिथि'))
    result_date = _labeled_date(text, ('result date', 'result declared', 'परिणाम तिथि'))

    vacancies = "Various Posts"
    m = re.search(r'(?:total\s*(?:posts|vacancies)|कुल\s*पद)[^\d\n]{0,20}(\d[\d,]*)', text, re.I)
    if not m:
        m = re.search(r'(\d[\d,]*)\s*(?:posts|post|vacancies|vacancy|पद)', text, re.I)
    if m:
        vacancies = f"{m.group(1)} Posts"

    fee_gen = fee_res = "As per notification"
    m = re.search(r'(?:general|UR|OBC)[^\n₹]{0,30}(₹\s?[\d,]+)', text, re.I)
    if m:
        fee_gen = m.group(1)
    m = re.search(r'(?:SC\s*/?\s*ST|reserved|female)[^\n₹]{0,30}(₹\s?[\d,]+)', text, re.I)
    if m:
        fee_res = m.group(1)

    return {
        'total_vacancies': vacancies,
        'link_apply_online': apply_url,
        'link_notification_pdf': notif_url,
        'link_official_website': official_website,
        'link_admit_card': admit_url,
        'link_answer_key': answer_url,
        'link_result': result_url,
        'apply_start_date': apply_start,
        'apply_last_date': apply_last,
        'exam_date': exam_date,
        'result_date': result_date,
        'fee_general': fee_gen,
        'fee_reserved': fee_res,
        'fee_payment_mode': 'Online / Net Banking / Debit Card / UPI',
        'min_age': 'As per notification',
        'max_age': 'As per notification',
        'age_as_on': 'As per notification',
        'age_relaxation': 'As per Government rules',
        'eligibility_criteria': 'Post-wise qualification official notification में दी गई है।',
        'selection_process': 'Official notification के अनुसार।',
        'syllabus_summary': 'Official notification में syllabus और exam pattern देखें।',
        'short_description': f"{fallback_title} — dates, eligibility, vacancy and official links. Full details official notification में देखें।",
    }

def sync_from_sarkariresult(limit_deep_scrape: int = 50):
    """Parse the homepage, enrich with detail pages, and upsert without duplicates."""
    init_db()
    categories = parse_sarkariresult_home()

    existing_map = {}
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM exams")
    for row in cursor.fetchall():
        existing_map.setdefault(dedupe_key(row['title']), row['id'])
    conn.close()

    inserted = 0
    updated = 0
    skipped = 0
    deep_scraped = 0
    seen = set()

    for cat_name, items in categories.items():
        for item in items:
            title = clean_title(item.get('title', ''))
            source_link = item.get('link', '')
            if not title or not source_link or is_junk_title(title):
                skipped += 1
                continue

            key = dedupe_key(title)
            if key in seen:
                continue
            seen.add(key)

            details = None
            if deep_scraped < limit_deep_scrape:
                print(f"[CRAWLER] Deep scraping details for: {title[:50]}...")
                details = extract_details_from_page(source_link, title)
                deep_scraped += 1
                time.sleep(0.2)

            payload = {
                'title': title,
                'slug': ensure_slug(title),
                'category': item.get('category', 'Latest Jobs'),
                'board_name': '',
                'total_vacancies': 'Various Posts',
                'short_description': f"{title} — latest update with official links and important dates.",
                'status': item.get('status', 'Applications Open'),
                'notification_date': datetime.now().strftime('%d/%m/%Y'),
                'apply_start_date': '',
                'apply_last_date': '',
                'fee_last_date': '',
                'exam_date': '',
                'result_date': '',
                'fee_general': 'As per notification',
                'fee_reserved': 'As per notification',
                'fee_payment_mode': 'Online / Net Banking / Debit Card / UPI',
                'min_age': 'As per notification',
                'max_age': 'As per notification',
                'age_as_on': 'As per notification',
                'age_relaxation': 'As per Government rules',
                'eligibility_criteria': 'Post-wise qualification official notification में दी गई है।',
                'selection_process': 'Official notification के अनुसार।',
                'syllabus_summary': 'Official notification में syllabus और exam pattern देखें।',
                'how_to_apply': '1. Official notification पढ़ें।\n2. Apply Online लिंक खोलें।\n3. फॉर्म भरकर दस्तावेज अपलोड करें।\n4. शुल्क जमा करके प्रिंट निकालें।',
                'link_apply_online': '',
                'link_notification_pdf': '',
                'link_admit_card': '',
                'link_answer_key': '',
                'link_result': '',
                'link_official_website': '',
                'link_previous_papers': '',
                'is_featured': item.get('is_featured', 0),
                'is_auto_synced': 1,
                'source_url': source_link,
            }
            if details:
                payload.update({k: v for k, v in details.items() if v})

            payload = normalize_record(payload, cap_content=True)
            try:
                if key in existing_map:
                    exam_id = existing_map[key]
                    if details:
                        update_payload = {
                            'status': payload['status'],
                            'total_vacancies': payload['total_vacancies'],
                            'short_description': payload['short_description'],
                            'category': payload['category'],
                            'state': payload['state'],
                            'board_name': payload['board_name'],
                        }
                        for field in ('notification_date', 'apply_start_date', 'apply_last_date', 'exam_date', 'result_date'):
                            if parse_date(payload.get(field)):
                                update_payload[field] = payload[field]
                        for field in (
                            'link_apply_online', 'link_notification_pdf', 'link_admit_card',
                            'link_answer_key', 'link_result', 'link_official_website',
                        ):
                            if payload.get(field):
                                update_payload[field] = payload[field]
                        update_exam(exam_id, update_payload)
                        updated += 1
                    else:
                        skipped += 1
                    continue

                base_slug = payload['slug']
                counter = 1
                while exam_exists(payload['slug']):
                    payload['slug'] = f"{base_slug}-{counter}"
                    counter += 1
                exam_id = create_exam(payload)
                existing_map[key] = exam_id
                inserted += 1
            except Exception as e:
                print(f"[CRAWLER ERROR] Failed to save {title}: {e}")
                skipped += 1

    msg = f"sarkariresult.com.cm sync: {inserted} new, {updated} updated, {skipped} skipped."
    log_sync("SUCCESS", inserted + updated + skipped, inserted, msg)
    print(f"[CRAWLER COMPLETE] {msg}")
    return {
        'status': 'success',
        'items_added': inserted,
        'items_updated': updated,
        'skipped': skipped,
        'deep_scraped': deep_scraped,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

if __name__ == "__main__":
    sync_from_sarkariresult(limit_deep_scrape=20)
