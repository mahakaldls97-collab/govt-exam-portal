import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portal.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Try adding is_auto_synced, source_url, and state columns if existing table doesn't have them
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
    
    # Hide expired vacancies from public view by default
    if hide_expired:
        query += " AND status != 'Expired'"
    
    if category and category.lower() != 'all':
        query += " AND LOWER(category) = LOWER(?)"
        params.append(category)
        
    if status:
        query += " AND status LIKE ?"
        params.append(f"%{status}%")

    if state and state.lower() != 'all':
        query += " AND (LOWER(state) = LOWER(?) OR LOWER(state) LIKE ?)"
        params.extend([state, f"%{state}%"])
        
    if featured_only:
        query += " AND is_featured = 1"
        
    if search:
        query += " AND (title LIKE ? OR board_name LIKE ? OR category LIKE ? OR state LIKE ? OR short_description LIKE ? OR keywords LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term, term, term, term])
        
    query += " ORDER BY updated_at DESC LIMIT ?"
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
        cursor.execute("UPDATE exams SET views_count = views_count + 1 WHERE slug = ?", (slug,))
        conn.commit()
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
        'meta_title', 'meta_description', 'keywords', 'is_featured', 'is_auto_synced', 'source_url', 'state'
    ]
    
    if not data.get('state'):
        data['state'] = 'All India'
        
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
    columns = [
        'title', 'slug', 'category', 'board_name', 'total_vacancies', 'short_description',
        'status', 'badge_color', 'notification_date', 'apply_start_date', 'apply_last_date',
        'fee_last_date', 'correction_last_date', 'admit_card_date', 'exam_date', 'result_date',
        'fee_general', 'fee_reserved', 'fee_payment_mode', 'min_age', 'max_age', 'age_as_on',
        'age_relaxation', 'eligibility_criteria', 'selection_process', 'syllabus_summary',
        'how_to_apply', 'link_apply_online', 'link_notification_pdf', 'link_admit_card',
        'link_answer_key', 'link_result', 'link_official_website', 'link_previous_papers',
        'meta_title', 'meta_description', 'keywords', 'is_featured', 'state'
    ]
    
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
    
    set_clause = ", ".join([f"{col} = ?" for col in columns])
    values = [data.get(col, '') for col in columns]
    values.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
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
    cursor.execute("SELECT COUNT(*) FROM exams")
    total_exams = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM exams WHERE status LIKE '%Open%' OR status LIKE '%Active%'")
    active_applications = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM exams WHERE status LIKE '%Admit Card%'")
    admit_cards = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM exams WHERE status LIKE '%Result%'")
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
    """
    Automatically marks old vacancies as 'Expired' if:
    1. apply_last_date has passed (and is a real date, not 'Check Official Portal')
    2. The exam was created more than 90 days ago and still says 'Applications Open'
    Returns count of cleaned up exams.
    """
    import re
    conn = get_db()
    cursor = conn.cursor()
    cleaned = 0
    now = datetime.now()
    
    # Get all exams that are still 'Applications Open' or 'Upcoming'
    cursor.execute("""
        SELECT id, title, apply_last_date, created_at, status 
        FROM exams 
        WHERE status LIKE '%Open%' OR status LIKE '%Active%' OR status LIKE '%Upcoming%'
    """)
    rows = cursor.fetchall()
    
    for row in rows:
        exam = dict(row)
        should_expire = False
        
        # Method 1: Check if apply_last_date has a real date that has passed
        last_date_str = exam.get('apply_last_date', '') or ''
        if last_date_str and last_date_str not in ['Check Official Portal', 'As per official notification', '', 'Various', 'N/A']:
            # Try to parse common date formats
            for fmt in ['%d %B %Y', '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%d %b %Y']:
                try:
                    last_date = datetime.strptime(last_date_str.strip(), fmt)
                    if last_date < now:
                        should_expire = True
                    break
                except ValueError:
                    continue
        
        # Method 2: If created more than 90 days ago and no real date available
        if not should_expire:
            created_str = exam.get('created_at', '')
            if created_str:
                try:
                    created_date = datetime.strptime(str(created_str)[:19], '%Y-%m-%d %H:%M:%S')
                    days_old = (now - created_date).days
                    if days_old > 90:
                        should_expire = True
                except Exception:
                    pass
        
        if should_expire:
            cursor.execute("""
                UPDATE exams SET status = 'Expired', badge_color = 'gray', updated_at = ? 
                WHERE id = ?
            """, (now.strftime('%Y-%m-%d %H:%M:%S'), exam['id']))
            cleaned += 1
            print(f"  [CLEANUP] Marked as Expired: {exam['title']}")
    
    conn.commit()
    conn.close()
    return cleaned
