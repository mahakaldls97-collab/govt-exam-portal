import uvicorn
import os
import sys

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, current_dir)
    print("=" * 60)
    print("  * SARKARI EXAM PORTAL & ALERTS (2026)")
    print("  * Public Portal:  http://127.0.0.1:8000/")
    print("  * Secret Admin:   http://127.0.0.1:8000/portal-boss-secure-2026/login")
    print("  * Admin Login:    admin / admin@examportal2026")
    print("=" * 60)
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
