import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

# Gmail SMTP configuration
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "durgalalsaini7757@gmail.com")
SMTP_PASS = os.environ.get("SMTP_PASS", "hfle qxjq kwta wqyk")

def send_password_reset_email(to_email: str, reset_link: str, otp: str) -> dict:
    subject = "Sarkari Exam Hub - Admin Password Reset OTP & Link"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f8fafc; margin: 0; padding: 20px; }}
            .card {{ max-width: 520px; margin: 0 auto; background: #ffffff; border-radius: 16px; padding: 30px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border: 1px solid #e2e8f0; }}
            .logo {{ font-size: 20px; font-weight: 800; color: #1e3a8a; margin-bottom: 20px; text-align: center; }}
            .otp-box {{ background-color: #eff6ff; border: 2px dashed #3b82f6; border-radius: 12px; padding: 15px; text-align: center; margin: 20px 0; }}
            .otp-code {{ font-size: 32px; font-weight: 900; letter-spacing: 6px; color: #1d4ed8; }}
            .btn {{ display: inline-block; background-color: #2563eb; color: #ffffff !important; font-weight: 700; text-decoration: none; padding: 12px 24px; border-radius: 10px; margin-top: 15px; text-align: center; }}
            .footer {{ font-size: 11px; color: #64748b; margin-top: 25px; border-top: 1px solid #e2e8f0; padding-top: 15px; text-align: center; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="logo">🏛️ Sarkari Exam Hub - Admin Security</div>
            <p>नमस्ते Admin,</p>
            <p>आपके एडमिन अकाउंट (<strong>{to_email}</strong>) के पासवर्ड रीसेट का अनुरोध प्राप्त हुआ है।</p>
            
            <div class="otp-box">
                <div style="font-size: 12px; color: #475569; font-weight: 600; text-transform: uppercase;">आपका 6-अंकों का गुप्त OTP</div>
                <div class="otp-code">{otp}</div>
                <div style="font-size: 11px; color: #64748b; margin-top: 5px;">यह OTP 15 मिनट के लिए वैध है।</div>
            </div>

            <p style="text-align: center;">या आप सीधे नीचे दिए गए बटन पर क्लिक करके नया पासवर्ड बना सकते हैं:</p>
            
            <div style="text-align: center;">
                <a href="{reset_link}" class="btn">सीधे नया पासवर्ड बनाएं (Reset Password)</a>
            </div>

            <p style="font-size: 12px; color: #64748b; margin-top: 20px;">यदि आपने यह अनुरोध नहीं किया था, तो कृपया इसे अनदेखा करें। आपका मौजूदा पासवर्ड पूरी तरह सुरक्षित रहेगा।</p>
            
            <div class="footer">
                Sarkari Exam Hub &copy; 2026. All rights reserved.
            </div>
        </div>
    </body>
    </html>
    """

    # Always write to security log so OTP and link are immediately available even if SMTP fails
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "password_resets.log")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"\n[RESET REQUEST] Email: {to_email} | OTP: {otp} | Link: {reset_link}\n")

    if SMTP_USER and SMTP_PASS:
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = SMTP_USER
            msg['To'] = to_email
            msg.attach(MIMEText(html_content, 'html'))
            
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(SMTP_USER, [to_email], msg.as_string())
            return {"success": True, "method": "smtp", "msg": f"Email successfully sent to {to_email}"}
        except Exception as e:
            return {"success": False, "method": "smtp_error", "error": str(e)}
    else:
        return {"success": True, "method": "logged", "msg": "OTP generated and saved for verification"}

