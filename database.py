import sqlite3
import os
import re
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from data_quality import CANONICAL_STATUSES, parse_date, canonical_status

IST = timezone(timedelta(hours=5, minutes=30))

def now_ist_str():
    # Syncs run on GitHub/Vercel (UTC) and locally (IST); pin IST so
    # updated_at ordering does not flip with the host timezone.
    return datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ORIGINAL_DB = os.path.join(BASE_DIR, "portal.db")

# In serverless environments (like Vercel), the deployment root is read-only.
# We copy portal.db to /tmp/portal.db so SQLite can execute reads and writes without error.
_override_db = os.getenv("PORTAL_DB_PATH", "").strip()
if _override_db:
    DB_PATH = os.path.abspath(_override_db)
elif os.getenv("VERCEL") or not os.access(BASE_DIR, os.W_OK):
    DB_PATH = os.path.join(tempfile.gettempdir(), "portal.db")
    if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) == 0:
        if os.path.exists(ORIGINAL_DB):
            shutil.copy2(ORIGINAL_DB, DB_PATH)
else:
    DB_PATH = ORIGINAL_DB

def _word_match(haystack, needle):
    if not haystack or not needle:
        return 0
    pattern = r"(?<![A-Za-z0-9])" + re.escape(str(needle)) + r"(?![A-Za-z0-9])"
    return 1 if re.search(pattern, str(haystack), re.IGNORECASE) else 0

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.create_function("word_match", 2, _word_match)
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
    except Exception:
        pass
    
    # Exams table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS exams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        category TEXT NOT NULL,
        board_name TEXT NOT NULL,
        total_vacancies TEXT DEFAULT 'Various Posts',
        short_description TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Applications Open',
        badge_color TEXT DEFAULT 'emerald',
        
        -- Important Dates
        notification_date TEXT,
        apply_start_date TEXT,
        apply_last_date TEXT,
        fee_last_date TEXT,
        correction_last_date TEXT,
        admit_card_date TEXT,
        exam_date TEXT,
        result_date TEXT,
        
        -- Fees
        fee_general TEXT,
        fee_reserved TEXT,
        fee_payment_mode TEXT DEFAULT 'Online (Debit/Credit Card, Net Banking, UPI)',
        
        -- Age Limits
        min_age TEXT,
        max_age TEXT,
        age_as_on TEXT,
        age_relaxation TEXT,
        
        -- Eligibility & Selection
        eligibility_criteria TEXT,
        selection_process TEXT,
        syllabus_summary TEXT,
        how_to_apply TEXT,
        
        -- Important Direct Action Links (Official)
        link_apply_online TEXT,
        link_notification_pdf TEXT,
        link_admit_card TEXT,
        link_answer_key TEXT,
        link_result TEXT,
        link_official_website TEXT,
        link_previous_papers TEXT,
        
        -- SEO Fields
        meta_title TEXT,
        meta_description TEXT,
        keywords TEXT,
        
        views_count INTEGER DEFAULT 0,
        is_featured INTEGER DEFAULT 0,
        is_auto_synced INTEGER DEFAULT 0,
        source_url TEXT DEFAULT '',
        state TEXT DEFAULT 'All India',
        content_html TEXT DEFAULT '',
        source_checked_at TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Try adding is_auto_synced, source_url, state, and content_html columns if existing table doesn't have them
    try:
        cursor.execute("ALTER TABLE exams ADD COLUMN is_auto_synced INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE exams ADD COLUMN source_url TEXT DEFAULT ''")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE exams ADD COLUMN state TEXT DEFAULT 'All India'")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE exams ADD COLUMN content_html TEXT DEFAULT ''")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE exams ADD COLUMN short_title TEXT DEFAULT ''")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE exams ADD COLUMN post_name TEXT DEFAULT ''")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE exams ADD COLUMN department TEXT DEFAULT ''")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE exams ADD COLUMN advt_no TEXT DEFAULT ''")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE exams ADD COLUMN pay_level TEXT DEFAULT ''")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE exams ADD COLUMN fee_refund_note TEXT DEFAULT ''")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE exams ADD COLUMN source_checked_at TEXT DEFAULT ''")
    except Exception:
        pass
    
    # Admin users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # FAQs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS faqs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_id INTEGER,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        FOREIGN KEY(exam_id) REFERENCES exams(id) ON DELETE CASCADE
    )
    """)
    
    # Automation Sync Logs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sync_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT NOT NULL,
        items_found INTEGER DEFAULT 0,
        items_added INTEGER DEFAULT 0,
        message TEXT
    )
    """)
    
    conn.commit()
    conn.close()

def exam_exists(slug=None, title=None, source_url=None):
    conn = get_db()
    cursor = conn.cursor()
    if slug:
        cursor.execute("SELECT id FROM exams WHERE slug = ?", (slug,))
        if cursor.fetchone():
            conn.close()
            return True
    if title:
        cursor.execute("SELECT id FROM exams WHERE LOWER(title) = LOWER(?)", (title,))
        if cursor.fetchone():
            conn.close()
            return True
    if source_url and source_url.strip():
        cursor.execute("SELECT id FROM exams WHERE source_url = ?", (source_url,))
        if cursor.fetchone():
            conn.close()
            return True
    conn.close()
    return False

def get_all_exams(limit=100, category=None, search=None, status=None, state=None, featured_only=False, hide_expired=True):
    conn = get_db()
    cursor = conn.cursor()
    query = "SELECT * FROM exams WHERE 1=1"
    params = []
    
    # Hide only archived/expired vacancies. Closed applications stay visible
    # with an accurate "Applications Closed" badge until they are archived.
    if hide_expired:
        query += " AND status NOT IN ('Archived', 'Expired')"
    
    if category and category.lower() != 'all':
        cat_clean = category.lower().replace("-", " ").strip()
        if cat_clean in ('results', 'result', 'परिणाम'):
            query += " AND status IN ('Result', 'Answer Key')"
        elif cat_clean in ('admit card', 'admit cards', 'admit', 'प्रवेश पत्र'):
            query += " AND status = 'Admit Card'"
        elif cat_clean in ('latest jobs', 'latest job', 'jobs', 'latest', 'ऑनलाइन फॉर्म', 'job'):
            query += " AND status IN ('Applications Open', 'Upcoming')"
        elif cat_clean in ('answer key', 'answer keys', 'answer', 'उत्तर कुंजी'):
            query += " AND (status = 'Answer Key' OR title LIKE '%Answer Key%' OR title LIKE '%उत्तर कुंजी%')"
        elif cat_clean in ('syllabus', 'exam pattern', 'पाठ्यक्रम'):
            query += (" AND (LOWER(title) LIKE '%syllabus%' OR LOWER(title) LIKE '%exam pattern%'"
                      " OR title LIKE '%पाठ्यक्रम%' OR title LIKE '%परीक्षा पैटर्न%' OR title LIKE '%सिलेबस%')")
        else:
            query += " AND LOWER(category) = LOWER(?)"
            params.append(category)
        
    if status:
        status_clean = status.strip()
        alias = {
            'open': 'Applications Open', 'active': 'Applications Open',
            'result declared': 'Result', 'results': 'Result',
            'admit card released': 'Admit Card', 'admit card / exam': 'Admit Card',
            'upcoming notification': 'Upcoming', 'answer key released': 'Answer Key',
        }.get(status_clean.lower(), status_clean)
        if alias in CANONICAL_STATUSES:
            query += " AND status = ?"
            params.append(alias)
        else:
            query += " AND status LIKE ?"
            params.append(f"%{status_clean}%")

    if state and state.lower() != 'all':
        query += " AND (LOWER(state) = LOWER(?) OR LOWER(state) LIKE ?)"
        params.extend([state, f"%{state}%"])
        
    if featured_only:
        query += " AND is_featured = 1"
        
    if search:
        query += (" AND (word_match(title, ?) OR word_match(board_name, ?) OR word_match(category, ?)"
                  " OR word_match(state, ?) OR word_match(short_description, ?) OR word_match(keywords, ?)"
                  " OR word_match(post_name, ?) OR word_match(advt_no, ?))")
        term = search.strip()
        params.extend([term] * 8)
        
    # Newest source post first. updated_at alone re-ranks old exams whenever a
    # maintenance pass touches them, so the source date drives the order.
    query += (" ORDER BY CASE WHEN notification_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'"
              " THEN notification_date ELSE date(updated_at) END DESC, updated_at DESC LIMIT ?")
    params.append(limit)
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_all_states():
    """Returns all distinct states present in exams table with count"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT state, COUNT(*) as count 
        FROM exams 
        WHERE state IS NOT NULL AND state != ''
          AND status NOT IN ('Archived', 'Expired')
        GROUP BY state 
        ORDER BY count DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_exam_by_slug(slug):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM exams WHERE slug = ?", (slug,))
    row = cursor.fetchone()
    if row:
        try:
            cursor.execute("UPDATE exams SET views_count = views_count + 1 WHERE slug = ?", (slug,))
            conn.commit()
        except Exception:
            pass
        exam = dict(row)
        cursor.execute("SELECT * FROM faqs WHERE exam_id = ?", (exam['id'],))
        exam['faqs'] = [dict(faq) for faq in cursor.fetchall()]
        conn.close()
        return exam
    conn.close()
    return None

def get_exam_by_id(exam_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM exams WHERE id = ?", (exam_id,))
    row = cursor.fetchone()
    if row:
        exam = dict(row)
        cursor.execute("SELECT * FROM faqs WHERE exam_id = ?", (exam['id'],))
        exam['faqs'] = [dict(faq) for faq in cursor.fetchall()]
        conn.close()
        return exam
    conn.close()
    return None

def create_exam(data):
    conn = get_db()
    cursor = conn.cursor()
    columns = [
        'title', 'slug', 'category', 'board_name', 'total_vacancies', 'short_description',
        'status', 'badge_color', 'notification_date', 'apply_start_date', 'apply_last_date',
        'fee_last_date', 'correction_last_date', 'admit_card_date', 'exam_date', 'result_date',
        'fee_general', 'fee_reserved', 'fee_payment_mode', 'min_age', 'max_age', 'age_as_on',
        'age_relaxation', 'eligibility_criteria', 'selection_process', 'syllabus_summary',
        'how_to_apply', 'link_apply_online', 'link_notification_pdf', 'link_admit_card',
        'link_answer_key', 'link_result', 'link_official_website', 'link_previous_papers',
        'meta_title', 'meta_description', 'keywords', 'is_featured', 'is_auto_synced', 'source_url', 'state', 'content_html',
        'short_title', 'post_name', 'department', 'advt_no', 'pay_level', 'fee_refund_note',
        'created_at', 'updated_at'
    ]
    
    if not data.get('state'):
        data['state'] = 'All India'

    now = now_ist_str()
    data.setdefault('created_at', now)
    data.setdefault('updated_at', now)
        
    status = data.get('status', 'Applications Open')
    if 'Open' in status or 'Active' in status:
        badge_color = 'emerald'
    elif 'Admit Card' in status:
        badge_color = 'blue'
    elif 'Result' in status:
        badge_color = 'amber'
    elif 'Answer Key' in status:
        badge_color = 'purple'
    elif 'Upcoming' in status:
        badge_color = 'indigo'
    else:
        badge_color = 'rose'
    data['badge_color'] = badge_color
    
    placeholders = ", ".join(["?" for _ in columns])
    col_str = ", ".join(columns)
    values = [data.get(col, '') for col in columns]
    
    cursor.execute(f"INSERT INTO exams ({col_str}) VALUES ({placeholders})", values)
    exam_id = cursor.lastrowid
    
    faqs = data.get('faqs', [])
    for faq in faqs:
        if faq.get('question') and faq.get('answer'):
            cursor.execute("INSERT INTO faqs (exam_id, question, answer) VALUES (?, ?, ?)",
                           (exam_id, faq['question'], faq['answer']))
            
    conn.commit()
    conn.close()
    return exam_id

def update_exam(exam_id, data):
    conn = get_db()
    cursor = conn.cursor()
    allowed_columns = [
        'title', 'slug', 'category', 'board_name', 'total_vacancies', 'short_description',
        'status', 'badge_color', 'notification_date', 'apply_start_date', 'apply_last_date',
        'fee_last_date', 'correction_last_date', 'admit_card_date', 'exam_date', 'result_date',
        'fee_general', 'fee_reserved', 'fee_payment_mode', 'min_age', 'max_age', 'age_as_on',
        'age_relaxation', 'eligibility_criteria', 'selection_process', 'syllabus_summary',
        'how_to_apply', 'link_apply_online', 'link_notification_pdf', 'link_admit_card',
        'link_answer_key', 'link_result', 'link_official_website', 'link_previous_papers',
        'meta_title', 'meta_description', 'keywords', 'is_featured', 'state', 'content_html',
        'short_title', 'post_name', 'department', 'advt_no', 'pay_level', 'fee_refund_note',
        'source_url', 'is_auto_synced'
    ]
    columns = [col for col in allowed_columns if col in data]
    if not columns:
        conn.close()
        return

    if 'status' in data:
        status = data.get('status') or 'Applications Open'
        if 'Open' in status or 'Active' in status:
            badge_color = 'emerald'
        elif 'Admit Card' in status:
            badge_color = 'blue'
        elif 'Result' in status:
            badge_color = 'amber'
        elif 'Answer Key' in status:
            badge_color = 'purple'
        elif 'Upcoming' in status:
            badge_color = 'indigo'
        else:
            badge_color = 'gray'
        if 'badge_color' not in data:
            data['badge_color'] = badge_color
            columns.append('badge_color')

    set_clause = ", ".join([f"{col} = ?" for col in columns])
    values = [data.get(col, '') for col in columns]
    values.append(now_ist_str())
    values.append(exam_id)
    
    cursor.execute(f"UPDATE exams SET {set_clause}, updated_at = ? WHERE id = ?", values)
    
    if 'faqs' in data:
        cursor.execute("DELETE FROM faqs WHERE exam_id = ?", (exam_id,))
        for faq in data['faqs']:
            if faq.get('question') and faq.get('answer'):
                cursor.execute("INSERT INTO faqs (exam_id, question, answer) VALUES (?, ?, ?)",
                               (exam_id, faq['question'], faq['answer']))
                               
    conn.commit()
    conn.close()

def delete_exam(exam_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM faqs WHERE exam_id = ?", (exam_id,))
    cursor.execute("DELETE FROM exams WHERE id = ?", (exam_id,))
    conn.commit()
    conn.close()

def log_sync(status: str, items_found: int, items_added: int, message: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO sync_logs (status, items_found, items_added, message)
    VALUES (?, ?, ?, ?)
    """, (status, items_found, items_added, message))
    conn.commit()
    conn.close()

def get_sync_logs(limit=15):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sync_logs ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_stats():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM exams WHERE status NOT IN ('Archived', 'Expired')")
    total_exams = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM exams WHERE status = 'Applications Open'")
    active_applications = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM exams WHERE status = 'Admit Card'")
    admit_cards = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM exams WHERE status IN ('Result', 'Answer Key')")
    results = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM exams WHERE is_auto_synced = 1")
    auto_synced_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT category, COUNT(*) as count FROM exams GROUP BY category")
    categories = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT timestamp FROM sync_logs WHERE status = 'SUCCESS' ORDER BY id DESC LIMIT 1")
    last_sync_row = cursor.fetchone()
    last_sync_time = last_sync_row[0] if last_sync_row else "Never"
    
    conn.close()
    return {
        'total_exams': total_exams,
        'active_applications': active_applications,
        'admit_cards': admit_cards,
        'results': results,
        'auto_synced_count': auto_synced_count,
        'last_sync_time': last_sync_time,
        'categories': categories
    }

def auto_cleanup_expired_exams():
    """Refresh statuses from real dates.

    Applications Open -> Upcoming -> Admit Card -> Result. Exams are hidden
    only when the source post itself is gone (source_cleanup.py), not merely
    because their dates are old, so historical exams stay readable.
    Title keywords always win (an update titled "Result" is never reopened).
    """
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now(IST)
    today = now.date()
    moved_to_admit = 0
    moved_to_result = 0
    archived = 0

    cursor.execute("""
        SELECT id, title, status, apply_start_date, apply_last_date, exam_date,
               result_date, notification_date
        FROM exams
        WHERE status != 'Archived'
    """)
    rows = cursor.fetchall()

    for row in rows:
        exam = dict(row)
        current = exam.get('status') or ''
        title = exam.get('title') or ''

        new_status = canonical_status(
            current, title,
            exam.get('apply_start_date') or '',
            exam.get('apply_last_date') or '',
            exam.get('exam_date') or '',
            exam.get('result_date') or '',
            exam.get('notification_date') or '',
            today=today,
        )

        if new_status == current:
            continue

        badge = {
            'Applications Open': 'emerald', 'Applications Closed': 'slate',
            'Upcoming': 'indigo', 'Admit Card': 'blue',
            'Answer Key': 'purple', 'Result': 'amber', 'Syllabus': 'teal',
            'Archived': 'gray',
        }.get(new_status, 'slate')
        cursor.execute(
            "UPDATE exams SET status = ?, badge_color = ? WHERE id = ?",
            (new_status, badge, exam['id'])
        )
        if new_status == 'Admit Card':
            moved_to_admit += 1
        elif new_status in ('Result', 'Answer Key'):
            moved_to_result += 1
        elif new_status == 'Archived':
            archived += 1

    conn.commit()
    conn.close()
    return {
        'moved_to_admit': moved_to_admit,
        'moved_to_result': moved_to_result,
        'archived': archived,
        'dates_synced': 0,
    }
