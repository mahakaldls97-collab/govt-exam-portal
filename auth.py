import hashlib
import secrets
from database import get_db

# Default admin credentials: admin / admin@examportal2026
ADMIN_SALT = "govt_exam_portal_salt_2026"

def hash_password(password: str) -> str:
    return hashlib.sha256((password + ADMIN_SALT).encode('utf-8')).hexdigest()

def init_admin():
    conn = get_db()
    cursor = conn.cursor()
    target_user = "durgalalsaini7757@gmail.com"
    target_hash = hash_password("Dls81077@")
    
    cursor.execute("SELECT id FROM admins WHERE username = ?", (target_user,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO admins (username, password_hash, full_name) VALUES (?, ?, ?)",
                       (target_user, target_hash, "Durga Lal Saini"))
        conn.commit()
    conn.close()

def verify_admin(username: str, password: str) -> bool:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM admins WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return False
    return row[0] == hash_password(password)

def reset_admin_password(email_or_user: str, new_password: str) -> bool:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM admins WHERE username = ?", (email_or_user,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False
    new_hash = hash_password(new_password)
    cursor.execute("UPDATE admins SET password_hash = ? WHERE username = ?", (new_hash, email_or_user))
    conn.commit()
    conn.close()
    return True

# In-memory store for password reset tokens and OTPs
# Format: { token: {"email": email, "expires_at": timestamp, "otp": otp} }
import time

reset_tokens = {}

def generate_password_reset_token(email: str) -> dict:
    token = secrets.token_urlsafe(32)
    otp = f"{secrets.randbelow(900000) + 100000}" # 6-digit OTP
    # Expires in 15 minutes (900 seconds)
    expires_at = time.time() + 900
    reset_tokens[token] = {
        "email": email.strip().lower(),
        "otp": otp,
        "expires_at": expires_at
    }
    return {
        "token": token,
        "otp": otp,
        "email": email.strip().lower(),
        "expires_at": expires_at
    }

def verify_reset_token(token: str) -> str:
    if not token or token not in reset_tokens:
        return None
    data = reset_tokens[token]
    if time.time() > data["expires_at"]:
        reset_tokens.pop(token, None)
        return None
    return data["email"]

def verify_reset_otp(email: str, entered_otp: str) -> str:
    now = time.time()
    for tok, data in list(reset_tokens.items()):
        if data["email"] == email.strip().lower() and data["otp"] == entered_otp.strip():
            if now <= data["expires_at"]:
                return tok
            else:
                reset_tokens.pop(tok, None)
    return None

def complete_password_reset(token: str, new_password: str) -> bool:
    email = verify_reset_token(token)
    if not email:
        return False
    ok = reset_admin_password(email, new_password)
    if ok:
        reset_tokens.pop(token, None)
        return True
    return False

# In-memory simple session management for admin
active_sessions = set()

def create_session() -> str:
    token = secrets.token_hex(24)
    active_sessions.add(token)
    return token

def is_valid_session(token: str) -> bool:
    if not token:
        return False
    return token in active_sessions

def invalidate_session(token: str):
    active_sessions.discard(token)
