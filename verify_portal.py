import urllib.request
import urllib.parse
import http.cookiejar
import json
import time
import sys

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_URL = "http://127.0.0.1:8000"

def test_routes():
    print("Testing Govt Exam Portal endpoints & Auto-Scraper...")
    
    # 1. Test Homepage
    try:
        req = urllib.request.urlopen(f"{BASE_URL}/", timeout=10)
        assert req.status == 200, f"Expected 200, got {req.status}"
        html = req.read().decode('utf-8')
        assert "CTET 2026" in html, "CTET 2026 not found in homepage"
        assert "SarkariExam" in html, "Brand title not found in homepage"
        print("[PASS] 1. Homepage (/) test passed!")
    except Exception as e:
        print(f"[FAIL] 1. Homepage test failed: {e}")
        return False

    # 2. Test Auto-Synced Exam Page (e.g. SSC CHSL 2026)
    try:
        req = urllib.request.urlopen(f"{BASE_URL}/exam/ssc-chsl-102-2026-notification-combined-higher-secondary-level", timeout=10)
        assert req.status == 200, f"Expected 200, got {req.status}"
        html = req.read().decode('utf-8')
        assert "ssc.gov.in" in html, "Official link ssc.gov.in not found"
        assert "Apply Online" in html, "Apply Online button not found"
        assert "Official Notification" in html, "Official Notification button not found"
        print("[PASS] 2. Auto-synced exam detail page (SSC CHSL 2026) test passed with Official Links!")
    except Exception as e:
        print(f"[FAIL] 2. Auto-synced exam detail page test failed: {e}")
        return False

    # 3. Test Admin Login, Automation Center & Manual Fetch Trigger
    try:
        cookie_jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
        
        login_data = urllib.parse.urlencode({
            "username": "admin",
            "password": "admin@examportal2026"
        }).encode('utf-8')
        
        req = urllib.request.Request(f"{BASE_URL}/admin/login", data=login_data, method="POST")
        opener.open(req)
        
        # Test /admin/automation
        auto_req = urllib.request.Request(f"{BASE_URL}/admin/automation")
        auto_resp = opener.open(auto_req)
        assert auto_resp.status == 200, "Automation center failed"
        auto_html = auto_resp.read().decode('utf-8')
        assert "Automated Vacancy Scraper" in auto_html, "Automation title missing"
        assert "Monitored Official Sources" in auto_html, "Sources missing"
        print("[PASS] 3. Admin Automation & Scraper Center (/admin/automation) test passed!")
        
        # Test 1-Click Trigger POST /admin/auto-fetch
        fetch_req = urllib.request.Request(f"{BASE_URL}/admin/auto-fetch", data=b"", method="POST")
        fetch_resp = opener.open(fetch_req)
        assert fetch_resp.status == 200, "Auto-fetch trigger failed"
        fetch_html = fetch_resp.read().decode('utf-8')
        assert "Auto-Sync Complete" in fetch_html, "Auto-sync success message missing"
        print("[PASS] 4. Admin 1-Click '⚡ Auto-Fetch Vacancies Now' trigger test passed!")

    except Exception as e:
        print(f"[FAIL] Admin automation tests failed: {e}")
        return False

    print("\n[ALL TESTS PASSED] The automated vacancy scraper and portal are 100% operational!")
    return True

if __name__ == "__main__":
    test_routes()
