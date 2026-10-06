import urllib.request
import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

url = "https://govt-exam-portal-i3am.onrender.com/exam/rajasthan-cet-12th-level-2026-notification"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})

try:
    content = urllib.request.urlopen(req, timeout=15).read().decode('utf-8')
    
    print("=== LIVE PAGE SECTIONS FOR RAJASTHAN CET ===")
    
    # Extract Highlights Table
    h_block = re.findall(r'<div class="bg-white rounded-3xl p-6 border border-slate-200 shadow-sm">.*?</h2>(.*?)</div>\s*</div>', content, re.DOTALL)
    
    # Strip HTML to see plain text
    clean_text = re.sub(r'<[^>]+>', ' | ', content)
    clean_text = re.sub(r'\s+', ' ', clean_text)
    
    # Find snippets for Dates, Fees, Age
    for keyword in ['महत्वपूर्ण तिथियां', 'आवेदन शुल्क', 'आयु सीमा', 'परीक्षा संक्षिप्त विवरण', 'Important Dates', 'Application Fee']:
        pos = clean_text.find(keyword)
        if pos != -1:
            print(f"\n--- FOUND [{keyword}] ---")
            print(clean_text[pos:pos+350])
            
except Exception as e:
    print("Error:", e)
