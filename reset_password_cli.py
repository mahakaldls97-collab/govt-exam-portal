import sys
from auth import reset_admin_password, verify_admin
from database import get_db

def main():
    print("==================================================")
    print("       ADMIN PASSWORD RESET UTILITY (CLI)")
    print("==================================================")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT username, full_name FROM admins")
    admins = cursor.fetchall()
    conn.close()
    
    if not admins:
        print("Koi admin account nahi mila!")
        return
        
    print("\nRegistered Admin Accounts:")
    for idx, adm in enumerate(admins, 1):
        print(f" {idx}. {adm[0]} ({adm[1]})")
        
    email = input("\nApna registered Email/Username enter karein [Default: durgalalsaini7757@gmail.com]: ").strip()
    if not email:
        email = "durgalalsaini7757@gmail.com"
        
    new_pass = input("Naya password enter karein (kam se kam 6 akshar): ").strip()
    if len(new_pass) < 6:
        print("Galti: Password kam se kam 6 aksharon ka hona chahiye!")
        return
        
    confirm_pass = input("Naya password dubara enter karein: ").strip()
    if new_pass != confirm_pass:
        print("Galti: Dono passwords aapas me match nahi hue!")
        return
        
    ok = reset_admin_password(email, new_pass)
    if ok:
        print(f"\nSUCCESS: Account '{email}' ka password safaltapoorvak badal diya gaya hai!")
        print(f"Ab aap browser me naye password ke sath login kar sakte hain.")
    else:
        print(f"\nGALTI: Account '{email}' nahi mila.")

if __name__ == '__main__':
    main()
