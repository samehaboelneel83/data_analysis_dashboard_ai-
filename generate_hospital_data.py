"""Build a synthetic dataset for a large Egyptian teaching hospital.

Shaped by what the platform's 64 widget types actually need, not by what a
schema diagram would look like:

  maps          patients carry a governorate with real coordinates; branches and
                referring clinics carry their own, so choropleth, points,
                clusters, density, lines and network maps all have something real
  hierarchies   division -> department -> unit, and a staff reporting line, so
                tree, sunburst, icicle, dendrogram and org charts have depth
  flows         appointment -> arrival -> triage -> admission -> discharge, so
                funnel and sankey have stages that genuinely narrow
  distributions length of stay, cost, lab values and wait times are drawn from
                skewed distributions, because a box plot or histogram of uniform
                noise shows nothing
  correlation   HbA1c, creatinine, BMI, age and length of stay are deliberately
                related, so a correlation matrix and scatter have signal to find
  time          two years of daily activity with weekday, seasonal and Ramadan
                effects, so trend, forecast and comparative time series are not
                flat lines

Clinically plausible for Egypt specifically: hepatitis C and its sequelae,
diabetes and hypertension prevalence, the mix of public insurance, Universal
Health Insurance, private insurers and cash, and a real governorate catchment
weighted towards Greater Cairo.

Everything is synthetic. No real person's data is used or reproduced.
"""
import datetime as dt
import math
import os
import random
import sqlite3
import sys

random.seed(20260910)                      # reproducible: same file every run

OUT = sys.argv[1]
START = dt.date(2024, 9, 1)
DAYS = 740
END = START + dt.timedelta(days=DAYS - 1)

N_PATIENTS = 40_000
N_ENCOUNTERS = 120_000
N_APPOINTMENTS = 140_000

# ── Geography ────────────────────────────────────────────────────────────────
# (name, arabic, lat, lon, share of catchment)
GOVERNORATES = [
    ("Cairo", "القاهرة", 30.0444, 31.2357, 0.240),
    ("Giza", "الجيزة", 30.0131, 31.2089, 0.170),
    ("Qalyubia", "القليوبية", 30.4595, 31.1780, 0.075),
    ("Alexandria", "الإسكندرية", 31.2001, 29.9187, 0.070),
    ("Sharqia", "الشرقية", 30.5877, 31.5020, 0.055),
    ("Dakahlia", "الدقهلية", 31.0409, 31.3785, 0.045),
    ("Beheira", "البحيرة", 30.8481, 30.3436, 0.040),
    ("Gharbia", "الغربية", 30.8754, 31.0335, 0.035),
    ("Menoufia", "المنوفية", 30.5972, 30.9876, 0.030),
    ("Fayoum", "الفيوم", 29.3084, 30.8428, 0.028),
    ("Beni Suef", "بني سويف", 29.0661, 31.0994, 0.025),
    ("Minya", "المنيا", 28.1099, 30.7503, 0.025),
    ("Asyut", "أسيوط", 27.1809, 31.1837, 0.022),
    ("Sohag", "سوهاج", 26.5591, 31.6957, 0.020),
    ("Qena", "قنا", 26.1551, 32.7160, 0.016),
    ("Ismailia", "الإسماعيلية", 30.5965, 32.2715, 0.014),
    ("Suez", "السويس", 29.9668, 32.5498, 0.012),
    ("Port Said", "بورسعيد", 31.2653, 32.3019, 0.012),
    ("Damietta", "دمياط", 31.4165, 31.8133, 0.010),
    ("Kafr El Sheikh", "كفر الشيخ", 31.1117, 30.9398, 0.010),
    ("Luxor", "الأقصر", 25.6872, 32.6396, 0.009),
    ("Aswan", "أسوان", 24.0889, 32.8998, 0.009),
    ("Red Sea", "البحر الأحمر", 27.2579, 33.8116, 0.007),
    ("Matrouh", "مطروح", 31.3543, 27.2373, 0.006),
    ("North Sinai", "شمال سيناء", 31.1313, 33.8034, 0.005),
    ("South Sinai", "جنوب سيناء", 28.2400, 33.6200, 0.005),
    ("New Valley", "الوادي الجديد", 25.4515, 30.5465, 0.005),
]
GOV_NAMES = [g[0] for g in GOVERNORATES]
GOV_W = [g[4] for g in GOVERNORATES]

BRANCHES = [
    (1, "Main Campus — Nasr City", "Cairo", 30.0566, 31.3300, 900),
    (2, "Dokki Branch", "Giza", 30.0388, 31.2119, 320),
    (3, "Shubra El Kheima Branch", "Qalyubia", 30.1286, 31.2422, 240),
    (4, "Smouha Branch — Alexandria", "Alexandria", 31.2156, 29.9553, 260),
    (5, "Mansoura Branch", "Dakahlia", 31.0364, 31.3807, 180),
    (6, "Assiut Branch", "Asyut", 27.1783, 31.1859, 160),
]

# ── People ───────────────────────────────────────────────────────────────────
MALE = ["Mohamed", "Ahmed", "Mahmoud", "Mostafa", "Youssef", "Omar", "Khaled",
        "Hassan", "Hussein", "Ibrahim", "Tarek", "Sherif", "Amr", "Karim",
        "Islam", "Ayman", "Sameh", "Wael", "Hany", "Ashraf", "Emad", "Gamal",
        "Nabil", "Adel", "Magdy", "Sayed", "Ramadan", "Abdelrahman", "Salah"]
FEMALE = ["Fatma", "Aya", "Mona", "Heba", "Nourhan", "Sara", "Yasmin", "Dina",
          "Mariam", "Salma", "Rana", "Doaa", "Amira", "Nesma", "Shaimaa",
          "Hoda", "Nagwa", "Samia", "Eman", "Ghada", "Rasha", "Marwa",
          "Nada", "Habiba", "Asmaa", "Zeinab", "Safaa"]
SURNAMES = ["Hassan", "Ibrahim", "Mahmoud", "El-Sayed", "Abdelaziz", "Farouk",
            "Zaki", "Shaker", "Gaber", "Fahmy", "Mostafa", "El-Masry", "Sabry",
            "Kamel", "Tawfik", "Saleh", "Nour", "Radwan", "El-Naggar", "Fathy",
            "Abdelhamid", "Serag", "Badawy", "Hegazy", "Attia", "Selim",
            "El-Sharkawy", "Abou Zeid", "Kandil", "Mansour"]

# ── Organisation ─────────────────────────────────────────────────────────────
# division, department, units...  Depth is what tree/sunburst/icicle need.
STRUCTURE = {
    "Medical": {
        "Internal Medicine": ["General Medicine", "Endocrinology", "Rheumatology"],
        "Cardiology": ["Coronary Care", "Cath Lab", "Echo & Non-invasive"],
        "Nephrology": ["Dialysis Unit", "Transplant Follow-up"],
        "Hepatology & GI": ["Hepatitis Clinic", "Endoscopy", "Liver Unit"],
        "Neurology": ["Stroke Unit", "Epilepsy Clinic"],
        "Chest & Respiratory": ["Asthma & COPD", "Sleep Lab"],
        "Oncology": ["Medical Oncology", "Day Chemotherapy"],
    },
    "Surgical": {
        "General Surgery": ["Upper GI", "Colorectal", "Day Surgery"],
        "Orthopaedics": ["Trauma", "Arthroplasty", "Spine"],
        "Cardiothoracic Surgery": ["Open Heart", "Thoracic"],
        "Neurosurgery": ["Cranial", "Spinal"],
        "Urology": ["Stone Unit", "Uro-oncology"],
        "ENT": ["Otology", "Head & Neck"],
        "Ophthalmology": ["Cataract", "Retina"],
        "Burns & Plastics": ["Burns Unit", "Reconstructive"],
    },
    "Critical Care": {
        "Emergency Department": ["Resuscitation", "Majors", "Minors", "Triage"],
        "Intensive Care": ["Medical ICU", "Surgical ICU", "Coronary ICU"],
    },
    "Women & Children": {
        "Obstetrics & Gynaecology": ["Labour Ward", "Antenatal", "Gynae Surgery"],
        "Paediatrics": ["General Paediatrics", "Paediatric ICU"],
        "Neonatology": ["NICU", "Special Care Nursery"],
    },
    "Diagnostics": {
        "Radiology": ["CT & MRI", "Ultrasound", "Interventional"],
        "Laboratory Medicine": ["Haematology", "Clinical Chemistry",
                                "Microbiology", "Blood Bank"],
        "Pathology": ["Histopathology", "Cytology"],
    },
    "Support": {
        "Pharmacy": ["Inpatient Pharmacy", "Outpatient Pharmacy", "Clinical Pharmacy"],
        "Physiotherapy": ["Inpatient Rehab", "Outpatient Rehab"],
        "Nutrition": ["Clinical Nutrition"],
    },
}

DIAGNOSES = [
    # (icd10, english, arabic, chronic, base_los, base_cost_egp, weight)
    ("E11", "Type 2 diabetes mellitus", "السكري من النوع الثاني", 1, 3.5, 9_000, 0.085),
    ("I10", "Essential hypertension", "ارتفاع ضغط الدم", 1, 2.8, 7_200, 0.080),
    ("B18.2", "Chronic hepatitis C", "التهاب الكبد الوبائي سي", 1, 4.2, 16_500, 0.055),
    ("N18", "Chronic kidney disease", "المرض الكلوي المزمن", 1, 6.0, 24_000, 0.045),
    ("J18", "Pneumonia", "الالتهاب الرئوي", 0, 5.5, 14_000, 0.050),
    ("I21", "Acute myocardial infarction", "احتشاء عضلة القلب", 0, 6.5, 68_000, 0.032),
    ("I63", "Cerebral infarction (stroke)", "جلطة دماغية", 0, 9.0, 52_000, 0.028),
    ("K35", "Acute appendicitis", "التهاب الزائدة الحاد", 0, 2.5, 21_000, 0.038),
    ("O80", "Normal delivery", "ولادة طبيعية", 0, 1.8, 11_000, 0.060),
    ("O82", "Caesarean section", "ولادة قيصرية", 0, 3.2, 26_000, 0.052),
    ("J45", "Asthma", "الربو", 1, 2.2, 6_500, 0.040),
    ("A09", "Gastroenteritis", "النزلة المعوية", 0, 1.9, 4_800, 0.055),
    ("S72", "Fracture of femur", "كسر عظمة الفخذ", 0, 8.5, 58_000, 0.022),
    ("K80", "Cholelithiasis", "حصوات المرارة", 0, 3.0, 27_000, 0.030),
    ("N20", "Urinary stones", "حصوات المسالك البولية", 0, 2.6, 19_000, 0.032),
    ("C50", "Breast cancer", "سرطان الثدي", 1, 5.5, 74_000, 0.020),
    ("C34", "Lung cancer", "سرطان الرئة", 1, 6.2, 81_000, 0.014),
    ("K74", "Hepatic cirrhosis", "تليف الكبد", 1, 7.5, 38_000, 0.026),
    ("D50", "Iron deficiency anaemia", "أنيميا نقص الحديد", 1, 2.0, 5_200, 0.036),
    ("P07", "Preterm newborn", "الولادة المبكرة", 0, 12.0, 63_000, 0.020),
    ("T30", "Burns", "الحروق", 0, 11.0, 47_000, 0.012),
    ("F32", "Depressive episode", "نوبة اكتئاب", 1, 4.0, 9_500, 0.014),
    ("H25", "Senile cataract", "المياه البيضاء", 0, 1.2, 15_000, 0.030),
    ("M17", "Osteoarthritis of knee", "خشونة الركبة", 1, 4.5, 44_000, 0.022),
    ("I50", "Heart failure", "هبوط القلب", 1, 6.8, 33_000, 0.031),
]
DX_W = [d[6] for d in DIAGNOSES]

PAYERS = [
    ("Universal Health Insurance", "government", 0.235),
    ("Health Insurance Organization", "government", 0.205),
    ("Cash / self-pay", "cash", 0.190),
    ("Misr Insurance", "private", 0.085),
    ("AXA Egypt", "private", 0.060),
    ("MetLife Egypt", "private", 0.052),
    ("Allianz Egypt", "private", 0.048),
    ("Bupa Egypt", "private", 0.035),
    ("Syndicate scheme", "syndicate", 0.045),
    ("Corporate contract", "corporate", 0.045),
]
PAYER_W = [p[2] for p in PAYERS]

LAB_TESTS = [
    # code, name, unit, low, high, mean, sd, panel
    ("HGB", "Haemoglobin", "g/dL", 12.0, 16.0, 12.6, 2.0, "Haematology"),
    ("WBC", "White cell count", "10^3/uL", 4.0, 11.0, 8.4, 3.2, "Haematology"),
    ("PLT", "Platelets", "10^3/uL", 150, 410, 246, 82, "Haematology"),
    ("GLU", "Fasting glucose", "mg/dL", 70, 100, 128, 46, "Clinical Chemistry"),
    ("HBA1C", "HbA1c", "%", 4.0, 5.7, 7.1, 1.8, "Clinical Chemistry"),
    ("CREA", "Creatinine", "mg/dL", 0.6, 1.3, 1.28, 0.75, "Clinical Chemistry"),
    ("UREA", "Blood urea", "mg/dL", 15, 45, 42, 22, "Clinical Chemistry"),
    ("ALT", "ALT", "U/L", 7, 56, 41, 28, "Clinical Chemistry"),
    ("AST", "AST", "U/L", 10, 40, 38, 26, "Clinical Chemistry"),
    ("TBIL", "Total bilirubin", "mg/dL", 0.2, 1.2, 1.0, 0.7, "Clinical Chemistry"),
    ("ALB", "Albumin", "g/dL", 3.5, 5.2, 3.8, 0.6, "Clinical Chemistry"),
    ("CRP", "C-reactive protein", "mg/L", 0, 6, 21, 32, "Clinical Chemistry"),
    ("TROP", "Troponin I", "ng/mL", 0, 0.04, 0.09, 0.35, "Clinical Chemistry"),
    ("NA", "Sodium", "mmol/L", 135, 145, 138, 4.4, "Clinical Chemistry"),
    ("K", "Potassium", "mmol/L", 3.5, 5.1, 4.3, 0.62, "Clinical Chemistry"),
    ("INR", "INR", "", 0.8, 1.2, 1.18, 0.42, "Haematology"),
    ("TSH", "TSH", "mIU/L", 0.4, 4.0, 2.9, 2.2, "Clinical Chemistry"),
    ("VITD", "Vitamin D", "ng/mL", 30, 100, 21, 11, "Clinical Chemistry"),
]

DRUGS = [
    ("Metformin 850mg", "Antidiabetic", 42.0), ("Insulin glargine", "Antidiabetic", 310.0),
    ("Amlodipine 5mg", "Antihypertensive", 38.0), ("Bisoprolol 5mg", "Antihypertensive", 55.0),
    ("Ramipril 5mg", "Antihypertensive", 47.0), ("Atorvastatin 20mg", "Lipid lowering", 68.0),
    ("Clopidogrel 75mg", "Antiplatelet", 96.0), ("Enoxaparin 40mg", "Anticoagulant", 145.0),
    ("Ceftriaxone 1g", "Antibiotic", 88.0), ("Meropenem 1g", "Antibiotic", 420.0),
    ("Vancomycin 1g", "Antibiotic", 265.0), ("Azithromycin 500mg", "Antibiotic", 74.0),
    ("Paracetamol 1g IV", "Analgesic", 32.0), ("Morphine 10mg", "Analgesic", 60.0),
    ("Omeprazole 40mg", "Gastro", 51.0), ("Sofosbuvir/Daclatasvir", "Antiviral", 1850.0),
    ("Furosemide 40mg", "Diuretic", 26.0), ("Salbutamol nebuliser", "Respiratory", 44.0),
    ("Hydrocortisone 100mg", "Steroid", 58.0), ("Ondansetron 8mg", "Antiemetic", 39.0),
    ("Erythropoietin 4000IU", "Haematology", 520.0), ("Iron sucrose 200mg", "Haematology", 240.0),
]

PROCEDURES = [
    ("PCI", "Percutaneous coronary intervention", 96_000, "Cardiology"),
    ("CABG", "Coronary artery bypass graft", 285_000, "Cardiothoracic Surgery"),
    ("APPY", "Appendicectomy", 24_000, "General Surgery"),
    ("CHOLE", "Laparoscopic cholecystectomy", 33_000, "General Surgery"),
    ("CSEC", "Caesarean section", 27_000, "Obstetrics & Gynaecology"),
    ("THR", "Total hip replacement", 118_000, "Orthopaedics"),
    ("TKR", "Total knee replacement", 126_000, "Orthopaedics"),
    ("ORIF", "Open reduction internal fixation", 61_000, "Orthopaedics"),
    ("PHACO", "Phacoemulsification", 17_000, "Ophthalmology"),
    ("TURP", "Transurethral resection of prostate", 42_000, "Urology"),
    ("ESWL", "Extracorporeal shockwave lithotripsy", 22_000, "Urology"),
    ("HD", "Haemodialysis session", 1_400, "Nephrology"),
    ("EGD", "Upper GI endoscopy", 9_500, "Hepatology & GI"),
    ("COLO", "Colonoscopy", 12_500, "Hepatology & GI"),
    ("CT", "CT scan with contrast", 5_600, "Radiology"),
    ("MRI", "MRI study", 8_900, "Radiology"),
    ("CRANI", "Craniotomy", 168_000, "Neurosurgery"),
    ("THROMB", "Thrombolysis for stroke", 74_000, "Neurology"),
]


def pick(items, weights):
    return random.choices(items, weights=weights, k=1)[0]


def skewed(mean, shape=1.7):
    """A right-skewed positive draw. Length of stay and cost are never normal —
    a handful of long, expensive stays carry most of the total, and a box plot of
    symmetric noise would show none of that."""
    return mean * random.weibullvariate(1.0, shape)


def seasonal(day: dt.date) -> float:
    """Attendance across a year. Winter respiratory peak, a summer trough, a
    visible Ramadan dip and an Eid spike, and quieter Fridays."""
    doy = day.timetuple().tm_yday
    season = 1.0 + 0.19 * math.cos(2 * math.pi * (doy - 20) / 365.0)
    weekday = {4: 0.72, 5: 0.86}.get(day.weekday(), 1.0)      # Fri, Sat
    # Ramadan drifts ~11 days earlier each year; approximated for these 2 years.
    ramadan = [(dt.date(2025, 3, 1), dt.date(2025, 3, 30)),
               (dt.date(2026, 2, 18), dt.date(2026, 3, 19))]
    factor = 1.0
    for a, b in ramadan:
        if a <= day <= b:
            factor = 0.78
        if b < day <= b + dt.timedelta(days=4):
            factor = 1.22                                      # Eid rebound
    return season * weekday * factor


def main():
    if os.path.exists(OUT):
        os.remove(OUT)
    c = sqlite3.connect(OUT)
    c.execute("PRAGMA journal_mode=OFF")
    c.execute("PRAGMA synchronous=OFF")

    c.executescript("""
    CREATE TABLE governorates (
      governorate_id INTEGER PRIMARY KEY, name TEXT, name_ar TEXT,
      latitude REAL, longitude REAL, region TEXT);
    CREATE TABLE branches (
      branch_id INTEGER PRIMARY KEY, branch_name TEXT, governorate TEXT,
      latitude REAL, longitude REAL, licensed_beds INTEGER, opened_on TEXT);
    CREATE TABLE departments (
      department_id INTEGER PRIMARY KEY, division TEXT, department TEXT,
      unit TEXT, parent_department_id INTEGER, cost_centre TEXT,
      is_inpatient INTEGER);
    CREATE TABLE staff (
      staff_id INTEGER PRIMARY KEY, full_name TEXT, gender TEXT, job_family TEXT,
      job_title TEXT, grade TEXT, department_id INTEGER, branch_id INTEGER,
      reports_to INTEGER, hired_on TEXT, monthly_salary_egp REAL, is_active INTEGER);
    CREATE TABLE patients (
      patient_id INTEGER PRIMARY KEY, mrn TEXT, full_name TEXT, gender TEXT,
      birth_date TEXT, age_years INTEGER, governorate TEXT, latitude REAL,
      longitude REAL, blood_group TEXT, smoker INTEGER, bmi REAL,
      has_diabetes INTEGER, has_hypertension INTEGER, hcv_positive INTEGER,
      registered_on TEXT);
    CREATE TABLE appointments (
      appointment_id INTEGER PRIMARY KEY, patient_id INTEGER, department_id INTEGER,
      branch_id INTEGER, booked_on TEXT, scheduled_for TEXT, channel TEXT,
      status TEXT, wait_days INTEGER);
    CREATE TABLE encounters (
      encounter_id INTEGER PRIMARY KEY, patient_id INTEGER, branch_id INTEGER,
      department_id INTEGER, attending_staff_id INTEGER, encounter_type TEXT,
      admission_source TEXT, arrived_at TEXT, triage_at TEXT, admitted_at TEXT,
      discharged_at TEXT, triage_category TEXT, wait_minutes INTEGER,
      length_of_stay_days REAL, primary_icd10 TEXT, discharge_disposition TEXT,
      died INTEGER, readmitted_30d INTEGER, satisfaction_score INTEGER,
      total_cost_egp REAL);
    CREATE TABLE encounter_diagnoses (
      id INTEGER PRIMARY KEY, encounter_id INTEGER, icd10 TEXT, rank INTEGER);
    CREATE TABLE diagnoses_ref (
      icd10 TEXT PRIMARY KEY, description TEXT, description_ar TEXT,
      chronic INTEGER, chapter TEXT);
    CREATE TABLE procedures (
      procedure_id INTEGER PRIMARY KEY, encounter_id INTEGER, code TEXT,
      description TEXT, performed_at TEXT, theatre TEXT, surgeon_staff_id INTEGER,
      minutes INTEGER, cost_egp REAL);
    CREATE TABLE lab_results (
      lab_id INTEGER PRIMARY KEY, encounter_id INTEGER, patient_id INTEGER,
      test_code TEXT, test_name TEXT, panel TEXT, resulted_at TEXT, value REAL,
      unit TEXT, ref_low REAL, ref_high REAL, abnormal_flag TEXT,
      turnaround_minutes INTEGER);
    CREATE TABLE pharmacy_dispense (
      dispense_id INTEGER PRIMARY KEY, encounter_id INTEGER, drug_name TEXT,
      drug_class TEXT, dispensed_at TEXT, quantity INTEGER, unit_cost_egp REAL,
      line_cost_egp REAL, route TEXT);
    CREATE TABLE billing (
      invoice_id INTEGER PRIMARY KEY, encounter_id INTEGER, payer TEXT,
      payer_type TEXT, issued_on TEXT, gross_egp REAL, discount_egp REAL,
      net_egp REAL, paid_egp REAL, outstanding_egp REAL, status TEXT,
      days_to_payment INTEGER);
    CREATE TABLE bed_occupancy (
      id INTEGER PRIMARY KEY, census_date TEXT, branch_id INTEGER,
      department_id INTEGER, staffed_beds INTEGER, occupied_beds INTEGER,
      occupancy_pct REAL);
    CREATE TABLE referrals (
      referral_id INTEGER PRIMARY KEY, referred_on TEXT, from_facility TEXT,
      from_governorate TEXT, from_latitude REAL, from_longitude REAL,
      to_branch_id INTEGER, to_department_id INTEGER, patients INTEGER,
      accepted INTEGER);
    CREATE TABLE staff_shifts (
      shift_id INTEGER PRIMARY KEY, staff_id INTEGER, department_id INTEGER,
      shift_date TEXT, shift_start TEXT, shift_end TEXT, shift_type TEXT,
      hours REAL, overtime_hours REAL);
    CREATE TABLE infection_events (
      event_id INTEGER PRIMARY KEY, encounter_id INTEGER, department_id INTEGER,
      detected_on TEXT, organism TEXT, infection_type TEXT,
      multidrug_resistant INTEGER, isolation_days INTEGER);
    CREATE TABLE equipment (
      asset_id INTEGER PRIMARY KEY, asset_name TEXT, category TEXT,
      branch_id INTEGER, department_id INTEGER, purchased_on TEXT,
      value_egp REAL, uptime_pct REAL, last_service_on TEXT, status TEXT);
    """)

    # ── reference tables ─────────────────────────────────────────────────────
    REGION = {"Cairo": "Greater Cairo", "Giza": "Greater Cairo",
              "Qalyubia": "Greater Cairo", "Alexandria": "Delta & Coast"}
    for i, (n, ar, la, lo, _w) in enumerate(GOVERNORATES, 1):
        region = REGION.get(n, "Delta & Coast" if la > 29.5 else "Upper Egypt")
        c.execute("INSERT INTO governorates VALUES (?,?,?,?,?,?)",
                  (i, n, ar, la, lo, region))
    for b in BRANCHES:
        c.execute("INSERT INTO branches VALUES (?,?,?,?,?,?,?)",
                  b + (str(dt.date(1998 + b[0] * 3, 4, 12)),))
    for icd, en, ar, chronic, *_ in DIAGNOSES:
        chapter = {"E": "Endocrine", "I": "Circulatory", "J": "Respiratory",
                   "N": "Genitourinary", "K": "Digestive", "O": "Obstetric",
                   "C": "Neoplasm", "D": "Blood", "S": "Injury", "T": "Injury",
                   "A": "Infectious", "B": "Infectious", "P": "Perinatal",
                   "F": "Mental", "H": "Eye", "M": "Musculoskeletal"}[icd[0]]
        c.execute("INSERT INTO diagnoses_ref VALUES (?,?,?,?,?)",
                  (icd, en, ar, chronic, chapter))

    dept_rows, dept_id = [], 0
    dept_by_name = {}
    for division, depts in STRUCTURE.items():
        for department, units in depts.items():
            dept_id += 1
            parent = dept_id
            inpatient = int(division in ("Medical", "Surgical", "Critical Care",
                                         "Women & Children"))
            dept_rows.append((dept_id, division, department, None, None,
                              "CC-%04d" % (1000 + dept_id), inpatient))
            dept_by_name[department] = dept_id
            for unit in units:
                dept_id += 1
                dept_rows.append((dept_id, division, department, unit, parent,
                                  "CC-%04d" % (1000 + dept_id), inpatient))
    c.executemany("INSERT INTO departments VALUES (?,?,?,?,?,?,?)", dept_rows)
    unit_ids = [r[0] for r in dept_rows if r[3]]
    print("departments:", len(dept_rows), flush=True)

    # ── staff, with a real reporting line ────────────────────────────────────
    staff, sid = [], 0
    JOBS = [("Consultant", "Physician", 0.10, 95_000), ("Specialist", "Physician", 0.16, 48_000),
            ("Resident", "Physician", 0.18, 22_000), ("Head Nurse", "Nursing", 0.05, 26_000),
            ("Staff Nurse", "Nursing", 0.30, 15_500), ("Technician", "Allied Health", 0.10, 14_000),
            ("Pharmacist", "Pharmacy", 0.04, 24_000), ("Administrator", "Administration", 0.07, 18_000)]
    JOB_W = [j[2] for j in JOBS]
    sid += 1
    staff.append((sid, "Prof. Hesham El-Kholy", "M", "Executive", "Chief Executive Officer",
                  "Exec", dept_by_name["Internal Medicine"], 1, None,
                  str(dt.date(2011, 1, 9)), 210_000, 1))
    ceo = sid
    division_heads = {}
    for division in STRUCTURE:
        sid += 1
        g = random.choice("MF")
        name = "Dr. %s %s" % (random.choice(MALE if g == "M" else FEMALE),
                              random.choice(SURNAMES))
        staff.append((sid, name, g, "Executive", "Director, %s" % division, "Exec",
                      dept_by_name[list(STRUCTURE[division])[0]],
                      random.randint(1, 6), ceo, str(dt.date(2013, 6, 1)), 150_000, 1))
        division_heads[division] = sid
    dept_heads = {}
    for division, depts in STRUCTURE.items():
        for department in depts:
            sid += 1
            g = random.choice("MF")
            name = "Dr. %s %s" % (random.choice(MALE if g == "M" else FEMALE),
                                  random.choice(SURNAMES))
            staff.append((sid, name, g, "Physician", "Head of %s" % department,
                          "Consultant", dept_by_name[department],
                          random.randint(1, 6), division_heads[division],
                          str(dt.date(random.randint(2012, 2020), random.randint(1, 12), 15)),
                          120_000, 1))
            dept_heads[department] = sid
    while sid < 1800:
        sid += 1
        title, family, _w, base = pick(JOBS, JOB_W)
        g = random.choice("MF")
        first = random.choice(MALE if g == "M" else FEMALE)
        prefix = "Dr. " if family == "Physician" else ""
        unit = random.choice(unit_ids)
        dept_name = next(r[2] for r in dept_rows if r[0] == unit)
        staff.append((sid, "%s%s %s" % (prefix, first, random.choice(SURNAMES)), g,
                      family, title, title, unit, random.randint(1, 6),
                      dept_heads[dept_name],
                      str(dt.date(random.randint(2014, 2026), random.randint(1, 12),
                                  random.randint(1, 28))),
                      round(base * random.uniform(0.85, 1.3), 2),
                      1 if random.random() > 0.06 else 0))
    c.executemany("INSERT INTO staff VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", staff)
    doctors = [s[0] for s in staff if s[3] == "Physician"]
    print("staff:", len(staff), flush=True)

    # ── patients ─────────────────────────────────────────────────────────────
    patients = []
    for pid in range(1, N_PATIENTS + 1):
        g = "F" if random.random() < 0.52 else "M"
        first = random.choice(FEMALE if g == "F" else MALE)
        age = min(97, max(0, int(random.gammavariate(6.0, 7.2))))
        gov = pick(GOV_NAMES, GOV_W)
        gi = GOV_NAMES.index(gov)
        _, _, la, lo, _ = GOVERNORATES[gi]
        bmi = round(max(15.0, random.gauss(29.4, 5.6)), 1)
        diabetic = int(random.random() < (0.05 + 0.0075 * age + 0.011 * max(0, bmi - 25)))
        htn = int(random.random() < (0.04 + 0.0095 * age))
        hcv = int(random.random() < (0.006 + 0.0011 * age))
        birth = END - dt.timedelta(days=age * 365 + random.randint(0, 364))
        patients.append((
            pid, "MRN%07d" % pid, "%s %s" % (first, random.choice(SURNAMES)), g,
            str(birth), age, gov,
            round(la + random.gauss(0, 0.16), 5), round(lo + random.gauss(0, 0.16), 5),
            random.choices(["O+", "A+", "B+", "AB+", "O-", "A-", "B-", "AB-"],
                           [0.34, 0.30, 0.20, 0.07, 0.03, 0.03, 0.02, 0.01])[0],
            int(g == "M" and random.random() < 0.42), bmi, diabetic, htn, hcv,
            str(START - dt.timedelta(days=random.randint(0, 2500)))))
    c.executemany("INSERT INTO patients VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", patients)
    print("patients:", len(patients), flush=True)
    c.commit()

    # ── the daily activity curve every time-series widget draws ──────────────
    days = [START + dt.timedelta(days=i) for i in range(DAYS)]
    weights = [seasonal(d) for d in days]

    ED = dept_by_name["Emergency Department"]
    inpatient_depts = [r[0] for r in dept_rows if r[6] and r[3]]
    all_units = unit_ids

    # ── appointments — the top of the funnel ─────────────────────────────────
    appts = []
    for aid in range(1, N_APPOINTMENTS + 1):
        d = random.choices(days, weights=weights, k=1)[0]
        wait = max(0, int(skewed(9.0, 1.5)))
        booked = d - dt.timedelta(days=wait)
        r = random.random()
        status = ("attended" if r < 0.63 else
                  "no_show" if r < 0.79 else
                  "cancelled" if r < 0.92 else "rescheduled")
        appts.append((aid, random.randint(1, N_PATIENTS), random.choice(all_units),
                      random.randint(1, 6), str(booked), str(d),
                      random.choices(["call centre", "walk-in", "mobile app", "referral"],
                                     [0.42, 0.28, 0.22, 0.08])[0], status, wait))
    c.executemany("INSERT INTO appointments VALUES (?,?,?,?,?,?,?,?,?)", appts)
    print("appointments:", len(appts), flush=True)
    del appts
    c.commit()

    # ── encounters, and everything hanging off them ──────────────────────────
    enc, edx, procs, labs, pharm, bills, infections = [], [], [], [], [], [], []
    lab_id = disp_id = proc_id = inf_id = 0
    dx_lookup = {d[0]: d for d in DIAGNOSES}

    for eid in range(1, N_ENCOUNTERS + 1):
        pid = random.randint(1, N_PATIENTS)
        p = patients[pid - 1]
        age, bmi, diabetic, htn = p[5], p[11], p[12], p[13]
        day = random.choices(days, weights=weights, k=1)[0]
        icd = pick([d[0] for d in DIAGNOSES], DX_W)
        _, _, _, chronic, base_los, base_cost, _ = dx_lookup[icd]

        etype = random.choices(["emergency", "inpatient", "outpatient", "day case"],
                               [0.29, 0.24, 0.35, 0.12])[0]
        dept = ED if etype == "emergency" else random.choice(
            inpatient_depts if etype in ("inpatient", "day case") else all_units)

        arrive = dt.datetime.combine(day, dt.time(0, 0)) + dt.timedelta(
            minutes=int(random.triangular(0, 1439, 620)))
        triage_cat = random.choices(["1 Immediate", "2 Very urgent", "3 Urgent",
                                     "4 Standard", "5 Non-urgent"],
                                    [0.04, 0.12, 0.31, 0.36, 0.17])[0]
        base_wait = {"1": 3, "2": 14, "3": 46, "4": 88, "5": 132}[triage_cat[0]]
        wait = max(1, int(random.gauss(base_wait, base_wait * 0.45)))
        triage = arrive + dt.timedelta(minutes=min(wait, 20))

        # length of stay rises with age, obesity, diabetes and the diagnosis
        los = 0.0
        if etype in ("inpatient", "emergency"):
            los = skewed(base_los * (1 + 0.010 * max(0, age - 45)
                                     + 0.16 * diabetic + 0.010 * max(0, bmi - 28)))
            los = round(min(los, 92.0), 2)
        admitted = arrive + dt.timedelta(minutes=wait) if los > 0 else None
        discharged = (admitted + dt.timedelta(days=los)) if admitted else None

        mortality = min(0.30, 0.002 + 0.00035 * max(0, age - 40) ** 1.35
                        + (0.04 if icd in ("I21", "I63", "C34", "K74") else 0))
        died = int(random.random() < mortality)
        disposition = ("died" if died else
                       random.choices(["home", "home with follow-up", "transferred",
                                       "discharged against advice"],
                                      [0.62, 0.29, 0.06, 0.03])[0])
        readmit = int(not died and random.random() < (0.055 + 0.05 * chronic))
        cost = round(base_cost * (0.55 + 0.62 * random.random())
                     * (1 + 0.055 * los) * random.uniform(0.9, 1.2), 2)
        satisfaction = max(1, min(10, int(random.gauss(
            8.4 - 0.02 * wait / 10 - 1.6 * died, 1.5))))

        enc.append((eid, pid, random.randint(1, 6), dept, random.choice(doctors),
                    etype, random.choices(["walk-in", "ambulance", "referral",
                                           "transfer", "scheduled"],
                                          [0.44, 0.13, 0.19, 0.05, 0.19])[0],
                    arrive.isoformat(sep=" "), triage.isoformat(sep=" "),
                    admitted.isoformat(sep=" ") if admitted else None,
                    discharged.isoformat(sep=" ") if discharged else None,
                    triage_cat, wait, los, icd, disposition, died, readmit,
                    satisfaction, cost))

        edx.append((None, eid, icd, 1))
        for extra in range(random.choices([0, 1, 2, 3], [0.34, 0.36, 0.22, 0.08])[0]):
            edx.append((None, eid, pick([d[0] for d in DIAGNOSES], DX_W), extra + 2))

        if random.random() < 0.32:
            code, desc, pcost, _dept = random.choice(PROCEDURES)
            proc_id += 1
            procs.append((proc_id, eid, code, desc,
                          (admitted or arrive).isoformat(sep=" "),
                          "Theatre %d" % random.randint(1, 12),
                          random.choice(doctors),
                          max(15, int(random.gauss(95, 55))),
                          round(pcost * random.uniform(0.85, 1.25), 2)))

        for _ in range(random.choices([0, 2, 4, 7, 12], [0.22, 0.26, 0.24, 0.19, 0.09])[0]):
            code, tname, unit, lo_r, hi_r, mean, sd, panel = random.choice(LAB_TESTS)
            v = random.gauss(mean, sd)
            if code == "HBA1C" and diabetic: v += 2.1
            if code == "GLU" and diabetic:   v += 58
            if code == "CREA" and icd == "N18": v += 2.4
            if code == "ALT" and p[14]:      v += 34          # HCV positive
            v = round(max(0.01, v), 2)
            flag = "L" if v < lo_r else ("H" if v > hi_r else "N")
            lab_id += 1
            labs.append((lab_id, eid, pid, code, tname, panel,
                         (arrive + dt.timedelta(minutes=random.randint(20, 2400)))
                         .isoformat(sep=" "), v, unit, lo_r, hi_r, flag,
                         max(8, int(skewed(74, 1.6)))))

        for _ in range(random.choices([0, 1, 2, 4, 6], [0.28, 0.24, 0.22, 0.17, 0.09])[0]):
            dname, dclass, ucost = random.choice(DRUGS)
            qty = random.randint(1, 30)
            disp_id += 1
            pharm.append((disp_id, eid, dname, dclass,
                          (admitted or arrive).isoformat(sep=" "), qty, ucost,
                          round(qty * ucost, 2),
                          random.choices(["oral", "IV", "IM", "inhaled", "topical"],
                                         [0.55, 0.30, 0.07, 0.05, 0.03])[0]))

        payer, ptype, _w = pick(PAYERS, PAYER_W)
        discount = round(cost * (0.32 if ptype == "government" else
                                 0.10 if ptype in ("corporate", "syndicate") else
                                 0.04 if ptype == "private" else 0.0), 2)
        net = round(cost - discount, 2)
        pay_ratio = (1.0 if ptype == "cash" else random.choices(
            [1.0, random.uniform(0.55, 0.95), 0.0], [0.58, 0.32, 0.10])[0])
        paid = round(net * pay_ratio, 2)
        bills.append((eid, eid, payer, ptype,
                      (discharged or arrive).date().isoformat(), cost, discount, net,
                      paid, round(net - paid, 2),
                      "paid" if paid >= net - 1 else ("partial" if paid > 0 else "unpaid"),
                      max(0, int(skewed(38, 1.4))) if ptype != "cash" else 0))

        if los > 3 and random.random() < 0.031:
            inf_id += 1
            organism, itype = random.choice([
                ("Klebsiella pneumoniae", "Bloodstream"), ("E. coli", "Urinary"),
                ("Acinetobacter baumannii", "Respiratory"), ("MRSA", "Surgical site"),
                ("Pseudomonas aeruginosa", "Respiratory"), ("C. difficile", "Gastrointestinal")])
            infections.append((inf_id, eid, dept,
                               ((admitted or arrive) + dt.timedelta(days=random.randint(2, 9)))
                               .date().isoformat(), organism, itype,
                               int(random.random() < 0.38), random.randint(3, 21)))

        if len(enc) >= 20_000:
            _flush(c, enc, edx, procs, labs, pharm, bills, infections)
            enc, edx, procs, labs, pharm, bills, infections = [], [], [], [], [], [], []
            print("  encounters written:", eid, flush=True)

    _flush(c, enc, edx, procs, labs, pharm, bills, infections)
    c.commit()

    # ── daily bed census ─────────────────────────────────────────────────────
    occ, oid = [], 0
    for d in days:
        for b in range(1, 7):
            for dept in random.sample(inpatient_depts, 12):
                staffed = random.randint(8, 60)
                pct = min(1.08, max(0.28, random.gauss(0.82 * seasonal(d), 0.13)))
                oid += 1
                occ.append((oid, d.isoformat(), b, dept, staffed,
                            int(staffed * pct), round(pct * 100, 1)))
    c.executemany("INSERT INTO bed_occupancy VALUES (?,?,?,?,?,?,?)", occ)
    print("bed_occupancy:", len(occ), flush=True)

    # ── referrals: the network and the flow map ──────────────────────────────
    CLINICS = ["Al-Salam Clinic", "El-Nasr Health Unit", "Dar El-Hekma Centre",
               "El-Amal Polyclinic", "Sidi Gaber Medical", "El-Horreya Centre",
               "Nile Family Practice", "El-Shorouk Clinic", "Bab El-Louk Unit",
               "El-Zahraa Centre", "Misr El-Gedida Clinic", "Helwan Health Unit"]
    refs = []
    for rid in range(1, 12_000):
        gov = pick(GOV_NAMES, GOV_W)
        gi = GOV_NAMES.index(gov)
        refs.append((rid, random.choices(days, weights=weights, k=1)[0].isoformat(),
                     random.choice(CLINICS), gov,
                     round(GOVERNORATES[gi][2] + random.gauss(0, 0.12), 5),
                     round(GOVERNORATES[gi][3] + random.gauss(0, 0.12), 5),
                     random.randint(1, 6), random.choice(all_units),
                     random.randint(1, 9), int(random.random() < 0.84)))
    c.executemany("INSERT INTO referrals VALUES (?,?,?,?,?,?,?,?,?,?)", refs)
    print("referrals:", len(refs), flush=True)

    # ── rosters: what the schedule (Gantt) widget draws ──────────────────────
    shifts, shid = [], 0
    active = [s for s in staff if s[11]]
    for d in days[::2]:
        for s in random.sample(active, 90):
            shid += 1
            stype = random.choices(["Morning", "Evening", "Night"], [0.45, 0.33, 0.22])[0]
            start_h = {"Morning": 8, "Evening": 16, "Night": 0}[stype]
            ot = round(max(0.0, random.gauss(0.7, 1.1)), 1)
            shifts.append((shid, s[0], s[6], d.isoformat(),
                           "%02d:00" % start_h, "%02d:00" % ((start_h + 8) % 24),
                           stype, 8.0, ot))
    c.executemany("INSERT INTO staff_shifts VALUES (?,?,?,?,?,?,?,?,?)", shifts)
    print("staff_shifts:", len(shifts), flush=True)

    # ── assets ───────────────────────────────────────────────────────────────
    ASSETS = [("CT Scanner", "Imaging", 28_000_000), ("MRI 1.5T", "Imaging", 45_000_000),
              ("Ultrasound", "Imaging", 1_400_000), ("Ventilator", "Critical Care", 850_000),
              ("Dialysis Machine", "Renal", 620_000), ("Anaesthesia Machine", "Theatre", 1_100_000),
              ("Infusion Pump", "Ward", 45_000), ("Patient Monitor", "Ward", 180_000),
              ("C-Arm", "Theatre", 3_200_000), ("Lab Analyser", "Laboratory", 2_600_000)]
    eq = []
    for aid in range(1, 1_201):
        name, cat, val = random.choice(ASSETS)
        bought = END - dt.timedelta(days=random.randint(60, 3600))
        eq.append((aid, name, cat, random.randint(1, 6), random.choice(all_units),
                   bought.isoformat(), round(val * random.uniform(0.8, 1.15), 2),
                   round(min(100.0, max(52.0, random.gauss(94.5, 6.0))), 1),
                   (END - dt.timedelta(days=random.randint(1, 400))).isoformat(),
                   random.choices(["in service", "under maintenance", "awaiting parts",
                                   "decommissioned"], [0.86, 0.07, 0.04, 0.03])[0]))
    c.executemany("INSERT INTO equipment VALUES (?,?,?,?,?,?,?,?,?,?)", eq)

    for stmt in ("CREATE INDEX ix_enc_dept ON encounters(department_id)",
                 "CREATE INDEX ix_enc_pat ON encounters(patient_id)",
                 "CREATE INDEX ix_lab_enc ON lab_results(encounter_id)",
                 "CREATE INDEX ix_bill_enc ON billing(encounter_id)"):
        c.execute(stmt)
    c.commit()

    print("\nrow counts:")
    for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        print("  %-22s %9d" % (t, c.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]))
    c.close()
    print("\nfile: %.1f MB" % (os.path.getsize(OUT) / 1e6))


def _flush(c, enc, edx, procs, labs, pharm, bills, infections):
    c.executemany("INSERT INTO encounters VALUES (%s)" % ",".join("?" * 20), enc)
    c.executemany("INSERT INTO encounter_diagnoses VALUES (?,?,?,?)", edx)
    c.executemany("INSERT INTO procedures VALUES (?,?,?,?,?,?,?,?,?)", procs)
    c.executemany("INSERT INTO lab_results VALUES (%s)" % ",".join("?" * 13), labs)
    c.executemany("INSERT INTO pharmacy_dispense VALUES (?,?,?,?,?,?,?,?,?)", pharm)
    c.executemany("INSERT INTO billing VALUES (%s)" % ",".join("?" * 12), bills)
    c.executemany("INSERT INTO infection_events VALUES (?,?,?,?,?,?,?,?)", infections)


main()
