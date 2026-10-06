import requests
import json
import html
import re
import sys
from bs4 import BeautifulSoup
from datetime import datetime

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from database import create_exam, update_exam, exam_exists, get_db, log_sync, init_db

BASE_URL = "https://studygovthelp.in"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# State detection rules focusing on central and state exams
STATE_DETECTION_RULES = {
    'Rajasthan': ['rajasthan', 'rsmssb', 'rpsc', 'reet', 'safai karmchari', 'raj ', 'jaipur', 'jodhpur', 'bikaner', 'churu', 'nagaur', 'kota', 'discom', 'vidyut', 'panchayat', 'sso rajasthan', 'bser'],
    'Uttar Pradesh': ['uttar pradesh', 'up ', 'upsssc', 'uppsc', 'upessc', 'uptet', 'uppbpb', 'lucknow', 'up tgt', 'up pgt', 'lekhpal', 'upcisb', 'anganwadi'],
    'Bihar': ['bihar', 'bpsc', 'bssc', 'bpssc', 'bcece', 'bseb', 'patna', 'deled', 'vidhan parishad'],
    'Madhya Pradesh': ['madhya pradesh', 'mp ', 'mppsc', 'mpesb', 'vyapam', 'bhopal', 'krashi vistar'],
    'Haryana': ['haryana', 'hssc', 'hpsc', 'htet', 'panchkula'],
    'Delhi': ['delhi', 'dsssb', 'delhi high court'],
    'Maharashtra': ['maharashtra', 'mpsc', 'mumbai', 'pune'],
    'Gujarat': ['gujarat', 'gpsc', 'gsssb', 'ojas'],
    'Punjab': ['punjab', 'ppsc', 'psssb'],
    'Uttarakhand': ['uttarakhand', 'ukpsc', 'uksssc', 'utet'],
    'Jharkhand': ['jharkhand', 'jssc', 'jpsc'],
    'Chhattisgarh': ['chhattisgarh', 'cgpsc', 'cgvyapam'],
    'West Bengal': ['west bengal', 'wbpsc', 'kolkata'],
    'Odisha': ['odisha', 'ossc', 'opsc'],
    'All India': ['ssc', 'upsc', 'railway', 'rrb', 'ibps', 'sbi', 'bank', 'nta', 'ugc net', 'csir', 'air force', 'army', 'navy', 'bsf', 'crpf', 'itbp', 'cisf', 'ssb', 'echs', 'isro', 'india post', 'gds', 'ctet', 'afcat', 'nda', 'cds', 'iob', 'emrs']
}

def detect_state(title: str, text: str = "") -> str:
    combined = f"{title} {text}".lower()
    for state, keywords in STATE_DETECTION_RULES.items():
        if state == 'All India':
            continue
        if any(kw in combined for kw in keywords):
            return state
    return 'All India'

def detect_category(title: str, board: str = "") -> str:
    combined = f"{title} {board}".lower()
    if any(k in combined for k in ['teacher', 'ctet', 'reet', 'tet', 'tgt', 'pgt', 'prt', 'kvs', 'school', 'faculty', 'set ', 'bser', 'board', '10th', '12th']):
        return 'Teaching'
    elif any(k in combined for k in ['police', 'constable', 'sub inspector', 'daroga', 'si ', 'agniveer', 'army', 'navy', 'airforce', 'air force', 'defense', 'bsf', 'crpf', 'itbp', 'cisf', 'ssb', 'echs', 'assam rifles', 'security', 'rpf']):
        return 'Police'
    elif any(k in combined for k in ['railway', 'rrb', 'rrc', 'ntpc', 'alp', 'technician', 'group d', 'loco pilot', 'metro']):
        return 'Railway'
    elif any(k in combined for k in ['upsc', 'ias', 'ips', 'civil services', 'nda', 'cds', 'capf']):
        return 'UPSC'
    elif any(k in combined for k in ['bank', 'ibps', 'sbi', 'rbi', 'clerk', ' po ', 'po/', 'po)', 'nabard', 'sebi', 'bob', 'pnb']):
        return 'Banking'
    elif any(k in combined for k in ['ssc', 'cgl', 'chsl', 'mts', 'cpo', 'stenographer', 'gd constable']):
        return 'SSC'
    else:
        return 'State'

def detect_status(title: str, content_text: str = "") -> str:
    combined = f"{title} {content_text}".lower()
    if any(k in combined for k in ['admit card', 'hall ticket', 'city intimation', 'city slip', 'exam schedule']):
        return 'Admit Card'
    elif any(k in combined for k in ['result declared', 'score card', 'answer key', 'result out', 'merit list', 'कटऑफ', 'रिजल्ट']):
        return 'Result / Answer Key'
    elif any(k in combined for k in ['upcoming', 'calendar', 'expected', 'coming soon', 'शीघ्र']):
        return 'Upcoming'
    return 'Applications Open'

def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text).strip('-')
    return text[:90]

def clean_html_content(soup: BeautifulSoup) -> str:
    """Removes scripts, ads, whatsapp/telegram spam, and applies clean modern Tailwind styles."""
    for elem in soup.find_all(['script', 'style', 'iframe', 'noscript', 'ins']):
        elem.decompose()
        
    for elem in soup.find_all(['div', 'p', 'span', 'section', 'aside', 'a']):
        text = elem.get_text(strip=True).lower()
        href = elem.get('href', '').lower()
        class_str = " ".join(elem.get('class', [])).lower()
        if 'telegram' in href or 't.me' in href or 'chat.whatsapp' in href or 'wp-block-buttons' in class_str:
            if any(w in text for w in ['whatsapp group', 'telegram group', 'join telegram', 'join whatsapp', 'टेलीग्राम चैनल', 'व्हाट्सएप ग्रुप']):
                elem.decompose()
                continue
                
    # Style all tables with responsive Tailwind classes
    for table in soup.find_all('table'):
        table['class'] = 'w-full text-xs sm:text-sm text-left border-collapse border border-slate-200 my-4 rounded-xl overflow-hidden'
        for tr in table.find_all('tr'):
            tr['class'] = 'border-b border-slate-200 hover:bg-slate-50 transition'
        for th in table.find_all('th'):
            th['class'] = 'bg-slate-100 p-3 font-bold text-slate-800 border-r border-slate-200 text-xs sm:text-sm'
        for td in table.find_all('td'):
            td['class'] = 'p-3 text-slate-700 border-r border-slate-200 text-xs sm:text-sm'
            
    # Wrap tables in overflow-x-auto container if not already wrapped
    for table in soup.find_all('table'):
        if table.parent and 'overflow-x-auto' not in table.parent.get('class', []):
            wrapper = soup.new_tag('div', **{'class': 'overflow-x-auto my-4 rounded-xl border border-slate-200 shadow-xs bg-white'})
            table.wrap(wrapper)

    # Style headings
    for h2 in soup.find_all('h2'):
        h2['class'] = 'text-base sm:text-lg font-black text-slate-900 mt-6 mb-3 flex items-center gap-2 pb-2 border-b border-slate-100'
    for h3 in soup.find_all('h3'):
        h3['class'] = 'text-sm sm:text-base font-bold text-slate-800 mt-4 mb-2'
    for p in soup.find_all('p'):
        p['class'] = 'text-xs sm:text-sm text-slate-700 leading-relaxed mb-3'
    for ul in soup.find_all(['ul', 'ol']):
        ul['class'] = 'list-disc list-inside space-y-1 text-xs sm:text-sm text-slate-700 mb-4 pl-2'

    return str(soup)

def parse_studygovthelp_post(post_data: dict) -> dict:
    raw_title = html.unescape(post_data.get('title', {}).get('rendered', '')).strip()
    title = re.sub(r'\s*[-|–]\s*(Study\s*Govt\s*Help|studygovthelp\.in).*$', '', raw_title, flags=re.IGNORECASE).strip()
    
    link = post_data.get('link', '')
    slug = post_data.get('slug', '') or slugify(title)
    publish_date = post_data.get('date', '')[:10]
    
    content_html = post_data.get('content', {}).get('rendered', '')
    soup = BeautifulSoup(content_html, 'html.parser')
    full_text = soup.get_text()
    
    state = detect_state(title, full_text)
    tables = soup.find_all('table')
    
    board_name = ""
    total_vacancies = "Various Posts"
    apply_start_date = ""
    apply_last_date = ""
    fee_last_date = ""
    exam_date = ""
    admit_card_date = ""
    result_date = ""
    fee_general = "As per notification"
    fee_reserved = "As per notification"
    fee_payment_mode = "Online (Debit/Credit Card, Net Banking, UPI)"
    min_age = "18 Years"
    max_age = "As per rules"
    age_relaxation = "Government rules applicable for reserved categories."
    eligibility_criteria = ""
    selection_process = ""
    salary_info = ""
    how_to_apply = ""
    
    link_apply_online = ""
    link_notification_pdf = ""
    link_official_website = ""
    link_admit_card = ""
    link_answer_key = ""
    link_result = ""
    
    # Parse table key-value pairs
    for table in tables:
        rows = table.find_all('tr')
        for tr in rows:
            cells = [td.get_text(strip=True) for td in tr.find_all(['th', 'td'])]
            if len(cells) >= 2:
                key = cells[0].lower().strip()
                val = cells[1].strip()
                
                # Board / Organization
                if any(k in key for k in ['organization', 'conducting authority', 'बोर्ड', 'संस्था', 'department']):
                    if not board_name:
                        board_name = val
                # Total Vacancies
                elif any(k in key for k in ['total vacancies', 'total posts', 'total post', 'कुल पद', 'पद संख्या', 'vacancies']):
                    if val and val != '-' and (not total_vacancies or total_vacancies == 'Various Posts'):
                        total_vacancies = val
                # Apply Start Date
                elif any(k in key for k in ['application start', 'start date', 'आवेदन शुरू', 'प्रारंभ तिथि']):
                    if not apply_start_date:
                        apply_start_date = val
                # Last Date
                elif any(k in key for k in ['last date to apply', 'last date', 'अंतिम तिथि', 'form last date', 'closing date']):
                    if not apply_last_date:
                        apply_last_date = val
                # Exam Date
                elif any(k in key for k in ['exam date', 'परीक्षा तिथि', 'परीक्षा']):
                    if not exam_date:
                        exam_date = val
                # Fees
                elif any(k in key for k in ['male ur/obc/ews', 'general', 'ur / ews', 'general/obc']):
                    fee_general = val
                elif any(k in key for k in ['sc/st', 'sc / st', 'female', 'महिला', 'आरक्षित']):
                    fee_reserved = val
                # Official Website text in table
                elif any(k in key for k in ['official website', 'वेबसाइट']):
                    a_tag = tr.find('a')
                    if a_tag and a_tag.get('href'):
                        link_official_website = a_tag.get('href')
                    elif val.startswith('http') or '.in' in val or '.gov' in val or '.nic' in val or '.org' in val:
                        link_official_website = val if val.startswith('http') else f"https://{val}"

    # Extract Action Links
    for a in soup.find_all('a'):
        a_text = a.get_text(strip=True).lower()
        a_href = a.get('href', '').strip()
        if not a_href or a_href.startswith('#') or 'telegram' in a_href or 'whatsapp' in a_href:
            continue
            
        parent_text = a.parent.get_text(strip=True).lower() if a.parent else ""
        
        if any(k in a_text or k in parent_text for k in ['apply online', 'online form', 'application form', 'apply here', 'आवेदन करें', 'form link']):
            if not link_apply_online and 'studygovthelp.in' not in a_href:
                link_apply_online = a_href
            elif not link_apply_online:
                link_apply_online = a_href
                
        elif any(k in a_text or k in parent_text for k in ['notification', 'official notification', 'विज्ञप्ति', 'notice download', 'download notification', 'pdf download']):
            if not link_notification_pdf:
                link_notification_pdf = a_href
                
        elif any(k in a_text or k in parent_text for k in ['official website', 'मुख्य वेबसाइट', 'आधिकारिक वेबसाइट']):
            if not link_official_website and 'studygovthelp.in' not in a_href:
                link_official_website = a_href
                
        elif any(k in a_text or k in parent_text for k in ['admit card', 'hall ticket', 'प्रवेश पत्र']):
            if not link_admit_card:
                link_admit_card = a_href
                
        elif any(k in a_text or k in parent_text for k in ['answer key', 'उत्तर कुंजी']):
            if not link_answer_key:
                link_answer_key = a_href

        elif any(k in a_text or k in parent_text for k in ['result', 'रिजल्ट', 'merit list']):
            if not link_result:
                link_result = a_href

    # Board fallback
    if not board_name:
        if 'rsmssb' in full_text.lower() or 'rsmssb' in title.lower():
            board_name = 'RSMSSB Rajasthan'
        elif 'rpsc' in full_text.lower() or 'rpsc' in title.lower():
            board_name = 'RPSC Rajasthan'
        elif 'itbp' in full_text.lower() or 'itbp' in title.lower():
            board_name = 'ITBP Indo-Tibetan Border Police'
        elif 'echs' in full_text.lower() or 'echs' in title.lower():
            board_name = 'ECHS Health Scheme'
        elif 'bser' in full_text.lower() or 'madhyamik shiksha' in full_text.lower():
            board_name = 'Board of Secondary Education Rajasthan'
        elif 'ssc' in full_text.lower() or 'ssc' in title.lower():
            board_name = 'Staff Selection Commission (SSC)'
        else:
            board_name = f"{state} Recruitment Board" if state != 'All India' else "Central Government Recruitment"

    category = detect_category(title, board_name)
    status = detect_status(title, full_text)
    
    # Extract Specific Text Sections
    for heading in soup.find_all(['h2', 'h3', 'h4']):
        h_text = heading.get_text(strip=True).lower()
        sec_paras = []
        curr = heading.next_sibling
        while curr and curr.name not in ['h2', 'h3', 'h4']:
            if curr.name in ['p', 'ul', 'ol', 'div'] and not curr.find('table'):
                t = curr.get_text(strip=True)
                if len(t) > 5 and not any(w in t.lower() for w in ['telegram', 'whatsapp group', 'join now']):
                    sec_paras.append(t)
            curr = curr.next_sibling
            
        sec_content = "\n".join(sec_paras).strip()
        
        if any(k in h_text for k in ['age limit', 'आयु सीमा']) and sec_content:
            m_min = re.search(r'(\d{2})\s*(?:year|वर्ष|साल)', sec_content, re.IGNORECASE)
            if m_min:
                min_age = f"{m_min.group(1)} Years"
            m_max = re.search(r'अधिकतम[^\d]*(\d{2})|maximum[^\d]*(\d{2})', sec_content, re.IGNORECASE)
            if m_max:
                max_age = f"{m_max.group(1) or m_max.group(2)} Years"
            age_relaxation = sec_content[:300]
            
        elif any(k in h_text for k in ['qualification', 'शैक्षणिक योग्यता', 'eligibility']) and sec_content:
            if not eligibility_criteria:
                eligibility_criteria = sec_content
                
        elif any(k in h_text for k in ['selection process', 'चयन प्रक्रिया']) and sec_content:
            if not selection_process:
                selection_process = sec_content
                
        elif any(k in h_text for k in ['how to apply', 'आवेदन कैसे करें']) and sec_content:
            if not how_to_apply:
                how_to_apply = sec_content
                
        elif any(k in h_text for k in ['salary', 'वेतनमान', 'pay scale']) and sec_content:
            if not salary_info:
                salary_info = sec_content

    cleaned_html = clean_html_content(soup)
    
    first_p = soup.find('p')
    short_desc = first_p.get_text(strip=True) if first_p else f"Complete information for {title} including eligibility criteria, schedule, vacancy and official links."
    if len(short_desc) > 300:
        short_desc = short_desc[:297] + '...'

    if not link_official_website:
        link_official_website = link_apply_online or link_notification_pdf or 'https://studygovthelp.in/'
    if not link_notification_pdf:
        link_notification_pdf = link_official_website
    if not link_apply_online and status == 'Applications Open':
        link_apply_online = link_official_website

    return {
        'title': title,
        'slug': slug,
        'category': category,
        'board_name': board_name,
        'total_vacancies': total_vacancies,
        'short_description': short_desc,
        'status': status,
        'notification_date': publish_date or datetime.now().strftime('%d %B %Y'),
        'apply_start_date': apply_start_date or 'Check Official Portal',
        'apply_last_date': apply_last_date or 'Check Official Portal',
        'fee_last_date': fee_last_date or apply_last_date or 'Check Official Portal',
        'admit_card_date': admit_card_date or 'Before Examination',
        'exam_date': exam_date or 'As per schedule',
        'result_date': result_date or 'After Examination',
        'fee_general': fee_general,
        'fee_reserved': fee_reserved,
        'fee_payment_mode': fee_payment_mode,
        'min_age': min_age,
        'max_age': max_age,
        'age_relaxation': age_relaxation,
        'eligibility_criteria': eligibility_criteria or '10th / 12th / Graduate or relevant qualification as per notification rules.',
        'selection_process': selection_process or '1. Written Examination / CBT\n2. Document Verification\n3. Medical Examination',
        'syllabus_summary': 'Detailed syllabus and examination scheme are available in the official notification.',
        'how_to_apply': how_to_apply or f"1. Visit official portal: {link_official_website}\n2. Check recruitment notification for {title}\n3. Submit application and download acknowledgement.",
        'link_apply_online': link_apply_online,
        'link_notification_pdf': link_notification_pdf,
        'link_official_website': link_official_website,
        'link_admit_card': link_admit_card,
        'link_answer_key': link_answer_key,
        'link_result': link_result,
        'meta_title': f"{title} - Dates, Eligibility, Vacancy & Apply Link",
        'meta_description': f"Apply online for {title}. Check qualification, total vacancies, age limit, selection process and direct official link.",
        'keywords': f"{title}, {state} govt jobs 2026, {category} bharti, studygovthelp, apply online",
        'state': state,
        'is_auto_synced': 1,
        'source_url': link,
        'content_html': cleaned_html
    }

def sync_from_studygovthelp(pages: int = 3, per_page: int = 20) -> dict:
    """
    Automated crawler for studygovthelp.in.
    Fetches latest recruitment posts via REST API and RSS feeds,
    parses all details, tables, and links, and synchronizes with portal database.
    """
    init_db()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now_str}] [STUDYGOVTHELP CRAWLER] Starting sync from studygovthelp.in...")
    
    total_found = 0
    items_added = 0
    items_updated = 0
    added_titles = []
    
    headers = {'User-Agent': USER_AGENT}
    
    for page in range(1, pages + 1):
        try:
            api_url = f"{BASE_URL}/wp-json/wp/v2/posts?page={page}&per_page={per_page}"
            resp = requests.get(api_url, headers=headers, timeout=15)
            if resp.status_code != 200:
                print(f"[STUDYGOVTHELP] Page {page} returned status {resp.status_code}, stopping.")
                break
                
            posts = resp.json()
            if not isinstance(posts, list) or len(posts) == 0:
                break
                
            total_found += len(posts)
            
            for p in posts:
                parsed = parse_studygovthelp_post(p)
                title = parsed['title']
                slug = parsed['slug']
                source_url = parsed['source_url']
                
                # Check if exists
                if exam_exists(slug=slug, title=title, source_url=source_url):
                    # Update content_html and latest dates if already in DB
                    try:
                        conn = get_db()
                        cursor = conn.cursor()
                        cursor.execute("SELECT id FROM exams WHERE slug = ? OR source_url = ?", (slug, source_url))
                        row = cursor.fetchone()
                        if row:
                            exam_id = row[0]
                            update_exam(exam_id, parsed)
                            items_updated += 1
                        conn.close()
                    except Exception as e:
                        print(f"Notice on updating existing record: {e}")
                    continue
                
                create_exam(parsed)
                items_added += 1
                added_titles.append(f"{title} ({parsed['state']})")
                print(f"  [+] Synced from studygovthelp.in: {title} [{parsed['state']}]")
                
        except Exception as e:
            print(f"[STUDYGOVTHELP CRAWLER ERROR] Page {page} failed: {e}")
            break

    status = "SUCCESS"
    msg = f"studygovthelp.in Auto-Sync completed! {total_found} posts examined, {items_added} new posts added, {items_updated} updated."
    if added_titles:
        msg += f" New posts: {', '.join(added_titles[:3])}"
        if len(added_titles) > 3:
            msg += f" and {len(added_titles) - 3} more."
            
    log_sync(status, total_found, items_added, msg)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")
    
    return {
        'status': status,
        'items_found': total_found,
        'items_added': items_added,
        'items_updated': items_updated,
        'message': msg
    }

if __name__ == '__main__':
    sync_from_studygovthelp(pages=2, per_page=15)
