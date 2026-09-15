import urllib.request
import xml.etree.ElementTree as ET
import re
import html
from datetime import datetime
from database import get_db, exam_exists, create_exam, log_sync
from auto_scraper import detect_state, detect_category, detect_status, slugify

SARKARIEXAM_FEEDS = [
    "https://www.sarkariexam.com/feed/",
    "https://www.sarkariexam.com/category/admit-card/feed/",
    "https://www.sarkariexam.com/category/top-online-form/feed/",
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def extract_clean_details(html_content: str) -> dict:
    """
    Extracts deep metadata from individual post HTML on sarkariexam.com:
    - Important Dates (start, last, fee last, exam, admit card)
    - Fees (general, reserved)
    - Age limits (min, max)
    - Total vacancies
    - Direct official links
    """
    details = {}
    
    # 1. Total Vacancies from HTML
    m_vac = re.search(r'Total\s+Posts?\s*[:\-]?\s*([0-9,]+\s*(?:Posts?|Vacanc(?:y|ies))?)', html_content, re.I)
    if m_vac:
        details['total_vacancies'] = re.sub(r'<[^>]+>', '', m_vac.group(1)).strip()
        
    # Convert HTML to clean plain text lines
    text = re.sub(r'<(?:br|/p|/tr|/td|/li|/h[1-6])[^>]*>', '\n', html_content, flags=re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'[ \t]+', ' ', text)
    
    # 2. Extract Important Dates
    m_start = re.search(r'(?:Application\s+Start|Registration\s+Start|Starting\s+Date|Start\s+Date)[^:\n\r]*:\s*([0-9]{1,2}[^\n\r]+?202[4-7])', text, re.I)
    if m_start:
        details['apply_start_date'] = m_start.group(1).strip()
        
    m_last = re.search(r'(?:Last\s+Date\s+for\s+Apply|Form\s+Submission\s+Last\s+Date|Apply\s+Last\s+Date|Registration\s+Last\s+Date|Last\s+Date)[^:\n\r]*:\s*([0-9]{1,2}[^\n\r]+?202[4-7])', text, re.I)
    if m_last:
        details['apply_last_date'] = m_last.group(1).strip()
        
    m_fee_last = re.search(r'(?:Fee\s+Payment\s+Last\s+Date|Pee\s+Payment\s+Last\s+Date|Fee\s+Last\s+Date)[^:\n\r]*:\s*([0-9]{1,2}[^\n\r]+?202[4-7])', text, re.I)
    if m_fee_last:
        details['fee_last_date'] = m_fee_last.group(1).strip()
        
    m_exam = re.search(r'(?:Exam\s+Date|CBT\s+Exam\s+Date|Examination\s+Date)[^:\n\r]*:\s*([0-9a-zA-Z\s,-]+?202[4-7]|Available\s+Soon|As\s+per\s+Schedule)', text, re.I)
    if m_exam:
        details['exam_date'] = m_exam.group(1).strip()
        
    m_admit = re.search(r'(?:Admit\s+Card\s+Date|Admit\s+Card|Exam\s+City\s+Details)[^:\n\r]*:\s*([^\n\r]+)', text, re.I)
    if m_admit:
        adm = m_admit.group(1).strip()
        if len(adm) < 45 and not any(k in adm for k in ['{', '}', 'http', 'window']):
            details['admit_card_date'] = adm
            
    # 3. Application Fee
    m_fee_gen = re.search(r'(?:General,\s*OBC[^\n\r:]*|General[^\n\r:]*):\s*(Rs\.?\s*[0-9]+/?-?|₹\s*[0-9]+|0/?-?)', text, re.I)
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
        if any(skip in href for skip in ['sarkariexam', 'sarkariresult', 't.me', 'whatsapp', 'play.google', 'youtube', 'facebook', 'instagram', 'age-calculator']):
            continue
        if ('apply' in t_clean or 'registration' in t_clean or 'online form' in t_clean) and 'link_apply_online' not in details:
            details['link_apply_online'] = href
        elif ('notification' in t_clean or 'advt' in t_clean or href.endswith('.pdf') or 'short notice' in t_clean) and 'link_notification_pdf' not in details:
            details['link_notification_pdf'] = href
        elif ('official website' in t_clean or 'official portal' in t_clean or 'homepage' in t_clean) and 'link_official_website' not in details:
            details['link_official_website'] = href
        elif ('admit card' in t_clean or 'hall ticket' in t_clean or 'city' in t_clean) and 'link_admit_card' not in details:
            details['link_admit_card'] = href
        elif ('result' in t_clean or 'score' in t_clean or 'merit' in t_clean) and 'link_result' not in details:
            details['link_result'] = href
            
    return details

def fetch_post_html(url: str) -> str:
    """Helper to safely fetch a post HTML"""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode('utf-8', errors='ignore')
    except Exception:
        return ""

def fetch_and_sync_sarkariexam():
    """
    Crawls RSS feeds and homepage of sarkariexam.com to extract
    latest government jobs, admit cards, and results with full dates, fees, and vacancies.
    """
    print("[SARKARIEXAM CRAWLER] Starting deep synchronization from sarkariexam.com...")
    items_found = 0
    items_added = 0
    seen_urls = set()
    
    # 1. Fetch RSS Feeds
    for feed_url in SARKARIEXAM_FEEDS:
        try:
            req = urllib.request.Request(feed_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                xml_data = resp.read()
                root = ET.fromstring(xml_data)
                items = root.findall('.//item')
                
                for item in items:
                    title_elem = item.find('title')
                    link_elem = item.find('link')
                    if title_elem is None or link_elem is None:
                        continue
                        
                    raw_title = html.unescape(title_elem.text or '').strip()
                    source_url = link_elem.text or ''
                    
                    if not raw_title or source_url in seen_urls:
                        continue
                    seen_urls.add(source_url)
                    items_found += 1
                    
                    clean_title = re.sub(r'&#[0-9]+;', '', raw_title)
                    clean_title = re.sub(r'\s+', ' ', clean_title).strip()
                    
                    slug = slugify(clean_title)
                    if exam_exists(slug=slug, title=clean_title, source_url=source_url):
                        continue
                        
                    # Fetch deep post details (Dates, Fees, Vacancies, Links)
                    post_html = fetch_post_html(source_url)
                    deep_info = extract_clean_details(post_html) if post_html else {}
                    
                    state_name, state_info = detect_state(clean_title)
                    board_name = state_info.get('default_board', 'Central Government / All India')
                    
                    category = detect_category(clean_title, board_name)
                    status = detect_status(clean_title)
                    
                    apply_start_date = deep_info.get('apply_start_date') or ('Check Official Portal' if status == 'Applications Open' else 'Closed')
                    apply_last_date = deep_info.get('apply_last_date') or ('Check Official Portal' if status == 'Applications Open' else 'Closed')
                    exam_date = deep_info.get('exam_date', '')
                    total_vacancies = deep_info.get('total_vacancies') or 'Check Official Notification'
                    fee_general = deep_info.get('fee_general') or 'As per official notification'
                    fee_reserved = deep_info.get('fee_reserved') or 'As per official notification'
                    min_age = deep_info.get('min_age') or '18 Years'
                    max_age = deep_info.get('max_age') or 'As per rules'
                    
                    exam_record = {
                        'title': clean_title,
                        'slug': slug,
                        'category': category,
                        'board_name': board_name,
                        'total_vacancies': total_vacancies,
                        'short_description': f"Official recruitment notification for {clean_title}. Total vacancies: {total_vacancies}. Check eligibility, important dates, fee details and direct official links to apply.",
                        'status': status,
                        'notification_date': datetime.now().strftime('%d %B %Y'),
                        'apply_start_date': apply_start_date,
                        'apply_last_date': apply_last_date,
                        'fee_last_date': deep_info.get('fee_last_date', apply_last_date),
                        'admit_card_date': deep_info.get('admit_card_date', 'Before Exam'),
                        'exam_date': exam_date,
                        'fee_general': fee_general,
                        'fee_reserved': fee_reserved,
                        'fee_payment_mode': 'Online (Debit/Credit Card, Net Banking, UPI)',
                        'min_age': min_age,
                        'max_age': max_age,
                        'eligibility_criteria': f'Please refer to the official notification document for detailed eligibility criteria and educational qualifications for {total_vacancies}.',
                        'selection_process': '1. Written Examination / CBT\n2. Document Verification\n3. Medical Examination',
                        'syllabus_summary': 'General Awareness, Reasoning Ability, Quantitative Aptitude, English/Hindi & Subject Knowledge.',
                        'how_to_apply': f'1. Visit official link: {deep_info.get("link_apply_online", source_url)}.\n2. Complete registration/login.\n3. Fill form, upload documents, and submit before {apply_last_date}.',
                        'link_apply_online': deep_info.get('link_apply_online', source_url),
                        'link_notification_pdf': deep_info.get('link_notification_pdf', source_url),
                        'link_admit_card': deep_info.get('link_admit_card', source_url),
                        'link_answer_key': deep_info.get('link_answer_key', source_url),
                        'link_result': deep_info.get('link_result', source_url),
                        'link_official_website': deep_info.get('link_official_website', 'https://www.sarkariexam.com/'),
                        'meta_title': f"{clean_title} - Last Date, Exam Date & Apply Online",
                        'meta_description': f"Check {clean_title} details. Total {total_vacancies}, Last Date: {apply_last_date}, Exam Date: {exam_date}. Direct official application link.",
                        'keywords': f"{clean_title}, sarkari exam, govt jobs 2026, admit card, result",
                        'is_featured': 0,
                        'is_auto_synced': 1,
                        'source_url': source_url,
                        'state': state_name
                    }
                    
                    try:
                        create_exam(exam_record)
                        items_added += 1
                        print(f"  [SARKARIEXAM DEEP ADDED] [{status}] {clean_title[:45]} | Dates: {apply_start_date} to {apply_last_date} | Exam: {exam_date}")
                    except Exception as e:
                        print(f"  [SARKARIEXAM INSERT ERROR] {e}")
        except Exception as e:
            print(f"  [SARKARIEXAM FEED ERROR] {feed_url} -> {e}")

    log_sync(
        status="SUCCESS",
        items_found=items_found,
        items_added=items_added,
        message=f"SarkariExam Deep Auto-Sync completed: {items_found} items found, {items_added} new items added."
    )
    print(f"[SARKARIEXAM CRAWLER COMPLETE] Found: {items_found}, Added: {items_added}")
    return items_added

def enrich_existing_sarkariexam_records(limit=50):
    """
    Enriches existing exams in database that have 'Check Official Portal' by deep parsing their source URLs.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, source_url, status 
        FROM exams 
        WHERE source_url LIKE '%sarkariexam.com%' 
        AND (apply_last_date = 'Check Official Portal' OR exam_date = '' OR total_vacancies = 'Check Official Notification')
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    
    enriched = 0
    print(f"[ENRICHER] Enriching {len(rows)} existing sarkariexam records with deep dates/fees/vacancies...")
    
    for row in rows:
        exam_id = row['id']
        url = row['source_url']
        title = row['title']
        
        post_html = fetch_post_html(url)
        if not post_html:
            continue
            
        details = extract_clean_details(post_html)
        if not details:
            continue
            
        updates = []
        params = []
        
        if details.get('total_vacancies'):
            updates.append("total_vacancies = ?")
            params.append(details['total_vacancies'])
        if details.get('apply_start_date'):
            updates.append("apply_start_date = ?")
            params.append(details['apply_start_date'])
        if details.get('apply_last_date'):
            updates.append("apply_last_date = ?")
            params.append(details['apply_last_date'])
        if details.get('fee_last_date'):
            updates.append("fee_last_date = ?")
            params.append(details['fee_last_date'])
        if details.get('exam_date'):
            updates.append("exam_date = ?")
            params.append(details['exam_date'])
        if details.get('admit_card_date'):
            updates.append("admit_card_date = ?")
            params.append(details['admit_card_date'])
        if details.get('fee_general'):
            updates.append("fee_general = ?")
            params.append(details['fee_general'])
        if details.get('fee_reserved'):
            updates.append("fee_reserved = ?")
            params.append(details['fee_reserved'])
        if details.get('min_age'):
            updates.append("min_age = ?")
            params.append(details['min_age'])
        if details.get('max_age'):
            updates.append("max_age = ?")
            params.append(details['max_age'])
        if details.get('link_apply_online'):
            updates.append("link_apply_online = ?")
            params.append(details['link_apply_online'])
        if details.get('link_notification_pdf'):
            updates.append("link_notification_pdf = ?")
            params.append(details['link_notification_pdf'])
            
        if updates:
            params.append(exam_id)
            query = f"UPDATE exams SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)
            enriched += 1
            print(f"  [ENRICHED #{exam_id}] {title[:40]} | Vac: {details.get('total_vacancies')} | Last: {details.get('apply_last_date')} | Exam: {details.get('exam_date')}")
            
    conn.commit()
    conn.close()
    print(f"[ENRICHER COMPLETE] Enriched {enriched} records.")
    return enriched
