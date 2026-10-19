#!/usr/bin/env python3
"""
Whizzard Admin Panel - Pending Users Super User Remarks Automation
===================================================================
Automates checking 'Pending' user profiles on the Whizzard Admin Panel and
applying standardized 'Super User Remarks' based on specific missing profile fields.

Requirements:
- Python 3.10+
- Selenium, webdriver-manager, python-dotenv
- Standardized Remark Rules matching exact frozensets of missing fields.

Author: Antigravity AI
"""

import argparse
import csv
import datetime
import os
import re
import sys
import time
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Load environment variables from .env file
load_dotenv()

# --- MAPPING RULES ---
# Standardized Super User Remarks based on exact sets of profile missing fields.
REMARK_RULES = [
    (
        frozenset(["Missing Client Employee Id"]),
        "Kindly mention client employee id for user activation."
    ),
    (
        frozenset(["Missing Gross Pay"]),
        "Kindly mention gross pay for user activation."
    ),
    (
        frozenset(["Missing Payment Plan"]),
        "Kindly mention payment plan for user activation."
    ),
    (
        frozenset(["Missing Client Employee Id", "Missing Payment Plan"]),
        "Kindly mention client employee id & payment plan for user activation."
    ),
    (
        frozenset(["Missing Bank Details", "Missing Bank Proof Photo", "Missing Payment Plan"]),
        "Kindly upload bank details and docs also mention payment plan for user activation."
    ),
    (
        frozenset(["Missing Bank Details", "Missing Bank Proof Photo", "Missing Gross Pay"]),
        "Kindly upload bank details and docs also mention gross pay for user activation."
    ),
    (
        frozenset(["Missing Bank Details", "Missing Bank Proof Photo"]),
        "Kindly upload bank details and docs for user activation."
    ),
]

LOG_CSV_PATH = "processed_log.csv"


def get_remark_text_for_missing_fields(missing_fields_list):
    """
    Returns the mapped Super User Remark text for missing fields using a hierarchical rule engine.

    Rules Hierarchy:
    1. > 7 missing fields -> "Kindly complete all fields for user activation."
    2. Bank Details + Bank Proof Photo + Gross Pay -> "Kindly upload bank details and docs also mention gross pay for user activation."
    3. Bank Details + Bank Proof Photo + Payment Plan -> "Kindly upload bank details and docs also mention payment plan for user activation."
    4. Bank Details + Bank Proof Photo -> "Kindly upload bank details and docs for user activation."
    5. Client Employee Id & Payment Plan -> "Kindly mention client employee id & payment plan for user activation."
    6. Client Employee Id (with or without BGV/minor fields) -> "Kindly mention client employee id for user activation."
    7. Gross Pay (+ minor non-critical fields) -> "Kindly mention gross pay for user activation."
    8. Payment Plan (+ minor non-critical fields) -> "Kindly mention payment plan for user activation."
    """
    normalized_list = [item.strip() for item in missing_fields_list if item.strip()]
    if not normalized_list:
        return None

    # Rule 1: Condition for > 7 missing fields
    if len(normalized_list) > 7:
        return "Kindly complete all fields for user activation."

    s = set(normalized_list)

    # Minor/Ignorable fields that don't alter the primary action rule
    minor_fields = {
        "Missing Profile Pic",
        "Missing Emergency Contact Number",
        "User Number And Emergency Contact Number Are Same",
        "Missing Family Details",
        "Missing Landmark",
        "Missing Pin Code",
    }

    bgv_fields = {
        "Missing BGV Verification Picture",
        "Missing BGV Status",
        "Missing BGV Verification Id",
    }

    core_fields = s - minor_fields

    # Rule 2: Bank Details + Bank Proof Photo + Gross Pay
    if {"Missing Bank Details", "Missing Bank Proof Photo", "Missing Gross Pay"}.issubset(s):
        return "Kindly upload bank details and docs also mention gross pay for user activation."

    # Rule 3: Bank Details + Bank Proof Photo + Payment Plan
    if {"Missing Bank Details", "Missing Bank Proof Photo", "Missing Payment Plan"}.issubset(s):
        return "Kindly upload bank details and docs also mention payment plan for user activation."

    # Rule 4: Bank Details + Bank Proof Photo (without Gross Pay or Payment Plan)
    if {"Missing Bank Details", "Missing Bank Proof Photo"}.issubset(s) and not ("Missing Gross Pay" in s or "Missing Payment Plan" in s):
        return "Kindly upload bank details and docs for user activation."

    # Rule 5: Client Employee Id & Payment Plan
    if "Missing Client Employee Id" in s and "Missing Payment Plan" in s:
        return "Kindly mention client employee id & payment plan for user activation."

    # Rule 6: Client Employee Id (with or without BGV / minor fields)
    if "Missing Client Employee Id" in s:
        return "Kindly mention client employee id for user activation."

    # Rule 7: Gross Pay (+ minor non-critical fields)
    if "Missing Gross Pay" in s and (core_fields == {"Missing Gross Pay"} or (core_fields - bgv_fields) == {"Missing Gross Pay"}):
        return "Kindly mention gross pay for user activation."

    # Rule 8: Payment Plan (+ minor non-critical fields)
    if "Missing Payment Plan" in s and (core_fields == {"Missing Payment Plan"} or (core_fields - bgv_fields) == {"Missing Payment Plan"}):
        return "Kindly mention payment plan for user activation."

    # Fallback exact matches
    normalized_set = frozenset(normalized_list)
    for required_set, remark_text in REMARK_RULES:
        if normalized_set == required_set:
            return remark_text

    return None


def init_csv_log():
    """Ensures processed_log.csv exists with proper headers."""
    if not os.path.exists(LOG_CSV_PATH):
        with open(LOG_CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Timestamp",
                "Profile Name",
                "Mobile",
                "Missing Fields",
                "Applied Remark",
                "Status",
                "Is Dry Run"
            ])


def has_remark_from_date(existing_remark_text, target_date=None):
    """
    Checks if existing_remark_text contains a remark dated on target_date (default: today's date YYYY-MM-DD).
    Supports multiple date formats (YYYY-MM-DD, YYYY/MM/DD, DD-MM-YYYY).
    """
    if not existing_remark_text or existing_remark_text.lower() == "no remarks":
        return False

    if target_date is None:
        target_date = datetime.date.today()
    elif isinstance(target_date, str):
        target_date = datetime.datetime.strptime(target_date, "%Y-%m-%d").date()

    date_patterns = [
        target_date.strftime("%Y-%m-%d"),  # e.g., 2026-09-17
        target_date.strftime("%Y/%m/%d"),  # e.g., 2026/09/17
        target_date.strftime("%d-%m-%Y"),  # e.g., 17-09-2026
        target_date.strftime("%d/%m/%Y"),  # e.g., 17/09/2026
    ]

    for pat in date_patterns:
        if pat in existing_remark_text:
            return True

    return False


def is_already_logged(mobile, profile_name, target_date_str=None):
    """
    Checks if a profile has already been processed in processed_log.csv with an applied remark on target_date_str (default: today's date YYYY-MM-DD).
    """
    if not os.path.exists(LOG_CSV_PATH):
        return False

    if target_date_str is None:
        target_date_str = datetime.date.today().strftime("%Y-%m-%d")

    with open(LOG_CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row_timestamp = row.get("Timestamp", "")
            if not row_timestamp.startswith(target_date_str):
                continue

            status = row.get("Status", "")
            if "REMARK_APPLIED" in status or "SUCCESS" in status:
                if row.get("Mobile") and row["Mobile"] != "Unknown" and row["Mobile"] == mobile:
                    return True
                elif row.get("Profile Name") and row["Profile Name"] == profile_name and profile_name != "Unknown":
                    return True
    return False


def append_csv_log(profile_name, mobile, missing_fields, remark, status, is_dry_run):
    """Appends an audit record to processed_log.csv."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fields_str = "; ".join(missing_fields) if isinstance(missing_fields, (list, set, tuple)) else str(missing_fields)
    
    with open(LOG_CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            timestamp,
            profile_name,
            mobile,
            fields_str,
            remark or "",
            status,
            "YES" if is_dry_run else "NO"
        ])


def wait_loader(driver, timeout=15):
    """Waits for Angular loading spinner (#loader-wrapper) to disappear."""
    try:
        WebDriverWait(driver, timeout).until(
            EC.invisibility_of_element_located((By.ID, "loader-wrapper"))
        )
    except Exception:
        pass


def run_automation(dry_run=False, headless=True):
    """Main execution workflow for Whizzard Super User Remarks automation."""
    mobile = os.environ.get("WHIZZARD_MOBILE")
    password = os.environ.get("WHIZZARD_PASSWORD")

    if not mobile or not password:
        print("[ERROR] Credentials missing! WHIZZARD_MOBILE and WHIZZARD_PASSWORD must be set in environment or .env file.")
        sys.exit(1)

    print("==================================================================")
    print("      WHIZZARD PENDING USERS SUPER USER REMARKS AUTOMATION       ")
    print("==================================================================")
    print(f"Mode: {'[DRY RUN]' if dry_run else '[LIVE EXECUTION]'}")
    print(f"Browser Mode: {'[HEADLESS]' if headless else '[HEADFUL / GUI]'}")
    print(f"Target URL: https://adminpanel.whizzard.in/#/login")
    print(f"Mobile Account: {mobile}")
    print("==================================================================\n")

    init_csv_log()

    # Configure Chrome Webdriver
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    wait = WebDriverWait(driver, 20)

    try:
        # Step 1: Login
        print("[STEP 1] Navigating to login page...")
        driver.get("https://adminpanel.whizzard.in/#/login")
        time.sleep(2)

        print("[STEP 1] Entering credentials...")
        mobile_input = wait.until(EC.presence_of_element_located((By.ID, "phoneNumber")))
        password_input = driver.find_element(By.ID, "password")

        mobile_input.clear()
        mobile_input.send_keys(mobile)
        password_input.clear()
        password_input.send_keys(password)

        login_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Login') or contains(., 'Login')]")
        login_btn.click()
        wait_loader(driver)
        time.sleep(3)

        print(f"[STEP 1] Successfully logged in! Current URL: {driver.current_url}")

        # Step 2 & 3: Navigate via Sidebar to Onboarding -> Search Users
        print("\n[STEP 2] Navigating to Onboarding -> Search Users...")
        try:
            onboarding_els = driver.find_elements(By.XPATH, "//*[contains(text(), 'Onboarding')]")
            if not onboarding_els or not onboarding_els[0].is_displayed():
                hamburger = driver.find_element(By.XPATH, "//button[contains(@class, 'navbar-toggler')] | //header//i | //button[span[contains(@class, 'navbar-toggler')]]")
                hamburger.click()
                time.sleep(1)
        except Exception as e:
            print(f"[NOTE] Sidebar check notice: {e}")

        onboarding_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Onboarding')]")))
        onboarding_btn.click()
        time.sleep(1)

        search_users_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Search Users')]")))
        search_users_btn.click()
        wait_loader(driver)
        time.sleep(2)

        # Step 4: Switch to Pending Tab
        print("[STEP 3] Switching to 'Pending' tab...")
        pending_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Pending') or contains(., 'Pending')] | //button[contains(text(), 'Pending')] | //li[contains(., 'Pending')]")))
        driver.execute_script("arguments[0].click();", pending_tab)
        wait_loader(driver)
        time.sleep(3)

        # Step 5: Select Maximum Page Size (e.g. 106 / 108 / Highest option in pull-right pagination)
        print("[STEP 4] Selecting maximum page size pagination...")
        try:
            # Locate pull-right pagination list items
            pull_right_lis = driver.find_elements(By.XPATH, "//ul[contains(@class, 'pull-right')]//li")
            if not pull_right_lis:
                # Fallback: look for second pagination list on page
                pag_uls = driver.find_elements(By.XPATH, "//ul[contains(@class, 'pagination')]")
                if len(pag_uls) >= 2:
                    pull_right_lis = pag_uls[-1].find_elements(By.TAG_NAME, "li")

            if pull_right_lis:
                opts_summary = [l.text.strip().replace("\n", " ") for l in pull_right_lis]
                print(f"[STEP 4] Available page size options: {opts_summary}")
                
                # Target the last pagination option (highest count option like 106 / 108)
                target_li = pull_right_lis[-1]
                target_text = target_li.text.strip().replace("\n", " ")
                print(f"[STEP 4] Clicking highest page size option: '{target_text}'")

                link_inside = target_li.find_elements(By.TAG_NAME, "a")
                btn_to_click = link_inside[0] if link_inside else target_li
                driver.execute_script("arguments[0].scrollIntoView(true);", btn_to_click)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", btn_to_click)
                wait_loader(driver)
                time.sleep(4)
            else:
                print("[STEP 4] Could not locate pull-right pagination items, proceeding with current view.")
        except Exception as e:
            print(f"[NOTE] Could not adjust page size: {e}")

        # Step 6: Process Profile Cards / Table Rows Across All Pages
        processed_count = 0
        skipped_remarked_count = 0
        skipped_unmapped_count = 0
        remark_applied_count = 0
        current_page_num = 1

        while True:
            rows = driver.find_elements(By.XPATH, "//tbody/tr")
            total_profiles_on_page = len(rows)
            print(f"\n[STEP 5] [Page #{current_page_num}] Found {total_profiles_on_page} pending profiles on this page. Processing...\n")

            for idx in range(total_profiles_on_page):
                # Re-query rows to avoid stale element references
                rows = driver.find_elements(By.XPATH, "//tbody/tr")
                if idx >= len(rows):
                    break
                
                row = rows[idx]
                tds = row.find_elements(By.TAG_NAME, "td")
                if len(tds) < 5:
                    continue

                processed_count += 1
                col0 = tds[0]
                col2_missing = tds[2]
                col4_remark = tds[4]

                # Parse Name & Mobile Number
                col0_text = col0.text
                name_match = re.search(r'Name:\s*([^\n]+)', col0_text)
                profile_name = name_match.group(1).strip() if name_match else "Unknown Name"

                mob_match = re.search(r'Mobile:\s*(\d{10})', col0_text, re.I)
                if not mob_match:
                    mob_match = re.search(r'\b\d{10}\b', col0_text)
                mobile_num = mob_match.group(1) if mob_match and mob_match.groups() else (mob_match.group(0) if mob_match else "Unknown Mobile")

                # Parse Missing Fields Bullet List
                missing_li_els = col2_missing.find_elements(By.TAG_NAME, "li")
                missing_fields = [li.text.strip() for li in missing_li_els if li.text.strip()]

                # Parse Existing Super User Remark
                existing_remark_text = col4_remark.text.strip()

                print(f"------------------------------------------------------------------")
                print(f"Profile #{idx+1:03d}/{total_profiles_on_page} (Overall #{processed_count}) | Name: {profile_name} | Mobile: {mobile_num}")
                print(f"Missing Fields: {missing_fields}")

                # Check Safety Net 1: Check if Super User Remark was ALREADY applied TODAY (Same Date)
                if has_remark_from_date(existing_remark_text):
                    status = "SKIPPED — Remark Already Present for Today (Same Date)"
                    print(f"[SKIP] {status}")
                    print(f"       Existing Remark Today: {existing_remark_text[:100]}...")
                    skipped_remarked_count += 1
                    append_csv_log(profile_name, mobile_num, missing_fields, existing_remark_text, status, dry_run)
                    continue

                # Check Safety Net 2: Check if processed TODAY in CSV log
                if is_already_logged(mobile_num, profile_name):
                    status = "SKIPPED — Previously Processed Today in CSV Log"
                    print(f"[SKIP] {status}")
                    skipped_remarked_count += 1
                    append_csv_log(profile_name, mobile_num, missing_fields, None, status, dry_run)
                    continue

                # Check Rule Mapping
                mapped_remark = get_remark_text_for_missing_fields(missing_fields)
                if not mapped_remark:
                    status = "SKIPPED — Unmapped Missing Field Pattern"
                    print(f"[SKIP] {status}")
                    skipped_unmapped_count += 1
                    append_csv_log(profile_name, mobile_num, missing_fields, None, status, dry_run)
                    continue

                # Mapped Rule Matched! Apply Remark via Modal
                print(f"[ACTION] Mapped Remark Found: '{mapped_remark}'")

                try:
                    pencil_btn = None
                    try:
                        pencil_btn = col4_remark.find_element(By.XPATH, ".//button | .//i[contains(@class, 'fa-pencil')]")
                    except Exception:
                        pencil_btn = col0.find_element(By.XPATH, ".//button[contains(@class, 'btn-outline-primary') or .//i[contains(@class, 'fa-pencil')]]")

                    btn_to_click = pencil_btn if pencil_btn.tag_name == "button" else pencil_btn.find_element(By.XPATH, "..")
                    driver.execute_script("arguments[0].click();", btn_to_click)
                    time.sleep(2)

                    # Wait for Super User Remark Modal
                    modal = wait.until(EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'modal-content')] | //div[contains(@class, 'modal-dialog')]")))
                    textarea = modal.find_element(By.TAG_NAME, "textarea")

                    textarea.clear()
                    textarea.send_keys(mapped_remark)
                    time.sleep(1)

                    if dry_run:
                        status = "DRY RUN — Remark Formatted (Not Saved)"
                        print(f"[DRY RUN] Typed remark into modal but NOT clicking Save.")
                        close_btn = modal.find_element(By.XPATH, ".//button[contains(text(), 'Close') or contains(., 'Close')]")
                        driver.execute_script("arguments[0].click();", close_btn)
                        time.sleep(1)
                    else:
                        save_btn = modal.find_element(By.XPATH, ".//button[contains(text(), 'Save') or contains(., 'Save')]")
                        driver.execute_script("arguments[0].click();", save_btn)
                        wait_loader(driver)
                        time.sleep(2)
                        status = "SUCCESS — Remark Applied & Saved"
                        print(f"[SUCCESS] Remark saved successfully!")
                        remark_applied_count += 1

                    append_csv_log(profile_name, mobile_num, missing_fields, mapped_remark, status, dry_run)

                except Exception as e:
                    err_msg = f"ERROR applying remark: {e}"
                    print(f"[ERROR] {err_msg}")
                    append_csv_log(profile_name, mobile_num, missing_fields, mapped_remark, f"FAILED — {err_msg}", dry_run)

            # Pagination check: see if Next page button exists in left pagination (ul:not(.pull-right))
            try:
                next_btns = driver.find_elements(By.XPATH, "//ul[contains(@class, 'pagination') and not(contains(@class, 'pull-right'))]//li[not(contains(@class, 'disabled'))]/a[text()='>' or text()='»' or contains(text(), 'Next')]")
                if not next_btns:
                    next_btns = driver.find_elements(By.XPATH, f"//ul[contains(@class, 'pagination') and not(contains(@class, 'pull-right'))]//li[not(contains(@class, 'disabled'))]/a[text()='{current_page_num + 1}']")

                if next_btns and next_btns[0].is_displayed():
                    current_page_num += 1
                    print(f"\n[PAGINATION] Navigating to Next Page #{current_page_num}...")
                    driver.execute_script("arguments[0].click();", next_btns[0])
                    wait_loader(driver)
                    time.sleep(3)
                else:
                    print("\n[PAGINATION] All pages processed. Exiting pagination loop.")
                    break
            except Exception as e:
                print(f"[PAGINATION] End of pages reached or pagination error: {e}")
                break

        # Summary Report
        print("\n==================================================================")
        print("                      EXECUTION SUMMARY                          ")
        print("==================================================================")
        print(f"Total Profiles Visited          : {processed_count}")
        print(f"Skipped (Already Remarked/Logged): {skipped_remarked_count}")
        print(f"Skipped (Unmapped Patterns)     : {skipped_unmapped_count}")
        print(f"Remarks Applied & Saved         : {remark_applied_count}")
        print(f"Audit Log Saved To              : {os.path.abspath(LOG_CSV_PATH)}")
        print("==================================================================\n")

    finally:
        driver.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Whizzard Admin Panel Pending Users Super User Remarks Automation")
    parser.add_argument("--dry-run", action="store_true", help="Run automation in dry-run mode without saving remarks.")
    parser.add_argument("--headful", action="store_true", help="Run browser with visible GUI window (non-headless).")

    args = parser.parse_args()
    run_automation(dry_run=args.dry_run, headless=not args.headful)
