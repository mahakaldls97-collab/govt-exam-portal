import sqlite3

def cleanup():
    conn = sqlite3.connect('portal.db')
    cursor = conn.cursor()
    
    # Delete exams where status is Result Declared or demo
    cursor.execute("DELETE FROM exams WHERE status LIKE '%Result%' OR title LIKE '%Demo%'")
    conn.commit()
    
    cursor.execute("SELECT id, title, status, exam_date, apply_last_date FROM exams")
    rows = cursor.fetchall()
    print(f"Total currently active/upcoming exams in database: {len(rows)}")
    for r in rows:
        print(f"- [{r[2]}] {r[1]} (Exam: {r[3]}, Last Date: {r[4]})")
        
    conn.close()

if __name__ == '__main__':
    cleanup()
