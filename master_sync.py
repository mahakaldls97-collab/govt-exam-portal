import urllib.request
import json
import re
from bs4 import BeautifulSoup
from database import create_exam, get_db, init_db, exam_exists
from app import parse_raw_exam_text

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

def clear_all_exams():
    """Wipes the exams and faqs tables cleanly."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM exams")
    cur.execute("DELETE FROM faqs")
    try:
        cur.execute("DELETE FROM sqlite_sequence WHERE name IN ('exams', 'faqs')")
    except Exception:
        pass
    conn.commit()
    conn.close()
    print("ALL OLD EXAMS WIPED CLEAN!")

def sync_studygovthelp_batch(pages=3, per_page=15):
    """
    Fetches real-time structured posts from studygovthelp.in REST API,
    processes them through Smart Parser V2, and saves them with all 9 steps!
    """
    print(f"\n[1/3] Syncing fresh posts from studygovthelp.in (pages={pages}, per_page={per_page})...")
    headers = {'User-Agent': USER_AGENT}
    added_count = 0

    for page in range(1, pages + 1):
        url = f"https://studygovthelp.in/wp-json/wp/v2/posts?page={page}&per_page={per_page}"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                posts = json.loads(resp.read().decode('utf-8'))
                
            for p in posts:
                raw_title = p.get('title', {}).get('rendered', '').strip()
                content_html = p.get('content', {}).get('rendered', '')
                source_url = p.get('link', '')
                publish_date = p.get('date', '')[:10]
                
                soup = BeautifulSoup(content_html, 'html.parser')
                body_text = soup.get_text('\n')
                
                full_raw = f"{raw_title}\n{body_text}"
                parsed = parse_raw_exam_text(full_raw)
                
                if not parsed or not parsed.get('title'):
                    continue
                    
                # Ensure unique slug
                base_slug = parsed['slug']
                slug = base_slug
                c = 1
                while exam_exists(slug):
                    slug = f"{base_slug}-{c}"
                    c += 1
                parsed['slug'] = slug
                parsed['source_url'] = source_url
                parsed['notification_date'] = publish_date or parsed.get('notification_date')
                parsed['is_auto_synced'] = 1
                
                # Extract official links from html anchor tags if missing
                for a in soup.find_all('a', href=True):
                    href = a['href'].strip()
                    txt = a.get_text().lower()
                    if '.gov.in' in href or '.nic.in' in href or 'indianrailways' in href:
                        if 'apply' in txt and not parsed.get('link_apply_online'):
                            parsed['link_apply_online'] = href
                        elif not parsed.get('link_official_website'):
                            parsed['link_official_website'] = href
                
                create_exam(parsed)
                added_count += 1
                print(f"  + Added: {parsed.get('short_title', parsed['title'])[:50]} [{parsed.get('category')}]")
        except Exception as e:
            print(f"  ! Page {page} error or complete: {e}")
            break

    print(f"-> Total from studygovthelp.in added: {added_count}")
    return added_count

def sync_sarkariresult_batch(limit=20):
    """
    Fetches latest job/admit card/result notifications from sarkariresult.com.cm,
    passes full deep-scraped content into parse_raw_exam_text, and adds to DB.
    """
    print(f"\n[2/3] Syncing fresh posts from sarkariresult.com.cm (limit={limit})...")
    from sarkariresult_crawler import parse_sarkariresult_home
    
    try:
        categories = parse_sarkariresult_home()
    except Exception as e:
        print(f"  ! Error fetching sarkariresult home: {e}")
        return 0
        
    added_count = 0
    scraped_items = []
    
    # Collect items across categories
    for cat_name, items in categories.items():
        for it in items[:7]:
            scraped_items.append((cat_name, it))
            
    headers = {'User-Agent': USER_AGENT}
    
    for cat_name, item in scraped_items[:limit]:
        title = item.get('title', '').strip()
        url = item.get('link', '').strip()
        if not title or not url or not url.startswith('http'):
            continue
            
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                page_html = resp.read().decode('utf-8', errors='ignore')
                
            soup = BeautifulSoup(page_html, 'html.parser')
            text = soup.get_text('\n')
            
            full_raw = f"{title}\n{text}"
            parsed = parse_raw_exam_text(full_raw)
            if not parsed or not parsed.get('title'):
                continue
                
            base_slug = parsed['slug']
            slug = base_slug
            c = 1
            while exam_exists(slug):
                slug = f"{base_slug}-{c}"
                c += 1
            parsed['slug'] = slug
            parsed['source_url'] = url
            parsed['is_auto_synced'] = 1
            
            # Status alignment
            if 'result' in cat_name.lower():
                parsed['status'] = 'Result Declared'
                parsed['category'] = 'Results'
            elif 'admit' in cat_name.lower():
                parsed['status'] = 'Admit Card Released'
                parsed['category'] = 'Admit Card'
                
            create_exam(parsed)
            added_count += 1
            print(f"  + Added: {parsed.get('short_title', parsed['title'])[:50]} [{parsed.get('category')}]")
        except Exception as e:
            # Skip on network timeout / block
            continue

    print(f"-> Total from sarkariresult added: {added_count}")
    return added_count

def run_master_pipeline():
    init_db()
    clear_all_exams()
    c1 = sync_studygovthelp_batch(pages=3, per_page=15)
    c2 = sync_sarkariresult_batch(limit=15)
    total = c1 + c2
    print(f"\n==========================================")
    print(f"SUCCESS: Total fresh exams added: {total}")
    print(f"==========================================")

if __name__ == '__main__':
    run_master_pipeline()
