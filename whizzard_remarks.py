#!/usr/bin/env python3
"""Apply standardized Super User Remarks to pending Whizzard profiles."""

import argparse
import csv
import datetime
import os
import re
import sys

from dotenv import load_dotenv
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

load_dotenv()

LOGIN_URL = "https://adminpanel.whizzard.in/#/login"
LOG_CSV_PATH = "processed_log.csv"
FAILURE_SCREENSHOT_PATH = "automation_failure.png"

REMARK_RULES = [
    (
        frozenset(["Missing Client Employee Id"]),
        "Kindly mention client employee id for user activation.",
    ),
    (
        frozenset(["Missing Gross Pay"]),
        "Kindly mention gross pay for user activation.",
    ),
    (
        frozenset(["Missing Payment Plan"]),
        "Kindly mention payment plan for user activation.",
    ),
    (
        frozenset(["Missing Client Employee Id", "Missing Payment Plan"]),
        "Kindly mention client employee id & payment plan for user activation.",
    ),
    (
        frozenset(
            ["Missing Bank Details", "Missing Bank Proof Photo", "Missing Payment Plan"]
        ),
        "Kindly upload bank details and docs also mention payment plan for user activation.",
    ),
    (
        frozenset(
            ["Missing Bank Details", "Missing Bank Proof Photo", "Missing Gross Pay"]
        ),
        "Kindly upload bank details and docs also mention gross pay for user activation.",
    ),
    (
        frozenset(["Missing Bank Details", "Missing Bank Proof Photo"]),
        "Kindly upload bank details and docs for user activation.",
    ),
]


def get_remark_text_for_missing_fields(missing_fields_list):
    """Return the standardized remark for a missing-field combination."""
    normalized_list = [item.strip() for item in missing_fields_list if item.strip()]
    if not normalized_list:
        return None
    if len(normalized_list) > 7:
        return "Kindly complete all fields for user activation."

    fields = set(normalized_list)
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
    core_fields = fields - minor_fields

    if {"Missing Bank Details", "Missing Bank Proof Photo", "Missing Gross Pay"}.issubset(fields):
        return "Kindly upload bank details and docs also mention gross pay for user activation."
    if {"Missing Bank Details", "Missing Bank Proof Photo", "Missing Payment Plan"}.issubset(fields):
        return "Kindly upload bank details and docs also mention payment plan for user activation."
    if {"Missing Bank Details", "Missing Bank Proof Photo"}.issubset(fields) and not {
        "Missing Gross Pay",
        "Missing Payment Plan",
    }.intersection(fields):
        return "Kindly upload bank details and docs for user activation."
    if {"Missing Client Employee Id", "Missing Payment Plan"}.issubset(fields):
        return "Kindly mention client employee id & payment plan for user activation."
    if "Missing Client Employee Id" in fields:
        return "Kindly mention client employee id for user activation."
    if "Missing Gross Pay" in fields and (
        core_fields == {"Missing Gross Pay"}
        or core_fields - bgv_fields == {"Missing Gross Pay"}
    ):
        return "Kindly mention gross pay for user activation."
    if "Missing Payment Plan" in fields and (
        core_fields == {"Missing Payment Plan"}
        or core_fields - bgv_fields == {"Missing Payment Plan"}
    ):
        return "Kindly mention payment plan for user activation."

    normalized_set = frozenset(normalized_list)
    for required_set, remark_text in REMARK_RULES:
        if normalized_set == required_set:
            return remark_text
    return None


def init_csv_log():
    if os.path.exists(LOG_CSV_PATH):
        return
    with open(LOG_CSV_PATH, "w", newline="", encoding="utf-8") as file:
        csv.writer(file).writerow(
            [
                "Timestamp",
                "Profile Name",
                "Mobile",
                "Missing Fields",
                "Applied Remark",
                "Status",
                "Is Dry Run",
            ]
        )


def has_remark_from_date(existing_remark_text, target_date=None):
    if not existing_remark_text or existing_remark_text.lower() == "no remarks":
        return False
    if target_date is None:
        target_date = datetime.date.today()
    elif isinstance(target_date, str):
        target_date = datetime.datetime.strptime(target_date, "%Y-%m-%d").date()
    return any(
        value in existing_remark_text
        for value in (
            target_date.strftime("%Y-%m-%d"),
            target_date.strftime("%Y/%m/%d"),
            target_date.strftime("%d-%m-%Y"),
            target_date.strftime("%d/%m/%Y"),
        )
    )


def is_already_logged(mobile, profile_name, target_date_str=None):
    if not os.path.exists(LOG_CSV_PATH):
        return False
    target_date_str = target_date_str or datetime.date.today().strftime("%Y-%m-%d")
    with open(LOG_CSV_PATH, "r", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            if not row.get("Timestamp", "").startswith(target_date_str):
                continue
            if not any(value in row.get("Status", "") for value in ("REMARK_APPLIED", "SUCCESS")):
                continue
            if row.get("Mobile") not in (None, "", "Unknown", "Unknown Mobile"):
                if row["Mobile"] == mobile:
                    return True
            if profile_name != "Unknown Name" and row.get("Profile Name") == profile_name:
                return True
    return False


def append_csv_log(profile_name, mobile, missing_fields, remark, status, is_dry_run):
    fields = (
        "; ".join(missing_fields)
        if isinstance(missing_fields, (list, set, tuple))
        else str(missing_fields)
    )
    with open(LOG_CSV_PATH, "a", newline="", encoding="utf-8") as file:
        csv.writer(file).writerow(
            [
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                profile_name,
                mobile,
                fields,
                remark or "",
                status,
                "YES" if is_dry_run else "NO",
            ]
        )


def wait_for_page(page, timeout=15_000):
    """Wait for navigation and known Angular overlays to settle."""
    page.wait_for_load_state("domcontentloaded", timeout=timeout)
    overlay_selector = (
        "#loader-wrapper, .ngx-spinner-overlay, .loading-overlay, "
        ".blockUI.blockOverlay"
    )
    try:
        page.wait_for_function(
            """selector => [...document.querySelectorAll(selector)].every(element => {
                const style = getComputedStyle(element);
                return style.display === 'none' || style.visibility === 'hidden' ||
                    style.opacity === '0' || element.getClientRects().length === 0;
            })""",
            arg=overlay_selector,
            timeout=timeout,
        )
    except PlaywrightTimeoutError:
        print(f"[NOTE] A blocking overlay remained after {timeout // 1000}s.")


def safe_click(page, locator, description="element", attempts=3, timeout=20_000):
    """Click with Playwright actionability checks, retries, and a force fallback."""
    target = locator.first
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            wait_for_page(page, timeout=min(timeout, 10_000))
            target.wait_for(state="visible", timeout=timeout)
            target.scroll_into_view_if_needed(timeout=timeout)
            target.click(timeout=timeout)
            return
        except (PlaywrightTimeoutError, PlaywrightError) as error:
            last_error = error
            print(
                f"[NOTE] Could not click {description} on attempt "
                f"{attempt}/{attempts}: {type(error).__name__}"
            )
            page.wait_for_timeout(attempt * 1_000)

    try:
        target.wait_for(state="attached", timeout=timeout)
        target.click(force=True, timeout=timeout)
        print(f"[NOTE] Used forced Playwright click for {description}.")
    except (PlaywrightTimeoutError, PlaywrightError) as error:
        raise RuntimeError(
            f"Unable to click {description} after {attempts} attempts"
        ) from (last_error or error)


def exact_text_control(page, text):
    return page.locator("a, button, span").filter(
        has_text=re.compile(rf"^\s*{re.escape(text)}\s*$", re.I)
    )


def normalize_label(value):
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def get_table_column_indexes(page):
    """Find important columns by their headings instead of fixed positions."""
    headers = [value.strip() for value in page.locator("thead th").all_text_contents()]
    normalized = [normalize_label(value) for value in headers]

    def find_index(required_words, fallback):
        for index, label in enumerate(normalized):
            if all(word in label for word in required_words):
                return index
        return fallback

    identity_index = next(
        (
            index
            for index, label in enumerate(normalized)
            if label in {"user", "profile", "user details"}
        ),
        0,
    )
    columns = {
        "identity": identity_index,
        "missing": find_index(("missing",), 2),
        "remark": find_index(("super", "remark"), -1),
    }
    if columns["remark"] == -1:
        columns["remark"] = find_index(("remark",), 4)
    print(f"[STEP 5] Table headers: {headers}")
    print(f"[STEP 5] Detected columns: {columns}")
    return columns


def parse_profile(row, columns):
    cells = row.locator("td")
    col0 = cells.nth(columns["identity"])
    col2_missing = cells.nth(columns["missing"])
    col4_remark = cells.nth(columns["remark"])
    identity_text = col0.inner_text()
    name_match = re.search(r"Name:\s*([^\n]+)", identity_text)
    mobile_match = re.search(r"Mobile:\s*(\d{10})", identity_text, re.I)
    if not mobile_match:
        mobile_match = re.search(r"\b\d{10}\b", identity_text)
    name = name_match.group(1).strip() if name_match else "Unknown Name"
    mobile = (
        mobile_match.group(1)
        if mobile_match and mobile_match.groups()
        else mobile_match.group(0) if mobile_match else "Unknown Mobile"
    )
    missing_fields = [
        value.strip()
        for value in col2_missing.locator("li").all_text_contents()
        if value.strip()
    ]
    return name, mobile, missing_fields, col4_remark


def apply_remark(page, remark_cell, remark, dry_run):
    """Open the row's remark editor, save it, and verify the table was updated."""
    edit_candidates = [
        remark_cell.locator(
            "button.btn.btn-xs:visible:has(i.fa-pencil), "
            "button.btn.btn-xs:visible:has(i[class*='pencil'])"
        ),
        remark_cell.locator("button.btn.btn-xs:visible"),
    ]
    editor = page.locator(
        "textarea:visible, "
        "input:visible[formcontrolname*='remark' i], "
        "input:visible[name*='remark' i], "
        "[contenteditable='true']:visible"
    ).first
    editor_opened = False
    candidate_number = 0
    attempted_controls = []
    for candidates in edit_candidates:
        for index in range(candidates.count()):
            candidate_number += 1
            candidate = candidates.nth(index)
            attempted_controls.append(
                candidate.evaluate(
                    """element => ({
                        tag: element.tagName,
                        text: (element.innerText || '').trim(),
                        title: element.getAttribute('title'),
                        ariaLabel: element.getAttribute('aria-label'),
                        className: element.getAttribute('class')
                    })"""
                )
            )
            try:
                safe_click(
                    page,
                    candidate,
                    description=f"remark edit candidate {candidate_number}",
                    attempts=1,
                    timeout=5_000,
                )
                editor.wait_for(state="visible", timeout=4_000)
                editor_opened = True
                break
            except (PlaywrightTimeoutError, RuntimeError):
                print(
                    f"[NOTE] Candidate {candidate_number} did not open the remark editor."
                )
                try:
                    candidate.evaluate("element => element.click()")
                    editor.wait_for(state="visible", timeout=4_000)
                    print(
                        f"[NOTE] DOM click opened candidate {candidate_number}."
                    )
                    editor_opened = True
                    break
                except (PlaywrightTimeoutError, PlaywrightError):
                    pass
        if editor_opened:
            break

    if not editor_opened:
        raise RuntimeError(
            "No remark edit control opened an editor. "
            f"Controls tried: {attempted_controls}"
        )

    editor.fill(remark)
    dialog = editor.locator(
        "xpath=ancestor::*[@role='dialog' or "
        "contains(concat(' ', normalize-space(@class), ' '), ' modal-content ')][1]"
    )
    controls = dialog if dialog.count() else page
    if dry_run:
        safe_click(
            page,
            controls.get_by_role("button", name=re.compile("close|cancel", re.I)),
            description="Close remark modal",
        )
        return "DRY RUN — Remark Formatted (Not Saved)"

    safe_click(
        page,
        controls.get_by_role(
            "button", name=re.compile(r"^\s*(save|submit|update)\s*$", re.I)
        ),
        description="Save remark",
    )
    wait_for_page(page)
    editor.wait_for(state="hidden", timeout=15_000)
    page.wait_for_timeout(1_000)

    # A click alone is not proof that the API accepted the remark. The table
    # must display the saved text before this profile is counted as successful.
    try:
        remark_cell.get_by_text(remark, exact=False).wait_for(
            state="visible", timeout=15_000
        )
    except PlaywrightTimeoutError as error:
        current_text = remark_cell.inner_text().strip()
        raise RuntimeError(
            "Save dialog closed, but the saved remark was not visible in the "
            f"profile row. Current remark cell: {current_text!r}"
        ) from error
    return "SUCCESS — Remark Applied & Saved"


def run_automation(dry_run=False, headless=True):
    mobile = os.environ.get("WHIZZARD_MOBILE")
    password = os.environ.get("WHIZZARD_PASSWORD")
    if not mobile or not password:
        print("[ERROR] WHIZZARD_MOBILE and WHIZZARD_PASSWORD must be configured.")
        sys.exit(1)

    print("=" * 66)
    print("      WHIZZARD PENDING USERS SUPER USER REMARKS AUTOMATION")
    print("=" * 66)
    print(f"Mode: {'[DRY RUN]' if dry_run else '[LIVE EXECUTION]'}")
    print(f"Browser Mode: {'[HEADLESS]' if headless else '[HEADFUL / GUI]'}")
    print(f"Mobile Account: {mobile}")
    print("=" * 66)
    init_csv_log()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        page.set_default_timeout(20_000)

        try:
            print("[STEP 1] Navigating to login page...")
            page.goto(LOGIN_URL, wait_until="domcontentloaded")
            page.locator("#phoneNumber").fill(mobile)
            page.locator("#password").fill(password)
            safe_click(
                page,
                page.get_by_role("button", name=re.compile("login", re.I)),
                description="Login button",
            )
            wait_for_page(page)
            page.wait_for_timeout(3_000)
            print(f"[STEP 1] Login completed. Current URL: {page.url}")

            print("[STEP 2] Navigating to Onboarding -> Search Users...")
            onboarding = exact_text_control(page, "Onboarding")
            if onboarding.count() == 0 or not onboarding.first.is_visible():
                safe_click(
                    page,
                    page.locator(
                        "button.navbar-toggler, button[aria-label*='menu' i], "
                        "button[aria-label*='navigation' i], i.fa.fa-bars"
                    ),
                    description="sidebar menu toggle",
                )
            safe_click(page, onboarding, description="Onboarding menu")
            safe_click(page, exact_text_control(page, "Search Users"), description="Search Users menu")
            wait_for_page(page)

            print("[STEP 3] Switching to Pending tab...")
            pending = page.locator("a, button, li").filter(
                has_text=re.compile(r"^\s*Pending\s*$", re.I)
            )
            safe_click(page, pending, description="Pending tab")
            wait_for_page(page)
            page.wait_for_timeout(2_000)

            print("[STEP 4] Selecting maximum page size...")
            page_sizes = page.locator("ul.pull-right li")
            if page_sizes.count() == 0 and page.locator("ul.pagination").count() >= 2:
                page_sizes = page.locator("ul.pagination").last.locator("li")
            if page_sizes.count():
                print(f"[STEP 4] Options: {page_sizes.all_text_contents()}")
                target = page_sizes.last
                target_link = target.locator("a")
                safe_click(
                    page,
                    target_link if target_link.count() else target,
                    description="highest page size",
                )
                wait_for_page(page)
                page.wait_for_timeout(3_000)

            columns = get_table_column_indexes(page)
            processed = skipped_existing = skipped_unmapped = applied = failures = 0
            page_number = 1
            while True:
                row_count = page.locator("tbody tr").count()
                print(f"[STEP 5] Page {page_number}: {row_count} pending profiles.")
                for index in range(row_count):
                    row = page.locator("tbody tr").nth(index)
                    if row.locator("td").count() <= max(columns.values()):
                        continue
                    processed += 1
                    name, user_mobile, missing, remark_cell = parse_profile(
                        row, columns
                    )
                    existing_remark = remark_cell.inner_text().strip()
                    print(
                        f"Profile {index + 1}/{row_count}: {name} | "
                        f"{user_mobile} | Missing: {missing}"
                    )

                    if has_remark_from_date(existing_remark):
                        status = "SKIPPED — Remark Already Present for Today"
                        skipped_existing += 1
                        append_csv_log(name, user_mobile, missing, existing_remark, status, dry_run)
                        continue
                    if is_already_logged(user_mobile, name):
                        status = "SKIPPED — Previously Processed Today in CSV Log"
                        skipped_existing += 1
                        append_csv_log(name, user_mobile, missing, None, status, dry_run)
                        continue

                    remark = get_remark_text_for_missing_fields(missing)
                    if not remark:
                        status = "SKIPPED — Unmapped Missing Field Pattern"
                        skipped_unmapped += 1
                        append_csv_log(name, user_mobile, missing, None, status, dry_run)
                        continue

                    try:
                        status = apply_remark(page, remark_cell, remark, dry_run)
                        if not dry_run:
                            applied += 1
                        print(f"[SUCCESS] {status}")
                        append_csv_log(name, user_mobile, missing, remark, status, dry_run)
                    except (PlaywrightError, RuntimeError) as error:
                        failures += 1
                        status = f"FAILED — ERROR applying remark: {error}"
                        print(f"[ERROR] {status}")
                        append_csv_log(name, user_mobile, missing, remark, status, dry_run)

                pagination_links = page.locator(
                    "ul.pagination:not(.pull-right) li:not(.disabled) a"
                )
                next_link = pagination_links.filter(
                    has_text=re.compile(r"^\s*(>|»|Next)\s*$", re.I)
                )
                if next_link.count() == 0:
                    next_link = pagination_links.filter(
                        has_text=re.compile(rf"^\s*{page_number + 1}\s*$")
                    )
                if next_link.count() == 0 or not next_link.first.is_visible():
                    break
                page_number += 1
                safe_click(page, next_link, description=f"page {page_number}")
                wait_for_page(page)
                page.wait_for_timeout(2_000)

            print("=" * 66)
            print(f"Total Profiles Visited           : {processed}")
            print(f"Skipped (Already Remarked/Logged): {skipped_existing}")
            print(f"Skipped (Unmapped Patterns)      : {skipped_unmapped}")
            print(f"Remarks Applied & Saved          : {applied}")
            print(f"Remark Posting Failures          : {failures}")
            print(f"Audit Log                        : {os.path.abspath(LOG_CSV_PATH)}")
            print("=" * 66)
            if failures:
                raise RuntimeError(
                    f"{failures} remark(s) could not be posted or verified. "
                    "See the audit log and failure screenshot."
                )
        except Exception:
            page.screenshot(path=FAILURE_SCREENSHOT_PATH, full_page=True)
            print(f"[ERROR] Failure screenshot saved to {FAILURE_SCREENSHOT_PATH}")
            raise
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Whizzard pending-user remarks automation"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Do not save remarks."
    )
    parser.add_argument(
        "--headful", action="store_true", help="Show the browser window."
    )
    arguments = parser.parse_args()
    run_automation(dry_run=arguments.dry_run, headless=not arguments.headful)
