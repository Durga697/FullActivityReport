# Whizzard Admin Panel Automations

Automated Python tools using **Selenium** for managing user workflows on the Whizzard Admin Panel:
1. **User Activation Automation (`whizzard_activation.py`)**: Identifies eligible pending users, maps Gross Pay from remarks to salary bands, unlocks personal & payout details, and updates bank information.
2. **Super User Remarks Automation (`whizzard_remarks.py`)**: Evaluates pending users' missing profile fields and automatically applies standardized Super User Remarks based on pre-defined business rules.

---

## 1. User Activation Automation (`whizzard_activation.py`)

### Features
- **Gross Pay Parsing & Band Mapping**: Parses Gross Pay values from Ops Team Remarks (e.g. `20K`, `20000`, `MON-R(20000)`, `Gross pay-26000/-`) and maps them to Band numbers (`01` through `15`).
- **Profile Field Unlocking & Auto-fill**:
  - Sets **Payouts Eligibility** to `Yes`.
  - Sets **Pan Aadhaar Linkage** to `Yes`.
  - Sets **Contract Staff** to `No`.
  - Fills mapped **Band** & **Gross Pay** in Payment Info.
- **Bank Information Update**: Opens and saves bank details.
- **Audit Logging**: Maintains `activation_log.csv` recording each activation attempt.

### Usage
```bash
# Dry-run test (safe testing without saving)
python whizzard_activation.py --dry-run

# Run with visible browser GUI
python whizzard_activation.py --headful

# Run production automation (headless)
python whizzard_activation.py
```

---

## 2. Super User Remarks Automation (`whizzard_remarks.py`)

### Features
- **Standardized Rule Mapping**:
  - `> 7 Missing Fields` → `Kindly complete all fields for user activation.`
  - `Missing Bank Details`, `Missing Bank Proof Photo` & `Missing Gross Pay` → `Kindly upload bank details and docs also mention gross pay for user activation.`
  - `Missing Bank Details`, `Missing Bank Proof Photo` & `Missing Payment Plan` → `Kindly upload bank details and docs also mention payment plan for user activation.`
  - `Missing Bank Details` & `Missing Bank Proof Photo` → `Kindly upload bank details and docs for user activation.`
  - `Missing Client Employee Id` & `Missing Payment Plan` → `Kindly mention client employee id & payment plan for user activation.`
  - `Missing Client Employee Id` → `Kindly mention client employee id for user activation.`
  - `Missing Gross Pay` → `Kindly mention gross pay for user activation.`
  - `Missing Payment Plan` → `Kindly mention payment plan for user activation.`
- **Idempotent & Date-Aware**: Skips profiles if a remark was already applied today, preventing duplicate remarks.
- **Audit Logging**: Maintains `processed_log.csv` recording each profile visited, missing fields, remark applied, and status.

### Usage
```bash
# Dry-run test (format remarks without saving to server)
python whizzard_remarks.py --dry-run

# Run with visible browser GUI
python whizzard_remarks.py --dry-run --headful

# Run production automation (headless)
python whizzard_remarks.py
```

---

## Common Setup Instructions

1. **Install Dependencies**:
   ```bash
   pip install selenium webdriver-manager python-dotenv
   ```

2. **Configure Environment Variables**:
   Copy `.env.example` to `.env` and fill in credentials:
   ```env
   WHIZZARD_MOBILE=your_mobile_number
   WHIZZARD_PASSWORD=your_password
   ```

---

## Repository Structure

```
├── .env.example            # Environment variables template
├── .gitignore              # Git ignore rules (.env, logs, pycache)
├── README.md               # Repository documentation
├── whizzard_activation.py  # User activation automation script
└── whizzard_remarks.py     # Super user remarks automation script
```
