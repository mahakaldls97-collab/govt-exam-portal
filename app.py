from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import os
import re
import asyncio

from database import (
    init_db, get_all_exams, get_exam_by_slug, get_exam_by_id,
    create_exam, update_exam, delete_exam, get_stats, get_sync_logs, get_all_states,
    auto_cleanup_expired_exams
)
from auth import (
    init_admin, verify_admin, create_session, is_valid_session, invalidate_session, reset_admin_password,
    generate_password_reset_token, verify_reset_token, verify_reset_otp, complete_password_reset
)
from email_service import send_password_reset_email
from seed_data import seed
from auto_scraper import fetch_and_sync_vacancies
from sarkariexam_scraper import fetch_and_sync_sarkariexam
from sarkariresult_crawler import sync_from_sarkariresult
from studygovthelp_scraper import sync_from_studygovthelp

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

app = FastAPI(title="Sarkari Result Portal", version="2.0.0")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

ENABLE_BACKGROUND_CRAWLER = os.getenv("ENABLE_BACKGROUND_CRAWLER", "false").lower() in ("true", "1", "yes")

# Background worker that automatically polls government sources and cleans expired vacancies
async def background_vacancy_crawler():
    if not ENABLE_BACKGROUND_CRAWLER:
        print("[BACKGROUND WORKER] Auto-crawler disabled on free tier to conserve quota and prevent suspension. Use Admin Panel or /api/sync/studygovthelp for on-demand sync.")
        return
    # Wait 60 seconds after server starts before first auto-sync
    await asyncio.sleep(60)
    while True:
        try:
            sync_from_studygovthelp(pages=2, per_page=15)
        except Exception as e:
            print(f"[STUDYGOVTHELP CRAWLER ERROR] {e}")
        try:
            sync_from_sarkariresult(limit_deep_scrape=15)
        except Exception as e:
            print(f"[SARKARIRESULT CRAWLER ERROR] {e}")
        try:
            fetch_and_sync_sarkariexam()
        except Exception as e:
            print(f"[SARKARIEXAM CRAWLER ERROR] {e}")
        try:
            res = auto_cleanup_expired_exams()
            print(f"[AUTO-LIFECYCLE] Moved to Admit Card: {res.get('moved_to_admit', 0)}, Moved to Result: {res.get('moved_to_result', 0)}, Archived: {res.get('archived', 0)}")
        except Exception as e:
            print(f"[CLEANUP ERROR] {e}")
        # Run every 6 hours (21600 seconds)
        await asyncio.sleep(21600)

@app.on_event("startup")
async def on_startup():
    init_db()
    init_admin()
    seed()
    # Start non-blocking background worker
    asyncio.create_task(background_vacancy_crawler())

# Helper to check admin session
def get_current_admin(request: Request):
    token = request.cookies.get("admin_session")
    if not token or not is_valid_session(token):
        return None
    return "admin"

# ----------------- PUBLIC ROUTES ----------------- #

# API: Manual sync from studygovthelp.in
@app.post("/api/sync/studygovthelp")
@app.get("/api/sync/studygovthelp")
async def api_sync_studygovthelp(pages: int = 2):
    try:
        result = sync_from_studygovthelp(pages=pages, per_page=20)
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

# API: Manual sync from sarkariresult.com.cm
@app.post("/api/sync/sarkariresult")
@app.get("/api/sync/sarkariresult")
async def api_sync_sarkariresult():
    try:
        result = sync_from_sarkariresult(limit_deep_scrape=10)
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

# API: Get exams by state (for map interaction)
@app.get("/api/exams-by-state")
async def api_exams_by_state(state: str = "All India"):
    exams = get_all_exams(limit=50)
    filtered = [dict(e) for e in exams if e['state'] == state or state == 'all']
    return JSONResponse(content={"state": state, "count": len(filtered), "exams": filtered[:30]})

@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    active_forms_exams = get_all_exams(limit=50, status="Applications Open")
    upcoming_exams = get_all_exams(limit=50, status="Upcoming")
    admit_cards_exams = get_all_exams(limit=50, status="Admit Card")
    result_exams = get_all_exams(limit=50, status="Result")
    police_exams = get_all_exams(limit=50, category="Police")
    all_active_exams = get_all_exams(limit=200)
    all_states = get_all_states()
    
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "all_exams": all_active_exams,
            "active_forms_exams": active_forms_exams,
            "upcoming_exams": upcoming_exams,
            "admit_cards_exams": admit_cards_exams,
            "result_exams": result_exams,
            "police_exams": police_exams,
            "all_states": all_states,
        }
    )

# Direct Official Redirect Mode
# When False: opens the internal rich exam detail page (with complete Saarni/Tables, Dates, Fees, and Apply Buttons)
# When True: forwards candidate straight to the official government apply/portal link.
DIRECT_OFFICIAL_REDIRECT = False

@app.get("/exam/{slug}", response_class=HTMLResponse)
async def exam_detail_page(request: Request, slug: str):
    exam = get_exam_by_slug(slug)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam information page not found")
        
    # Forward directly to official government portal
    if DIRECT_OFFICIAL_REDIRECT:
        target_url = (
            exam.get('link_apply_online')
            or exam.get('link_official_website')
            or exam.get('link_notification_pdf')
            or "/"
        )
        if target_url and target_url.startswith("http"):
            return RedirectResponse(url=target_url, status_code=status.HTTP_302_FOUND)

    return templates.TemplateResponse(
        request=request,
        name="exam_detail.html",
        context={"exam": exam}
    )

@app.get("/category/{category}", response_class=HTMLResponse)
async def category_page(request: Request, category: str):
    exams = get_all_exams(category=category, limit=250)
    all_states = get_all_states()
    
    cat_clean = category.lower().replace("-", " ").strip()
    if cat_clean in ('results', 'result'):
        display_title = "Results & Cut-Off (सरकारी रिजल्ट)"
    elif cat_clean in ('admit card', 'admit cards', 'admit'):
        display_title = "Admit Cards & Exam Dates (प्रवेश पत्र)"
    elif cat_clean in ('latest jobs', 'latest job', 'jobs', 'latest'):
        display_title = "Latest Online Jobs & Forms (नवीनतम सरकारी नौकरियां)"
    elif cat_clean in ('answer key', 'answer keys'):
        display_title = "Answer Keys & Solutions (उत्तर कुंजी)"
    elif cat_clean in ('syllabus', 'exam pattern'):
        display_title = "Syllabus & Exam Pattern (पाठ्यक्रम व पैटर्न)"
    else:
        display_title = f"{category} Category Exams"

    return templates.TemplateResponse(
        request=request,
        name="category.html",
        context={
            "category_name": display_title,
            "raw_category": category,
            "exams": exams,
            "all_states": all_states
        }
    )

@app.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, q: str = "", status: str = "", state: str = ""):
    exams = get_all_exams(search=q if q else None, status=status if status else None, state=state if state else None, limit=150)
    all_states = get_all_states()
    return templates.TemplateResponse(
        request=request,
        name="search.html",
        context={
            "search_query": q or status or state,
            "exams": exams,
            "selected_state": state,
            "all_states": all_states
        }
    )

@app.get("/disclaimer", response_class=HTMLResponse)
async def disclaimer_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="disclaimer.html",
        context={}
    )

@app.get("/privacy-policy", response_class=HTMLResponse)
async def privacy_policy_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="privacy_policy.html",
        context={}
    )

@app.get("/about-us", response_class=HTMLResponse)
async def about_us_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="about_us.html",
        context={}
    )

@app.get("/contact-us", response_class=HTMLResponse)
async def contact_us_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="contact_us.html",
        context={}
    )

@app.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="terms.html",
        context={}
    )

# ----------------- GOOGLE SEARCH & SEO (ROBOTS & SITEMAP) ----------------- #

@app.get("/google5d3c641d428c5323.html", response_class=Response)
async def google_verification():
    return Response(content="google-site-verification: google5d3c641d428c5323.html", media_type="text/html")

@app.get("/ads.txt", response_class=Response)
async def ads_txt():
    content = "google.com, pub-3194593974955223, DIRECT, f08c47fec0942fa0\n"
    return Response(content=content, media_type="text/plain")

@app.get("/robots.txt", response_class=Response)
async def robots_txt(request: Request):
    base_url = str(request.base_url).rstrip('/')
    content = f"""User-agent: *
Allow: /
Allow: /exam/
Allow: /category/
Allow: /search
Allow: /disclaimer
Allow: /privacy-policy
Allow: /about-us
Allow: /contact-us
Allow: /terms
Allow: /ads.txt
Disallow: /portal-boss-secure-2026/
Disallow: /admin

Sitemap: {base_url}/sitemap.xml
"""
    return Response(content=content, media_type="text/plain")

@app.get("/sitemap.xml", response_class=Response)
async def sitemap_xml(request: Request):
    base_url = str(request.base_url).rstrip('/')
    exams = get_all_exams(limit=1000)
    categories = ["Police", "SSC", "Railway", "Teaching", "UPSC", "Banking", "State", "Others"]
    
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        f'  <url><loc>{base_url}/</loc><changefreq>hourly</changefreq><priority>1.0</priority></url>',
        f'  <url><loc>{base_url}/privacy-policy</loc><changefreq>monthly</changefreq><priority>0.5</priority></url>',
        f'  <url><loc>{base_url}/about-us</loc><changefreq>monthly</changefreq><priority>0.5</priority></url>',
        f'  <url><loc>{base_url}/contact-us</loc><changefreq>monthly</changefreq><priority>0.5</priority></url>',
        f'  <url><loc>{base_url}/terms</loc><changefreq>monthly</changefreq><priority>0.5</priority></url>',
        f'  <url><loc>{base_url}/disclaimer</loc><changefreq>monthly</changefreq><priority>0.3</priority></url>'
    ]
    for cat in categories:
        xml_lines.append(f'  <url><loc>{base_url}/category/{cat}</loc><changefreq>daily</changefreq><priority>0.9</priority></url>')
        
    for exam in exams:
        slug = exam.get('slug')
        if slug:
            xml_lines.append(f'  <url><loc>{base_url}/exam/{slug}</loc><changefreq>daily</changefreq><priority>0.8</priority></url>')
        
    xml_lines.append('</urlset>')
    return Response(content="\n".join(xml_lines), media_type="application/xml")

# ----------------- SECRET ADMIN ROUTES ----------------- #
# Custom secret path so public visitors cannot guess or access admin panel
SECRET_ADMIN_PATH = "/portal-boss-secure-2026"

# Block standard /admin route completely (returns 404 so hackers/visitors see nothing)
@app.get("/admin")
@app.get("/admin/{full_path:path}")
async def block_public_admin():
    raise HTTPException(status_code=404, detail="Page not found")

@app.get(f"{SECRET_ADMIN_PATH}/login", response_class=HTMLResponse)
async def admin_login_page(request: Request, msg: str = None):
    if is_valid_session(request.cookies.get("admin_session")):
        return RedirectResponse(url=SECRET_ADMIN_PATH, status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request=request,
        name="admin/login.html",
        context={"error": None, "success_msg": msg}
    )

@app.post(f"{SECRET_ADMIN_PATH}/login")
async def admin_login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    if verify_admin(username, password):
        token = create_session()
        response = RedirectResponse(url=SECRET_ADMIN_PATH, status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            key="admin_session",
            value=token,
            httponly=True,
            max_age=86400, # 24 hours
            samesite="lax"
        )
        return response
    
    return templates.TemplateResponse(
        request=request,
        name="admin/login.html",
        context={"error": "Invalid username or password! Please check credentials.", "success_msg": None}
    )

@app.get(f"{SECRET_ADMIN_PATH}/forgot-password", response_class=HTMLResponse)
async def admin_forgot_password_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin/forgot_password.html",
        context={"error": None}
    )

@app.post(f"{SECRET_ADMIN_PATH}/forgot-password")
async def admin_forgot_password_submit(
    request: Request,
    email: str = Form(...)
):
    clean_email = email.strip().lower()
    # Check if this email is a registered admin in DB
    from database import get_db
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM admins WHERE LOWER(username) = ?", (clean_email,))
    admin_row = cursor.fetchone()
    conn.close()

    if not admin_row:
        return templates.TemplateResponse(
            request=request,
            name="admin/forgot_password.html",
            context={"error": f"ईमेल '{email}' किसी भी अधिकृत एडमिन खाते से मेल नहीं खाता!"}
        )

    # Generate secure reset token & 6-digit OTP
    reset_data = generate_password_reset_token(clean_email)
    base_host = request.headers.get("host", "127.0.0.1:8000")
    protocol = "https" if request.url.scheme == "https" else "http"
    reset_link = f"{protocol}://{base_host}{SECRET_ADMIN_PATH}/reset-password-verify?token={reset_data['token']}"

    # Send reset notification with direct link and 6-digit OTP to the admin's Gmail
    send_result = send_password_reset_email(clean_email, reset_link, reset_data["otp"])

    info_text = f"आपके ईमेल ({clean_email}) पर वेरिफिकेशन लिंक व 6 अंकों का OTP भेज दिया गया है।"
    if send_result.get("method") == "logged":
        info_text += " (सुरक्षा कोड सफलतापूर्वक जनरेट हो गया है)"

    return templates.TemplateResponse(
        request=request,
        name="admin/reset_password_verify.html",
        context={
            "error": None,
            "info_msg": info_text,
            "email": clean_email,
            "token": reset_data["token"],
            "generated_link": reset_link,
            "generated_otp": reset_data["otp"]
        }
    )

@app.get(f"{SECRET_ADMIN_PATH}/reset-password-verify", response_class=HTMLResponse)
async def admin_reset_password_verify_page(request: Request, token: str = None):
    email = None
    if token:
        email = verify_reset_token(token)
        if not email:
            return templates.TemplateResponse(
                request=request,
                name="admin/forgot_password.html",
                context={"error": "यह पासवर्ड रीसेट लिंक अमान्य है या 15 मिनट की समय सीमा समाप्त (Expire) हो चुकी है! कृपया नया लिंक भेजें।"}
            )
    
    return templates.TemplateResponse(
        request=request,
        name="admin/reset_password_verify.html",
        context={
            "error": None,
            "info_msg": "ईमेल लिंक सत्यापित हुआ! कृपया अपना नया पासवर्ड दर्ज करें।" if token else None,
            "email": email or "durgalalsaini7757@gmail.com",
            "token": token
        }
    )

@app.post(f"{SECRET_ADMIN_PATH}/reset-password-verify")
async def admin_reset_password_verify_submit(
    request: Request,
    email: str = Form(...),
    token: str = Form(None),
    otp: str = Form(None),
    new_password: str = Form(...),
    confirm_password: str = Form(...)
):
    clean_email = email.strip().lower()
    clean_pass = new_password.strip()

    if clean_pass != confirm_password.strip():
        return templates.TemplateResponse(
            request=request,
            name="admin/reset_password_verify.html",
            context={
                "error": "दोनों पासवर्ड आपस में मेल नहीं खा रहे हैं!",
                "email": clean_email,
                "token": token
            }
        )

    if len(clean_pass) < 6:
        return templates.TemplateResponse(
            request=request,
            name="admin/reset_password_verify.html",
            context={
                "error": "पासवर्ड कम से कम 6 अक्षरों का होना चाहिए!",
                "email": clean_email,
                "token": token
            }
        )

    # Validate either via valid token or via matching 6-digit OTP
    valid_token = None
    if token and verify_reset_token(token) == clean_email:
        valid_token = token
    elif otp:
        matched_tok = verify_reset_otp(clean_email, otp)
        if matched_tok:
            valid_token = matched_tok

    if not valid_token:
        return templates.TemplateResponse(
            request=request,
            name="admin/reset_password_verify.html",
            context={
                "error": "गलत OTP या लिंक की अवधि समाप्त हो चुकी है! कृपया ईमेल में आया सही कोड दर्ज करें।",
                "email": clean_email,
                "token": None
            }
        )

    # Complete the password change
    ok = complete_password_reset(valid_token, clean_pass)
    if ok:
        return RedirectResponse(
            url=f"{SECRET_ADMIN_PATH}/login?msg=पासवर्ड+सफलतापूर्वक+बदल+दिया+गया+है!+अब+नए+पासवर्ड+से+लॉगिन+करें।",
            status_code=status.HTTP_302_FOUND
        )
    else:
        return templates.TemplateResponse(
            request=request,
            name="admin/reset_password_verify.html",
            context={
                "error": "पासवर्ड अपडेट करने में तकनीकी समस्या आई! कृपया पुनः प्रयास करें।",
                "email": clean_email,
                "token": None
            }
        )

@app.get(f"{SECRET_ADMIN_PATH}/logout")
async def admin_logout(request: Request):
    token = request.cookies.get("admin_session")
    if token:
        invalidate_session(token)
    response = RedirectResponse(url=f"{SECRET_ADMIN_PATH}/login?msg=आप+सफलतापूर्वक+लॉगआउट+हो+गए+हैं。", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("admin_session")
    return response

@app.get(SECRET_ADMIN_PATH, response_class=HTMLResponse)
async def admin_dashboard(request: Request, msg: str = None):
    admin = get_current_admin(request)
    if not admin:
        return RedirectResponse(url=f"{SECRET_ADMIN_PATH}/login", status_code=status.HTTP_302_FOUND)
    
    exams = get_all_exams(limit=100)
    stats = get_stats()
    return templates.TemplateResponse(
        request=request,
        name="admin/dashboard.html",
        context={
            "exams": exams,
            "stats": stats,
            "message": msg
        }
    )

# Dedicated Automation & Scraper Center
@app.get(f"{SECRET_ADMIN_PATH}/automation", response_class=HTMLResponse)
async def admin_automation_center(request: Request, msg: str = None):
    admin = get_current_admin(request)
    if not admin:
        return RedirectResponse(url=f"{SECRET_ADMIN_PATH}/login", status_code=status.HTTP_302_FOUND)
        
    stats = get_stats()
    logs = get_sync_logs(limit=25)
    return templates.TemplateResponse(
        request=request,
        name="admin/automation.html",
        context={
            "stats": stats,
            "logs": logs,
            "message": msg
        }
    )

# Manual 1-Click Trigger for Vacancy Auto-Fetch
@app.post(f"{SECRET_ADMIN_PATH}/auto-fetch")
async def admin_manual_auto_fetch(request: Request):
    admin = get_current_admin(request)
    if not admin:
        return RedirectResponse(url=f"{SECRET_ADMIN_PATH}/login", status_code=status.HTTP_302_FOUND)
        
    res_study = sync_from_studygovthelp(pages=3, per_page=20)
    res = fetch_and_sync_vacancies()
    msg = f"Auto-Sync Complete! studygovthelp.in ({res_study['items_added']} added) + Pan-India Feeds ({res['items_added']} added)."
    return RedirectResponse(url=f"{SECRET_ADMIN_PATH}/automation?msg={msg}", status_code=status.HTTP_302_FOUND)

@app.post(f"{SECRET_ADMIN_PATH}/sync-studygovthelp")
async def admin_sync_studygovthelp(request: Request):
    admin = get_current_admin(request)
    if not admin:
        return RedirectResponse(url=f"{SECRET_ADMIN_PATH}/login", status_code=status.HTTP_302_FOUND)
    res = sync_from_studygovthelp(pages=3, per_page=20)
    msg = f"studygovthelp.in Sync Complete! {res['items_found']} posts examined, {res['items_added']} new vacancies added."
    return RedirectResponse(url=f"{SECRET_ADMIN_PATH}/automation?msg={msg}", status_code=status.HTTP_302_FOUND)

def parse_raw_exam_text(raw_text: str) -> dict:
    if not raw_text or not raw_text.strip():
        return {}
    text = raw_text.strip()
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return {}

    full_lower = text.lower()

    # -------------------------------------------------------------
    # 1. ACCURATE TITLE & SHORT TITLE EXTRACTION
    # -------------------------------------------------------------
    first_line = lines[0]
    title = first_line
    short_title = ""

    if ":" in first_line:
        p1, p2 = first_line.split(":", 1)
        if len(p1.strip()) >= 5:
            short_title = p1.strip()
            title = first_line
    else:
        m_eng = re.search(r'([A-Za-z0-9\s\(\)\-\/]+202\d[A-Za-z0-9\s\(\)\-\/]*)', first_line)
        if m_eng and len(m_eng.group(1).strip()) > 8:
            short_title = m_eng.group(1).strip()
        else:
            short_title = first_line[:60]

    # Clean short title of trailing junk
    short_title = re.sub(r'\s*(?:Overview|Details|Information|Click Here|Notification|Apply Online)$', '', short_title, flags=re.I).strip()
    if not short_title:
        short_title = title[:50]

    slug = re.sub(r'[^a-z0-9]+', '-', short_title.lower()).strip('-')
    if not slug or len(slug) < 3:
        slug = f"govt-exam-{abs(hash(title)) % 100000}"

    # -------------------------------------------------------------
    # 2. SECTION SLICING (StudyGovtHelp / Notification standard layout)
    # -------------------------------------------------------------
    sec_keywords = [
        ('overview', 'overview'),
        ('important dates', 'dates'),
        ('application fees', 'fees'),
        ('age limit', 'age'),
        ('vacancy details', 'vacancy'),
        ('educational qualification', 'qualification'),
        ('selection process', 'selection'),
        ('how to apply', 'how_to_apply'),
        ('important links', 'links')
    ]

    sec_lines = {'intro': []}
    current_sec = 'intro'
    for line in lines:
        lower_line = line.lower()
        matched = None
        for kw, sec_id in sec_keywords:
            if kw in lower_line and len(lower_line) < 70:
                matched = sec_id
                break
        if matched:
            current_sec = matched
            sec_lines[current_sec] = []
        else:
            sec_lines.setdefault(current_sec, []).append(line)

    junk_tokens = [
        'ज़्यादा जानें', 'परीक्षा तैयारी सामग्री', 'सरकारी नौकरी शिक्षा',
        'पुलिस भर्ती देखें', 'सरकारी भर्ती सूचना', 'स्थानीय परमिट लें',
        'तैयारी करें', 'सरकारी भर्ती खोजें', 'Details', 'Information',
        'Event', 'Date', 'Category', 'Application Fee', 'Post Name',
        'Pay Level', 'Vacancies'
    ]

    # -------------------------------------------------------------
    # 3. OVERVIEW SECTION EXTRACTION
    # -------------------------------------------------------------
    overview_lines = sec_lines.get('overview', [])
    board = ""
    department = ""
    post_name = ""
    advt_no = ""
    vacancies = ""
    pay_level = ""
    notif_date = ""
    app_mode = "Online"
    official_site = ""

    for i in range(len(overview_lines) - 1):
        k = overview_lines[i]
        v = overview_lines[i+1]
        if k == 'Recruitment Organization': board = v
        elif k == 'Department': department = v
        elif k == 'Post Name': post_name = v
        elif k in ['Advertisement Number', 'Advertisement No', 'Advt No', 'CEN Number', 'CEN No']: advt_no = v
        elif k in ['Total Vacancies', 'Total Posts']: vacancies = v
        elif k == 'Pay Level': pay_level = v
        elif k == 'Notification Date': notif_date = v
        elif k == 'Application Mode': app_mode = v
        elif k == 'Official Website': official_site = v

    # Fallback regex search across entire text if overview section table was missing
    if not board:
        m_b = re.search(r'(?:Recruitment Organization|भर्ती बोर्ड|Department|विभाग)\s*[\n\r:]+\s*([^\n\r]+)', text, re.I)
        if m_b: board = m_b.group(1).strip()
    if not advt_no:
        m_advt = re.search(r'(?:CEN\s*(?:No\.?)?\s*[\d\w\/]+|Advt\.?\s*(?:No\.?)?\s*[\d\w\/]+|विज्ञापन संख्या[^\n\r:]*)', text, re.I)
        if m_advt: advt_no = m_advt.group(0).strip()
    if not vacancies:
        m_v = re.search(r'(?:Total Vacancies|Vacancies|Total Posts|कुल रिक्तियां|कुल पद)\s*[\n\r:]+\s*([^\n\r]+)', text, re.I)
        if m_v:
            vacancies = m_v.group(1).strip()
        else:
            m_v2 = re.search(r'(?:लगभग|approx\.?)?\s*(\d[\d,]*\+?)\s*(?:posts|vacancies|पद|रिक्तियां)', text, re.I)
            if m_v2: vacancies = m_v2.group(0).strip()

    # -------------------------------------------------------------
    # 4. IMPORTANT DATES SECTION EXTRACTION
    # -------------------------------------------------------------
    dates_lines = sec_lines.get('dates', [])
    indicative_date = ""
    detailed_notif_date = ""
    start_date = ""
    last_date = ""
    exam_date = ""

    for i in range(len(dates_lines) - 1):
        k = dates_lines[i]
        v = dates_lines[i+1]
        if k in ['Indicative Notice Release', 'Notice Release']: indicative_date = v
        elif k in ['Detailed Notification', 'Notification Release']: detailed_notif_date = v
        elif k in ['Online Application Start', 'Application Start', 'Start Date', 'आवेदन शुरू']: start_date = v
        elif k in ['Last Date to Apply', 'Last Date', 'Closing Date', 'अंतिम तिथि']: last_date = v
        elif k in ['Exam Date', 'CBT Date', 'परीक्षा तिथि']: exam_date = v

    # Regex fallback for dates
    if not start_date:
        m_sd = re.search(r'(?:Online Application Start|Application Start|Start Date|आवेदन शुरू)\s*[\n\r:]+\s*([^\n\r]+)', text, re.I)
        if m_sd: start_date = m_sd.group(1).strip()
    if not last_date:
        m_ld = re.search(r'(?:Last Date to Apply|Last Date|Closing Date|अंतिम तिथि)\s*[\n\r:]+\s*([^\n\r]+)', text, re.I)
        if m_ld: last_date = m_ld.group(1).strip()
    if not exam_date:
        m_ed = re.search(r'(?:Exam Date|CBT Date|परीक्षा तिथि)\s*[\n\r:]+\s*([^\n\r]+)', text, re.I)
        if m_ed: exam_date = m_ed.group(1).strip()

    # -------------------------------------------------------------
    # 5. APPLICATION FEES & REFUND RULES EXTRACTION
    # -------------------------------------------------------------
    fees_lines = sec_lines.get('fees', [])
    fee_gen = ""
    fee_res = ""
    payment_mode = "Online"
    refund_note = ""

    for i in range(len(fees_lines) - 1):
        k = fees_lines[i]
        v = fees_lines[i+1]
        if 'UR' in k or 'General' in k: fee_gen = v
        elif 'SC' in k or 'आरक्षित' in k: fee_res = v
        elif k == 'Payment Mode': payment_mode = v

    for l in fees_lines:
        if any(w in l for w in ['रिफंड', 'वापस', 'Refund', 'refund']):
            clean_l = re.sub(r'(?:परीक्षा तैयारी सामग्री|ज़्यादा जानें|सरकारी भर्ती सूचना)', '', l).strip()
            if clean_l: refund_note = clean_l

    if not fee_gen:
        m_fg = re.search(r'(?:UR\s*/\s*OBC\s*/\s*EWS|General|UR|सामान्य)[^\n\r:]*\s*[\n\r:]+\s*([₹\d]+)', text, re.I)
        if m_fg: fee_gen = m_fg.group(1).strip()
        if fee_gen and not fee_gen.startswith('₹'): fee_gen = '₹' + fee_gen
    if not fee_res:
        m_fr = re.search(r'(?:SC\s*/\s*ST[^\n\r:]*|आरक्षित[^\n\r:]*|Female[^\n\r:]*)\s*[\n\r:]+\s*([₹\d]+)', text, re.I)
        if m_fr: fee_res = m_fr.group(1).strip()
        if fee_res and not fee_res.startswith('₹'): fee_res = '₹' + fee_res

    # -------------------------------------------------------------
    # 6. AGE LIMIT EXTRACTION
    # -------------------------------------------------------------
    age_lines = sec_lines.get('age', [])
    age_as_on = ""
    age_text = " ".join(age_lines) if age_lines else text
    m_age_on = re.search(r'आयु की गणना के लिए\s*([0-9\s]+(?:जनवरी|फरवरी|मार्च|अप्रैल|मई|जून|जुलाई|अगस्त|सितंबर|अक्टूबर|नवंबर|दिसंबर|January|February|March|April|May|June|July|August|September|October|November|December)\s*\d{4})', age_text)
    if m_age_on:
        age_as_on = m_age_on.group(1).strip()
    elif "2027" in age_text:
        age_as_on = "01 January 2027"
    else:
        age_as_on = "01 January 2026"

    # -------------------------------------------------------------
    # 7. VACANCY DETAILS EXTRACTION
    # -------------------------------------------------------------
    vac_lines = sec_lines.get('vacancy', [])
    for l in vac_lines:
        if ('level' in l.lower() or 'grade' in l.lower()) and not pay_level:
            pay_level = l
        if re.search(r'\d+', l) and ('लगभग' in l or 'पद' in l or 'posts' in l.lower()) and not vacancies:
            vacancies = l

    # -------------------------------------------------------------
    # 8. QUALIFICATION, SELECTION & HOW TO APPLY
    # -------------------------------------------------------------
    qual_lines = [l for l in sec_lines.get('qualification', []) if l not in junk_tokens and len(l) > 10]
    qualification = "\n".join(qual_lines)

    sel_lines = [l for l in sec_lines.get('selection', []) if l not in junk_tokens and len(l) > 3 and not l.startswith('उपलब्ध जानकारी')]
    selection_process = "\n".join([f"• {l}" if not l.startswith('•') and not re.match(r'^\d+\.', l) else l for l in sel_lines])

    how_lines = [l for l in sec_lines.get('how_to_apply', []) if l not in junk_tokens and len(l) > 10]
    how_to_apply = "\n".join([f"{i+1}. {l}" if not re.match(r'^\d+\.', l) else l for i, l in enumerate(how_lines)])

    # -------------------------------------------------------------
    # 9. OFFICIAL GOVERNMENT LINKS EXTRACTION
    # -------------------------------------------------------------
    all_urls = re.findall(r'https?://[^\s<>\"\'\)]+', text)
    if official_site and not official_site.startswith('http'):
        official_site = 'https://' + official_site
    if not official_site:
        gov_urls = [u for u in all_urls if '.gov.in' in u or '.nic.in' in u or 'indianrailways' in u]
        if gov_urls:
            official_site = gov_urls[-1]
        elif all_urls:
            official_site = all_urls[0]

    apply_link = official_site
    for u in all_urls:
        if 'apply' in u.lower():
            apply_link = u
            break

    # -------------------------------------------------------------
    # 10. CATEGORY & STATE DETECTION
    # -------------------------------------------------------------
    category = "State"
    state_val = "All India"
    if any(k in full_lower for k in ["rajasthan", "राजस्थान", "rssb", "rsmssb", "rpsc"]):
        state_val = "Rajasthan"
    elif any(k in full_lower for k in ["uttar pradesh", "उत्तर प्रदेश", "up police", "uppsc", "uppbpb"]):
        state_val = "Uttar Pradesh"
    elif any(k in full_lower for k in ["bihar", "बिहार", "bpsc", "bssc"]):
        state_val = "Bihar"
    elif any(k in full_lower for k in ["haryana", "हरियाणा", "hssc", "hpsc"]):
        state_val = "Haryana"
    elif any(k in full_lower for k in ["madhya pradesh", "मध्य प्रदेश", "mppsc", "esb"]):
        state_val = "Madhya Pradesh"

    if re.search(r'\b(railway|rrb|ntpc|group\s*d|rpf|alp|cen\s*no|रेलवे)\b', full_lower):
        category = "Railway"
        state_val = "All India"
    elif re.search(r'\b(police|constable|daroga|si\b|cisf|bsf|crpf|itbp|army|navy|airforce|agniveer|पुलिस|दरोगा|सिपाही)\b', full_lower) or ("sashastra seema bal" in full_lower):
        category = "Police"
    elif re.search(r'\b(ssc|cgl|chsl|mts|cpo|stenographer|कर्मचारी चयन आयोग)\b', full_lower) and not any(k in full_lower for k in ["rssb", "rsmssb", "rajasthan"]):
        category = "SSC"
        state_val = "All India"
    elif re.search(r'\b(upsc|ias|ips|nda|cds|civil services|cse|संघ लोक सेवा आयोग)\b', full_lower):
        category = "UPSC"
        state_val = "All India"
    elif re.search(r'\b(ctet|reet|kvs|nvs|dsssb|tet|teacher|shikshak|adhyapak|bed|d\.el\.ed|prt|tgt|pgt|शिक्षक|अध्यापक)\b', full_lower):
        category = "Teaching"
    elif re.search(r'\b(bank|ibps|sbi|rbi|nabard|clerk|po\b|probationary officer|बैंकिंग)\b', full_lower):
        category = "Banking"
        state_val = "All India"

    # -------------------------------------------------------------
    # 11. POST TYPE & STATUS DETECTION
    # -------------------------------------------------------------
    if any(w in full_lower for w in ["result", "रिजल्ट", "scorecard", "परिणाम", "cut off", "कटऑफ"]):
        post_type = "result"
        status_val = "Result Declared"
    elif any(w in full_lower for w in ["admit card", "प्रवेश पत्र", "hall ticket", "call letter"]):
        post_type = "admit_card"
        status_val = "Admit Card Released"
    elif any(w in full_lower for w in ["answer key", "उत्तर कुंजी", "आंसर की"]):
        post_type = "answer_key"
        status_val = "Answer Key Released"
    elif any(w in full_lower for w in ["upcoming", "संभावित", "आगामी"]) and "start" not in full_lower:
        post_type = "upcoming"
        status_val = "Upcoming Notification"
    else:
        post_type = "job"
        status_val = "Applications Open"

    # -------------------------------------------------------------
    # 12. FALLBACK DEFAULTS FOR ANY EMPTY FIELD
    # -------------------------------------------------------------
    if not board:
        board = "Railway Recruitment Boards (RRBs)" if category == "Railway" else f"{state_val} Recruitment Board"
    if not post_name:
        post_name = short_title
    if not department:
        department = board
    if not vacancies:
        vacancies = "Various Posts"
    if not pay_level:
        pay_level = "Level 2 to Level 7 / 7th CPC Matrix"
    if not notif_date:
        notif_date = detailed_notif_date or indicative_date or "October 2026"
    if not start_date:
        start_date = "आवेदन प्रारंभ (Check Notice)" if post_type == "job" else "संपन्न"
    if not last_date:
        last_date = "अधिसूचना अनुसार"
    if not exam_date:
        exam_date = "To Be Notified Soon (CBT)" if post_type != "result" else "परीक्षा संपन्न"
    if not fee_gen:
        fee_gen = "₹500 (अधिसूचना अनुसार)" if post_type == "job" else "N/A"
    if not fee_res:
        fee_res = "₹250 (अधिसूचना अनुसार)" if post_type == "job" else "N/A"
    if not qualification:
        qualification = "पदवार शैक्षणिक योग्यता व अन्य शर्तें विस्तृत आधिकारिक विज्ञापन में देखें।"
    if not selection_process:
        selection_process = "• कंप्यूटर आधारित परीक्षा (CBT / Written Exam)\n• दस्तावेज सत्यापन (Document Verification)\n• चिकित्सा परीक्षण (Medical Examination)"
    if not how_to_apply:
        how_to_apply = f"1. सबसे पहले {board} की आधिकारिक वेबसाइट {official_site or 'पर'} जाएं।\n2. विस्तृत विज्ञापन डाउनलोड करें और पात्रता जांचें।\n3. 'Apply Online' लिंक पर क्लिक करके अपना फॉर्म भरें।\n4. आवेदन शुल्क जमा करके फाइनल प्रिंट निकाल लें।"

    # Short intro description
    if post_type == "result":
        short_desc = f"{board} द्वारा {short_title} का परिणाम व स्कोरकार्ड घोषित कर दिया गया है। अभ्यर्थी सीधे आधिकारिक पोर्टल {official_site} से अपना रिजल्ट चेक कर सकते हैं।"
    else:
        short_desc = f"{board} ने {short_title} का विज्ञापन ({advt_no or 'Notification'}) जारी कर दिया है। कुल {vacancies} पदों पर भर्ती हेतु ऑनलाइन आवेदन {start_date} से {last_date} तक आमंत्रित किए गए हैं।"

    # Dynamic SEO
    if post_type == "result":
        meta_title = f"{short_title} Result, Cut Off & Merit List - SarkariNexus 360"
        meta_description = f"{short_title} Result declared by {board}. Check direct scorecard link and cut off at {official_site}."
        keywords = f"{short_title}, {board}, {short_title} result, scorecard, merit list, cut off"
    else:
        meta_title = f"{short_title} Notification, Apply Online, Vacancy & Dates"
        meta_description = f"{short_title} notification for {vacancies}. Check online application dates, fees, qualification and direct apply link at {official_site}."
        keywords = f"{short_title}, {board}, {category} Bharti 2026, {post_name}, apply online, {advt_no}"

    # Build clean HTML content paras for extra details
    clean_paras = []
    for line in lines:
        if len(line) > 40 and not line.startswith('http') and not any(p in line for p in junk_tokens):
            clean_paras.append(f"<p class='text-slate-700 leading-relaxed my-2'>{line}</p>")
    content_html = "\n".join(clean_paras[:6])

    return {
        "title": title,
        "short_title": short_title,
        "slug": slug,
        "category": category,
        "state": state_val,
        "board_name": board,
        "department": department,
        "post_name": post_name,
        "advt_no": advt_no,
        "total_vacancies": vacancies,
        "pay_level": pay_level,
        "status": status_val,
        "badge_color": "emerald" if post_type == "job" else ("amber" if post_type == "result" else "blue"),
        "notification_date": notif_date,
        "apply_start_date": start_date,
        "apply_last_date": last_date,
        "fee_last_date": last_date,
        "correction_last_date": "As per notification rules",
        "admit_card_date": "Before Examination" if post_type == "job" else "उपलब्ध",
        "exam_date": exam_date,
        "result_date": "After Examination" if post_type != "result" else "घोषित (Declared)",
        "fee_general": fee_gen,
        "fee_reserved": fee_res,
        "fee_payment_mode": payment_mode,
        "fee_refund_note": refund_note,
        "min_age": "18 Years",
        "max_age": "Post-wise / पद के अनुसार",
        "age_as_on": age_as_on,
        "age_relaxation": "SC/ST: 5 Years | OBC: 3 Years | PwBD: 10 Years as per rules",
        "eligibility_criteria": qualification,
        "selection_process": selection_process,
        "how_to_apply": how_to_apply,
        "link_apply_online": apply_link,
        "link_notification_pdf": official_site,
        "link_admit_card": official_site,
        "link_result": official_site if post_type == "result" else "",
        "link_official_website": official_site,
        "content_html": content_html,
        "meta_title": meta_title,
        "meta_description": meta_description[:160],
        "keywords": keywords,
        "short_description": short_desc
    }

# API endpoint for smart raw text parsing
@app.post(f"{SECRET_ADMIN_PATH}/api/auto-parse")
async def api_auto_parse_exam(request: Request):
    admin = get_current_admin(request)
    if not admin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = await request.json()
        raw_text = payload.get("raw_text", "")
    else:
        form_data = await request.form()
        raw_text = form_data.get("raw_text", "")
        
    parsed = parse_raw_exam_text(raw_text)
    return JSONResponse(content={"status": "success", "data": parsed})

# 1-Click Instant Save & Publish Endpoint
@app.post(f"{SECRET_ADMIN_PATH}/quick-publish")
async def admin_quick_publish(request: Request):
    admin = get_current_admin(request)
    if not admin:
        return RedirectResponse(url=f"{SECRET_ADMIN_PATH}/login", status_code=status.HTTP_302_FOUND)
    
    form_data = await request.form()
    raw_text = form_data.get("raw_text", "")
    if not raw_text or not raw_text.strip():
        return RedirectResponse(url=f"{SECRET_ADMIN_PATH}?msg=Error: No raw text provided", status_code=status.HTTP_302_FOUND)
        
    parsed = parse_raw_exam_text(raw_text)
    if not parsed:
        return RedirectResponse(url=f"{SECRET_ADMIN_PATH}?msg=Error: Unable to parse text", status_code=status.HTTP_302_FOUND)
    
    # Ensure unique slug
    slug = parsed['slug']
    base_slug = slug
    counter = 1
    while get_exam_by_slug(slug):
        slug = f"{base_slug}-{counter}"
        counter += 1
    parsed['slug'] = slug
    parsed['is_featured'] = 1
    parsed['is_auto_synced'] = 0
    
    create_exam(parsed)
    return RedirectResponse(url=f"/exam/{slug}", status_code=status.HTTP_302_FOUND)

@app.get(f"{SECRET_ADMIN_PATH}/exams/new", response_class=HTMLResponse)
async def admin_new_exam_page(request: Request, raw_text: str = ""):
    admin = get_current_admin(request)
    if not admin:
        return RedirectResponse(url=f"{SECRET_ADMIN_PATH}/login", status_code=status.HTTP_302_FOUND)
    
    initial_exam = None
    if raw_text and raw_text.strip():
        initial_exam = parse_raw_exam_text(raw_text)
        
    return templates.TemplateResponse(
        request=request,
        name="admin/exam_form.html",
        context={"exam": initial_exam, "raw_text": raw_text}
    )

@app.post(f"{SECRET_ADMIN_PATH}/exams/new")
async def admin_new_exam_submit(request: Request):
    admin = get_current_admin(request)
    if not admin:
        return RedirectResponse(url=f"{SECRET_ADMIN_PATH}/login", status_code=status.HTTP_302_FOUND)
    
    form_data = await request.form()
    exam_dict = dict(form_data)
    exam_dict['is_featured'] = 1 if form_data.get('is_featured') else 0
    exam_dict['is_auto_synced'] = 0
    
    create_exam(exam_dict)
    return RedirectResponse(url=f"/exam/{exam_dict['slug']}", status_code=status.HTTP_302_FOUND)

@app.get(f"{SECRET_ADMIN_PATH}/exams/edit/" + "{exam_id}", response_class=HTMLResponse)
async def admin_edit_exam_page(request: Request, exam_id: int):
    admin = get_current_admin(request)
    if not admin:
        return RedirectResponse(url=f"{SECRET_ADMIN_PATH}/login", status_code=status.HTTP_302_FOUND)
    
    exam = get_exam_by_id(exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
        
    return templates.TemplateResponse(
        request=request,
        name="admin/exam_form.html",
        context={"exam": exam}
    )

@app.post(f"{SECRET_ADMIN_PATH}/exams/edit/" + "{exam_id}")
async def admin_edit_exam_submit(request: Request, exam_id: int):
    admin = get_current_admin(request)
    if not admin:
        return RedirectResponse(url=f"{SECRET_ADMIN_PATH}/login", status_code=status.HTTP_302_FOUND)
    
    form_data = await request.form()
    exam_dict = dict(form_data)
    exam_dict['is_featured'] = 1 if form_data.get('is_featured') else 0
    
    update_exam(exam_id, exam_dict)
    return RedirectResponse(url=SECRET_ADMIN_PATH, status_code=status.HTTP_302_FOUND)

@app.post(f"{SECRET_ADMIN_PATH}/exams/delete/" + "{exam_id}")
async def admin_delete_exam(request: Request, exam_id: int):
    admin = get_current_admin(request)
    if not admin:
        return RedirectResponse(url=f"{SECRET_ADMIN_PATH}/login", status_code=status.HTTP_302_FOUND)
    
    delete_exam(exam_id)
    return RedirectResponse(url=SECRET_ADMIN_PATH, status_code=status.HTTP_302_FOUND)

# API endpoint for instant search
@app.get("/api/search")
async def api_search(q: str = ""):
    exams = get_all_exams(search=q if q else None, limit=10)
    return JSONResponse(content=[{
        "title": ex["title"],
        "slug": ex["slug"],
        "category": ex["category"],
        "board_name": ex["board_name"],
        "status": ex["status"]
    } for ex in exams])
