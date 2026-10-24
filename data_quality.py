import html
import re
from datetime import datetime, date, timedelta
from urllib.parse import urlparse

CANONICAL_STATUSES = (
    "Applications Open",
    "Applications Closed",
    "Upcoming",
    "Admit Card",
    "Answer Key",
    "Result",
    "Syllabus",
    "Archived",
)

POST_TYPE_CATEGORIES = {
    "result", "results", "admit card", "latest jobs", "latest job",
    "answer key", "syllabus", "other", "news", "jobs",
}

AGGREGATOR_HOSTS = {
    "sarkariresult.com.cm", "www.sarkariresult.com.cm",
    "sarkariresult.com", "www.sarkariresult.com",
    "sarkariexam.com", "www.sarkariexam.com",
    "studygovthelp.in", "www.studygovthelp.in",
    "sarkariresult.net", "www.sarkariresult.net",
    "rojgarresult.com", "www.rojgarresult.com",
    "freejobalert.com", "www.freejobalert.com",
    "indgovtjobs.in", "www.indgovtjobs.in",
}

BLOCKED_HOST_PARTS = (
    "telegram", "t.me", "whatsapp", "facebook", "twitter", "instagram",
    "youtube", "bit.ly", "tinyurl", "google.com/amp",
)

TRUSTED_GOV_SUFFIXES = (".gov.in", ".nic.in", ".gov", ".mil.in")

STATE_RULES = [
    ("Rajasthan", ("rajasthan", "राजस्थान", "rsmssb", "rssb", "rpsc", "reet", "jaipur", "jodhpur", "bikaner", "kota", "bser", "ruhs", "chittorgarh", "chittaurgarh", "jhunjhunu", "tonk", "hanumangarh", "udaipur", "ajmer", "alwar", "sikar", "bhilwara", "churu", "nagaur", "sriganganagar", "ganganagar", "barmer", "jaisalmer", "dausa", "dholpur", "karauli")),
    ("Uttar Pradesh", ("uttar pradesh", "उत्तर प्रदेश", "upsssc", "uppsc", "upessc", "uppbpb", "uptet", "up police", "up deled", "lekhpal", "up tgt", "up pgt", "up ecce", "lucknow", "kanpur", "rampur", "fatehpur", "varanasi", "prayagraj", "agra", "meerut", "ghaziabad", "noida", "bareilly", "gorakhpur", "jhansi", "moradabad", "aligarh", "ayodhya", "mathura", "saharanpur", "कानपुर", "वाराणसी", "प्रयागराज", "मेरठ")),
    ("Bihar", ("bihar", "बिहार", "bpsc", "bssc", "btsc", "bcece", "bseb", "patna")),
    ("Madhya Pradesh", ("madhya pradesh", "मध्य प्रदेश", "mppsc", "mpesb", "vyapam", "bhopal")),
    ("Haryana", ("haryana", "हरियाणा", "hssc", "hpsc", "htet", "panchkula")),
    ("Himachal Pradesh", ("himachal", "हिमाचल", "hppsc", "hpsssb", "hpssc", "shimla")),
    ("Delhi", ("delhi", "दिल्ली", "dsssb", "delhi high court", "mcd", "दिल्ली नगर निगम", "gnctd", "ndmc")),
    ("Maharashtra", ("maharashtra", "महाराष्ट्र", "mpsc", "mumbai", "pune", "nagpur")),
    ("Gujarat", ("gujarat", "गुजरात", "gpsc", "gsssb", "ojas")),
    ("Punjab", ("punjab", "पंजाब", "ppsc", "psssb", "pspcl")),
    ("Uttarakhand", ("uttarakhand", "उत्तराखंड", "ukpsc", "uksssc", "utet")),
    ("Jharkhand", ("jharkhand", "झारखंड", "jssc", "jpsc")),
    ("Chhattisgarh", ("chhattisgarh", "छत्तीसगढ़", "cgpsc", "cgvyapam")),
    ("West Bengal", ("west bengal", "पश्चिम बंगाल", "wbpsc", "wbprb", "kolkata")),
    ("Odisha", ("odisha", "orissa", "ओडिशा", "ossc", "opsc")),
    ("Assam & North East", ("assam", "असम", "assam rifles", "apsc", "tripura", "meghalaya", "manipur", "arunachal", "nagaland", "mizoram", "sikkim", "त्रिपुरा", "मेघालय", "मणिपुर", "अरुणाचल", "नागालैंड", "मिजोरम", "सिक्किम")),
    ("Goa", ("goa psc", "goa police", "goa shipyard", "government of goa", "panaji", "गोवा")),
    ("Chandigarh", ("chandigarh", "चंडीगढ़")),
    ("Ladakh", ("ladakh", "लद्दाख")),
    ("Puducherry", ("puducherry", "pondicherry", "पुदुचेरी")),
    ("Andaman & Nicobar", ("andaman", "nicobar", "अंडमान")),
    ("Daman & Diu", ("daman", "diu", "dadra", "दमन", "दादरा")),
    ("Lakshadweep", ("lakshadweep", "लक्षद्वीप")),
    ("Tamil Nadu", ("tamil nadu", "तमिलनाडु", "tnpsc", "tnusrb", "chennai")),
    ("Kerala", ("kerala", "केरल", "keralapsc", "psc kerala")),
    ("Karnataka", ("karnataka", "कर्नाटक", "kpsc", "kea", "bengaluru")),
    ("Telangana", ("telangana", "तेलंगाना", "tspsc", "tgpsc")),
    ("Andhra Pradesh", ("andhra pradesh", "आंध्र प्रदेश", "appsc", "apssb")),
    ("Jammu & Kashmir", ("jammu", "kashmir", "जम्मू", "jkpsc", "jkssb")),
]

BOARD_RULES = [
    (r"\bupessc\b|up essc|up education service", "UP Education Service Selection Commission (UPESSC)", "https://upessc.up.gov.in/"),
    (r"\bupsssc\b|उत्तर प्रदेश अधीनस्थ सेवा चयन", "UPSSSC (UP Subordinate Services Selection Commission)", "https://upsssc.gov.in/"),
    (r"\buppsc\b|\buppcs\b|उत्तर प्रदेश लोक सेवा आयोग", "Uttar Pradesh Public Service Commission (UPPSC)", "https://uppsc.up.nic.in/"),
    (r"\buppbpb\b|up police|uttar pradesh police|यूपी पुलिस|उत्तर प्रदेश पुलिस", "UP Police Recruitment & Promotion Board (UPPBPB)", "https://uppbpb.gov.in/"),
    (r"\brpsc\b|राजस्थान लोक सेवा आयोग", "Rajasthan Public Service Commission (RPSC)", "https://rpsc.rajasthan.gov.in/"),
    (r"\brsmssb\b|\brssb\b|\bvanpal\b|rajasthan staff selection board|rajasthan cet|rajasthan ldc|computer anudeshak|कंप्यूटर अनुदेशक|rajasthan jen|राजस्थान कर्मचारी चयन बोर्ड|राजस्थान एलडीसी|वनपाल", "Rajasthan Staff Selection Board (RSSB)", "https://rssb.rajasthan.gov.in/"),
    (r"rajasthan set|राजस्थान राज्य पात्रता परीक्षा|राजस्थान स्टेट एलिजिबिलिटी", "University of Kota (Rajasthan SET)", "https://www.uok.ac.in/"),
    (r"rajasthan ration dealer|राशन डीलर", "Rajasthan Food, Civil Supplies & Consumer Affairs Department", "https://food.rajasthan.gov.in/"),
    (r"rajasthan anganwadi|आंगनवाड़ी", "Rajasthan Women & Child Development Department", "https://wcd.rajasthan.gov.in/"),
    (r"yuva sambal|युवा संबल", "Rajasthan Skill, Employment & Entrepreneurship Department", "https://skill.rajasthan.gov.in/"),
    (r"van mitra|वन मित्र", "Rajasthan Forest Department", "https://forest.rajasthan.gov.in/"),
    (r"\breet\b|माध्यमिक शिक्षा बोर्ड", "Rajasthan Board of Secondary Education (RBSE/REET)", "https://reetbser.in/"),
    (r"\bdsssb\b|दिल्ली अधीनस्थ सेवा चयन", "Delhi Subordinate Services Selection Board (DSSSB)", "https://dsssb.delhi.gov.in/"),
    (r"\bbpsc\b|बिहार लोक सेवा आयोग", "Bihar Public Service Commission (BPSC)", "https://www.bpsc.bihar.gov.in/"),
    (r"\bbssc\b|\bbtsc\b|बिहार कर्मचारी चयन", "Bihar Staff Selection Commission (BSSC)", "https://bssc.bihar.gov.in/"),
    (r"\bmppsc\b|मध्य प्रदेश लोक सेवा आयोग", "Madhya Pradesh Public Service Commission (MPPSC)", "https://mppsc.mp.gov.in/"),
    (r"\bmpesb\b|\bvyapam\b|मध्य प्रदेश कर्मचारी चयन", "MP Employee Selection Board (MPESB)", "https://esb.mp.gov.in/"),
    (r"\bhssc\b|हरियाणा कर्मचारी चयन", "Haryana Staff Selection Commission (HSSC)", "https://hssc.gov.in/"),
    (r"\bhpsc\b|हरियाणा लोक सेवा आयोग", "Haryana Public Service Commission (HPSC)", "https://hpsc.gov.in/"),
    (r"\bhppsc\b|himachal pradesh public service commission", "Himachal Pradesh Public Service Commission (HPPSC)", "https://www.hppsc.hp.gov.in/"),
    (r"\bhpsssb\b|\bhpssc\b|himachal pradesh staff selection", "Himachal Pradesh Staff Selection Commission (HPSSC)", "https://www.hpsssb.hp.gov.in/"),
    (r"\bwbpsc\b", "West Bengal Public Service Commission (WBPSC)", "https://wbpsc.gov.in/"),
    (r"\bwbprb\b|west bengal police", "West Bengal Police Recruitment Board (WBPRB)", "https://wbprb.applythrunet.co.in/"),
    (r"\bjssc\b", "Jharkhand Staff Selection Commission (JSSC)", "https://jssc.nic.in/"),
    (r"\bjpsc\b", "Jharkhand Public Service Commission (JPSC)", "https://jpsc.gov.in/"),
    (r"\bcgpsc\b", "Chhattisgarh Public Service Commission (CGPSC)", "https://psc.cg.gov.in/"),
    (r"\bukpsc\b", "Uttarakhand Public Service Commission (UKPSC)", "https://ukpsc.net.in/"),
    (r"\buksssc\b", "Uttarakhand Subordinate Service Selection Commission (UKSSSC)", "https://sssc.uk.gov.in/"),
    (r"\bgpsc\b", "Gujarat Public Service Commission (GPSC)", "https://gpsc.gujarat.gov.in/"),
    (r"\bppsc\b", "Punjab Public Service Commission (PPSC)", "https://ppsc.gov.in/"),
    (r"\bopsc\b", "Odisha Public Service Commission (OPSC)", "https://opsc.gov.in/"),
    (r"\bossc\b", "Odisha Staff Selection Commission (OSSC)", "https://www.ossc.gov.in/"),
    (r"\bmpsc\b|maharashtra public service commission", "Maharashtra Public Service Commission (MPSC)", "https://mpsc.gov.in/"),
    (r"\bgoa psc\b|goa public service commission", "Goa Public Service Commission", "https://gpsc.goa.gov.in/"),
    (r"\btnpsc\b", "Tamil Nadu Public Service Commission (TNPSC)", "https://www.tnpsc.gov.in/"),
    (r"kerala psc|keralapsc", "Kerala Public Service Commission (Kerala PSC)", "https://www.keralapsc.gov.in/"),
    (r"\bkpsc\b", "Karnataka Public Service Commission (KPSC)", "https://kpsc.kar.nic.in/"),
    (r"\btspsc\b|\btgpsc\b", "Telangana State Public Service Commission (TSPSC)", "https://www.tspsc.gov.in/"),
    (r"\bappsc\b", "Andhra Pradesh Public Service Commission (APPSC)", "https://psc.ap.gov.in/"),
    (r"\bjkpsc\b|\bjkssb\b", "J&K Public Service Commission / JKSSB", "https://jkpsc.nic.in/"),
    (r"\bssc\b|staff selection commission|कर्मचारी चयन आयोग", "Staff Selection Commission (SSC)", "https://ssc.gov.in/"),
    (r"\bupsc\b|union public service commission|\bnda\b|\bcds\b|civil services|संघ लोक सेवा आयोग", "Union Public Service Commission (UPSC)", "https://upsc.gov.in/"),
    (r"\bibps\b|आईबीपीएस", "Institute of Banking Personnel Selection (IBPS)", "https://www.ibps.in/"),
    (r"\brrb\b|\brailway\b|\brrc\b|loco pilot|group d|रेलवे भर्ती बोर्ड|रेलवे", "Railway Recruitment Board (RRB)", "https://www.rrbapply.gov.in/"),
    (r"\bsbi\b|state bank of india|स्टेट बैंक ऑफ", "State Bank of India (SBI)", "https://sbi.co.in/web/careers"),
    (r"\brbi\b|reserve bank of india|भारतीय रिज़र्व बैंक", "Reserve Bank of India (RBI)", "https://opportunities.rbi.org.in/"),
    (r"\bnabard\b|नाबार्ड", "NABARD", "https://www.nabard.org/careers.aspx"),
    (r"\bnta\b|national testing agency|\bctet\b|\bugc net\b|\bnet\b|सीटेट|यूजीसी नेट", "National Testing Agency (NTA)", "https://nta.ac.in/"),
    (r"\bjnv\b|jawahar navodaya|navodaya vidyalaya|नवोदय", "Jawahar Navodaya Vidyalaya (JNV)", "https://navodaya.gov.in/"),
    (r"\bindia post\b|\bgds\b|department of posts|डाक विभाग|इंडिया पोस्ट", "Department of Posts (India Post)", "https://indiapostgdsonline.gov.in/"),
    (r"\bnavy\b|indian navy|भारतीय नौसेना|नेवी", "Indian Navy", "https://www.joinindiannavy.gov.in/"),
    (r"\bair force\b|airforce|afcat|वायु सेना|एयरफोर्स", "Indian Air Force", "https://afcat.cdac.in/"),
    (r"\barmy\b|agniveer|join indian army|भारतीय सेना|अग्निवीर", "Indian Army", "https://joinindianarmy.nic.in/"),
    (r"\bcisf\b", "Central Industrial Security Force (CISF)", "https://www.cisf.gov.in/"),
    (r"\bbsf\b", "Border Security Force (BSF)", "https://www.bsf.gov.in/"),
    (r"\bcrpf\b", "Central Reserve Police Force (CRPF)", "https://crpf.gov.in/"),
    (r"\bitbp\b", "Indo-Tibetan Border Police (ITBP)", "https://www.itbpolice.nic.in/"),
    (r"\bssb\b|sashastra seema bal", "Sashastra Seema Bal (SSB)", "https://www.ssb.nic.in/"),
    (r"assam rifles", "Assam Rifles", "https://assamrifles.gov.in/"),
    (r"coast guard", "Indian Coast Guard", "https://joinindiancoastguard.cdac.in/"),
    (r"\bntpc\b", "NTPC Limited", "https://careers.ntpc.co.in/"),
    (r"\bisro\b", "ISRO", "https://www.isro.gov.in/careers.html"),
    (r"\bdrdo\b", "DRDO", "https://drdo.gov.in/drdo/careers"),
    (r"\bbel\b", "Bharat Electronics Limited (BEL)", "https://bel-india.in/careers/"),
    (r"\bongc\b", "ONGC", "https://ongcindia.com/web/eng/careers"),
    (r"\bcoal india\b|\bcil\b", "Coal India Limited (CIL)", "https://www.coalindia.in/career/"),
    (r"\bnhpc\b", "NHPC Limited", "https://www.nhpcindia.com/careers/"),
    (r"\bcwc\b|central warehousing", "Central Warehousing Corporation (CWC)", "https://cewacor.nic.in/"),
    (r"\bc-dac\b|\bcdac\b|centre for development of advanced computing", "Centre for Development of Advanced Computing (C-DAC)", "https://www.cdac.in/"),
    (r"\bicsil\b|intelligent communication systems india", "Intelligent Communication Systems India Ltd (ICSIL)", "https://www.icsil.in/"),
    (r"\bscl\b|semi-conductor laboratory", "Semi-Conductor Laboratory (SCL)", "https://www.scl.gov.in/"),
    (r"\bpnb\b|punjab national bank|पंजाब नेशनल बैंक", "Punjab National Bank (PNB)", "https://www.pnbindia.in/"),
    (r"bsvs|baroda swarojgar|बड़ौदा स्वरोजगार", "Baroda Swarojgar Vikas Sansthan (BSVS), Tonk", "https://www.bankofbaroda.in/"),
    (r"\bbank of baroda\b|बैंक ऑफ बड़ौदा|बैंक ऑफ़ बड़ोदा", "Bank of Baroda (BOB)", "https://www.bankofbaroda.in/career"),
    (r"\bcanara bank\b|केनरा बैंक", "Canara Bank", "https://canarabank.com/careers"),
    (r"\bcentral bank of india\b|सेंट्रल बैंक ऑफ इंडिया", "Central Bank of India", "https://www.centralbankofindia.co.in/en/recruitment"),
    (r"\bindian overseas bank\b|इंडियन ओवरसीज बैंक", "Indian Overseas Bank (IOB)", "https://www.iob.in/Careers.aspx"),
    (r"\bunion bank of india\b|यूनियन बैंक ऑफ इंडिया", "Union Bank of India", "https://www.unionbankofindia.co.in/en/careers"),
    (r"\bbank of india\b|बैंक ऑफ इंडिया", "Bank of India", "https://bankofindia.co.in/recruitments"),
    (r"\buiic\b|united india insurance|यूनाइटेड इंडिया इंश्योरेंस", "United India Insurance Company (UIIC)", "https://uiic.co.in/careers"),
    (r"\bnicl\b|national insurance company", "National Insurance Company (NICL)", "https://nationalinsurance.nic.co.in/"),
    (r"\bmcd\b|municipal corporation of delhi|दिल्ली नगर निगम", "Municipal Corporation of Delhi (MCD)", "https://mcdonline.nic.in/"),
    (r"\bechs\b|ex-servicemen contributory health", "Ex-Servicemen Contributory Health Scheme (ECHS)", "https://echs.gov.in/"),
    (r"\bruhs\b|rajasthan university of health", "Rajasthan University of Health Sciences (RUHS)", "https://ruhsraj.org/"),
    (r"delhi high court|दिल्ली हाईकोर्ट|दिल्ली उच्च न्यायालय", "Delhi High Court", "https://delhihighcourt.nic.in/"),
    (r"rajasthan high court|राजस्थान हाई कोर्ट|राजस्थान हाईकोर्ट|राजस्थान उच्च न्यायालय", "Rajasthan High Court", "https://hcraj.nic.in/"),
    (r"naval dockyard|नेवल डॉकयार्ड|ship building centre", "Indian Navy", "https://www.joinindiannavy.gov.in/"),
    (r"rajasthan police|राजस्थान पुलिस", "Rajasthan Police", "https://police.rajasthan.gov.in/"),
    (r"rajasthan vidyut|विद्युत विभाग|बिजली विभाग", "Rajasthan Power Distribution Companies", "https://energy.rajasthan.gov.in/"),
    (r"delhi police|दिल्ली पुलिस", "Delhi Police", "https://www.delhipolice.gov.in/"),
    (r"\bcapf\b|central armed police forces", "Central Armed Police Forces (CAPF)", "https://www.mha.gov.in/"),
    (r"\bdgqa\b|directorate general of quality assurance", "DGQA (Ministry of Defence)", "https://dgqadmis.in/"),
    (r"\basc centre\b|army service corps", "Indian Army", "https://joinindianarmy.nic.in/"),
    (r"\bsail\b|steel authority of india|सेल", "Steel Authority of India Limited (SAIL)", "https://sailcareers.com/"),
    (r"\bbhel\b|भेल", "Bharat Heavy Electricals Limited (BHEL)", "https://careers.bhel.in/"),
    (r"\bhal\b|hindustan aeronautics", "Hindustan Aeronautics Limited (HAL)", "https://hal-india.co.in/careers"),
    (r"\bbeml\b|भेमल", "BEML Limited", "https://www.bemlindia.in/careers"),
    (r"hindustan copper|हिंदुस्तान कॉपर", "Hindustan Copper Limited (HCL)", "https://www.hindustancopper.com/careers"),
    (r"\bwcl\b|western coalfields", "Western Coalfields Limited (WCL)", "https://www.westerncoal.nic.in/"),
    (r"\baai\b|airports authority of india|एयरपोर्ट अथॉरिटी", "Airports Authority of India (AAI)", "https://www.aai.aero/en/careers/recruitment"),
    (r"\bicf\b|integral coach factory", "Integral Coach Factory (ICF)", "https://www.icf.indianrailways.gov.in/"),
    (r"\brcf\b|rail coach factory", "Rail Coach Factory (RCF)", "https://rcf.indianrailways.gov.in/"),
    (r"press council of india|भारतीय प्रेस परिषद", "Press Council of India", "https://presscouncil.nic.in/"),
    (r"\bcpri\b|central power research institute", "Central Power Research Institute (CPRI)", "https://www.cpri.in/careers"),
    (r"krishi vigyan kendra|कृषि विज्ञान केंद्र", "Krishi Vigyan Kendra (ICAR)", "https://icar.org.in/"),
    (r"tata memorial|टाटा मेमोरियल", "Tata Memorial Centre (TMC)", "https://tmc.gov.in/"),
    (r"sainik school|सैनिक स्कूल", "Sainik School Society", "https://sainikschoolsociety.in/"),
    (r"\bnbems\b", "National Board of Examinations in Medical Sciences (NBEMS)", "https://natboard.edu.in/"),
    (r"grih kalyan kendra", "Grih Kalyan Kendra", "https://gkk.mha.gov.in/"),
    (r"\bcsir\b", "Council of Scientific & Industrial Research (CSIR)", "https://www.csir.res.in/careers"),
    (r"\bbihar police\b|\bbpssc\b|\bcsbc\b|बिहार पुलिस", "Central Selection Board of Constable (CSBC), Bihar", "https://csbc.bih.nic.in/"),
    (r"\bjipmer\b", "JIPMER", "https://www.jipmer.edu.in/recruitment"),
    (r"\baiims\b", "AIIMS", "https://www.aiims.edu/en/careers.html"),
    (r"\bicmr\b", "ICMR", "https://www.icmr.gov.in/careers.html"),
    (r"\besic\b", "ESIC", "https://www.esic.gov.in/recruitments"),
    (r"\bepfo\b", "EPFO", "https://www.epfindia.gov.in/site_en/Recruitment.php"),
    (r"\bincome tax\b|cbdt|आयकर विभाग", "Income Tax Department (CBDT)", "https://incometaxindia.gov.in/Pages/about-us/recruitment.aspx"),
    (r"\bcustoms\b|cbic", "Central Board of Indirect Taxes & Customs (CBIC)", "https://www.cbic.gov.in/"),
    (r"\bhigh court\b", "High Court", ""),
    (r"\bsupreme court\b|सुप्रीम कोर्ट|उच्चतम न्यायालय", "Supreme Court of India", "https://www.sci.gov.in/"),
]

GENERIC_BOARD_MARKERS = (
    "recruitment board", "central / state government", "central government / all india",
    "central government recruitment", "state recruitment board", "state government",
    "government of india", "various department", "check official notification",
    "all india recruitment board", "central government", "all india",
)

JUNK_TITLE_WORDS = (
    "mock test", "मॉक टेस्ट", "scholarship", "छात्रवृत्ति", "admission", "एडमिशन",
    "voter list", "voter", "चुनाव", "aadhar", "आधार कार्ड", "pan card",
    "work from home", "वर्क फ्रॉम होम", "entertainment", "bollywood", "cricket",
    "yojana", "योजना", "bonus", "बोनस", "fastag", "caller name", "time table",
    "timetable", "समय सारणी", "hdfc", "icici", "axis bank", "kotak mahindra",
    "yes bank", "indusind", "federal bank", "bandhan bank", "idfc",
)

JUNK_TITLE_PATTERNS = (
    r"\buniversity\b.*\b(semester|admit card|b\.?ed|ba|bsc|bcom)\b",
    r"\buniversity\b\s+(result|exam)\b",
    r"\bsemester\b",
    r"\bb\.?ed\b",
    r"\bbstc\b",
    r"\bdeled\b|\bd\.?el\.?ed\b",
    r"\brscit\b",
    r"\b(rajasthan\s+)?jet\b",
    r"\biti\s+allotment\b|\bcollege\s+allotment\b|\bbstc\s+allotment\b",
    r"\belection\s+result\b|\bnagar\s+nikay\b|\bpanchayat\s+chunav\b",
    r"\bdigipin\b",
    r"\bpaper\s+pattern\s+change\b",
    r"\breservation\b",
    r"\btotal\s+form\b|\brecord\s+applications\b",
    r"\banubhav\s+praman\s+patra\b",
    r"\bfree\s+(rscit\s+)?course\b|निःशुल्क\s+कोर्स",
    r"\bintern\s+program\b",
    r"\bexam\s+calendar\b",
    r"\brssb\s+result\b",
    r"\bstse\b|\bnmms\b|\bntse\b",
    r"\bentrance\b|प्रवेश\s+परीक्षा",
    r"\b(b\.?tech|b\.?arch|m\.?tech|mba|bba|bca|mca|b\.?sc|b\.?com)\b.*\b(result|semester|admit card)\b",
    r"\b(result|semester|admit card)\b.*\b(b\.?tech|b\.?arch|mba|bba|bca|mca)\b",
    r"\buniversity\b.*\b(result|semester|admit card|date\s*sheet)\b",
    r"\b(date\s*sheet|academic\s+calendar)\b",
)

RELEVANT_TITLE_WORDS = (
    "recruitment", "bharti", "भर्ती", "vacancy", "vacancies", "रिक्ति", "पद",
    "online form", "apply online", "आवेदन", "notification", "विज्ञप्ति", "नोटिफिकेशन",
    "result", "रिजल्ट", "परिणाम", "merit list", "मेरिट", "scorecard", "score card",
    "cut off", "cutoff", "कटऑफ", "admit card", "प्रवेश पत्र", "hall ticket",
    "answer key", "उत्तर कुंजी", "आंसर की", "exam date", "परीक्षा तिथि",
    "typing test", "document verification", "exam city", "city intimation", "syllabus",
    "allotment", "counselling", "selection list", "waiting list",
    "exam centre", "exam center", "परीक्षा केंद्र", "withdraw", "withdrawal",
    "physical", "शारीरिक", "pet exam", "pst exam",
)

CENTRAL_BOARD_MARKERS = (
    "staff selection commission", "union public service commission", "railway recruitment board",
    "rrb", "ibps", "state bank of india", "reserve bank of india", "nabard",
    "national testing agency", "nta", "department of posts", "india post",
    "indian army", "indian navy", "indian air force", "coast guard",
    "cisf", "bsf", "crpf", "itbp", "sashastra seema bal", "assam rifles",
    "isro", "drdo", "bharat electronics", "ongc", "ntpc", "nhpc", "coal india",
    "central warehousing", "semi-conductor laboratory", "c-dac", "cdac",
    "income tax", "supreme court", "high court", "epfo", "esic", "icmr", "aiims",
    "jipmer", "cbic", "customs", "central government",
    "punjab national bank", "bank of baroda", "canara bank", "central bank of india",
    "indian overseas bank", "union bank of india", "bank of india",
    "united india insurance", "national insurance company",
    "steel authority of india", "bharat heavy electricals", "hindustan aeronautics",
    "beml", "hindustan copper", "western coalfields", "airports authority of india",
    "integral coach factory", "rail coach factory", "press council of india",
    "central power research institute", "krishi vigyan kendra", "tata memorial centre",
    "sainik school society", "national board of examinations", "grih kalyan kendra",
    "council of scientific", "capf", "dgqa", "naval dockyard", "ship building centre",
)

HINDI_MONTHS = {
    "जनवरी": "January", "फरवरी": "February", "मार्च": "March", "अप्रैल": "April",
    "मई": "May", "जून": "June", "जुलाई": "July", "अगस्त": "August",
    "सितंबर": "September", "अक्टूबर": "October", "नवंबर": "November", "दिसंबर": "December",
}


def clean_text(value, limit=None):
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = text.replace("\ufffd", "-").replace("\u00a0", " ")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -–|")
    if limit:
        text = text[:limit]
    return text


def clean_title(title):
    text = clean_text(title, 220)
    text = re.sub(
        r"\s*[-|–]\s*(Study\s*Govt\s*Help|studygovthelp\.in|Sarkari\s*Result.*|"
        r"FreeJobAlert(?:\.Com)?|Rojgar\s*Result(?:\.Com)?|IndGovtJobs(?:\.in)?)\s*$",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"\s*[-|–]\s*Last Date Today\s*$", "", text, flags=re.I)
    text = re.sub(r"\bOctomber\b", "October", text, flags=re.I)
    text = re.sub(r"\bWithdrow\b", "Withdraw", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_junk_title(title):
    t = (title or "").lower()
    if not t.strip():
        return True
    if any(word in t for word in JUNK_TITLE_WORDS):
        return True
    if any(re.search(pattern, t) for pattern in JUNK_TITLE_PATTERNS):
        return True
    if not any(word in t for word in RELEVANT_TITLE_WORDS):
        return True
    return False


def detect_state(title, existing="All India"):
    combined = (title or "").lower()
    combined = re.sub(
        r"\b(pnb|punjab national bank|bank of baroda|bank of india|bank of maharashtra|"
        r"central bank of india|punjab & sind bank)\b",
        " ",
        combined,
    )
    combined = re.sub(
        r"पंजाब नेशनल बैंक|पंजाब एंड सिंध बैंक|बैंक ऑफ बड़ौदा|बैंक ऑफ इंडिया|"
        r"बैंक ऑफ महाराष्ट्र|सेंट्रल बैंक ऑफ इंडिया",
        " ",
        combined,
    )
    for state, keywords in STATE_RULES:
        if any(k in combined for k in keywords):
            return state
    existing = clean_text(existing)
    if existing and existing.lower() not in ("all india", "central government / all india", "central government"):
        return existing
    return "All India"


def is_central_board(board):
    low = (board or "").lower()
    return any(marker in low for marker in CENTRAL_BOARD_MARKERS)


def detect_category(title, board="", existing="", state="All India"):
    t = (title or "").lower()
    b = (board or "").lower()
    combined = f"{t} {b}"
    if any(k in combined for k in (
        "teacher", "ctet", "reet", "tet", "tgt", "pgt", "prt", "kvs", "nvs", "jnv",
        "navodaya", "emrs", "school", "lecturer", "professor", "principal",
        "शिक्षक", "अध्यापक", "आचार्य",
    )):
        return "Teaching"
    if re.search(
        r"\b(police|constable|sub inspector|daroga|cisf|bsf|crpf|itbp|ssb|assam rifles|"
        r"sashastra seema bal|agniveer|army|navy|air force|airforce|defence|defense|"
        r"coast guard|fireman|fire fighter)\b",
        combined,
        re.I,
    ) or any(k in combined for k in ("पुलिस", "सिपाही", "दरोगा", "अर्धसैनिक")):
        return "Police"
    # "IBPS RRB" is a bank exam even though it contains the letters RRB.
    if re.search(r"\b(bank|ibps|sbi|rbi|nabard|insurance|बैंक)\b", combined):
        return "Banking"
    if any(k in combined for k in ("railway", "rrb", "rrc", "loco pilot", "group d", "रेलवे")):
        return "Railway"
    if re.search(r"\b(upsc|ias|ips|nda|cds|capf)\b", combined) or "civil services" in combined:
        return "UPSC"
    if any(k in combined for k in (
        "isro", "drdo", "bharat electronics", "bel ", "ongc", "ntpc", "nhpc",
        "coal india", "cwc", "central warehousing", "semi-conductor", "scl ",
        "c-dac", "cdac", "icsil", "steel authority", "bharat heavy", "beml",
        "hindustan aeronautics", "hindustan copper", "western coalfields",
        "airports authority", "integral coach", "rail coach", "central power research",
        "tata memorial",
    )):
        return "PSU"
    if re.search(r"\bssc\b", combined) and "upsssc" not in combined and "upessc" not in combined:
        return "SSC"
    if any(k in combined for k in (
        "upsssc", "uppsc", "rpsc", "rsmssb", "rssb", "bpsc", "bssc", "btsc", "mppsc",
        "mpesb", "hssc", "hpsc", "wbpsc", "jssc", "jpsc", "cgpsc", "ukpsc", "uksssc",
        "gpsc", "ppsc", "opsc", "ossc", "tnpsc", "kpsc", "tspsc", "appsc", "psc",
        "public service commission", "staff selection", "लोक सेवा आयोग",
    )):
        return "State"
    if any(k in combined for k in (
        "income tax", "supreme court", "high court", "epfo", "esic", "customs", "cbic",
    )):
        return "Others"

    if state and state != "All India":
        return "State"
    return "Others"


def detect_board(title, existing="", state="All India"):
    # Match the title first; a wrong legacy board value must not contaminate a clear match.
    title_low = (title or "").lower()
    for pattern, board, site in BOARD_RULES:
        if re.search(pattern, title_low, re.I):
            return board, site

    existing = clean_text(existing)
    low = existing.lower()
    if existing and not any(marker in low for marker in GENERIC_BOARD_MARKERS):
        return existing, ""
    if is_central_board(existing):
        return existing, ""
    if state and state != "All India":
        return f"{state} Government", ""
    return "Central Government", ""


def cleanup_vacancies(value):
    text = clean_text(value, 80)
    if not text:
        return "Various Posts"
    low = text.lower()
    if any(k in low for k in ("various", "check official", "not specified", "as per notification", "n/a", "na")):
        return "Various Posts"

    # A bare year is not a vacancy count.
    bare = re.fullmatch(r"[^\d]*(\d{1,2}[,.]?\d{3})[^\d]*", text)
    if bare:
        number = int(re.sub(r"\D", "", bare.group(1)))
        if 1900 <= number <= 2100:
            return "Various Posts"

    m = re.search(r"(\d[\d,]*)\s*(?:posts?|post|vacancies|vacancy|पद|रिक्तियां)", text, re.I)
    if m:
        digits = re.sub(r"\D", "", m.group(1))
        if digits:
            number = int(digits)
            if number == 0:
                return "Various Posts"
            return f"{number:,} Posts"

    # Values like "(02)", "(1688*)" or "1180 Post"
    m = re.fullmatch(r"[^\d]*(\d[\d,]*)\D*", text)
    if m:
        digits = re.sub(r"\D", "", m.group(1))
        if digits:
            number = int(digits)
            if 1900 <= number <= 2100:
                return "Various Posts"
            if number > 0:
                return f"{number:,} Posts"

    return text if len(text) <= 60 else "Various Posts"


def parse_date(value):
    if not value:
        return None
    text = clean_text(value, 120)
    for hindi, english in HINDI_MONTHS.items():
        text = text.replace(hindi, english)
    text = re.sub(r"\(.*?\)", " ", text)
    text = re.sub(r"(\d{1,2})(?:st|nd|rd|th)\b", r"\1", text, flags=re.I)
    text = re.sub(r"\b(at|till|upto|up to)\b.*$", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" .,-")
    if not text or re.search(r"expected|soon|announce|notify|check|various|n/?a|tba|tbd|संभावित|शीघ्र", text, re.I):
        return None

    m = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", text)
    if m:
        normalized = re.sub(r"[/.-]", "/", m.group(0))
        try:
            return datetime.strptime(normalized, "%d/%m/%Y").date()
        except ValueError:
            pass

    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if m:
        try:
            return datetime.strptime(m.group(0), "%Y-%m-%d").date()
        except ValueError:
            pass

    m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2})\b", text)
    if m:
        try:
            return datetime.strptime(f"{m.group(1)}/{m.group(2)}/{m.group(3)}", "%d/%m/%y").date()
        except ValueError:
            pass

    for regex in (r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})"):
        m = re.search(regex, text)
        if not m:
            continue
        try:
            if regex.startswith(r"(\d"):
                day, month, year = m.group(1), m.group(2), m.group(3)
            else:
                month, day, year = m.group(1), m.group(2), m.group(3)
            month = month[:3].title() if len(month) > 3 else month.title()
            return datetime.strptime(f"{int(day)} {month} {int(year)}", "%d %b %Y").date()
        except ValueError:
            continue
    return None


def infer_apply_last_date(title, apply_last_date, content_html="", notification_date=""):
    """Recover a real last date when the source only has free text."""
    if parse_date(apply_last_date):
        return apply_last_date

    text = clean_text(content_html, 30000)
    title_text = title or ""
    for hindi, english in HINDI_MONTHS.items():
        text = text.replace(hindi, english)
        title_text = title_text.replace(hindi, english)

    month = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    date_re = rf"(\d{{1,2}})\s+({month})\.?\s+(\d{{4}})"
    patterns = (
        rf"(?:last\s*date|अंतिम\s*(?:तिथि|तारीख)|आवेदन\s*की\s*अंतिम\s*(?:तिथि|तारीख))[^0-9]{{0,80}}{date_re}",
        rf"{date_re}[^.\d]{{0,50}}(?:तक|tak)[^.\d]{{0,20}}(?:आवेदन|apply)",
        rf"(?:आवेदन|apply)[^.\d]{{0,50}}{date_re}\s*(?:तक|tak)",
    )
    for source in (title_text, text):
        for pattern in patterns:
            match = re.search(pattern, source, re.I)
            if not match:
                continue
            day, month_name, year = match.groups()
            parsed = parse_date(f"{day} {month_name} {year}")
            if parsed:
                return parsed.isoformat()

    low = (apply_last_date or "").lower()
    days = re.search(r"(\d{1,2})\s*(?:days?|दिन)", low)
    if days and any(k in low for k in (
        "within", "from advertisement", "प्रकाशन", "नोटिस जारी", "advertisement",
    )):
        base = parse_date(notification_date)
        if base:
            return (base + timedelta(days=int(days.group(1)))).isoformat()
    return apply_last_date


def canonical_status(status, title, apply_start_date="", apply_last_date="", exam_date="", result_date="", notification_date="", today=None):
    today = today or date.today()
    title_low = (title or "").lower()
    current = (status or "").lower()

    if any(k in title_low for k in ("answer key", "उत्तर कुंजी", "आंसर की", "omr sheet")):
        return "Answer Key"
    if any(k in title_low for k in (
        "result", "रिजल्ट", "परिणाम", "merit list", "मेरिट", "score card", "scorecard",
        "cut off", "cutoff", "कटऑफ", "allotment", "selection list", "waiting list",
    )):
        return "Result"
    if any(k in title_low for k in (
        "admit card", "प्रवेश पत्र", "hall ticket", "call letter", "city intimation",
        "exam city", "exam date", "exam centre", "exam center", "परीक्षा केंद्र",
        "physical date", "physical exam", "pet date", "pst date", "परीक्षा तिथि",
    )):
        return "Admit Card"
    if any(k in title_low for k in ("syllabus", "पाठ्यक्रम", "exam pattern", "परीक्षा पैटर्न")):
        return "Syllabus"
    if any(k in title_low for k in ("upcoming", "expected soon", "coming soon", "संभावित", "आगामी")):
        return "Upcoming"

    start = parse_date(apply_start_date)
    last = parse_date(apply_last_date)
    exam = parse_date(exam_date)
    result = parse_date(result_date)

    if start and start > today:
        return "Upcoming"
    if last:
        if last >= today:
            return "Applications Open"
        if result and result <= today:
            return "Result"
        if exam or result:
            return "Admit Card"
        return "Applications Closed"
    if exam:
        # A walk-in interview date is an application deadline, not an admit card.
        if "walk-in" in title_low or "walkin" in title_low or "walk in" in title_low:
            return "Applications Closed" if exam < today else "Applications Open"
        # Exam date alone does not prove the result is out.
        return "Admit Card"
    if result:
        return "Result" if result <= today else "Admit Card"

    # No usable deadline and the post is over two months old: the window is over.
    notified = parse_date(notification_date)
    if notified and (today - notified).days > 60:
        return "Applications Closed"

    if "answer key" in current:
        return "Answer Key"
    if "result" in current:
        return "Result"
    if "admit" in current:
        return "Admit Card"
    if "syllabus" in current:
        return "Syllabus"
    if "upcoming" in current:
        return "Upcoming"
    if "closed" in current or "expired" in current:
        return "Applications Closed"
    if "archiv" in current:
        return "Archived"
    return "Applications Open"


def is_aggregator(url):
    host = urlparse(url).netloc.lower()
    return host in AGGREGATOR_HOSTS


def clean_url(url):
    if not url:
        return ""
    url = html.unescape(str(url)).strip().strip("'\"").rstrip(".,;:)]}")
    if not url or url.startswith("#") or url.lower().startswith(("javascript:", "mailto:", "tel:")):
        return ""
    if url.startswith("//"):
        url = "https:" + url
    elif re.match(r"^www\.", url, re.I):
        url = "https://" + url
    elif not re.match(r"^https?://", url, re.I):
        if re.match(r"^[\w.-]+\.(gov|nic|in|com|org|net|ac)(\.in)?(/|$)", url, re.I):
            url = "https://" + url
        else:
            return ""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host or not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", host):
        return ""
    if any(part in parsed.netloc.lower() for part in BLOCKED_HOST_PARTS):
        return ""
    return url


def is_root_url(url):
    parsed = urlparse(url)
    return parsed.path in ("", "/")


def _is_pdf_url(url):
    return (url or "").lower().split("?")[0].endswith(".pdf")


def should_keep_action_link(field, url, official_url, source_url):
    if not url:
        return False
    if is_aggregator(url):
        return False
    if source_url and url == source_url:
        # Commission notice boards publish the notice itself as a PDF, so the
        # source of such a record is the document the candidate should open.
        return _is_pdf_url(url)
    if official_url and url == official_url:
        return field == "notification" and _is_pdf_url(url)
    if field in ("apply_online", "admit_card", "result", "answer_key", "previous_papers"):
        if is_root_url(url) and (field != "apply_online" or not official_url or _same_site(url, official_url)):
            return False
    if field == "notification":
        if _is_pdf_url(url):
            return True
        if is_root_url(url):
            return False
    return True


def ensure_slug(title, fallback_seed=""):
    base = (title or fallback_seed or "exam").lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    base = re.sub(r"-{2,}", "-", base)[:90].strip("-")
    return base or "govt-exam"


def dedupe_key(title):
    text = (title or "").lower()
    if any(k in text for k in ("answer key", "उत्तर कुंजी", "आंसर की")):
        kind = "answer"
    elif any(k in text for k in ("syllabus", "पाठ्यक्रम", "exam pattern", "परीक्षा पैटर्न")):
        kind = "syllabus"
    elif any(k in text for k in ("result", "रिजल्ट", "परिणाम", "merit list", "score card", "scorecard", "cut off", "cutoff", "कटऑफ", "allotment", "selection list")):
        kind = "result"
    elif any(k in text for k in ("admit card", "प्रवेश पत्र", "hall ticket", "city intimation", "exam city")):
        kind = "admit"
    else:
        kind = "job"
    text = re.sub(r"\b20\d{2}\b", " ", text)
    for word in (
        "online form", "apply online", "application form", "notification", "recruitment",
        "bharti", "vacancy", "vacancies", "latest", "update", "revised", "final", "out",
        "declared", "download", "link", "check", "here", "direct", "today", "last date",
    ):
        text = re.sub(rf"\b{re.escape(word)}\b", " ", text)
    text = re.sub(r"[^a-z0-9\u0900-\u097f]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return f"{kind}:{text[:110]}"


def _same_site(url_a, url_b):
    host_a = urlparse(url_a).netloc.lower().replace("www.", "")
    host_b = urlparse(url_b).netloc.lower().replace("www.", "")
    if not host_a or not host_b:
        return False
    return host_a == host_b or host_a.endswith("." + host_b) or host_b.endswith("." + host_a)


def normalize_record(row, today=None, cap_content=False):
    data = dict(row or {})
    title = clean_title(data.get("title", ""))
    data["title"] = title
    data["short_title"] = clean_text(data.get("short_title"), 80) or title[:70]

    existing_state = clean_text(data.get("state", "")) or "All India"
    title_state = detect_state(title, "All India")
    board_state = title_state if title_state != "All India" else existing_state
    board, board_site = detect_board(title, data.get("board_name", ""), board_state)

    if title_state != "All India":
        state = title_state
    elif is_central_board(board):
        state = "All India"
    else:
        state = board_state or "All India"

    category = detect_category(title, board, data.get("category", ""), state)
    data["state"] = state
    data["board_name"] = board
    data["category"] = category
    data["department"] = clean_text(data.get("department"), 120) or board
    data["post_name"] = clean_text(data.get("post_name"), 120) or title[:90]
    data["total_vacancies"] = cleanup_vacancies(data.get("total_vacancies"))
    apply_last = infer_apply_last_date(
        title,
        data.get("apply_last_date", ""),
        data.get("content_html", ""),
        data.get("notification_date", ""),
    )
    if apply_last:
        data["apply_last_date"] = apply_last
    data["status"] = canonical_status(
        data.get("status", ""),
        title,
        data.get("apply_start_date", ""),
        apply_last,
        data.get("exam_date", ""),
        data.get("result_date", ""),
        data.get("notification_date", ""),
        today=today,
    )
    data["badge_color"] = {
        "Applications Open": "emerald",
        "Applications Closed": "slate",
        "Upcoming": "indigo",
        "Admit Card": "blue",
        "Answer Key": "purple",
        "Result": "amber",
        "Syllabus": "teal",
        "Archived": "gray",
    }.get(data["status"], "slate")

    source = clean_url(data.get("source_url"))
    official = clean_url(data.get("link_official_website"))
    if not official or is_aggregator(official):
        official = board_site or ""
    if board_site and official and not _same_site(official, board_site):
        official = board_site
    if board_site and official.startswith("http://") and board_site.startswith("https://") and _same_site(official, board_site):
        official = board_site
    if source and official == source:
        official = board_site or ""
    data["link_official_website"] = official

    field_map = {
        "apply_online": "link_apply_online",
        "notification": "link_notification_pdf",
        "admit_card": "link_admit_card",
        "answer_key": "link_answer_key",
        "result": "link_result",
        "previous_papers": "link_previous_papers",
    }
    for field, column in field_map.items():
        url = clean_url(data.get(column))
        if not should_keep_action_link(field, url, official, source):
            url = ""
        data[column] = url

    desc = clean_text(data.get("short_description"), 320)
    if not desc or len(desc) < 25:
        desc = f"{title} — {board}. Check important dates, eligibility, fees and official links."
    data["short_description"] = desc

    if data.get("link_notification_pdf") and data.get("link_notification_pdf") == data.get("link_apply_online"):
        data["link_apply_online"] = ""

    if cap_content:
        content = data.get("content_html") or ""
        if len(content) > 60000:
            cut = content.rfind("</", 0, 60000)
            end = content.find(">", cut) if cut != -1 else -1
            data["content_html"] = content[:end + 1] if end != -1 else content[:60000]
        data["short_description"] = data["short_description"][:320]

    if not data.get("notification_date"):
        data["notification_date"] = "Not specified"
    if not data.get("apply_start_date"):
        data["apply_start_date"] = "Check Official Notification"
    if not data.get("apply_last_date"):
        data["apply_last_date"] = "Check Official Notification"
    if not data.get("exam_date"):
        data["exam_date"] = "As per schedule"
    if not data.get("result_date"):
        data["result_date"] = "After Examination" if data["status"] != "Result" else "Declared"
    if not data.get("fee_general"):
        data["fee_general"] = "As per notification"
    if not data.get("fee_reserved"):
        data["fee_reserved"] = "As per notification"

    status = data["status"]
    if status == "Result":
        meta_title = f"{title} - Result, Cut Off & Merit List"
        meta_desc = f"{title} result declared by {board}. Check direct scorecard, cut off and merit list."
    elif status == "Answer Key":
        meta_title = f"{title} - Answer Key & Response Sheet"
        meta_desc = f"{title} answer key by {board}. Check provisional answer key and objection details."
    elif status == "Admit Card":
        meta_title = f"{title} - Admit Card & Exam Date"
        meta_desc = f"{title} admit card by {board}. Check exam date, city intimation and download link."
    elif status == "Syllabus":
        meta_title = f"{title} - Syllabus & Exam Pattern"
        meta_desc = f"{title} syllabus and exam pattern by {board}. Check subject-wise topics and marking scheme."
    else:
        meta_title = f"{title} - Notification, Eligibility & Apply Link"
        meta_desc = f"{title} notification by {board}. Check {data['total_vacancies']}, eligibility, age limit, dates and official apply link."
    data["meta_title"] = clean_text(meta_title, 180)
    data["meta_description"] = clean_text(meta_desc, 160)
    data["keywords"] = clean_text(
        f"{title}, {board}, {state} govt jobs, {category} recruitment, admit card, result",
        240,
    )

    return data
