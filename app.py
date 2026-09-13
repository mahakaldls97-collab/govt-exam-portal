from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import os
import asyncio

from database import (
    init_db, get_all_exams, get_exam_by_slug, get_exam_by_id,
    create_exam, update_exam, delete_exam, get_stats, get_sync_logs, get_all_states
)
from auth import (
    init_admin, verify_admin, create_session, is_valid_session, invalidate_session, reset_admin_password,
    generate_password_reset_token, verify_reset_token, verify_reset_otp, complete_password_reset
)
from email_service import send_password_reset_email
from seed_data import seed
from auto_scraper import fetch_and_sync_vacancies

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

app = FastAPI(title="Govt Exam Information Portal", version="1.1.0")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Background worker that automatically polls government sources periodically
async def background_vacancy_crawler():
    # Wait 10 seconds after server starts before first auto-sync
    await asyncio.sleep(10)
    while True:
        try:
            fetch_and_sync_vacancies()
        except Exception as e:
            print(f"[BACKGROUND WORKER ERROR] Auto-sync encountered an error: {e}")
        # Run every 1 hour (3600 seconds)
        await asyncio.sleep(3600)

@app.on_event("startup")
def on_startup():
    init_db()
    init_admin()
    seed()
    # Run initial vacancy sync and start background crawler
    try:
        fetch_and_sync_vacancies()
    except Exception as e:
        print(f"Startup initial sync notice: {e}")
    asyncio.create_task(background_vacancy_crawler())

# Helper to check admin session
def get_current_admin(request: Request):
    token = request.cookies.get("admin_session")
    if not token or not is_valid_session(token):
        return None
    return "admin"

# ----------------- PUBLIC ROUTES ----------------- #

@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    # Only active, ongoing, and upcoming exams (no finished/result exams)
    active_forms_exams = get_all_exams(limit=50, status="Applications Open")
    upcoming_exams = get_all_exams(limit=50, status="Upcoming")
    admit_cards_exams = get_all_exams(limit=50, status="Admit Card")
    police_exams = get_all_exams(limit=50, category="Police")
    all_active_exams = get_all_exams(limit=100)
    all_states = get_all_states()
    
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "all_exams": all_active_exams,
            "active_forms_exams": active_forms_exams,
            "upcoming_exams": upcoming_exams,
            "admit_cards_exams": admit_cards_exams,
            "police_exams": police_exams,
            "all_states": all_states,
        }
    )

@app.get("/exam/{slug}", response_class=HTMLResponse)
async def exam_detail_page(request: Request, slug: str):
    exam = get_exam_by_slug(slug)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam information page not found")
    return templates.TemplateResponse(
        request=request,
        name="exam_detail.html",
        context={"exam": exam}
    )

@app.get("/category/{category}", response_class=HTMLResponse)
async def category_page(request: Request, category: str):
    exams = get_all_exams(category=category, limit=100)
    all_states = get_all_states()
    return templates.TemplateResponse(
        request=request,
        name="category.html",
        context={
            "category_name": category,
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

# ----------------- GOOGLE SEARCH & SEO (ROBOTS & SITEMAP) ----------------- #

@app.get("/robots.txt", response_class=Response)
async def robots_txt(request: Request):
    base_url = str(request.base_url).rstrip('/')
    content = f"""User-agent: *
Allow: /
Allow: /exam/
Allow: /category/
Allow: /search
Allow: /disclaimer
Disallow: /portal-boss-secure-2026/
Disallow: /admin

Sitemap: {base_url}/sitemap.xml
"""
    return Response(content=content, media_type="text/plain")

@app.get("/sitemap.xml", response_class=Response)
async def sitemap_xml(request: Request):
    base_url = str(request.base_url).rstrip('/')
    exams = get_all_exams(limit=1000)
    categories = ["Police", "SSC", "Railway", "Teaching", "UPSC", "Banking", "State"]
    
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        f'  <url><loc>{base_url}/</loc><changefreq>hourly</changefreq><priority>1.0</priority></url>',
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
        
    res = fetch_and_sync_vacancies()
    msg = f"Auto-Sync Complete! Checked official sources: {res['items_found']} notices found, {res['items_added']} new vacancies automatically added."
    return RedirectResponse(url=f"{SECRET_ADMIN_PATH}/automation?msg={msg}", status_code=status.HTTP_302_FOUND)

@app.get(f"{SECRET_ADMIN_PATH}/exams/new", response_class=HTMLResponse)
async def admin_new_exam_page(request: Request):
    admin = get_current_admin(request)
    if not admin:
        return RedirectResponse(url=f"{SECRET_ADMIN_PATH}/login", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request=request,
        name="admin/exam_form.html",
        context={"exam": None}
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
