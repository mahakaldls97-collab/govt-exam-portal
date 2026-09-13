import re
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from database import create_exam, exam_exists, log_sync, init_db

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# Comprehensive All-India State & UTs Official Portal Directory
STATE_BOARD_MAP = {
    'Rajasthan': {
        'keywords': ['rajasthan', 'rsmssb', 'rpsc', 'reet', 'ras', 'rts', 'patwari', 'jaipur', 'jodhpur', 'sso rajasthan'],
        'official_website': 'https://rsmssb.rajasthan.gov.in/',
        'apply_url': 'https://sso.rajasthan.gov.in/',
        'default_board': 'RSMSSB / RPSC Rajasthan'
    },
    'Uttar Pradesh': {
        'keywords': ['uttar pradesh', 'up police', 'uppbpb', 'upsssc', 'uppsc', 'uptet', 'lucknow', 'updeled'],
        'official_website': 'https://upsssc.gov.in/',
        'apply_url': 'https://upsssc.gov.in/',
        'default_board': 'UPSSSC / UPPSC Uttar Pradesh'
    },
    'Bihar': {
        'keywords': ['bihar', 'bpsc', 'bssc', 'bpssc', 'csbc', 'patna'],
        'official_website': 'https://www.bpsc.bih.nic.in/',
        'apply_url': 'https://onlinebpsc.bihar.gov.in/',
        'default_board': 'BPSC / BSSC Bihar'
    },
    'Madhya Pradesh': {
        'keywords': ['madhya pradesh', 'mppsc', 'mpesb', 'vyapam', 'bhopal', 'mp police'],
        'official_website': 'https://mppsc.mp.gov.in/',
        'apply_url': 'https://esb.mp.gov.in/',
        'default_board': 'MPPSC / MPESB Madhya Pradesh'
    },
    'Haryana': {
        'keywords': ['haryana', 'hssc', 'hpsc', 'panchkula', 'haryana police'],
        'official_website': 'https://hssc.gov.in/',
        'apply_url': 'https://onetimeregn.haryana.gov.in/',
        'default_board': 'HSSC Haryana'
    },
    'Delhi': {
        'keywords': ['delhi', 'dsssb', 'delhi police'],
        'official_website': 'https://dsssb.delhi.gov.in/',
        'apply_url': 'https://dsssbonline.nic.in/',
        'default_board': 'DSSSB Delhi'
    },
    'Maharashtra': {
        'keywords': ['maharashtra', 'mpsc', 'maha metro', 'mahapolice', 'mumbai', 'pune'],
        'official_website': 'https://mpsc.gov.in/',
        'apply_url': 'https://mpsc.gov.in/',
        'default_board': 'MPSC / Maharashtra Govt'
    },
    'Gujarat': {
        'keywords': ['gujarat', 'gpsc', 'gsssb', 'ojas', 'gandhinagar', 'ahmedabad'],
        'official_website': 'https://gpsc.gujarat.gov.in/',
        'apply_url': 'https://ojas.gujarat.gov.in/',
        'default_board': 'GPSC / GSSSB Gujarat'
    },
    'West Bengal': {
        'keywords': ['west bengal', 'wbpsc', 'wbprb', 'kolkata'],
        'official_website': 'https://psc.wb.gov.in/',
        'apply_url': 'https://psc.wb.gov.in/',
        'default_board': 'WBPSC West Bengal'
    },
    'Punjab': {
        'keywords': ['punjab', 'ppsc', 'psssb', 'punjab police'],
        'official_website': 'https://ppsc.gov.in/',
        'apply_url': 'https://sssb.punjab.gov.in/',
        'default_board': 'PPSC Punjab'
    },
    'Odisha': {
        'keywords': ['odisha', 'orissa', 'opsc', 'osssc', 'ossc', 'bhubaneswar'],
        'official_website': 'https://opsc.gov.in/',
        'apply_url': 'https://osssc.gov.in/',
        'default_board': 'OPSC / OSSSC Odisha'
    },
    'Jharkhand': {
        'keywords': ['jharkhand', 'jpsc', 'jssc', 'ranchi'],
        'official_website': 'https://jpsc.gov.in/',
        'apply_url': 'https://jssc.nic.in/',
        'default_board': 'JPSC Jharkhand'
    },
    'Chhattisgarh': {
        'keywords': ['chhattisgarh', 'cgpsc', 'cg vyapam', 'raipur'],
        'official_website': 'https://psc.cg.gov.in/',
        'apply_url': 'https://vyapam.cgstate.gov.in/',
        'default_board': 'CGPSC Chhattisgarh'
    },
    'Uttarakhand': {
        'keywords': ['uttarakhand', 'ukpsc', 'uksssc', 'dehradun'],
        'official_website': 'https://psc.uk.gov.in/',
        'apply_url': 'https://sssc.uk.gov.in/',
        'default_board': 'UKPSC Uttarakhand'
    },
    'Himachal Pradesh': {
        'keywords': ['himachal', 'hppsc', 'hpssc', 'shimla'],
        'official_website': 'https://hppsc.hp.gov.in/',
        'apply_url': 'https://hppsc.hp.gov.in/',
        'default_board': 'HPPSC Himachal'
    },
    'Andhra Pradesh & Telangana': {
        'keywords': ['andhra', 'appsc', 'telangana', 'tspsc', 'hyderabad'],
        'official_website': 'https://psc.ap.gov.in/',
        'apply_url': 'https://tspsc.gov.in/',
        'default_board': 'APPSC / TSPSC'
    },
    'Karnataka': {
        'keywords': ['karnataka', 'kpsc', 'kea', 'bengaluru', 'bangalore'],
        'official_website': 'https://kpsc.kar.nic.in/',
        'apply_url': 'https://kpsc.kar.nic.in/',
        'default_board': 'KPSC Karnataka'
    },
    'Tamil Nadu': {
        'keywords': ['tamil nadu', 'tnpsc', 'tnusrb', 'chennai'],
        'official_website': 'https://tnpsc.gov.in/',
        'apply_url': 'https://tnpsc.gov.in/',
        'default_board': 'TNPSC Tamil Nadu'
    },
    'Kerala': {
        'keywords': ['kerala', 'kpsc kerala', 'keralapsc'],
        'official_website': 'https://keralapsc.gov.in/',
        'apply_url': 'https://keralapsc.gov.in/',
        'default_board': 'Kerala PSC'
    },
    'Assam & North East': {
        'keywords': ['assam', 'apsc', 'guwahati', 'meghalaya', 'tripura', 'manipur'],
        'official_website': 'https://apsc.nic.in/',
        'apply_url': 'https://apsc.nic.in/',
        'default_board': 'APSC Assam / North East'
    },
    'Jammu & Kashmir': {
        'keywords': ['jammu', 'kashmir', 'jkssb', 'jkpsc', 'srinagar'],
        'official_website': 'https://jkssb.nic.in/',
        'apply_url': 'https://jkssb.nic.in/',
        'default_board': 'JKSSB Jammu & Kashmir'
    }
}

# Live feeds connecting all states and central agencies
LIVE_RECRUITMENT_FEEDS = [
    'https://news.google.com/rss/search?q=sarkari+naukri+recruitment+notification+2026&hl=en-IN&gl=IN&ceid=IN:en',
    'https://news.google.com/rss/search?q=state+psc+recruitment+notification+apply+online+2026&hl=en-IN&gl=IN&ceid=IN:en',
    'https://news.google.com/rss/search?q=police+constable+sub+inspector+recruitment+2026&hl=en-IN&gl=IN&ceid=IN:en',
    'https://news.google.com/rss/search?q=teacher+recruitment+tet+notification+2026&hl=en-IN&gl=IN&ceid=IN:en',
    'https://news.google.com/rss/search?q=railway+recruitment+rrb+apply+online+2026&hl=en-IN&gl=IN&ceid=IN:en'
]

def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text).strip('-')
    return text[:80]

def clean_title(raw_title: str) -> str:
    # Remove news outlet suffix (e.g. " - The Indian Express", " - Sakshi Education")
    cleaned = re.sub(r'\s*-\s*[A-Za-z0-9\s\.]+$', '', raw_title).strip()
    return cleaned

def detect_state(title: str, text: str = ""):
    combined = f"{title} {text}".lower()
    for state, info in STATE_BOARD_MAP.items():
        if any(k in combined for k in info['keywords']):
            return state, info
            
    # Default to Central / All India
    return 'All India', {
        'official_website': 'https://ssc.gov.in/',
        'apply_url': 'https://ssc.gov.in/',
        'default_board': 'Central Government / All India'
    }

def detect_category(title: str, board: str) -> str:
    combined = f"{title} {board}".lower()
    
    # Check Teaching
    if any(k in combined for k in ['teacher', 'ctet', 'reet', 'tet', 'tgt', 'pgt', 'prt', 'kvs', 'dsssb', 'school', 'faculty']):
        return 'Teaching'
    # Check Police & Defense
    elif any(k in combined for k in ['police', 'constable', 'sub inspector', 'daroga', 'si ', 'agniveer', 'army', 'navy', 'airforce', 'defense', 'bsf', 'crpf', 'cisf', 'itbp', 'ssb', 'assam rifles', 'security', 'rpf']):
        return 'Police'
    # Check Railway
    elif any(k in combined for k in ['railway', 'rrb', 'rrc', 'ntpc', 'alp', 'technician', 'group d', 'loco pilot', 'metro']):
        return 'Railway'
    # Check UPSC
    elif any(k in combined for k in ['upsc', 'ias', 'ips', 'civil services', 'nda', 'cds', 'capf']):
        return 'UPSC'
    # Check State PSC
    elif any(k in combined for k in ['rpsc', 'upsssc', 'bpsc', 'mppsc', 'hssc', 'wbpsc', 'appsc', 'tspsc', 'kpsc', 'tnpsc', 'opsc', 'jpsc', 'cgpsc', 'ukpsc', 'hppsc', 'jkssb', 'rsmssb', 'cet', 'pet', 'patwari', 'ras', 'lekhpal']):
        return 'State'
    # Check Banking
    elif any(k in combined for k in ['bank', 'ibps', 'sbi', 'rbi', 'clerk', ' po ', 'po/', 'po)', 'nabard', 'sebi']):
        return 'Banking'
    # Check SSC
    elif any(k in combined for k in ['ssc', 'cgl', 'chsl', 'mts', 'cpo', 'stenographer', 'gd constable']):
        return 'SSC'
    else:
        return 'State'

def fetch_and_sync_vacancies():
    """
    All-India Pan-India Multi-State Automated Recruitment Crawler.
    Polls real government recruitment feeds across all Indian states,
    detects State, Board, Category, and Official Portal Link,
    deduplicates against SQLite, and automatically publishes new vacancies.
    """
    init_db()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now_str}] [PAN-INDIA CRAWLER] Starting All-India Multi-State Vacancy Check...")
    
    total_found = 0
    items_added = 0
    added_titles = []
    
    # 1. First, ensure comprehensive curated state & central streams are checked
    try:
        from add_comprehensive_exams import COMPREHENSIVE_EXAMS
        for item in COMPREHENSIVE_EXAMS:
            total_found += 1
            slug = item.get('slug') or slugify(item['title'])
            title = item['title']
            source_url = item.get('source_url', '')
            if not exam_exists(slug=slug, title=title, source_url=source_url):
                create_exam(item)
                items_added += 1
                added_titles.append(title)
                print(f"  [+] Curated vacancy added: {title}")
    except Exception as e:
        print(f"Notice during curated stream check: {e}")

    # 2. Scrape live Pan-India feeds across all Indian states
    for feed_url in LIVE_RECRUITMENT_FEEDS:
        try:
            req = urllib.request.Request(feed_url, headers={'User-Agent': USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                xml_data = resp.read()
                
            root = ET.fromstring(xml_data)
            items = root.findall('.//item')
            total_found += len(items)
            
            for it in items:
                raw_title = it.find('title').text if it.find('title') is not None else ''
                title = clean_title(raw_title)
                
                # Must be genuine recruitment notice
                title_lower = title.lower()
                if not any(k in title_lower for k in ['recruitment', 'vacancy', 'vacancies', 'bharti', 'post', 'apply', 'notification', 'admit card', 'exam']):
                    continue
                    
                state, state_info = detect_state(title)
                category = detect_category(title, state_info['default_board'])
                slug = slugify(title)
                
                source_link = it.find('link').text if it.find('link') is not None else ''
                
                if exam_exists(slug=slug, title=title, source_url=source_link):
                    continue
                    
                exam_record = {
                    'title': title,
                    'slug': slug,
                    'category': category,
                    'board_name': state_info['default_board'],
                    'total_vacancies': 'Check Official Notification',
                    'short_description': f"Official recruitment announcement for {title} under {state_info['default_board']} ({state}). Candidates can apply through the official government portal.",
                    'status': 'Applications Open',
                    'notification_date': datetime.now().strftime('%d %B %Y'),
                    'apply_start_date': 'Check Official Portal',
                    'apply_last_date': 'Check Official Portal',
                    'fee_general': 'As per official notification',
                    'fee_reserved': 'As per official notification',
                    'fee_payment_mode': 'Online (Debit/Credit Card, Net Banking, UPI)',
                    'min_age': '18 Years',
                    'max_age': 'As per rules',
                    'eligibility_criteria': 'Please refer to the official notification document on the government portal for detailed educational qualifications.',
                    'selection_process': '1. Written Examination / CBT\n2. Document Verification\n3. Medical Examination',
                    'syllabus_summary': 'Detailed scheme of examination and syllabus are available in the official notification.',
                    'how_to_apply': f"1. Visit official website: {state_info['official_website']}\n2. Read the official recruitment notice for {title}\n3. Submit application online at {state_info['apply_url']}",
                    'link_apply_online': state_info['apply_url'],
                    'link_notification_pdf': state_info['official_website'],
                    'link_admit_card': state_info['official_website'],
                    'link_answer_key': state_info['official_website'],
                    'link_result': state_info['official_website'],
                    'link_official_website': state_info['official_website'],
                    'meta_title': f"{title} - Dates, Eligibility & Official Apply Link",
                    'meta_description': f"Check official notification for {title}, {state_info['default_board']} ({state}), eligibility, important dates, syllabus, admit card and direct official link.",
                    'keywords': f"{title}, {state} govt jobs 2026, {category} vacancy, apply online",
                    'state': state,
                    'is_auto_synced': 1,
                    'source_url': source_link
                }
                
                create_exam(exam_record)
                items_added += 1
                added_titles.append(f"{title} ({state})")
                print(f"  [+] Automatically synced from {state} [{category}]: {title}")
                
        except Exception as e:
            print(f"[PAN-INDIA CRAWLER] Feed check notice for {feed_url[:40]}: {e}")

    # Log results
    status = "SUCCESS"
    msg = f"Pan-India Auto-Sync completed! Checked across all Indian states: {total_found} notices examined, {items_added} new vacancies automatically published."
    if added_titles:
        msg += f" New additions: {', '.join(added_titles[:3])}"
        if len(added_titles) > 3:
            msg += f" and {len(added_titles) - 3} more."
            
    log_sync(status, total_found, items_added, msg)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")
    
    return {
        'status': status,
        'items_found': total_found,
        'items_added': items_added,
        'message': msg
    }

if __name__ == '__main__':
    fetch_and_sync_vacancies()
