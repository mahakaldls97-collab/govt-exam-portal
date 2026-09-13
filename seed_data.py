from database import get_db, create_exam, init_db
from auth import init_admin

def seed():
    init_db()
    init_admin()
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM exams")
    count = cursor.fetchone()[0]
    conn.close()
    
    if count > 0:
        print("Database already contains exam data. Skipping seed.")
        return
        
    print("Seeding initial Government Exam data...")
    
    exams_to_seed = [
        {
            'title': 'CTET 2026 Notification - Central Teacher Eligibility Test',
            'slug': 'ctet-2026',
            'category': 'Teaching',
            'board_name': 'CBSE (Central Board of Secondary Education)',
            'total_vacancies': 'Eligibility Test (National Level)',
            'short_description': 'Central Board of Secondary Education (CBSE) has released the official notification for Central Teacher Eligibility Test (CTET 2026) for candidates aspiring to become teachers for Class I to VIII in Central Government Schools (KVS, NVS, Central Tibetan Schools, etc.).',
            'status': 'Applications Open',
            'notification_date': '01 February 2026',
            'apply_start_date': '05 February 2026',
            'apply_last_date': '28 February 2026 (11:59 PM)',
            'fee_last_date': '28 February 2026',
            'correction_last_date': '02 March to 08 March 2026',
            'admit_card_date': '2 Days Before Exam Date',
            'exam_date': '12 July 2026 (Sunday)',
            'result_date': 'August 2026',
            'fee_general': 'Single Paper: ₹1000 | Both Papers (I & II): ₹1200',
            'fee_reserved': 'Single Paper: ₹500 | Both Papers (I & II): ₹600 (SC / ST / Differently Abled)',
            'fee_payment_mode': 'Online through Debit Card / Credit Card / Net Banking / UPI',
            'min_age': '18 Years',
            'max_age': 'No Upper Age Limit',
            'age_as_on': 'As on examination notification guidelines',
            'age_relaxation': 'Applicable as per NCTE rules and Central Govt norms.',
            'eligibility_criteria': '''
• **Paper I (Primary Stage - Class I to V)**:
  - Senior Secondary (or its equivalent) with at least 50% marks and passed or appearing in final year of 2-year Diploma in Elementary Education (D.El.Ed). OR
  - Senior Secondary with at least 45% marks and passed/appearing in final year of 2-year D.El.Ed in accordance with NCTE Regulations. OR
  - Senior Secondary with at least 50% marks and passed/appearing in final year of 4-year Bachelor of Elementary Education (B.El.Ed). OR
  - Graduation with at least 50% marks and Bachelor of Education (B.Ed).

• **Paper II (Elementary Stage - Class VI to VIII)**:
  - Graduation and passed or appearing in final year of 2-year Diploma in Elementary Education (D.El.Ed). OR
  - At least 50% marks either in Graduation or in Post-Graduation and passed or appearing in Bachelor in Education (B.Ed). OR
  - Senior Secondary with at least 50% marks and passed or appearing in final year of 4-year B.El.Ed or B.A/B.Sc.Ed or B.A.Ed/B.Sc.Ed.
            ''',
            'selection_process': '''
1. CTET Written Examination (OMR Based Pen-Paper Test or CBT).
2. Paper I (for Primary Teachers Class 1-5).
3. Paper II (for Upper Primary Teachers Class 6-8).
4. Minimum Qualifying Marks: 60% (90 out of 150 marks) for General Category; 55% (82 out of 150 marks) for SC/ST/OBC/Differently Abled candidates.
5. Validity of CTET Certificate: Lifetime.
            ''',
            'syllabus_summary': '''
• **Paper I Subjects (150 MCQs - 150 Marks - 2.5 Hours)**:
  1. Child Development and Pedagogy (30 Qs - 30 Marks)
  2. Language I (Compulsory) (30 Qs - 30 Marks)
  3. Language II (Compulsory) (30 Qs - 30 Marks)
  4. Mathematics (30 Qs - 30 Marks)
  5. Environmental Studies (EVS) (30 Qs - 30 Marks)
  *Note: No negative marking.*

• **Paper II Subjects (150 MCQs - 150 Marks - 2.5 Hours)**:
  1. Child Development & Pedagogy (30 Qs - 30 Marks)
  2. Language I (30 Qs - 30 Marks)
  3. Language II (30 Qs - 30 Marks)
  4. Mathematics & Science (for Maths/Science teacher) OR Social Studies/Social Science (60 Qs - 60 Marks)
            ''',
            'how_to_apply': '''
1. Visit the official CTET portal: https://ctet.nic.in/
2. Click on "Apply for CTET 2026".
3. Complete New Registration by providing Name, Mobile Number, Email ID, and Date of Birth.
4. Fill Educational Qualifications, Paper Selection (Paper I, Paper II or Both), and Preferred Exam Cities.
5. Upload scanned photograph (10-100 KB) and signature (3-30 KB) in JPG/JPEG format.
6. Pay the Application Fee through Debit/Credit Card or Net Banking/UPI.
7. Download and print the Confirmation Page for future reference.
            ''',
            'link_apply_online': 'https://ctet.nic.in/',
            'link_notification_pdf': 'https://ctet.nic.in/',
            'link_admit_card': 'https://ctet.nic.in/',
            'link_answer_key': 'https://ctet.nic.in/',
            'link_result': 'https://ctet.nic.in/',
            'link_official_website': 'https://ctet.nic.in/',
            'link_previous_papers': 'https://ctet.nic.in/archive-ctet-question-paper/',
            'meta_title': 'CTET 2026 Notification, Exam Date, Eligibility, Fees & Apply Online Link',
            'meta_description': 'Check CTET 2026 Notification details, CBSE CTET application form start date, last date, eligibility criteria, syllabus, exam pattern, admit card and direct official link to apply online at ctet.nic.in.',
            'keywords': 'CTET 2026, CTET notification 2026, CTET apply online, ctet nic in, ctet exam date, ctet eligibility, ctet syllabus 2026, ctet admit card, ctet result',
            'is_featured': 1,
            'faqs': [
                {'question': 'CTET 2026 ke liye online aavedan kab shuru hoga?', 'answer': 'CTET 2026 ke online aavedan official portal ctet.nic.in par jaari notification ke anusar shuru ho chuke hain.'},
                {'question': 'Kya CTET certificate ki validity lifetime hoti hai?', 'answer': 'Haan, NCTE ke niyam anusar CTET certificate ki validity ab ajeevan (Lifetime) hoti hai.'},
                {'question': 'CTET exam mein negative marking hoti hai ya nahi?', 'answer': 'CTET examination mein koi negative marking nahi hoti hai. Har sahi uttar ke liye 1 mark diya jaata hai.'},
                {'question': 'General category ke liye CTET qualify karne ke kitne number chahiye?', 'answer': 'General category ke candidates ko 150 mein se minimum 60% (yaani 90 marks) lana anivarya hota hai.'}
            ]
        },
        {
            'title': 'SSC CGL 2026 Notification - Combined Graduate Level Exam',
            'slug': 'ssc-cgl-2026',
            'category': 'SSC',
            'board_name': 'Staff Selection Commission (SSC)',
            'total_vacancies': '14,000+ Posts (Tentative)',
            'short_description': 'Staff Selection Commission (SSC) has invited online applications for the Combined Graduate Level Examination (CGL 2026) for recruitment to Group B and Group C posts in various Ministries, Departments, and Organizations of Government of India.',
            'status': 'Applications Open',
            'notification_date': '10 January 2026',
            'apply_start_date': '15 January 2026',
            'apply_last_date': '15 February 2026',
            'fee_last_date': '16 February 2026',
            'correction_last_date': '18 February to 20 February 2026',
            'admit_card_date': '10 Days Before Tier-I Exam',
            'exam_date': 'Tier-I: May - June 2026',
            'result_date': 'July 2026',
            'fee_general': '₹100 (General / OBC / EWS Male)',
            'fee_reserved': '₹0 (SC / ST / PwBD / ESM & All Category Female candidates)',
            'fee_payment_mode': 'Online (BHIM UPI, Net Banking, Visa, MasterCard, RuPay)',
            'min_age': '18 Years',
            'max_age': '27 to 32 Years (Post wise)',
            'age_as_on': '01-08-2026',
            'age_relaxation': 'OBC: 3 Years | SC/ST: 5 Years | PwBD: 10 Years',
            'eligibility_criteria': '''
• Bachelor’s Degree in any discipline from a recognized University or equivalent.
• For Assistant Audit Officer/Assistant Accounts Officer: Bachelor's degree (Desirable: CA/CS/MBA Finance/M.Com).
• For Junior Statistical Officer (JSO): Bachelor’s Degree in any subject with at least 60% Marks in Mathematics at 12th standard OR Bachelor’s Degree with Statistics as one of the subjects.
• Final year students can also apply conditionally provided they acquire the degree before the cutoff date.
            ''',
            'selection_process': '''
1. Tier-I Examination (Computer Based Test - Qualifying).
2. Tier-II Examination (Computer Based Test - Merit based).
3. Data Entry Speed Test (DEST) / Typing Test (for specific posts).
4. Document Verification (DV) conducted by User Departments.
5. Medical Examination.
            ''',
            'syllabus_summary': '''
• **Tier-I Exam (100 Qs - 200 Marks - 60 Minutes)**:
  - General Intelligence & Reasoning (25 Qs - 50 Marks)
  - General Awareness (25 Qs - 50 Marks)
  - Quantitative Aptitude (25 Qs - 50 Marks)
  - English Comprehension (25 Qs - 50 Marks)
  *Negative marking: 0.50 marks per wrong answer.*

• **Tier-II Exam**:
  - Paper-I: Mathematical Abilities, Reasoning, English Language, General Awareness, Computer Knowledge Module, and Typing Speed Test.
            ''',
            'how_to_apply': '''
1. Visit the new SSC official website: https://ssc.gov.in/
2. Complete One Time Registration (OTR) with personal details and Aadhaar.
3. Login using Registration Number and Password.
4. Go to "Live Examinations" and click "Apply" on SSC CGL 2026.
5. Upload live webcam photograph and scanned signature as per guidelines.
6. Pay the application fee and submit the application form.
            ''',
            'link_apply_online': 'https://ssc.gov.in/',
            'link_notification_pdf': 'https://ssc.gov.in/',
            'link_admit_card': 'https://ssc.gov.in/',
            'link_answer_key': 'https://ssc.gov.in/',
            'link_result': 'https://ssc.gov.in/',
            'link_official_website': 'https://ssc.gov.in/',
            'link_previous_papers': 'https://ssc.gov.in/',
            'meta_title': 'SSC CGL 2026 Notification Out, Exam Dates, Eligibility & Apply Online ssc.gov.in',
            'meta_description': 'SSC CGL 2026 recruitment notification details. Check vacancies, qualification criteria, age limit, selection process, syllabus, admit card date, and direct official apply online link.',
            'keywords': 'SSC CGL 2026, ssc gov in, ssc cgl notification, ssc cgl syllabus, ssc cgl qualification, ssc cgl admit card, ssc result',
            'is_featured': 1,
            'faqs': [
                {'question': 'SSC CGL 2026 mein kaun apply kar sakta hai?', 'answer': 'Kissi bhi recognized university se Graduate (Bachelor Degree) pass ya appearing candidate apply kar sakta hai.'},
                {'question': 'SSC CGL 2026 form ki fees kitni hai?', 'answer': 'General/OBC/EWS Male candidates ke liye ₹100, aur mahilaon tatha SC/ST/PwD ke liye form bilkul nishulk (Free) hai.'}
            ]
        },
        {
            'title': 'UPSC Civil Services (IAS/IFS) 2026 Notification',
            'slug': 'upsc-civil-services-2026',
            'category': 'UPSC',
            'board_name': 'Union Public Service Commission (UPSC)',
            'total_vacancies': '1,100+ Posts',
            'short_description': 'Union Public Service Commission (UPSC) has announced the Civil Services Examination (CSE 2026) and Indian Forest Service (IFoS) for recruitment to prestigious administrative services including IAS, IPS, IFS, IRS, and allied central services.',
            'status': 'Applications Open',
            'notification_date': '14 February 2026',
            'apply_start_date': '14 February 2026',
            'apply_last_date': '05 March 2026 (06:00 PM)',
            'fee_last_date': '05 March 2026',
            'correction_last_date': '06 March to 12 March 2026',
            'admit_card_date': 'May 2026',
            'exam_date': 'Prelims: 24 May 2026 | Mains: September 2026',
            'result_date': 'Prelims Result: June 2026',
            'fee_general': '₹100 (General / OBC / EWS Male)',
            'fee_reserved': '₹0 (Female / SC / ST / PwBD candidates are exempted)',
            'fee_payment_mode': 'Online Net Banking / Visa / Mastercard / RuPay or SBI Branch Cash Challan',
            'min_age': '21 Years',
            'max_age': '32 Years (General Category)',
            'age_as_on': '01-08-2026',
            'age_relaxation': 'OBC: 3 Years (Up to 35) | SC/ST: 5 Years (Up to 37) | PwBD: 10 Years',
            'eligibility_criteria': '''
• Candidate must hold a Graduate Degree in any discipline from a recognized University or institution recognized by the UGC.
• Candidates appearing in the final semester/year of their graduation are also eligible to appear in the Preliminary Examination.
• For Indian Forest Service (IFoS): Bachelor's degree with at least one subject among Animal Husbandry & Veterinary Science, Botany, Chemistry, Geology, Mathematics, Physics, Statistics and Zoology or Agriculture/Forestry/Engineering.
            ''',
            'selection_process': '''
1. Civil Services (Preliminary) Examination (Objective Type - Qualifying).
2. Civil Services (Main) Examination (Written Descriptive - 9 Papers).
3. Personality Test / Interview (275 Marks).
4. Final Merit List based on Marks in Mains (1750) + Interview (275) = 2025 Total Marks.
            ''',
            'syllabus_summary': '''
• **Prelims Exam (400 Marks Total)**:
  - GS Paper 1 (100 Qs - 200 Marks): Indian Polity, History, Geography, Economy, Science & Tech, Environment, Current Events.
  - GS Paper 2 / CSAT (80 Qs - 200 Marks): Reading Comprehension, Logical Reasoning, Basic Numeracy (Qualifying with 33% marks).
  *Negative Marking: 1/3rd mark deduction.*

• **Mains Exam (9 Descriptive Papers)**:
  - Essay, GS I, GS II, GS III, GS IV (Ethics), Optional Subject Paper 1 & 2, plus Compulsory Indian Language & English papers.
            ''',
            'how_to_apply': '''
1. Visit UPSC One Time Registration (OTR) portal: https://upsconline.nic.in/
2. Register your profile if not already done.
3. Login using registered Email / Mobile and OTP.
4. Fill Application Part-I (Personal, Education, Exam Center).
5. Pay Application fee online.
6. Upload Photograph, Signature, and Photo Identity Card (Aadhaar / Voter ID / Passport).
7. Submit Part-II and download confirmation page.
            ''',
            'link_apply_online': 'https://upsconline.nic.in/',
            'link_notification_pdf': 'https://upsc.gov.in/',
            'link_admit_card': 'https://upsconline.nic.in/',
            'link_answer_key': 'https://upsc.gov.in/',
            'link_result': 'https://upsc.gov.in/',
            'link_official_website': 'https://upsc.gov.in/',
            'link_previous_papers': 'https://upsc.gov.in/examinations/previous-question-papers',
            'meta_title': 'UPSC Civil Services (IAS) 2026 Notification, Exam Date & Apply Online upsc.gov.in',
            'meta_description': 'UPSC CSE 2026 notification released. Complete details on IAS/IPS vacancies, eligibility, age limit, syllabus, prelims exam date, and official online application form.',
            'keywords': 'UPSC 2026, UPSC CSE 2026, IAS notification 2026, upsc online nic in, upsc prelims date, ias eligibility, upsc syllabus',
            'is_featured': 1,
            'faqs': [
                {'question': 'UPSC 2026 Prelims exam kab aayojit hoga?', 'answer': 'UPSC Calendar ke mutabik Civil Services Preliminary Examination 24 May 2026 ko aayojit kiya jayega.'},
                {'question': 'General category ke liye kitne attempts allowed hote hain?', 'answer': 'General category ke candidates ke liye maximum 6 attempts 32 varsh ki aayu tak allowed hote hain.'}
            ]
        },
        {
            'title': 'Railway RRB NTPC 2026 Recruitment (Graduate & Under Graduate)',
            'slug': 'rrb-ntpc-2026',
            'category': 'Railway',
            'board_name': 'Railway Recruitment Boards (RRB)',
            'total_vacancies': '11,558 Posts',
            'short_description': 'Government of India, Ministry of Railways has released centralized employment notification (CEN) for recruitment of Non-Technical Popular Categories (NTPC) including Station Master, Goods Train Manager, Senior Clerk, Junior Clerk, and Commercial Apprentice.',
            'status': 'Admit Card Released',
            'notification_date': '12 September 2025',
            'apply_start_date': '14 September 2025',
            'apply_last_date': '20 October 2025',
            'fee_last_date': '22 October 2025',
            'correction_last_date': '23 October to 30 October 2025',
            'admit_card_date': 'Available Now (City Intimation Live)',
            'exam_date': 'CBT-1: March - April 2026',
            'result_date': 'May 2026',
            'fee_general': '₹500 (₹400 refundable upon attending CBT-1)',
            'fee_reserved': '₹250 (Full ₹250 refundable upon attending CBT-1 for SC/ST/Female/Ex-Servicemen/EBC)',
            'fee_payment_mode': 'Online through Internet Banking, UPI, Credit/Debit Cards',
            'min_age': '18 Years',
            'max_age': '33 to 36 Years (with COVID age relaxation)',
            'age_as_on': '01-01-2026',
            'age_relaxation': 'OBC: 3 Years | SC/ST: 5 Years | PwBD: 10 Years',
            'eligibility_criteria': '''
• **Undergraduate Posts (Level 2 & 3)**: 12th (+2 Stage) or its equivalent examination with not less than 50% marks in the aggregate.
• **Graduate Posts (Level 5 & 6)**: University Degree or its equivalent from a recognized University/Institution.
            ''',
            'selection_process': '''
1. 1st Stage Computer Based Test (CBT-1) - Common for all posts.
2. 2nd Stage Computer Based Test (CBT-2) - Post specific.
3. Computer Based Aptitude Test (CBAT) for Station Master / Typing Skill Test for Clerical posts.
4. Document Verification (DV) & Medical Examination.
            ''',
            'syllabus_summary': '''
• **CBT-1 Exam Pattern (100 Qs - 100 Marks - 90 Minutes)**:
  - General Awareness: 40 Qs (Current affairs, General Science, History, Geography, Indian Polity, Economy)
  - Mathematics: 30 Qs (Number System, Decimals, Fractions, LCM/HCF, Ratio, Percentages, Mensuration, Time & Work, Time & Distance, SI/CI, Profit & Loss)
  - General Intelligence & Reasoning: 30 Qs (Analogies, Number & Alphabetical Series, Coding & Decoding, Syllogism, Venn Diagrams)
  *Negative Marking: 1/3rd of the marks allotted to each question.*
            ''',
            'how_to_apply': '''
1. Go to your respective RRB Regional portal (e.g., RRB Chandigarh, RRB Allahabad, RRB Mumbai, RRB Bhopal).
2. Click on CEN NTPC Application Link.
3. Fill Registration Details and verify Mobile OTP and Email.
4. Fill Educational details and community category.
5. Upload clear colored photograph with plain background and clear signature.
6. Pay examination fee and download printout.
            ''',
            'link_apply_online': 'https://www.rrbapply.gov.in/',
            'link_notification_pdf': 'https://www.rrbcdg.gov.in/',
            'link_admit_card': 'https://www.rrbapply.gov.in/',
            'link_answer_key': 'https://www.rrbapply.gov.in/',
            'link_result': 'https://www.rrbapply.gov.in/',
            'link_official_website': 'https://www.rrbcdg.gov.in/',
            'link_previous_papers': 'https://www.rrbcdg.gov.in/',
            'meta_title': 'RRB NTPC 2026 Admit Card, Exam Date, City Intimation Slip & Exam Pattern',
            'meta_description': 'Railway Recruitment Board RRB NTPC 2026 Admit Card and City Intimation link live. Check exam schedule, CBT-1 syllabus, vacancies, and direct download links.',
            'keywords': 'RRB NTPC 2026, Railway NTPC admit card, rrb apply gov in, rrb cdg, rrb ntpc exam date, rrb ntpc syllabus',
            'is_featured': 1,
            'faqs': [
                {'question': 'RRB NTPC Admit Card kab download kar sakte hain?', 'answer': 'CBT Exam se 4 din pehle official admit card download link active ho jaata hai, jabki Exam City Intimation slip 10 din pehle aati hai.'},
                {'question': 'Kya CBT-1 ke baad fees refund hoti hai?', 'answer': 'Haan, jo candidates CBT-1 exam mein baithte hain, unki bank fees refundable amount bank account mein transfer ki jaati hai.'}
            ]
        },
        {
            'title': 'REET 2026 Notification - Rajasthan Eligibility Examination for Teachers',
            'slug': 'reet-2026',
            'category': 'Teaching',
            'board_name': 'Board of Secondary Education, Rajasthan (BSER)',
            'total_vacancies': '30,000+ Teacher Posts (Expected)',
            'short_description': 'Board of Secondary Education Rajasthan (BSER), Ajmer will conduct REET 2026 (Rajasthan Eligibility Examination for Teachers) for Level-1 (Primary 1st to 5th) and Level-2 (Upper Primary 6th to 8th) Third Grade Teachers in Rajasthan schools.',
            'status': 'Upcoming Notification',
            'notification_date': 'March 2026 (Expected)',
            'apply_start_date': 'March 2026',
            'apply_last_date': 'April 2026',
            'fee_last_date': 'April 2026',
            'correction_last_date': 'May 2026',
            'admit_card_date': 'July 2026',
            'exam_date': 'August 2026',
            'result_date': 'October 2026',
            'fee_general': 'Level 1 or Level 2 Single: ₹550 | Both Levels: ₹750',
            'fee_reserved': 'Level 1 or Level 2 Single: ₹550 | Both Levels: ₹750',
            'fee_payment_mode': 'Online E-Mitra / Net Banking / Credit/Debit Cards / UPI',
            'min_age': '18 Years',
            'max_age': '40 Years (Relaxation as per Rajasthan Govt rules)',
            'age_as_on': '01-01-2026',
            'age_relaxation': 'SC/ST/OBC/MBC/EWS Male of Rajasthan: 5 Years | Female: 10 Years',
            'eligibility_criteria': '''
• **REET Level 1 (Class 1 to 5)**:
  - 12th Pass with minimum 50% marks and 2-year Diploma in Elementary Education (D.El.Ed / BSTc) pass or final year appearing.
• **REET Level 2 (Class 6 to 8)**:
  - Graduation with 50% marks and 2-year B.Ed or 4-year B.El.Ed / B.A.B.Ed / B.Sc.B.Ed or 2-year D.El.Ed.
            ''',
            'selection_process': '''
1. REET Eligibility Exam (Passing Marks: 60% for General, 55% for OBC/MBC/EWS/SC/ST of Rajasthan).
2. Level 1 (Primary) and Level 2 (Upper Primary) separate papers.
3. REET Certificate with Lifetime Validity.
4. Subsequent Rajasthan 3rd Grade Teacher Mains Exam (RSSB) for recruitment.
            ''',
            'syllabus_summary': '''
• **REET Exam (150 Marks - 150 Questions - 150 Minutes)**:
  - Child Development & Pedagogy (30 Marks)
  - Language I (Hindi/English/Sanskrit/Urdu/Sindhi/Punjabi/Gujarati) (30 Marks)
  - Language II (30 Marks)
  - Mathematics / Science OR Social Science / Rajasthan GK (60 Marks)
  *No Negative Marking in REET Eligibility Exam.*
            ''',
            'how_to_apply': '''
1. Visit official REET portal (rajeduboard.rajasthan.gov.in / reetbser).
2. Click on "REET 2026 Application Portal".
3. Generate Bank Challan / Token by filling basic details.
4. Complete fee payment through online banking or E-Mitra.
5. Fill personal details, education details, select Level-1/Level-2.
6. Upload photo, signature, and submit application.
            ''',
            'link_apply_online': 'https://rajeduboard.rajasthan.gov.in/',
            'link_notification_pdf': 'https://rajeduboard.rajasthan.gov.in/',
            'link_admit_card': 'https://rajeduboard.rajasthan.gov.in/',
            'link_answer_key': 'https://rajeduboard.rajasthan.gov.in/',
            'link_result': 'https://rajeduboard.rajasthan.gov.in/',
            'link_official_website': 'https://rajeduboard.rajasthan.gov.in/',
            'link_previous_papers': 'https://rajeduboard.rajasthan.gov.in/',
            'meta_title': 'REET 2026 Notification, Syllabus, Qualification, Exam Date & Online Form',
            'meta_description': 'REET 2026 Rajasthan Eligibility Examination for Teachers details. Check Level 1 and Level 2 syllabus, BSTc/B.Ed eligibility, age limit, and official portal link.',
            'keywords': 'REET 2026, REET notification 2026, REET Level 1, REET Level 2, rajasthan teacher vacancy, reet bser, reet syllabus',
            'is_featured': 1,
            'faqs': [
                {'question': 'REET certificate ki validity kitne saal hoti hai?', 'answer': 'REET pass certificate ki vaidyata ajeevan (Lifetime) hoti hai.'},
                {'question': 'Kya B.Ed wale Level-1 (Primary) mein aavedan kar sakte hain?', 'answer': 'Supreme Court ke aadesh anusar Level-1 mein kewal BSTc/D.El.Ed pass candidates hi eligible hain.'}
            ]
        },
        {
            'title': 'IBPS PO / MT 2026 Notification - Bank PO Recruitment',
            'slug': 'ibps-po-2026',
            'category': 'Banking',
            'board_name': 'Institute of Banking Personnel Selection (IBPS)',
            'total_vacancies': '4,500+ Posts',
            'short_description': 'Institute of Banking Personnel Selection (IBPS) announces Common Recruitment Process (CRP PO/MT-XVI) for recruitment of Probationary Officers / Management Trainees in 11 Participating Public Sector Banks across India.',
            'status': 'Applications Open',
            'notification_date': '01 August 2026',
            'apply_start_date': '01 August 2026',
            'apply_last_date': '21 August 2026',
            'fee_last_date': '21 August 2026',
            'correction_last_date': '21 August 2026',
            'admit_card_date': 'October 2026',
            'exam_date': 'Prelims: October 2026 | Mains: November 2026',
            'result_date': 'Final Allotment: April 2027',
            'fee_general': '₹850 (General / EWS / OBC)',
            'fee_reserved': '₹175 (SC / ST / PWD)',
            'fee_payment_mode': 'Online (Net Banking, Cards, UPI)',
            'min_age': '20 Years',
            'max_age': '30 Years',
            'age_as_on': '01-08-2026',
            'age_relaxation': 'OBC: 3 Years | SC/ST: 5 Years | PwD: 10 Years',
            'eligibility_criteria': '''
• A Degree (Graduation) in any discipline from a University recognized by the Govt. Of India or any equivalent qualification.
• Operating and working knowledge in computer systems is mandatory.
            ''',
            'selection_process': '''
1. Preliminary Examination (Online CBT - 100 Marks).
2. Main Examination (Online CBT + Descriptive English - 225 Marks).
3. Common Interview conducted by Participating Banks (100 Marks).
            ''',
            'syllabus_summary': '''
• **Prelims Exam Pattern (100 Qs - 100 Marks - 60 Min with sectional timing)**:
  - English Language: 30 Qs (20 Min)
  - Quantitative Aptitude: 35 Qs (20 Min)
  - Reasoning Ability: 35 Qs (20 Min)
  *Negative marking: 0.25 marks per wrong answer.*
            ''',
            'how_to_apply': '''
1. Go to official website: https://www.ibps.in/
2. Click on "CRP PO/MT" and select new registration.
3. Enter basic details, upload scanned photograph, signature, left thumb impression, and handwritten declaration.
4. Enter educational qualifications and bank preferences.
5. Pay online fees and download application form.
            ''',
            'link_apply_online': 'https://www.ibps.in/',
            'link_notification_pdf': 'https://www.ibps.in/',
            'link_admit_card': 'https://www.ibps.in/',
            'link_answer_key': 'https://www.ibps.in/',
            'link_result': 'https://www.ibps.in/',
            'link_official_website': 'https://www.ibps.in/',
            'link_previous_papers': 'https://www.ibps.in/',
            'meta_title': 'IBPS PO 2026 Notification, Exam Dates, Syllabus & Apply Online ibps.in',
            'meta_description': 'IBPS PO 2026 Bank PO recruitment notification. Check participating banks, eligibility, age limit, prelims & mains exam pattern, and official application link.',
            'keywords': 'IBPS PO 2026, bank po vacancy, ibps in, ibps po apply online, bank exam 2026, ibps syllabus',
            'is_featured': 0,
            'faqs': [
                {'question': 'IBPS PO mein kaun se banks participate karte hain?', 'answer': 'Punjab National Bank, Bank of Baroda, Canara Bank, Union Bank of India sahit kul 11 Public Sector Banks participate karte hain.'}
            ]
        }
    ]
    
    try:
        from add_comprehensive_exams import COMPREHENSIVE_EXAMS
        exams_to_seed.extend(COMPREHENSIVE_EXAMS)
    except Exception:
        pass

    for ex in exams_to_seed:
        create_exam(ex)
        print(f"Seeded: {ex['title']}")
        
    print("Database seeding completed successfully!")

if __name__ == '__main__':
    seed()
