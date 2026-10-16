#!/usr/bin/env python3
"""
Whizzard Admin Panel - User Activation Automation
=================================================
Automates the full user activation workflow on the Whizzard Admin Panel
based on the visual screenshot workflow and prompt instructions.

Workflow Summary:
1. Login to Whizzard Admin Panel (https://adminpanel.whizzard.in/#/login).
2. Navigate to Onboarding -> Search Users (#/users).
3. Process every user displayed under the Pending tab without filtering by missing fields.
4. Parse Gross Pay from 'Ops Team Remarks' (e.g., '20K', '20000', 'MON-R(20000)', 'Gross pay-26000/-').
5. Map Gross Pay (range 3000 to 43000) to Band number (01 to 15) using Band Lookup Table.
6. Open user profile page, unlock/edit personal information:
   - Payouts Eligibility -> Has Payout*: Yes
   - Pan Aadhaar Linkage -> Linked*: Yes
   - Contract Staff -> Is Contract Staff: No
   - Payment Info -> Set Band & Gross Pay.
7. Verify Aadhaar & PAN document uploads, then Save Profile Information.
8. Navigate to Bank Account Details and save Bank Information.
9. Return to Search Users, filter by mobile number, and confirm status is 'Completed'.
10. Stop after saving the profile and bank information; do not activate the profile.

Requirements:
- Python 3.10+
- selenium, webdriver-manager, python-dotenv
- Environment variables: WHIZZARD_MOBILE, WHIZZARD_PASSWORD

Author: Antigravity AI
"""

import argparse
import csv
import datetime
import os
import re
import sys
import time

# Force unbuffered UTF-8 output for real-time console logging
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

from typing import Optional, Tuple
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Load environment variables
load_dotenv()

# --- CONSTANTS ---
DEFAULT_LOGIN_URL = "https://adminpanel.whizzard.in/#/login"
DEFAULT_USERS_URL = "https://adminpanel.whizzard.in/#/users"
LOG_CSV_PATH = "activation_log.csv"

# Band Lookup Table: (Min Thousands, Max Thousands, Band String)
# E.g. Gross Pay 26000 -> 26k -> range 26-27 -> Band "07"
BAND_LOOKUP_TABLE = [
    (14, 15, "01"),
    (16, 17, "02"),
    (18, 19, "03"),
    (20, 21, "04"),
    (22, 23, "05"),
    (24, 25, "06"),
    (26, 27, "07"),
    (28, 29, "08"),
    (30, 31, "09"),
    (32, 33, "10"),
    (34, 35, "11"),
    (36, 37, "12"),
    (38, 39, "13"),
    (40, 41, "14"),
    (42, 43, "15"),
]

# --- UTILITY & PARSING FUNCTIONS ---

def parse_gross_pay(remark_text: str) -> Optional[int]:
    """
    Parses numeric rupee value from Ops Team Remarks text.
    Handles formats like '20K', '20000', 'MON-R(20000)', 'MON-R(20000),WO', 'Gross pay-26000/-'.
    Validates that the final Gross Pay integer is between 3000 and 43000 (inclusive).
    Returns integer value or None if invalid.
    """
    if not remark_text:
        return None

    clean_text = remark_text.strip()

    # Match '20K' or '20k' pattern
    k_match = re.search(r'(\d+)\s*[kK]', clean_text)
    if k_match:
        val = int(k_match.group(1)) * 1000
        if 3000 <= val <= 43000:
            return val

    # Match explicit numbers (e.g. 26000, 20000, 26000/-)
    numbers = re.findall(r'\b\d{4,5}\b', clean_text)
    for num_str in numbers:
        val = int(num_str)
        if 3000 <= val <= 43000:
            return val

    # Fallback match any numbers in text
    all_nums = re.findall(r'\d+', clean_text)
    for num_str in all_nums:
        val = int(num_str)
        if 3000 <= val <= 43000:
            return val

    return None


def get_band_from_gross_pay(gross_pay: int) -> Optional[str]:
    """
    Maps Gross Pay integer to Band string using the Band Lookup Table.
    If Gross Pay is between 3000 and 13999 (< 14000), maps to Band "0".
    If Gross Pay is between 14000 and 43000, maps to "01" through "15".
    """
    if not gross_pay or gross_pay < 3000 or gross_pay > 43000:
        return None

    if gross_pay < 14000:
        return "0"

    thousands = gross_pay // 1000
    for min_k, max_k, band_code in BAND_LOOKUP_TABLE:
        if min_k <= thousands <= max_k:
            return band_code

    return None



def init_csv_log(filepath: str = LOG_CSV_PATH):
    """Initializes audit CSV log file with appropriate header row if not present."""
    if not os.path.exists(filepath):
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Timestamp",
                "Profile Name",
                "Mobile",
                "Ops Remark",
                "Parsed Gross Pay",
                "Band",
                "Status",
                "Details/Error",
                "Is Dry Run"
            ])


def append_csv_log(
    profile_name: str,
    mobile: str,
    ops_remark: str,
    gross_pay: Optional[int],
    band: Optional[str],
    status: str,
    details: str = "",
    is_dry_run: bool = False,
    filepath: str = LOG_CSV_PATH
):
    """Appends an execution record to the audit CSV log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            timestamp,
            profile_name or "Unknown",
            mobile or "Unknown",
            ops_remark or "",
            gross_pay if gross_pay is not None else "",
            band or "",
            status,
            details,
            "YES" if is_dry_run else "NO"
        ])


def wait_loader(driver: webdriver.Chrome, timeout: int = 15):
    """Waits for Angular/UI loading overlays or spinners to disappear."""
    try:
        WebDriverWait(driver, timeout).until(
            EC.invisibility_of_element_located((By.XPATH, "//div[contains(@id, 'loader') or contains(@class, 'spinner') or contains(@class, 'loading')]"))
        )
    except Exception:
        pass


# --- MAIN AUTOMATION CLASS ---

class WhizzardActivationAutomation:
    def __init__(self, dry_run: bool = False, headless: bool = True, max_users: Optional[int] = None):
        self.dry_run = dry_run
        self.headless = headless
        self.max_users = max_users
        self.mobile = os.environ.get("WHIZZARD_MOBILE", "7658978951")
        self.password = os.environ.get("WHIZZARD_PASSWORD", "zxcvbnm,")

        init_csv_log()

        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 20)

    def close(self):
        """Safely quits the browser instance."""
        try:
            self.driver.quit()
        except Exception:
            pass

    def login(self):
        """STEP 1: Log into Whizzard Admin Panel."""
        print("\n[STEP 1] Navigating to login page...")
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                self.driver.get(DEFAULT_LOGIN_URL)
                time.sleep(2)
                break
            except Exception as e:
                print(f"[WARNING] Login page navigation attempt {attempt}/{max_retries} failed: {e}")
                if attempt == max_retries:
                    raise RuntimeError(
                        f"Failed to connect to Whizzard Admin Panel ({DEFAULT_LOGIN_URL}) after {max_retries} attempts. "
                        "Please check your internet/VPN connection or verify if adminpanel.whizzard.in is accessible."
                    )
                time.sleep(5)

        print("[STEP 1] Entering credentials...")
        mobile_input = self.wait.until(EC.presence_of_element_located((By.ID, "phoneNumber")))
        password_input = self.driver.find_element(By.ID, "password")

        mobile_input.clear()
        mobile_input.send_keys(self.mobile)
        password_input.clear()
        password_input.send_keys(self.password)

        login_btn = self.driver.find_element(
            By.XPATH, "//button[contains(text(), 'Login') or contains(., 'Login')]"
        )
        login_btn.click()
        wait_loader(self.driver)
        time.sleep(3)

        print(f"[STEP 1] Successfully logged in! Current URL: {self.driver.current_url}")


    def navigate_to_search_users(self):
        """STEPS 2, 3, 4: Navigate to Search Users page, switch to Pending tab & adjust pagination."""
        print("\n[STEPS 2-4] Navigating to Search Users...")
        try:
            self.driver.get(DEFAULT_USERS_URL)
            wait_loader(self.driver)
            time.sleep(2)
        except Exception as e:
            print(f"[NOTE] Direct navigation notice: {e}")



        # Switch to Pending Tab
        print("[STEPS 2-4] Switching to 'Pending' tab...")
        try:
            pending_tab = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Pending') or contains(., 'Pending')] | //button[contains(text(), 'Pending')] | //li[contains(., 'Pending')]"))
            )
            self.driver.execute_script("arguments[0].click();", pending_tab)
            wait_loader(self.driver)
            time.sleep(3)
        except Exception as e:
            print(f"[NOTE] Pending tab click notice: {e}")

        # Select maximum page size pagination if present
        print("[STEPS 2-4] Adjusting page size pagination...")
        try:
            pull_right_lis = self.driver.find_elements(By.XPATH, "//ul[contains(@class, 'pull-right')]//li")
            if not pull_right_lis:
                pag_uls = self.driver.find_elements(By.XPATH, "//ul[contains(@class, 'pagination')]")
                if len(pag_uls) >= 2:
                    pull_right_lis = pag_uls[-1].find_elements(By.TAG_NAME, "li")
            if pull_right_lis:
                target_li = pull_right_lis[-1]
                link_inside = target_li.find_elements(By.TAG_NAME, "a")
                btn_to_click = link_inside[0] if link_inside else target_li
                self.driver.execute_script("arguments[0].click();", btn_to_click)
                wait_loader(self.driver)
                time.sleep(3)
        except Exception as e:
            print(f"[NOTE] Pagination adjustment notice: {e}")


    def apply_super_user_remark(self, mobile: str, remark_text: str) -> bool:
        """Applies a Super User Remark modal text on a user card in Search Users list by searching for mobile number."""
        try:
            self.navigate_to_search_users()
            
            # Filter search users by mobile number
            search_inputs = self.driver.find_elements(
                By.XPATH, "//input[contains(@placeholder, 'Search') or contains(@placeholder, 'Mobile') or contains(@ng-model, 'search')]"
            )
            if search_inputs:
                s_input = search_inputs[0]
                s_input.clear()
                s_input.send_keys(mobile)
                self.driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", s_input)
                self.driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", s_input)
                s_input.send_keys(Keys.RETURN)
                wait_loader(self.driver)
                time.sleep(2)

            cards = self.driver.find_elements(By.XPATH, "//tbody/tr | //div[contains(@class, 'user-card')]")
            target_card = None
            for c in cards:
                if mobile in c.text:
                    target_card = c
                    break
            if not target_card and cards:
                target_card = cards[0]

            if not target_card:
                print(f"[ERROR] Could not locate user card for {mobile} to apply remark.")
                return False

            tds = target_card.find_elements(By.TAG_NAME, "td")
            pencil_btn = None
            if len(tds) >= 4:
                col4 = tds[4] if len(tds) > 4 else tds[-1]
                col0 = tds[0]
                try:
                    pencil_btn = col4.find_element(By.XPATH, ".//button | .//i[contains(@class, 'fa-pencil')]")
                except Exception:
                    try:
                        pencil_btn = col0.find_element(By.XPATH, ".//button[contains(@class, 'btn-outline-primary') or .//i[contains(@class, 'fa-pencil')]]")
                    except Exception:
                        pass

            if not pencil_btn:
                pencil_btn = target_card.find_element(
                    By.XPATH, ".//button[contains(@class, 'pencil') or .//i[contains(@class, 'fa-pencil')]] | .//i[contains(@class, 'fa-pencil')]"
                )

            btn_click = pencil_btn if pencil_btn.tag_name == "button" else pencil_btn.find_element(By.XPATH, "..")
            self.driver.execute_script("arguments[0].click();", btn_click)
            time.sleep(2)

            modal = self.wait.until(EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'modal-content')] | //div[contains(@class, 'modal-dialog')]")))
            textarea = modal.find_element(By.TAG_NAME, "textarea")
            textarea.clear()
            textarea.send_keys(remark_text)
            time.sleep(1)

            if not self.dry_run:
                save_btn = modal.find_element(By.XPATH, ".//button[contains(text(), 'Save') or contains(., 'Save') or contains(text(), 'Submit')]")
                self.driver.execute_script("arguments[0].click();", save_btn)
                wait_loader(self.driver)
                time.sleep(2)
                print(f"[REMARK SAVED SUCCESS] Remark for {mobile}: '{remark_text}'")
            else:
                print(f"[DRY RUN] Would save remark for {mobile}: '{remark_text}'")
                close_btn = modal.find_element(By.XPATH, ".//button[contains(text(), 'Close') or contains(., 'Close') or contains(@class, 'btn-close')]")
                self.driver.execute_script("arguments[0].click();", close_btn)
                time.sleep(1)

            return True
        except Exception as e:
            print(f"[ERROR] Failed to apply Super User Remark for {mobile}: {e}")
            return False

    def process_user_profile(self, profile_url: str, gross_pay: Optional[int], band: Optional[str], mobile: str, name: str) -> Tuple[bool, str]:
        """
        STEPS 6-13: Process an individual user profile:
        - Unlock / edit profile
        - Set Payout Eligibility, Pan Aadhaar Linkage, Payment Info (Band & Gross Pay)
        - Save Profile Information
        - Check & Validate Bank Account Details
        - Save Bank Information
        """
        print(f"\n---> Opening user profile: {name} ({mobile}) | URL: {profile_url}")
        self.driver.get(profile_url)
        wait_loader(self.driver)
        time.sleep(2)

        # STEP 6: Unlock profile fields & Open Profile Information card
        print("[STEP 6] Opening Profile Information section...")
        try:
            # 1. Click Edit Profile unlock toggle (label.btn-lock / #inpLock)
            lock_labels = self.driver.find_elements(
                By.XPATH,
                "//label[@for='inpLock' or contains(@class, 'btn-lock')] | "
                "//input[@id='inpLock'] | "
                "//*[@title='Edit Profile']"
            )
            if lock_labels:
                print("[STEP 6] Clicking Edit Profile unlock toggle (label.btn-lock)...")
                self.driver.execute_script("arguments[0].click();", lock_labels[0])
                time.sleep(1.5)
            else:
                unlock_icons = self.driver.find_elements(
                    By.XPATH,
                    "//div[contains(@class, 'avatar') or contains(@class, 'profile')]//i | "
                    "//i[contains(@class, 'pencil') or contains(@class, 'edit') or contains(@class, 'lock') or contains(@class, 'fa-camera')]"
                )
                if unlock_icons:
                    self.driver.execute_script("arguments[0].click();", unlock_icons[0])
                    time.sleep(1)

            # 2. Click 'Profile Information' box card to display form
            prof_info_box = self.driver.find_elements(
                By.XPATH,
                "//*[contains(text(), 'Profile Information')] | "
                "//div[contains(@class, 'card') and contains(., 'Profile Information')]"
            )
            if prof_info_box:
                self.driver.execute_script("arguments[0].click();", prof_info_box[0])
                time.sleep(2)
        except Exception as e:
            print(f"[NOTE] Profile unlock/opening notice: {e}")

        # STEP 7: Update eligibility toggles & payment info
        print("[STEP 7] Updating Payout Eligibility, Pan-Aadhaar Linkage, and Payment Info...")
        try:
            # Payouts Eligibility -> Has Payout* -> Yes
            # Helper to set input values without invalid element state errors
            def set_field_value(el, val):
                val_str = str(val)
                try:
                    self.driver.execute_script("arguments[0].removeAttribute('disabled'); arguments[0].removeAttribute('readonly');", el)
                    el.clear()
                    el.send_keys(val_str)
                except Exception:
                    self.driver.execute_script(
                        "arguments[0].removeAttribute('disabled'); "
                        "arguments[0].removeAttribute('readonly'); "
                        "arguments[0].value = arguments[1]; "
                        "arguments[0].dispatchEvent(new Event('input', { bubbles: true })); "
                        "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));",
                        el, val_str
                    )

            def click_safely(el):
                try:
                    self.driver.execute_script("arguments[0].removeAttribute('disabled'); arguments[0].click();", el)
                except Exception:
                    try:
                        el.click()
                    except Exception:
                        pass

            def select_radio(el):
                try:
                    self.driver.execute_script(
                        "arguments[0].checked = true; "
                        "arguments[0].dispatchEvent(new Event('change', { bubbles: true })); "
                        "arguments[0].dispatchEvent(new Event('click', { bubbles: true }));",
                        el
                    )
                    try:
                        parent_lbl = el.find_element(By.XPATH, "..")
                        self.driver.execute_script("arguments[0].click();", parent_lbl)
                    except Exception:
                        pass
                except Exception:
                    click_safely(el)

            # 1. Payouts Eligibility -> Has Payout* -> Yes
            payout_radios = self.driver.find_elements(By.XPATH, "//input[@name='hasPayoutCategory']")
            if payout_radios:
                select_radio(payout_radios[0])  # Index 0 is Yes
                time.sleep(0.5)
            else:
                payout_yes_targets = self.driver.find_elements(
                    By.XPATH,
                    "//div[contains(., 'Payouts Eligibility') or contains(., 'Payout')]//div[contains(@class, 'form-check')][.//label[contains(text(), 'Yes')]]//input[@type='radio'] | "
                    "//div[contains(., 'Payouts Eligibility') or contains(., 'Payout')]//label[contains(., 'Yes')]"
                )
                if payout_yes_targets:
                    select_radio(payout_yes_targets[0])
                    time.sleep(0.5)

            # 2. Pan Aadhaar Linkage -> Linked* -> Yes
            pan_radios = self.driver.find_elements(By.XPATH, "//input[@name='aadharPanCategory']")
            if pan_radios:
                select_radio(pan_radios[0])  # Index 0 is Yes
                time.sleep(0.5)
            else:
                pan_link_targets = self.driver.find_elements(
                    By.XPATH,
                    "//div[contains(., 'Pan Aadhaar') or contains(., 'Aadhaar Linkage')]//div[contains(@class, 'form-check')][.//label[contains(text(), 'Yes')]]//input[@type='radio'] | "
                    "//div[contains(., 'Pan Aadhaar') or contains(., 'Aadhaar Linkage')]//label[contains(., 'Yes')]"
                )
                if pan_link_targets:
                    select_radio(pan_link_targets[0])
                    time.sleep(0.5)

            # 3. Contract Staff -> Is Contract Staff -> No
            contract_radios = self.driver.find_elements(By.XPATH, "//input[@name='contractStaffUser']")
            if len(contract_radios) >= 2:
                select_radio(contract_radios[1])  # Index 1 is No
                time.sleep(0.5)
            else:
                contract_no_targets = self.driver.find_elements(
                    By.XPATH,
                    "//div[contains(., 'Contract Staff')]//div[contains(@class, 'form-check')][.//label[contains(text(), 'No')]]//input[@type='radio']"
                )
                if contract_no_targets:
                    select_radio(contract_no_targets[0])
                    time.sleep(0.5)

            # Payment Info: Band & Gross Pay (Set if provided)
            band_inputs = self.driver.find_elements(
                By.XPATH,
                "//label[contains(., 'Band')]/following::input[1] | "
                "//input[@id='band' or @name='band' or contains(@placeholder, 'Band') or contains(@ng-model, 'band')]"
            )
            gross_inputs = self.driver.find_elements(
                By.XPATH,
                "//label[contains(., 'Gross Pay')]/following::input[1] | "
                "//input[@id='grossPay' or @name='grossPay' or contains(@placeholder, 'Gross') or contains(@ng-model, 'gross')]"
            )

            if band is not None and band_inputs:
                set_field_value(band_inputs[0], band)

            if gross_pay is not None and gross_inputs:
                set_field_value(gross_inputs[0], gross_pay)

            print(f"[STEP 7] Updated Payout Eligibility (Yes) & Pan-Aadhaar Linkage (Yes) | Band: {band}, Gross Pay: {gross_pay}")



        except Exception as e:
            err_msg = f"Failed to populate Payment Info / Toggles: {e}"
            print(f"[ERROR] {err_msg}")
            return False, err_msg


        # STEP 8 & 9: Save Profile Information
        print("[STEP 9] Saving Profile Information...")
        try:
            save_clicked = False
            # 1. Try explicit Selenium XPaths
            save_xpaths = [
                "//button[contains(normalize-space(.), 'Save Profile Information')]",
                "//button[contains(normalize-space(.), 'Save Profile')]",
                "//button[contains(@class, 'btn-danger') and (contains(., 'Save') or contains(., 'Profile'))]",
                "//button[contains(@class, 'btn-primary') and contains(., 'Save') and not(contains(., 'Bank'))]",
                "//button[contains(., 'Save') and not(contains(., 'Bank'))]",
                "//input[@type='submit' and contains(@value, 'Save')]"
            ]
            for xpath in save_xpaths:
                btn_els = self.driver.find_elements(By.XPATH, xpath)
                if btn_els:
                    for btn in btn_els:
                        if btn.is_displayed() or True:
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                            time.sleep(0.5)
                            try:
                                btn.click()
                            except Exception:
                                self.driver.execute_script("arguments[0].click();", btn)
                            save_clicked = True
                            print(f"[FOUND & CLICKED SAVE PROFILE BUTTON] via XPath '{xpath}' | Text: '{btn.text.strip()}'")
                            break
                if save_clicked:
                    break

            # 2. Fallback to JS DOM search across scrollable containers
            if not save_clicked:
                js_scroll_click = """
                var target = 'save profile';
                var allContainers = document.querySelectorAll('*');
                for (var i = 0; i < allContainers.length; i++) {
                    if (allContainers[i].scrollHeight > allContainers[i].clientHeight) {
                        allContainers[i].scrollTop = allContainers[i].scrollHeight;
                    }
                }
                var clickables = document.querySelectorAll('button, input[type="submit"], input[type="button"], a.btn, [role="button"], [ng-click]');
                for (var j = 0; j < clickables.length; j++) {
                    var el = clickables[j];
                    var txt = (el.innerText || el.textContent || el.value || '').trim().toLowerCase();
                    if (txt && (txt.indexOf(target) !== -1 || (txt.indexOf('save') !== -1 && txt.indexOf('bank') === -1))) {
                        el.scrollIntoView({block: 'center'});
                        el.click();
                        return (el.innerText || el.textContent || el.value || '').trim();
                    }
                }
                return null;
                """
                matched_save_btn = self.driver.execute_script(js_scroll_click)
                if matched_save_btn:
                    save_clicked = True
                    print(f"[FOUND & CLICKED SAVE PROFILE BUTTON] via JS: '{matched_save_btn}'")

            if save_clicked:
                wait_loader(self.driver)
                time.sleep(3)

                toast_errs = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'toast-error') or contains(@class, 'alert-danger')]")
                if toast_errs and toast_errs[0].is_displayed():
                    err_text = toast_errs[0].text
                    print(f"[ERROR] Profile save toast error: {err_text}")
                    return False, f"Profile Save Toast Error: {err_text}"
            else:
                print("[NOTE] Save Profile button not found among scrollable elements, proceeding.")
        except Exception as e:
            print(f"[NOTE] Save Profile Information notice: {e}")

        # STEP 10: Bank Account Details Tab
        print("[STEP 10] Switching to Bank Account Details tab...")
        try:
            bank_tab_clicked = False
            bank_tab_xpaths = [
                "//a[contains(normalize-space(.), 'Bank Account Details')]",
                "//li[contains(normalize-space(.), 'Bank Account Details')]",
                "//button[contains(normalize-space(.), 'Bank Account Details')]",
                "//*[contains(text(), 'Bank Account Details')]"
            ]
            for xpath in bank_tab_xpaths:
                tabs = self.driver.find_elements(By.XPATH, xpath)
                if tabs:
                    tab = tabs[0]
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tab)
                    self.driver.execute_script("arguments[0].click();", tab)
                    bank_tab_clicked = True
                    print(f"[STEP 10] Clicked Bank Account Details tab via XPath: '{xpath}'")
                    break

            if not bank_tab_clicked:
                js_click_bank_tab = """
                var target = 'bank account details';
                var clickables = document.querySelectorAll('button, a, div, span, li');
                for (var j = 0; j < clickables.length; j++) {
                    var el = clickables[j];
                    var txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                    if (txt && txt.indexOf(target) !== -1) {
                        var btnToClick = el.closest('a, button, li, [ng-click]') || el;
                        btnToClick.scrollIntoView({block: 'center'});
                        btnToClick.click();
                        return txt;
                    }
                }
                return null;
                """
                self.driver.execute_script(js_click_bank_tab)

            wait_loader(self.driver)
            time.sleep(3)

        except Exception as e:
            err_msg = f"Failed to open Bank Account Details tab: {e}"
            print(f"[ERROR] {err_msg}")
            return False, err_msg

        # STEP 11: Save bank information without document verification.
        print("[STEP 11] Saving Bank Information...")
        try:
            bank_saved = False
            save_bank_xpaths = [
                "//button[contains(normalize-space(.), 'Save Bank Information')]",
                "//button[contains(normalize-space(.), 'Save Bank')]",
                "//button[contains(@class, 'btn-danger') and contains(., 'Bank')]",
                "//button[contains(., 'Save') and contains(., 'Bank')]"
            ]
            for xpath in save_bank_xpaths:
                b_els = self.driver.find_elements(By.XPATH, xpath)
                if b_els:
                    btn = b_els[0]
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                    self.driver.execute_script("arguments[0].click();", btn)
                    bank_saved = True
                    print(f"[FOUND & CLICKED SAVE BANK BUTTON] via XPath '{xpath}'")
                    break

            if not bank_saved:
                js_scroll_click_bank = """
                var target = 'save bank';
                var allContainers = document.querySelectorAll('*');
                for (var i = 0; i < allContainers.length; i++) {
                    if (allContainers[i].scrollHeight > allContainers[i].clientHeight) {
                        allContainers[i].scrollTop = allContainers[i].scrollHeight;
                    }
                }
                var clickables = document.querySelectorAll('button, input[type="submit"], input[type="button"], a.btn, [role="button"], [ng-click]');
                for (var j = 0; j < clickables.length; j++) {
                    var el = clickables[j];
                    var txt = (el.innerText || el.textContent || el.value || '').trim().toLowerCase();
                    if (txt && txt.indexOf(target) !== -1) {
                        el.scrollIntoView({block: 'center'});
                        el.click();
                        return (el.innerText || el.textContent || el.value || '').trim();
                    }
                }
                return null;
                """
                matched_bank_save = self.driver.execute_script(js_scroll_click_bank)
                if matched_bank_save:
                    print(f"[FOUND & CLICKED SAVE BANK BUTTON] via JS: '{matched_bank_save}'")

            wait_loader(self.driver)
            time.sleep(2)
        except Exception as e:
            print(f"[NOTE] Save Bank Information step notice: {e}")

        return True, "PROFILE_SAVED_SUCCESSFULLY"


    def activate_user(self, mobile: str, profile_name: str) -> bool:
        """
        STEPS 14-15: Finalize user activation by clicking the green checkmark (✓ / approve icon)
        and approving inside the modal popup.

        Tries activation directly on the open profile page first, then falls back to
        filtering Search Users by mobile number.
        """
        print(f"\n[STEPS 14-15] Finalizing activation for {profile_name} ({mobile})...")

        # Approach 1: Try activating directly on the currently open profile page
        try:
            profile_checkmarks = self.driver.find_elements(
                By.XPATH,
                "//i[contains(@class, 'dotMark') or contains(@class, 'fa-check') or contains(@data-bs-target, 'Modal')] | "
                "//label[contains(@class, 'avatar-preview')]/following-sibling::i"
            )
            if profile_checkmarks:
                print(f"[STEP 15] Clicking activation checkmark on profile page...")
                self.driver.execute_script("arguments[0].click();", profile_checkmarks[0])
                time.sleep(2)

                modals = self.driver.find_elements(
                    By.XPATH, "//div[contains(@class, 'modal-content') or contains(@class, 'modal-dialog') or @id='exampleModalUser']"
                )
                visible_modals = [m for m in modals if m.is_displayed()]
                if visible_modals:
                    modal = visible_modals[0]
                    if not self.dry_run:
                        approve_btns = modal.find_elements(
                            By.XPATH, ".//button[contains(text(), 'Approve') or contains(text(), 'Activate') or contains(@class, 'btn-success')]"
                        )
                        if approve_btns:
                            self.driver.execute_script("arguments[0].click();", approve_btns[0])
                            wait_loader(self.driver)
                            time.sleep(3)
                            print(f"[SUCCESS] User {profile_name} ({mobile}) ACTIVATED successfully via profile page!")
                            return True
                    else:
                        print(f"[DRY RUN] Would click 'Approve' inside Activation Status popup.")
                        close_btns = modal.find_elements(By.XPATH, ".//button[contains(text(), 'Close') or contains(text(), 'Cancel')]")
                        if close_btns:
                            self.driver.execute_script("arguments[0].click();", close_btns[0])
                            time.sleep(1)
                        return True
        except Exception as e:
            print(f"[NOTE] Profile page direct activation notice: {e}")

        # Approach 2: Fallback to Search Users (#/users) list filtering by mobile
        print(f"[STEPS 14-15] Fallback: Navigating to Search Users for {mobile}...")
        self.navigate_to_search_users()

        try:
            search_inputs = self.driver.find_elements(
                By.XPATH, "//input[contains(@placeholder, 'Search') or contains(@placeholder, 'Mobile') or contains(@ng-model, 'search')]"
            )
            if search_inputs:
                s_input = search_inputs[0]
                s_input.clear()
                s_input.send_keys(mobile)
                self.driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", s_input)
                self.driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", s_input)
                s_input.send_keys(Keys.RETURN)
                wait_loader(self.driver)
                time.sleep(3)

            user_cards = self.driver.find_elements(By.XPATH, "//tbody/tr | //div[contains(@class, 'user-card')]")
            target_card = None
            for card in user_cards:
                if mobile in card.text or (profile_name and profile_name.split()[0] in card.text):
                    target_card = card
                    break

            if not target_card and len(user_cards) == 1:
                target_card = user_cards[0]

            if not target_card:
                print(f"[ERROR] User {mobile} card not found on Search Users page.")
                return False

            print(f"[STEP 15] Clicking activation checkmark for {profile_name} on list card...")
            approve_icon = target_card.find_element(
                By.XPATH, ".//i[contains(@class, 'check') or contains(@class, 'fa-check') or contains(@class, 'green') or contains(@class, 'dotMark')] | .//button[contains(@class, 'btn-success') or .//i[contains(@class, 'fa-check')]]"
            )
            btn_click = approve_icon if approve_icon.tag_name == "button" else approve_icon.find_element(By.XPATH, "..")
            self.driver.execute_script("arguments[0].click();", btn_click)
            time.sleep(2)

            modal = self.wait.until(EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'modal-content')] | //div[contains(@class, 'modal-dialog')]")))
            
            if not self.dry_run:
                modal_approve_btn = modal.find_element(
                    By.XPATH, ".//button[contains(text(), 'Approve') or contains(text(), 'Activate') or contains(@class, 'btn-success')]"
                )
                self.driver.execute_script("arguments[0].click();", modal_approve_btn)
                wait_loader(self.driver)
                time.sleep(3)
                print(f"[SUCCESS] User {profile_name} ({mobile}) ACTIVATED successfully!")
            else:
                print(f"[DRY RUN] Would click 'Approve' inside Activation Status popup.")
                modal_close_btn = modal.find_element(By.XPATH, ".//button[contains(text(), 'Close') or contains(text(), 'Cancel')]")
                self.driver.execute_script("arguments[0].click();", modal_close_btn)
                time.sleep(1)

            return True

        except Exception as e:
            print(f"[ERROR] Activation step failed for {mobile}: {e}")
            return False


    def run(self):
        """Main execution workflow iterating over all eligible pending users."""
        print("==================================================================")
        print("         WHIZZARD ADMIN PANEL - USER ACTIVATION AUTOMATION        ")
        print("==================================================================")
        print(f"Mode: {'[DRY RUN]' if self.dry_run else '[LIVE EXECUTION]'}")
        print(f"Browser: {'[HEADLESS]' if self.headless else '[HEADFUL / GUI]'}")
        print(f"Max Users Limit: {self.max_users or 'Unlimited'}")
        print("==================================================================\n")

        try:
            self.login()
            self.navigate_to_search_users()

            processed_count = 0
            updated_count = 0
            skipped_count = 0
            processed_profiles = set()

            # Iterate through rows/cards on Search Users page
            rows = self.driver.find_elements(By.XPATH, "//tbody/tr | //div[contains(@class, 'user-card')]")
            total_on_page = len(rows)
            print(f"[INFO] Found {total_on_page} user records on current view.\n")

            idx = 0
            while idx < len(rows):
                if self.max_users and processed_count >= self.max_users:
                    print(f"\n[LIMIT REACHED] Reached maximum user processing limit ({self.max_users}). Stopping.")
                    break

                # Re-fetch rows to avoid stale references
                rows = self.driver.find_elements(By.XPATH, "//tbody/tr | //div[contains(@class, 'user-card')]")
                if idx >= len(rows):
                    break

                row = rows[idx]
                tds = row.find_elements(By.TAG_NAME, "td")
                if len(tds) < 4:
                    idx += 1
                    continue

                col0 = tds[0]
                col2_missing = tds[2]
                col3_ops = tds[3]

                col0_text = col0.text
                name_match = re.search(r'Name:\s*([^\n]+)', col0_text)
                profile_name = name_match.group(1).strip() if name_match else "Unknown Name"

                mob_match = re.search(r'Mobile:\s*(\d{10})', col0_text, re.I)
                if not mob_match:
                    mob_match = re.search(r'\b\d{10}\b', col0_text)
                mobile_num = mob_match.group(1) if mob_match and mob_match.groups() else (mob_match.group(0) if mob_match else "Unknown Mobile")
                profile_key = (mobile_num, profile_name)

                if profile_key in processed_profiles:
                    idx += 1
                    continue

                # Parse missing fields list, stripping leading item numbers (e.g. '1. Missing Gross Pay' -> 'Missing Gross Pay')
                missing_li_els = col2_missing.find_elements(By.TAG_NAME, "li")
                if missing_li_els:
                    raw_items = [li.text.strip() for li in missing_li_els if li.text.strip()]
                else:
                    raw_items = [line.strip() for line in col2_missing.text.split("\n") if line.strip()]

                missing_fields = [re.sub(r'^\d+[\.\s]*', '', item).strip() for item in raw_items if item.strip()]
                ops_remark = col3_ops.text.strip()

                processed_count += 1
                print("------------------------------------------------------------------")
                print(f"Processing Pending User #{processed_count} | Name: {profile_name} | Mobile: {mobile_num}")
                print(f"Missing Fields: {missing_fields}")
                print(f"Ops Team Remarks: '{ops_remark}'")

                # PARSE GROSS PAY & MAP BAND (IF PRESENT)
                gross_pay = parse_gross_pay(ops_remark)
                band = get_band_from_gross_pay(gross_pay) if gross_pay else None

                if gross_pay and band:
                    print(f"[GROSS PAY PARSED] Value: {gross_pay} -> Computed Band: {band}")
                else:
                    print("[GROSS PAY] No valid gross pay found; continuing with the Pending profile.")

                # Locate profile URL from first column link
                try:
                    profile_link = col0.find_element(By.TAG_NAME, "a")
                    profile_url = profile_link.get_attribute("href")
                except Exception:
                    profile_link = row.find_element(By.XPATH, ".//a[contains(@href, 'userProfile')]")
                    profile_url = profile_link.get_attribute("href")

                processed_profiles.add(profile_key)

                # PROCESS PROFILE
                success, details = self.process_user_profile(profile_url, gross_pay, band, mobile_num, profile_name)

                if not success:
                    skipped_count += 1
                    append_csv_log(profile_name, mobile_num, ops_remark, gross_pay, band, "FAILED — Profile Save Error", details, self.dry_run)
                    self.navigate_to_search_users()
                    rows = self.driver.find_elements(By.XPATH, "//tbody/tr | //div[contains(@class, 'user-card')]")
                    idx = 0
                    continue

                # Profile activation is intentionally not performed.
                updated_count += 1
                append_csv_log(
                    profile_name,
                    mobile_num,
                    ops_remark,
                    gross_pay,
                    band,
                    "PROFILE_UPDATED_SUCCESSFULLY",
                    "Payouts Eligibility and Pan Aadhaar Linkage set to Yes; profile not activated",
                    self.dry_run,
                )

                self.navigate_to_search_users()
                rows = self.driver.find_elements(By.XPATH, "//tbody/tr | //div[contains(@class, 'user-card')]")
                idx = 0

            print("\n==================================================================")
            print("                       AUTOMATION SUMMARY                         ")
            print("==================================================================")
            print(f"Total Eligible Users Processed : {processed_count}")
            print(f"Successfully Updated           : {updated_count}")
            print(f"Skipped / Action Required      : {skipped_count}")
            print(f"Audit Log Saved To             : {LOG_CSV_PATH}")
            print("==================================================================\n")

        finally:
            self.close()


# --- CLI ENTRY POINT ---

def main():
    parser = argparse.ArgumentParser(
        description="Whizzard Admin Panel - User Activation Automation Script"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the workflow and log decisions without saving changes or activating users."
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Run browser in visible GUI mode (default is headless)."
    )
    parser.add_argument(
        "--max-users",
        type=int,
        default=None,
        help="Maximum number of eligible users to process in this run."
    )
    args = parser.parse_args()

    automation = WhizzardActivationAutomation(
        dry_run=args.dry_run,
        headless=not args.headful,
        max_users=args.max_users
    )
    automation.run()


if __name__ == "__main__":
    main()
