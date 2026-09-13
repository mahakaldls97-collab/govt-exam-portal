import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'portal.db')
conn = sqlite3.connect(db_path)
c = conn.cursor()

try:
    c.execute("ALTER TABLE exams ADD COLUMN state TEXT DEFAULT 'All India'")
    print("Column state added.")
except Exception as e:
    print(f"Column state already exists: {e}")

c.execute("UPDATE exams SET state = 'Rajasthan' WHERE title LIKE '%Rajasthan%' OR title LIKE '%REET%' OR title LIKE '%RAS%' OR title LIKE '%Patwari%'")
c.execute("UPDATE exams SET state = 'Haryana' WHERE title LIKE '%Haryana%'")
c.execute("UPDATE exams SET state = 'Uttar Pradesh' WHERE title LIKE '%UP %' OR title LIKE '%UPSSSC%' OR title LIKE '%UPTET%'")
c.execute("UPDATE exams SET state = 'Bihar' WHERE title LIKE '%Bihar%' OR title LIKE '%BPSC%'")
c.execute("UPDATE exams SET state = 'Delhi' WHERE title LIKE '%Delhi%' OR title LIKE '%DSSSB%'")
c.execute("UPDATE exams SET state = 'All India' WHERE state IS NULL OR state = ''")
conn.commit()

c.execute("SELECT state, COUNT(id) FROM exams GROUP BY state")
for state, count in c.fetchall():
    print(f" - {state}: {count} vacancies")

conn.close()
