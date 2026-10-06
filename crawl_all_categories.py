import urllib.request
import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

category_pages = [
    ("Top Online Forms", "https://www.sarkariexam.com/category/top-online-form/"),
    ("Admit Cards", "https://www.sarkariexam.com/category/admit-card/"),
    ("Exam Results", "https://www.sarkariexam.com/category/exam-result/"),
    ("Answer Key", "https://www.sarkariexam.com/category/answer-key/"),
    ("Railway Jobs", "https://www.sarkariexam.com/category/railway-jobs/"),
    ("Police Jobs", "https://www.sarkariexam.com/category/police-jobs/"),
    ("Teaching Jobs", "https://www.sarkariexam.com/category/teaching-jobs/"),
    ("SSC Jobs", "https://www.sarkariexam.com/category/ssc-jobs/"),
    ("Bank Jobs", "https://www.sarkariexam.com/category/bank-jobs/"),
    ("Defence Jobs", "https://www.sarkariexam.com/category/defence-jobs/"),
    ("UP Jobs", "https://www.sarkariexam.com/category/up-job/"),
    ("Bihar Jobs", "https://www.sarkariexam.com/category/bihar-job/"),
]

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

total_unique_links = set()

for name, cat_url in category_pages:
    try:
        req = urllib.request.Request(cat_url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            
            # Extract links and titles
            matches = re.findall(r'<a[^>]+href=[\'"](https?://www.sarkariexam.com/[a-z0-9-]+/)[\'"][^>]*>(.*?)</a>', html, re.I | re.DOTALL)
            count = 0
            for url, title in matches:
                if any(skip in url for skip in ['category', 'tag', 'about', 'contact', 'privacy', 'disclaimer', 'page', 'author', 'feed']):
                    continue
                clean_t = re.sub(r'<[^>]+>', '', title).strip()
                if len(clean_t) > 10:
                    total_unique_links.add((clean_t, url))
                    count += 1
            print(f"[{name:<20}] -> Found {count} exams")
    except Exception as e:
        print(f"[{name:<20}] -> Error: {e}")

print(f"\n=======================================================")
print(f"Total Unique Exams Discovered: {len(total_unique_links)}")
print(f"=======================================================")
