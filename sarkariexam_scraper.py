import urllib.request
import xml.etree.ElementTree as ET
import re
import html
from datetime import datetime
from database import get_db, exam_exists, create_exam, log_sync

def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text).strip('-')
    return text[:80]

def detect_status(title: str) -> str:
    t = title.lower()
    if any(k in t for k in ['result', 'cutoff', 'score card', 'merit list', 'marks', 'selected list']):
        return 'Result'
    if any(k in t for k in ['admit card', 'hall ticket', 'call letter', 'exam date', 'exam city', 'city slip', 'exam schedule', 'time table', 'date out', 'exam notice']):
        return 'Admit Card'
    if any(k in t for k in ['answer key', 'response sheet', 'objection']):
        return 'Admit Card'
    if any(k in t for k in ['upcoming', 'soon', 'expected', 'calender', 'calendar']):
        return 'Upcoming'
    return 'Applications Open'

def detect_category(title: str, board_name: str = '') -> str:
    combined = f"{title} {board_name}".lower()
    if any(k in combined for k in ['railway', 'rrb', 'rrc', 'alp', 'ntpc', 'technician', 'group d', 'loco pilot']):
        return 'Railway'
    if any(k in combined for k in ['police', 'constable', 'sub inspector', 'si ', 'asi ', 'daroga', 'home guard', 'army', 'navy', 'air force', 'nda', 'cds', 'agniveer', 'crpf', 'bsf', 'cisf', 'itbp', 'ssb', 'defence', 'defense']):
        return 'Police'
    if any(k in combined for k in ['ctet', 'reet', 'uptet', 'htet', 'btet', 'mptet', 'kvs', 'nvs', 'dsssb prt', 'tgt', 'pgt', 'teacher', 'shikshak', 'bed', 'deled', 'ugc net', 'csir net']):
        return 'Teaching'
    if any(k in combined for k in ['bank', 'ibps', 'sbi', 'rbi', 'nabard', 'sebi', 'lic', 'po ', 'clerk', 'so ']):
        return 'Banking'
    if any(k in combined for k in ['ssc', 'cgl', 'chsl', 'mts', 'cpo', 'gd constable', 'stenographer', 'selection post']):
        return 'SSC'
    if any(k in combined for k in ['upsc', 'ias', 'ips', 'ifs', 'civil services', 'cse', 'nda', 'cds', 'epfo']):
        return 'UPSC'
    if any(k in combined for k in ['rajasthan', 'rsmssb', 'rpsc', 'uttar pradesh', 'upsssc', 'uppsc', 'bihar', 'bpsc', 'bssc', 'madhya pradesh', 'mppsc', 'mpesb', 'haryana', 'hssc', 'delhi', 'dsssb', 'maharashtra', 'mpsc', 'gujarat', 'gpsc', 'punjab', 'ppsc', 'jharkhand', 'jssc', 'odisha', 'ossc', 'west bengal', 'wbpsc', 'assam', 'apsc', 'karnataka', 'kpsc', 'tamil nadu', 'tnpsc', 'andhra pradesh', 'appsc', 'tspsc', 'jkssb']):
        return 'State'
    return 'Others'

def detect_state(title: str):
    t = title.lower()
    state_keywords = {
        'Rajasthan': ('Rajasthan', {'default_board': 'RSMSSB / RPSC Rajasthan'}),
        'Uttar Pradesh': ('Uttar Pradesh', {'default_board': 'UPSSSC / UPPSC Uttar Pradesh'}),
        'Bihar': ('Bihar', {'default_board': 'BPSC / BSSC Bihar'}),
        'Madhya Pradesh': ('Madhya Pradesh', {'default_board': 'MPPSC / MPESB Madhya Pradesh'}),
        'Haryana': ('Haryana', {'default_board': 'HSSC / HPSC Haryana'}),
        'Delhi': ('Delhi', {'default_board': 'DSSSB Delhi'}),
        'Maharashtra': ('Maharashtra', {'default_board': 'MPSC Maharashtra'}),
        'Gujarat': ('Gujarat', {'default_board': 'GPSC / GSSSB Gujarat'}),
        'Punjab': ('Punjab', {'default_board': 'PPSC / PSSSB Punjab'}),
        'Uttarakhand': ('Uttarakhand', {'default_board': 'UKPSC / UKSSSC Uttarakhand'}),
        'Jharkhand': ('Jharkhand', {'default_board': 'JSSC / JPSC Jharkhand'}),
        'Odisha': ('Odisha', {'default_board': 'OSSC / OPSC Odisha'}),
        'Chhattisgarh': ('Chhattisgarh', {'default_board': 'CGPSC Chhattisgarh'}),
        'West Bengal': ('West Bengal', {'default_board': 'WBPSC / WBPRB West Bengal'}),
        'Assam & North East': ('Assam & North East', {'default_board': 'APSC Assam / North East'}),
        'Karnataka': ('Karnataka', {'default_board': 'KPSC Karnataka'}),
        'Tamil Nadu': ('Tamil Nadu', {'default_board': 'TNPSC Tamil Nadu'}),
        'Andhra Pradesh & Telangana': ('Andhra Pradesh & Telangana', {'default_board': 'APPSC / TSPSC'}),
        'Jammu & Kashmir': ('Jammu & Kashmir', {'default_board': 'JKSSB / JKPSC J&K'}),
    }
    for state_name, (detected_state, info) in state_keywords.items():
        if state_name.lower() in t or any(w in t for w in state_name.lower().split()):
            return detected_state, info
    return 'All India', {'default_board': 'Central Government / All India / Others'}

SARKARIEXAM_FEEDS = [
    "https://www.sarkariexam.com/feed/",
    "https://www.sarkariexam.com/category/admit-card/feed/",
    "https://www.sarkariexam.com/category/top-online-form/feed/",
    "https://www.sarkariexam.com/category/exam-result/feed/",
]

SARKARIEXAM_CATEGORIES = [
    "https://www.sarkariexam.com/category/top-online-form/",
    "https://www.sarkariexam.com/category/top-online-form/page/2/",
    "https://www.sarkariexam.com/category/top-online-form/page/3/",
    "https://www.sarkariexam.com/category/admit-card/",
    "https://www.sarkariexam.com/category/admit-card/page/2/",
    "https://www.sarkariexam.com/category/exam-result/",
    "https://www.sarkariexam.com/category/exam-result/page/2/",
    "https://www.sarkariexam.com/category/railway-jobs/",
    "https://www.sarkariexam.com/category/teaching-jobs/",
    "https://www.sarkariexam.com/category/bank-jobs/",
    "https://www.sarkariexam.com/category/defence-jobs/",
    "https://www.sarkariexam.com/"
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

def extract_clean_details(html_content: str, title: str = '') -> dict:
    """
    Extracts deep metadata from individual post HTML on sarkariexam.com:
    - Important Dates (start, last, fee last, exam, admit card)
    - Fees (general, reserved)
    - Age limits (min, max)
    - Total vacancies
    - Direct official links
    - Eligibility and selection process
    """
    details = {}
    
    # 1. Total Vacancies from HTML
    m_vac = re.search(r'Total\s+Posts?\s*[:\-]?\s*([0-9,]+\s*(?:Posts?|Vacanc(?:y|ies)|पद)?)', html_content, re.I)
    if m_vac:
        details['total_vacancies'] = re.sub(r'<[^>]+>', '', m_vac.group(1)).strip()
        
    # Convert HTML to clean plain text lines
    text = re.sub(r'<(?:br|/p|/tr|/td|/li|/h[1-6])[^>]*>', '\n', html_content, flags=re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'[ \t]+', ' ', text)
    
    # 2. Extract Important Dates
    m_start = re.search(r'(?:Application\s+Start|Registration\s+Start|Starting\s+Date|Start\s+Date|प्रारंभ\s+तिथि)[^:\n\r]*:\s*([0-9]{1,2}[^\n\r]+?202[4-7])', text, re.I)
    if m_start:
        details['apply_start_date'] = m_start.group(1).strip()
        
    m_last = re.search(r'(?:Last\s+Date\s+for\s+Apply|Form\s+Submission\s+Last\s+Date|Apply\s+Last\s+Date|Registration\s+Last\s+Date|Last\s+Date|अंतिम\s+तिथि)[^:\n\r]*:\s*([0-9]{1,2}[^\n\r]+?202[4-7])', text, re.I)
    if m_last:
        details['apply_last_date'] = m_last.group(1).strip()
        
    m_fee_last = re.search(r'(?:Fee\s+Payment\s+Last\s+Date|Pee\s+Payment\s+Last\s+Date|Fee\s+Last\s+Date)[^:\n\r]*:\s*([0-9]{1,2}[^\n\r]+?202[4-7])', text, re.I)
    if m_fee_last:
        details['fee_last_date'] = m_fee_last.group(1).strip()
        
    m_exam = re.search(r'(?:Exam\s+Date|CBT\s+Exam\s+Date|Examination\s+Date|Exam\s+Held\s+On|परीक्षा\s+तिथि)[^:\n\r]*:\s*([0-9a-zA-Z\s,-]+?202[4-7]|Available\s+Soon|As\s+per\s+Schedule|(?:September|October|November|December|January|February|March|April|May|June|July|August)\s+(?:Cycle|202[4-7]))', text, re.I)
    if m_exam:
        details['exam_date'] = m_exam.group(1).strip()
    elif title:
        m_t_date = re.search(r'((?:January|February|March|April|May|June|July|August|September|October|November|December)\s*(?:Cycle|202[4-7])|\d{1,2}\s*(?:to|-)\s*\d{1,2}\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*202[4-7]|\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+202[4-7])', title, re.I)
        if m_t_date:
            details['exam_date'] = m_t_date.group(1).strip()
        
    m_admit = re.search(r'(?:Admit\s+Card\s+Date|Admit\s+Card|Exam\s+City\s+Details|प्रवेश\s+पत्र)[^:\n\r]*:\s*([^\n\r]+)', text, re.I)
    if m_admit:
        adm = m_admit.group(1).strip()
        if len(adm) < 45 and not any(k in adm for k in ['{', '}', 'http', 'window']):
            details['admit_card_date'] = adm
            
    # 3. Application Fee
    m_fee_gen = re.search(r'(?:General,\s*OBC[^\n\r:]*|General[^\n\r:]*|GEN\s*/\s*OBC):\s*(Rs\.?\s*[0-9]+/?-?|₹\s*[0-9]+|0/?-?)', text, re.I)
    if m_fee_gen:
        details['fee_general'] = m_fee_gen.group(0).strip()
    m_fee_res = re.search(r'(?:SC,\s*ST[^\n\r:]*|SC\s*/\s*ST[^\n\r:]*):\s*(Rs\.?\s*[0-9]+/?-?|₹\s*[0-9]+|0/?-?)', text, re.I)
    if m_fee_res:
        details['fee_reserved'] = m_fee_res.group(0).strip()
        
    # 4. Age Limit
    m_min_age = re.search(r'Minimum\s+Age\s*:\s*([0-9]+\s*Years?)', text, re.I)
    if m_min_age:
        details['min_age'] = m_min_age.group(1).strip()
    m_max_age = re.search(r'Maximum\s+Age\s*:\s*([0-9]+\s*Years?)', text, re.I)
    if m_max_age:
        details['max_age'] = m_max_age.group(1).strip()
        
    # 5. Direct Action Links from Table
    links = re.findall(r'<a[^>]+href=[\'"](https?://[^\'"]+)[\'"][^>]*>(.*?)</a>', html_content, re.I | re.DOTALL)
    for href, link_text in links:
        t_clean = re.sub(r'<[^>]+>', '', link_text).strip().lower()
        if any(skip in href for skip in ['sarkariexam', 'sarkariresult', 't.me', 'whatsapp', 'play.google', 'youtube', 'facebook', 'instagram', 'age-calculator', 'javascript']):
            continue
        if ('apply' in t_clean or 'registration' in t_clean or 'online form' in t_clean) and 'link_apply_online' not in details:
            details['link_apply_online'] = href
        elif ('notification' in t_clean or 'advt' in t_clean or href.endswith('.pdf') or 'short notice' in t_clean or 'notice' in t_clean) and 'link_notification_pdf' not in details:
            details['link_notification_pdf'] = href
        elif ('official website' in t_clean or 'official portal' in t_clean or 'homepage' in t_clean) and 'link_official_website' not in details:
            details['link_official_website'] = href
        elif ('admit card' in t_clean or 'hall ticket' in t_clean or 'city' in t_clean or 'exam date' in t_clean or 'schedule' in t_clean) and 'link_admit_card' not in details:
            details['link_admit_card'] = href
        elif ('result' in t_clean or 'score' in t_clean or 'merit' in t_clean) and 'link_result' not in details:
            details['link_result'] = href
        elif ('answer key' in t_clean or 'key' in t_clean) and 'link_answer_key' not in details:
            details['link_answer_key'] = href
            
    return details

def fetch_post_html(url: str) -> str:
    """Helper to safely fetch a post HTML"""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode('utf-8', errors='ignore')
    except Exception:
        return ""

def process_exam_entry(title: str, source_url: str) -> bool:
    """Processes a single exam title and URL into portal.db"""
    clean_title = re.sub(r'&#[0-9]+;', '', title)
    clean_title = re.sub(r'\s+', ' ', clean_title).strip()
    
    if len(clean_title) < 8 or any(skip in clean_title.lower() for skip in ['disclaimer', 'contact us', 'privacy policy', 'terms and conditions']):
        return False
        
    slug = slugify(clean_title)
    if exam_exists(slug=slug, title=clean_title, source_url=source_url):
        return False
        
    post_html = fetch_post_html(source_url)
    deep_info = extract_clean_details(post_html, clean_title) if post_html else {}
    
    state_name, state_info = detect_state(clean_title)
    board_name = state_info.get('default_board', 'Central Government / All India / Others')
    
    category = detect_category(clean_title, board_name)
    status = detect_status(clean_title)
    
    # Smart fallbacks based on status
    if status == 'Admit Card':
        apply_start_date = deep_info.get('apply_start_date') or 'Closed (Exam Stage)'
        apply_last_date = deep_info.get('apply_last_date') or 'Closed (Exam Stage)'
    elif status == 'Result':
        apply_start_date = deep_info.get('apply_start_date') or 'Closed (Result Declared)'
        apply_last_date = deep_info.get('apply_last_date') or 'Closed (Result Declared)'
    else:
        apply_start_date = deep_info.get('apply_start_date') or 'Check Official Portal'
        apply_last_date = deep_info.get('apply_last_date') or 'Check Official Portal'
        
    exam_date = deep_info.get('exam_date', '')
    total_vacancies = deep_info.get('total_vacancies') or 'Check Official Notification'
    fee_general = deep_info.get('fee_general') or 'As per official notification'
    fee_reserved = deep_info.get('fee_reserved') or 'As per official notification'
    min_age = deep_info.get('min_age') or '18 Years'
    max_age = deep_info.get('max_age') or 'As per rules'
    
    # Specific Enrichment for major national exams
    t_low = clean_title.lower()
    if 'ctet' in t_low:
        if not exam_date:
            exam_date = 'September / December 2026 (Official Cycle)'
        if 'As per official' in fee_general:
            fee_general = '₹1,000 (Paper I or II) / ₹1,200 (Both Papers)'
            fee_reserved = '₹500 (Paper I or II) / ₹600 (Both Papers)'
        if min_age == '18 Years':
            min_age = '18 Years (No Upper Age Limit)'
        total_vacancies = 'Teacher Eligibility Certification (TET)'
    elif 'rrb' in t_low or 'railway' in t_low:
        if 'As per official' in fee_general:
            fee_general = '₹500 (₹400 Refundable after CBT-1)'
            fee_reserved = '₹250 (Full Refundable after CBT-1)'
    elif 'ssc' in t_low:
        if 'As per official' in fee_general:
            fee_general = '₹100 (General / OBC / EWS)'
            fee_reserved = '₹0 (SC / ST / Female Exempted)'
            
    exam_record = {
        'title': clean_title,
        'slug': slug,
        'category': category,
        'board_name': board_name,
        'total_vacancies': total_vacancies,
        'short_description': f"Official recruitment notification for {clean_title}. Total vacancies: {total_vacancies}. Check eligibility criteria, important dates schedule, application fee, and direct official links.",
        'status': status,
        'notification_date': datetime.now().strftime('%d %B %Y'),
        'apply_start_date': apply_start_date,
        'apply_last_date': apply_last_date,
        'fee_last_date': deep_info.get('fee_last_date', apply_last_date),
        'admit_card_date': deep_info.get('admit_card_date', 'Before Exam Date' if status != 'Admit Card' else 'Available / Released'),
        'exam_date': exam_date,
        'fee_general': fee_general,
        'fee_reserved': fee_reserved,
        'fee_payment_mode': 'Online (Debit/Credit Card, Net Banking, UPI)',
        'min_age': min_age,
        'max_age': max_age,
        'eligibility_criteria': f'Please refer to the official notification document for detailed educational qualification and eligibility criteria for {total_vacancies}.',
        'selection_process': '1. Written Examination / CBT\n2. Document Verification & Merit List\n3. Medical & Physical Test (if applicable)',
        'how_to_apply': f'1. Visit the official website or click Apply Online link.\n2. Read the official advertisement for {clean_title}.\n3. Fill in required details, upload documents, and submit before last date.',
        'link_apply_online': deep_info.get('link_apply_online', deep_info.get('link_official_website', state_info.get('apply_url', ''))),
        'link_notification_pdf': deep_info.get('link_notification_pdf', deep_info.get('link_official_website', state_info.get('official_website', ''))),
        'link_admit_card': deep_info.get('link_admit_card', deep_info.get('link_official_website', '')),
        'link_result': deep_info.get('link_result', deep_info.get('link_official_website', '')),
        'link_answer_key': deep_info.get('link_answer_key', ''),
        'link_official_website': deep_info.get('link_official_website', state_info.get('official_website', 'https://www.sarkariexam.com')),
        'meta_title': f"{clean_title} - Official Form, Dates, Fee & Eligibility 2026",
        'meta_description': f"Complete details for {clean_title}. Important dates, eligibility, age limit, application fee and direct links.",
        'keywords': f"{clean_title}, sarkari exam, govt jobs 2026, notification, admit card, exam date",
        'badge_color': 'blue' if category != 'Police' else 'rose',
        'state': state_name
    }
    
    try:
        new_id = create_exam(exam_record)
        if new_id:
            print(f"  [SARKARIEXAM SYNCED] [{status}] [{category}] {clean_title[:35]} | Vac: {total_vacancies} | Date: {exam_date or apply_last_date}")
            return True
    except Exception as e:
        print(f"  [DB INSERT ERROR] {clean_title[:30]}: {e}")
        
    return False

def fetch_and_sync_sarkariexam() -> int:
    """
    Crawls SarkariExam RSS Feeds and Category Pages.
    Extracts deep metadata (dates, fees, age, vacancies, links).
    """
    print("[SARKARIEXAM CRAWLER START] Polling SarkariExam...")
    items_to_process = []
    
    # 1. Fetch from RSS Feeds
    for feed_url in SARKARIEXAM_FEEDS:
        try:
            req = urllib.request.Request(feed_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)
            for item in root.findall('.//item'):
                title = item.find('title')
                link = item.find('link')
                if title is not None and link is not None and title.text and link.text:
                    items_to_process.append((title.text.strip(), link.text.strip()))
        except Exception as e:
            print(f"  [FEED ERROR] {feed_url}: {e}")
            
    # 2. Fetch from Multi-Category Pages
    for cat_url in SARKARIEXAM_CATEGORIES:
        try:
            req = urllib.request.Request(cat_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as resp:
                html_data = resp.read().decode('utf-8', errors='ignore')
            
            # Extract post links with headlines
            links = re.findall(r'<a[^>]+href=[\'"](https?://www\.sarkariexam\.com/[a-zA-Z0-9\-]+/?[\'"])[^>]*>(.*?)</a>', html_data, re.I | re.DOTALL)
            for href, anchor_text in links:
                href = href.strip('\'"')
                clean_text = re.sub(r'<[^>]+>', '', anchor_text).strip()
                if len(clean_text) > 12 and not any(skip in href for skip in ['/category/', '/tag/', '/page/', '/author/', '/feed/', 'privacy', 'contact', 'about', 'disclaimer']):
                    items_to_process.append((clean_text, href))
        except Exception as e:
            print(f"  [CATEGORY SCRAPE ERROR] {cat_url}: {e}")
            
    # Deduplicate items by URL
    unique_items = {}
    for t, u in items_to_process:
        if u not in unique_items:
            unique_items[u] = t
            
    added_count = 0
    for url, title in unique_items.items():
        if process_exam_entry(title, url):
            added_count += 1
            
    try:
        log_sync("Success", len(unique_items), added_count, f"SarkariExam Full Scraper: {added_count} added")
    except Exception as e:
        print(f"Log sync notice: {e}")
    print(f"[SARKARIEXAM CRAWLER COMPLETE] Found: {len(unique_items)}, Added: {added_count}")
    return added_count

if __name__ == "__main__":
    fetch_and_sync_sarkariexam()
