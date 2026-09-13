import re
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from database import init_db, create_exam, exam_exists, get_db

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

STATE_BOARD_MAP = {
    'Rajasthan': {
        'keywords': ['rajasthan', 'rsmssb', 'rpsc', 'reet', 'ras', 'rts', 'patwari', 'jaipur', 'jodhpur'],
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
        'keywords': ['haryana', 'hssc', 'hpsc', 'panchkula'],
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
        'keywords': ['gujarat', 'gpsc', 'gsssb', 'ojas', 'gandhinagar'],
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
        'keywords': ['punjab', 'ppsc', 'psssb'],
        'official_website': 'https://ppsc.gov.in/',
        'apply_url': 'https://sssb.punjab.gov.in/',
        'default_board': 'PPSC Punjab'
    },
    'Odisha': {
        'keywords': ['odisha', 'orissa', 'opsc', 'osssc', 'ossc'],
        'official_website': 'https://opsc.gov.in/',
        'apply_url': 'https://osssc.gov.in/',
        'default_board': 'OPSC / OSSSC Odisha'
    },
    'Jharkhand': {
        'keywords': ['jharkhand', 'jpsc', 'jssc'],
        'official_website': 'https://jpsc.gov.in/',
        'apply_url': 'https://jssc.nic.in/',
        'default_board': 'JPSC Jharkhand'
    },
    'Chhattisgarh': {
        'keywords': ['chhattisgarh', 'cgpsc', 'cg vyapam'],
        'official_website': 'https://psc.cg.gov.in/',
        'apply_url': 'https://vyapam.cgstate.gov.in/',
        'default_board': 'CGPSC Chhattisgarh'
    },
    'Uttarakhand': {
        'keywords': ['uttarakhand', 'ukpsc', 'uksssc'],
        'official_website': 'https://psc.uk.gov.in/',
        'apply_url': 'https://sssc.uk.gov.in/',
        'default_board': 'UKPSC Uttarakhand'
    },
    'Himachal Pradesh': {
        'keywords': ['himachal', 'hppsc', 'hpssc'],
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
        'keywords': ['karnataka', 'kpsc', 'bengaluru'],
        'official_website': 'https://kpsc.kar.nic.in/',
        'apply_url': 'https://kpsc.kar.nic.in/',
        'default_board': 'KPSC Karnataka'
    },
    'Tamil Nadu': {
        'keywords': ['tamil nadu', 'tnpsc', 'tnusrb'],
        'official_website': 'https://tnpsc.gov.in/',
        'apply_url': 'https://tnpsc.gov.in/',
        'default_board': 'TNPSC Tamil Nadu'
    },
    'Kerala': {
        'keywords': ['kerala', 'keralapsc'],
        'official_website': 'https://keralapsc.gov.in/',
        'apply_url': 'https://keralapsc.gov.in/',
        'default_board': 'Kerala PSC'
    },
    'Assam & North East': {
        'keywords': ['assam', 'apsc', 'guwahati', 'meghalaya', 'tripura', 'manipur'],
        'official_website': 'https://apsc.nic.in/',
        'apply_url': 'https://apsc.nic.in/',
        'default_board': 'APSC Assam / North East'
    }
}

def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text).strip('-')
    return text[:80]

def clean_title(raw_title: str) -> str:
    # Remove news outlet suffix
    cleaned = re.sub(r'\s*-\s*[A-Za-z0-9\s\.]+$', '', raw_title).strip()
    return cleaned

def detect_state(title: str, text: str = ""):
    combined = f"{title} {text}".lower()
    for state, info in STATE_BOARD_MAP.items():
        if any(k in combined for k in info['keywords']):
            return state, info
    return 'All India', {
        'official_website': 'https://ssc.gov.in/',
        'apply_url': 'https://ssc.gov.in/',
        'default_board': 'Central Government / All India'
    }

def detect_category(title: str, board: str) -> str:
    combined = f"{title} {board}".lower()
    if any(k in combined for k in ['teacher', 'ctet', 'reet', 'tet', 'tgt', 'pgt', 'prt', 'kvs', 'dsssb']):
        return 'Teaching'
    elif any(k in combined for k in ['police', 'constable', 'sub inspector', 'daroga', 'si', 'agniveer', 'army', 'navy', 'airforce']):
        return 'Police'
    elif any(k in combined for k in ['railway', 'rrb', 'rrc', 'ntpc', 'alp', 'technician', 'group d', 'loco pilot']):
        return 'Railway'
    elif any(k in combined for k in ['bank', 'ibps', 'sbi', 'rbi', 'clerk', 'po', 'nabard']):
        return 'Banking'
    elif any(k in combined for k in ['ssc', 'cgl', 'chsl', 'mts', 'cpo', 'gd']):
        return 'SSC'
    elif any(k in combined for k in ['upsc', 'ias', 'ips', 'civil services', 'nda', 'cds']):
        return 'UPSC'
    else:
        return 'State'

def run_test():
    feed_url = 'https://news.google.com/rss/search?q=sarkari+naukri+recruitment+notification+2026&hl=en-IN&gl=IN&ceid=IN:en'
    req = urllib.request.Request(feed_url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=10) as resp:
        xml_data = resp.read()
    
    root = ET.fromstring(xml_data)
    items = root.findall('.//item')
    print(f"Total live items found: {len(items)}")
    
    saved = 0
    for it in items:
        raw_title = it.find('title').text if it.find('title') is not None else ''
        title = clean_title(raw_title)
        
        # Check if actually a recruitment notification
        title_lower = title.lower()
        if not any(k in title_lower for k in ['recruitment', 'vacancy', 'vacancies', 'bharti', 'post', 'apply', 'notification', 'admit card', 'exam']):
            continue
            
        state, state_info = detect_state(title)
        category = detect_category(title, state_info['default_board'])
        slug = slugify(title)
        
        if exam_exists(slug=slug, title=title):
            continue
            
        print(f"Adding from {state} [{category}]: {title[:60]}")
        create_exam({
            'title': title,
            'slug': slug,
            'category': category,
            'board_name': state_info['default_board'],
            'total_vacancies': 'Check Official Notification',
            'short_description': f"Official recruitment announcement for {title} under {state_info['default_board']} ({state}).",
            'status': 'Applications Open',
            'notification_date': datetime.now().strftime('%d %B %Y'),
            'apply_start_date': 'Check Official Portal',
            'apply_last_date': 'Check Official Portal',
            'fee_general': 'As per official notification',
            'fee_reserved': 'As per official notification',
            'min_age': '18 Years',
            'max_age': 'As per rules',
            'eligibility_criteria': 'Please refer to the official notification document for detailed post-wise educational qualifications.',
            'selection_process': '1. Written Examination / CBT\n2. Document Verification\n3. Medical Examination',
            'how_to_apply': f"1. Visit official website: {state_info['official_website']}\n2. Read the official advertisement\n3. Submit online application on {state_info['apply_url']}",
            'link_apply_online': state_info['apply_url'],
            'link_notification_pdf': state_info['official_website'],
            'link_admit_card': state_info['official_website'],
            'link_answer_key': state_info['official_website'],
            'link_result': state_info['official_website'],
            'link_official_website': state_info['official_website'],
            'meta_title': f"{title} - Dates, Eligibility & Official Apply Link",
            'meta_description': f"Check official notification for {title}, {state_info['default_board']} ({state}), eligibility, syllabus, admit card and direct official apply online link.",
            'keywords': f"{title}, {state} govt jobs 2026, {category} vacancy, apply online",
            'state': state,
            'is_auto_synced': 1,
            'source_url': it.find('link').text if it.find('link') is not None else ''
        })
        saved += 1
        if saved >= 15:
            break
            
    print(f"\nSuccessfully added {saved} live state and central vacancies automatically!")

if __name__ == '__main__':
    run_test()
