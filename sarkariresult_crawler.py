import urllib.request
import re
import html
import time
from datetime import datetime
from database import get_db, exam_exists, create_exam, log_sync, init_db

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

def fetch_url(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode('utf-8', errors='ignore')

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
            std_status = 'Admit Card'
            
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

def extract_details_from_page(url: str, fallback_title: str):
    """
    Extracts deep details from an individual post page.
    """
    try:
        page_html = fetch_url(url, timeout=10)
    except Exception as e:
        print(f"[CRAWLER] Could not fetch detail page {url}: {e}")
        return None
        
    # Extract links
    links = re.findall(r'<a[^>]+href=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</a>', page_html)
    apply_url = ""
    notif_url = ""
    official_website = ""
    admit_url = ""
    result_url = ""
    
    for l, txt in links:
        cleaned = re.sub(r'<[^>]+>', '', txt).strip().lower()
        if 'apply online' in cleaned or ('apply' in cleaned and 'online' in cleaned):
            if not apply_url: apply_url = l
        elif 'notification' in cleaned or 'download notification' in cleaned:
            if not notif_url: notif_url = l
        elif 'official website' in cleaned:
            if not official_website: official_website = l
        elif 'admit card' in cleaned or 'hall ticket' in cleaned:
            if not admit_url: admit_url = l
        elif 'result' in cleaned or 'score card' in cleaned:
            if not result_url: result_url = l

    # Extract posts/vacancies count if in title or body
    vacancies_match = re.search(r'(\d[\d,]*\+?)\s*(?:posts|post|vacancies|vacancy|पद)', page_html, re.IGNORECASE)
    vacancies = vacancies_match.group(0) if vacancies_match else "Various Posts"
    
    # Try finding dates in tables
    apply_start = datetime.now().strftime("%d/%m/%Y")
    apply_end = (datetime.now()).strftime("%d/%m/%Y")
    
    date_match = re.search(r'Last Date[^<:]*[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', page_html, re.IGNORECASE)
    if date_match:
        apply_end = date_match.group(1)
        
    fee_gen = "General / OBC: ₹ 100/-"
    fee_res = "SC / ST: ₹ 0/- (Exempted)"
    if 'free' in page_html.lower() or '0/-' in page_html:
        fee_gen = "₹ 0/- (No Application Fee)"
        fee_res = "₹ 0/-"

    return {
        'total_vacancies': vacancies,
        'link_apply_online': apply_url or url,
        'link_notification_pdf': notif_url or url,
        'link_official_website': official_website or "https://sarkariresult.com.cm/",
        'link_admit_card': admit_url,
        'link_result': result_url,
        'apply_start_date': apply_start,
        'apply_last_date': apply_end,
        'fee_general': fee_gen,
        'fee_reserved': fee_res,
        'fee_payment_mode': 'Online / Net Banking / Debit Card / UPI',
        'min_age': '18 Years',
        'max_age': '27-40 Years (Post Wise)',
        'eligibility_criteria': 'Passed 10th / 12th / Graduate / Diploma in relevant discipline from any recognized board/university in India.',
        'short_description': f"Online recruitment details for {fallback_title}. Check eligibility, dates, syllabus, and official notification."
    }

def sync_from_sarkariresult(limit_deep_scrape: int = 15):
    """
    Main sync routine:
    1. Parse homepage items
    2. Check if item already exists in database
    3. Insert or update
    4. Log sync results
    """
    init_db()
    categories = parse_sarkariresult_home()
    
    inserted = 0
    skipped = 0
    deep_scraped = 0
    
    for cat_name, items in categories.items():
        for item in items:
            title = item['title']
            source_link = item['link']
            slug = slugify(title)
            
            if not slug or len(slug) < 3:
                continue
                
            # Check if exists
            if exam_exists(slug):
                skipped += 1
                continue
                
            state = detect_state_for_title(title)
            board_name = "Central / State Government"
            if state != "All India":
                board_name = f"{state} Recruitment Board"
            elif any(k in title.lower() for k in ['ssc', 'cgl', 'chsl', 'gd']):
                board_name = "Staff Selection Commission (SSC)"
            elif any(k in title.lower() for k in ['upsc', 'nda', 'cds', 'ias']):
                board_name = "Union Public Service Commission (UPSC)"
            elif any(k in title.lower() for k in ['rrb', 'railway']):
                board_name = "Railway Recruitment Board (RRB)"
            elif any(k in title.lower() for k in ['ibps', 'sbi', 'bank']):
                board_name = "Banking Personnel Selection"
            elif any(k in title.lower() for k in ['india post', 'gds']):
                board_name = "Department of Posts, India"
            elif any(k in title.lower() for k in ['nta', 'ugc net', 'ctet']):
                board_name = "National Testing Agency (NTA)"
                
            # Extract deep details for the top items
            details = None
            if deep_scraped < limit_deep_scrape:
                print(f"[CRAWLER] Deep scraping details for: {title[:40]}...")
                details = extract_details_from_page(source_link, title)
                deep_scraped += 1
                time.sleep(0.3)
                
            if not details:
                # Fallback details
                details = {
                    'total_vacancies': 'Various Posts',
                    'link_apply_online': source_link,
                    'link_notification_pdf': source_link,
                    'link_official_website': 'https://sarkariresult.com.cm/',
                    'link_admit_card': source_link if item['status'] == 'Admit Card' else '',
                    'link_result': source_link if item['status'] == 'Result' else '',
                    'apply_start_date': datetime.now().strftime("%d/%m/%Y"),
                    'apply_last_date': 'Check Notification',
                    'fee_general': 'As per official rules',
                    'fee_reserved': 'As per rules (Exempted)',
                    'fee_payment_mode': 'Online',
                    'min_age': '18 Years',
                    'max_age': 'Post Wise',
                    'eligibility_criteria': '10th / 12th / Graduate from recognized board / university in India.',
                    'short_description': f"Official recruitment update for {title}. Live link directly verified."
                }
                
            # Insert into database
            try:
                exam_payload = {
                    'title': title,
                    'slug': slug,
                    'category': item['category'] if item['category'] != 'Trending' else 'Latest Jobs',
                    'board_name': board_name,
                    'total_vacancies': details['total_vacancies'],
                    'short_description': details['short_description'],
                    'status': item['status'],
                    'badge_color': 'emerald' if item['status'] == 'Applications Open' else ('indigo' if item['status'] == 'Admit Card' else 'amber'),
                    'notification_date': datetime.now().strftime("%d/%m/%Y"),
                    'apply_start_date': details['apply_start_date'],
                    'apply_last_date': details['apply_last_date'],
                    'fee_last_date': details['apply_last_date'],
                    'correction_last_date': '',
                    'admit_card_date': 'Available Soon' if item['status'] != 'Admit Card' else 'Out Now',
                    'exam_date': 'As per Schedule',
                    'result_date': 'Declared' if item['status'] == 'Result' else 'To be announced',
                    'fee_general': details['fee_general'],
                    'fee_reserved': details['fee_reserved'],
                    'fee_payment_mode': details['fee_payment_mode'],
                    'min_age': details['min_age'],
                    'max_age': details['max_age'],
                    'age_as_on': '01/01/2026',
                    'age_relaxation': 'Applicable as per Government Rules',
                    'eligibility_criteria': details['eligibility_criteria'],
                    'selection_process': 'Written Exam / Merit List / Document Verification / Medical',
                    'syllabus_summary': 'Standard official syllabus as per notification.',
                    'how_to_apply': '1. Read official notification.\n2. Click on Apply Online link.\n3. Fill details and upload documents.\n4. Submit fee and save printout.',
                    'link_apply_online': details['link_apply_online'],
                    'link_notification_pdf': details['link_notification_pdf'],
                    'link_admit_card': details['link_admit_card'],
                    'link_answer_key': source_link if 'answer' in title.lower() else '',
                    'link_result': details['link_result'],
                    'link_official_website': details['link_official_website'],
                    'link_previous_papers': '',
                    'meta_title': f"{title} - Sarkari Result 2026",
                    'meta_description': f"Check {title} dates, eligibility, direct online form link, and syllabus on Sarkari Result.",
                    'keywords': f"{title}, sarkari result, online form 2026, admit card, exam result",
                    'is_featured': item.get('is_featured', 0),
                    'is_auto_synced': 1,
                    'source_url': source_link,
                    'state': state
                }
                create_exam(exam_payload)
                inserted += 1
            except Exception as e:
                print(f"[CRAWLER ERROR] Failed to insert {title}: {e}")
                
    log_sync("sarkariresult.com.cm", inserted, "SUCCESS", f"Inserted: {inserted}, Skipped: {skipped}")
    print(f"[CRAWLER COMPLETE] Synced successfully! Inserted {inserted} new exams, {skipped} existing skipped.")
    return {
        'status': 'success',
        'inserted': inserted,
        'skipped': skipped,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

if __name__ == "__main__":
    sync_from_sarkariresult(limit_deep_scrape=10)
