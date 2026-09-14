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

def fetch_and_sync_sarkariexam():
    """
    Crawls RSS feeds and homepage of sarkariexam.com to extract
    latest government jobs, admit cards, and results.
    """
    print("[SARKARIEXAM CRAWLER] Starting synchronization from sarkariexam.com...")
    items_found = 0
    items_added = 0
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    seen_urls = set()
    
    # 1. Fetch RSS Feeds
    for feed_url in SARKARIEXAM_FEEDS:
        try:
            req = urllib.request.Request(feed_url, headers=headers)
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
                    
                    # Clean title
                    clean_title = re.sub(r'&#[0-9]+;', '', raw_title)
                    clean_title = re.sub(r'\s+', ' ', clean_title).strip()
                    
                    slug = slugify(clean_title)
                    if exam_exists(slug=slug, title=clean_title, source_url=source_url):
                        continue
                        
                    state_name, state_info = detect_state(clean_title)
                    board_name = state_info.get('default_board', 'Central Government / All India')
                    
                    category = detect_category(clean_title, board_name)
                    status = detect_status(clean_title)
                    
                    # Determine apply/exam dates
                    apply_last_date = 'Check Official Portal'
                    exam_date = ''
                    if status == 'Admit Card':
                        apply_last_date = 'Closed'
                        exam_date = 'Check Admit Card & City Slip'
                    elif status == 'Result / Answer Key':
                        apply_last_date = 'Closed'
                        exam_date = 'Conducted'
                    
                    exam_record = {
                        'title': clean_title,
                        'slug': slug,
                        'category': category,
                        'board_name': board_name,
                        'total_vacancies': 'Check Official Notification',
                        'short_description': f"Official recruitment notification for {clean_title}. Sourced from official recruitment updates. Check eligibility, exam dates and direct link to apply.",
                        'status': status,
                        'notification_date': datetime.now().strftime('%d %B %Y'),
                        'apply_start_date': 'Check Official Portal' if status == 'Applications Open' else 'Closed',
                        'apply_last_date': apply_last_date,
                        'fee_general': 'As per official notification',
                        'fee_reserved': 'As per official notification',
                        'fee_payment_mode': 'Online (Debit/Credit Card, Net Banking, UPI)',
                        'min_age': '18 Years',
                        'max_age': 'As per rules',
                        'eligibility_criteria': 'Please refer to the official notification document on the portal for detailed post-wise educational qualifications.',
                        'selection_process': '1. Written Examination / CBT\n2. Document Verification\n3. Medical Examination',
                        'syllabus_summary': 'General Awareness, Reasoning Ability, Quantitative Aptitude, English/Hindi & Subject Knowledge.',
                        'how_to_apply': f'1. Visit official link.\n2. Complete registration/login.\n3. Fill form, upload documents, and submit.',
                        'link_apply_online': source_url,
                        'link_notification_pdf': source_url,
                        'link_admit_card': source_url,
                        'link_answer_key': source_url,
                        'link_result': source_url,
                        'link_official_website': 'https://www.sarkariexam.com/',
                        'meta_title': f"{clean_title} - Eligibility, Dates & Link",
                        'meta_description': f"Check latest updates for {clean_title}. Apply online, download admit card and check result.",
                        'keywords': f"{clean_title}, sarkari exam, govt jobs 2026, admit card, result",
                        'is_featured': 0,
                        'is_auto_synced': 1,
                        'source_url': source_url,
                        'state': state_name
                    }
                    
                    try:
                        create_exam(exam_record)
                        items_added += 1
                        print(f"  [SARKARIEXAM ADDED] [{status}] {clean_title[:50]}")
                    except Exception as e:
                        print(f"  [SARKARIEXAM INSERT ERROR] {e}")
        except Exception as e:
            print(f"  [SARKARIEXAM FEED ERROR] {feed_url} -> {e}")
            
    # 2. Fetch Homepage Links for extra coverage
    try:
        req = urllib.request.Request("https://www.sarkariexam.com/", headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            page_html = resp.read().decode('utf-8', errors='ignore')
            links = re.findall(r'<a[^>]+href=[\'"](https?://www.sarkariexam.com/[a-z0-9-]+/)[\'"][^>]*>(.*?)</a>', page_html, re.I)
            
            for url_path, link_text in links:
                if url_path in seen_urls or any(skip in url_path for skip in ['category', 'tag', 'about', 'contact', 'privacy', 'disclaimer', 'author', 'page']):
                    continue
                seen_urls.add(url_path)
                
                clean_t = re.sub(r'<[^>]+>', '', link_text).strip()
                clean_t = html.unescape(clean_t)
                clean_t = re.sub(r'&#[0-9]+;', '', clean_t)
                
                if len(clean_t) < 12 or len(clean_t) > 150:
                    continue
                    
                items_found += 1
                slug = slugify(clean_t)
                if exam_exists(slug=slug, title=clean_t, source_url=url_path):
                    continue
                    
                state_name, state_info = detect_state(clean_t)
                board_name = state_info.get('default_board', 'Central Government / All India')
                
                category = detect_category(clean_t, board_name)
                status = detect_status(clean_t)
                
                exam_record = {
                    'title': clean_t,
                    'slug': slug,
                    'category': category,
                    'board_name': board_name,
                    'total_vacancies': 'Check Official Notification',
                    'short_description': f"Official recruitment alert for {clean_t}. Candidates can check eligibility, last date and direct link.",
                    'status': status,
                    'notification_date': datetime.now().strftime('%d %B %Y'),
                    'apply_start_date': 'Check Official Portal' if status == 'Applications Open' else 'Closed',
                    'apply_last_date': 'Check Official Portal' if status == 'Applications Open' else 'Closed',
                    'fee_general': 'As per official notification',
                    'fee_reserved': 'As per official notification',
                    'fee_payment_mode': 'Online (Debit/Credit Card, Net Banking, UPI)',
                    'min_age': '18 Years',
                    'max_age': 'As per rules',
                    'eligibility_criteria': 'Please refer to the official notification document on the portal for detailed post-wise educational qualifications.',
                    'selection_process': '1. Written Examination / CBT\n2. Document Verification\n3. Medical Examination',
                    'syllabus_summary': 'General Awareness, Reasoning Ability, Quantitative Aptitude, English/Hindi & Subject Knowledge.',
                    'how_to_apply': f'1. Visit official link.\n2. Complete registration/login.\n3. Fill form, upload documents, and submit.',
                    'link_apply_online': url_path,
                    'link_notification_pdf': url_path,
                    'link_admit_card': url_path,
                    'link_answer_key': url_path,
                    'link_result': url_path,
                    'link_official_website': 'https://www.sarkariexam.com/',
                    'meta_title': f"{clean_t} - Recruitment Details & Links",
                    'meta_description': f"Check latest recruitment updates for {clean_t}. Apply online, download admit card and check result.",
                    'keywords': f"{clean_t}, sarkari exam, govt jobs 2026",
                    'is_featured': 0,
                    'is_auto_synced': 1,
                    'source_url': url_path,
                    'state': state_name
                }
                
                try:
                    create_exam(exam_record)
                    items_added += 1
                    print(f"  [SARKARIEXAM HOME ADDED] [{status}] {clean_t[:50]}")
                except Exception as e:
                    print(f"  [SARKARIEXAM INSERT ERROR] {e}")
    except Exception as e:
        print(f"  [SARKARIEXAM HOMEPAGE ERROR] {e}")

    log_sync(
        status="SUCCESS",
        items_found=items_found,
        items_added=items_added,
        message=f"SarkariExam Auto-Sync completed: {items_found} items found, {items_added} new items added."
    )
    print(f"[SARKARIEXAM CRAWLER COMPLETE] Found: {items_found}, Added: {items_added}")
    return items_added
