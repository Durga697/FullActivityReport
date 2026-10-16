# Whizzard Admin Panel - User Activation Automation

Automated Python tool using **Selenium** to log into the Whizzard Admin Panel, identify eligible pending users, map Gross Pay to salary bands, and update personal, payout, and bank information.

---

## Features

- **Automated Authentication**: Securely logs into Whizzard Admin Panel using credentials from `.env`.
- **Gross Pay Parsing & Band Mapping**:
  - Automatically parses Gross Pay values from Ops Team Remarks (e.g. `20K`, `20000`, `MON-R(20000)`, `Gross pay-26000/-`).
  - Maps Gross Pay to corresponding Band numbers (`01` through `15`) based on configured pay range brackets.
- **Profile Field Unlocking & Auto-fill**:
  - Sets **Payouts Eligibility** to `Yes`.
  - Sets **Pan Aadhaar Linkage** to `Yes`.
  - Sets **Contract Staff** to `No`.
  - Fills mapped **Band** & **Gross Pay** in Payment Info.
- **Bank Information Update**: Opens and saves bank information without bank-document OCR verification.
- **Activation Finalization**:
  - Confirms updated status, executes approval checkmarks, and verifies `Completed` / `Activated` user state.
- **Safety Flags**:
  - `--dry-run`: Test navigation, parsing, and form filling without applying final changes.
  - `--headful`: Run browser with GUI visible (default is headless).
- **Audit Logging**: Maintains a CSV log (`activation_log.csv`) recording every user activation attempt and result.

---

## Setup Instructions

1. **Install Dependencies**:
   ```bash
   pip install selenium webdriver-manager python-dotenv
   ```

2. **Configure Environment Variables**:
   Copy `.env.example` to `.env` and configure credentials:
   ```env
   WHIZZARD_MOBILE=7658978951
   WHIZZARD_PASSWORD=zxcvbnm,.
   ```

---

## Usage

### Run in Dry-Run Mode (Safe Testing)
```bash
python whizzard_activation.py --dry-run
```

### Run in Headful / Visible GUI Mode
```bash
python whizzard_activation.py --headful
```

### Run Production Automation
```bash
python whizzard_activation.py
```

---

## File Structure

- `whizzard_activation.py`: Main user activation automation script.
- `.env`: Local credentials & API keys (ignored by Git).
- `.env.example`: Template for credentials.
- `.gitignore`: Git exclusion configuration.
- `activation_log.csv`: Generated audit log file.
- `README.md`: Documentation and instructions.
