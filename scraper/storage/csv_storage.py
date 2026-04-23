import csv
import os
from datetime import datetime

from scraper.config import (
    CSV_OUTPUT_DIR,
    BBB_DETAIL_OUTPUT_FILE,
    BBB_FAIL_LOG_FILE,
    BBB_OUTPUT_FILE,
    BBB_STATUS_FILE,
    DETAIL_HEADERS,
    DETAIL_OUTPUT_FILE,
    FAIL_LOG_FILE,
    HOUZZ_DETAIL_OUTPUT_FILE,
    HOUZZ_FAIL_LOG_FILE,
    HOUZZ_OUTPUT_FILE,
    HOUZZ_STATUS_FILE,
    LEGACY_PROGRESS_FILE,
    LOG_OUTPUT_DIR,
    MASTER_HEADERS,
    OUTPUT_FILE,
    STATUS_FILE,
    STATUS_HEADERS,
)
from scraper.filters.email_filters import is_valid_email_candidate
from scraper.filters.email_quality import score_email_quality


ACTIVE_PATHS = {
    "source": "houzz",
    "output_file": HOUZZ_OUTPUT_FILE,
    "detail_output_file": HOUZZ_DETAIL_OUTPUT_FILE,
    "status_file": HOUZZ_STATUS_FILE,
    "fail_log_file": HOUZZ_FAIL_LOG_FILE,
}


def get_source_paths(source="houzz"):
    clean_source = (source or "houzz").lower()
    if clean_source == "bbb":
        return {
            "source": "bbb",
            "output_file": BBB_OUTPUT_FILE,
            "detail_output_file": BBB_DETAIL_OUTPUT_FILE,
            "status_file": BBB_STATUS_FILE,
            "fail_log_file": BBB_FAIL_LOG_FILE,
        }

    return {
        "source": "houzz",
        "output_file": HOUZZ_OUTPUT_FILE,
        "detail_output_file": HOUZZ_DETAIL_OUTPUT_FILE,
        "status_file": HOUZZ_STATUS_FILE,
        "fail_log_file": HOUZZ_FAIL_LOG_FILE,
    }


def set_active_source(source="houzz"):
    ACTIVE_PATHS.update(get_source_paths(source))
    return dict(ACTIVE_PATHS)


def get_active_output_file():
    return ACTIVE_PATHS["output_file"]


def get_active_detail_output_file():
    return ACTIVE_PATHS["detail_output_file"]


def get_active_status_file():
    return ACTIVE_PATHS["status_file"]


def get_active_fail_log_file():
    return ACTIVE_PATHS["fail_log_file"]


def ensure_parent_dir(path):
    parent_dir = os.path.dirname(path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)


def ensure_csv_header(path, headers):
    ensure_parent_dir(path)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        migrate_detail_csv_if_needed(path)
        return
    with open(path, "w", encoding="utf-8", newline="") as file_obj:
        writer = csv.writer(file_obj)
        writer.writerow(headers)


def migrate_detail_csv_if_needed(path):
    if os.path.basename(path) not in {"houzz_results_detailed.csv", "bbb_results_detailed.csv"}:
        return

    try:
        with open(path, "r", encoding="utf-8", newline="") as file_obj:
            reader = csv.DictReader(file_obj)
            rows = list(reader)
            fieldnames = reader.fieldnames or []
    except Exception as exc:
        log_failure("detail_migration_load", path, exc)
        return

    if fieldnames == DETAIL_HEADERS:
        return

    migrated_rows = []
    for row in rows:
        sources = set(filter(None, (row.get("sources") or "").split("|")))
        quality, reason = score_email_quality(
            row.get("email", ""),
            business_name=row.get("name", ""),
            website=row.get("website", ""),
            sources=sources,
        )
        row["email_quality"] = row.get("email_quality") or quality
        row["email_quality_reason"] = row.get("email_quality_reason") or reason
        migrated_rows.append({header: row.get(header, "") for header in DETAIL_HEADERS})

    with open(path, "w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=DETAIL_HEADERS)
        writer.writeheader()
        writer.writerows(migrated_rows)


def ensure_output_files():
    os.makedirs(CSV_OUTPUT_DIR, exist_ok=True)
    os.makedirs(LOG_OUTPUT_DIR, exist_ok=True)
    ensure_csv_header(get_active_output_file(), MASTER_HEADERS)
    ensure_csv_header(get_active_detail_output_file(), DETAIL_HEADERS)
    ensure_csv_header(get_active_status_file(), STATUS_HEADERS)


def load_master_emails():
    emails = set()
    output_file = get_active_output_file()
    if not os.path.exists(output_file):
        return emails

    try:
        with open(output_file, "r", encoding="utf-8", newline="") as file_obj:
            reader = csv.reader(file_obj)
            for row in reader:
                if row and is_valid_email_candidate(row[0].strip()):
                    emails.add(row[0].lower().strip())
    except Exception as exc:
        log_failure("output_load", output_file, exc)
    return emails


def load_existing_detail_keys():
    keys = set()
    detail_output_file = get_active_detail_output_file()
    if not os.path.exists(detail_output_file) or os.path.getsize(detail_output_file) == 0:
        return keys

    try:
        with open(detail_output_file, "r", encoding="utf-8", newline="") as file_obj:
            reader = csv.DictReader(file_obj)
            for row in reader:
                email = (row.get("email") or "").strip().lower()
                profile_url = (row.get("houzz_profile") or "").strip()
                if email and profile_url and is_valid_email_candidate(email):
                    keys.add((email, profile_url))
    except Exception as exc:
        log_failure("detail_output_load", detail_output_file, exc)
    return keys


def load_statuses():
    status_map = {}

    if os.path.exists(LEGACY_PROGRESS_FILE):
        with open(LEGACY_PROGRESS_FILE, "r", encoding="utf-8") as file_obj:
            for line in file_obj:
                profile_url = line.strip()
                if profile_url:
                    status_map[profile_url] = {
                        "status": "processed",
                        "detail": "legacy_progress",
                        "updated_at": "",
                    }

    status_file = get_active_status_file()
    if not os.path.exists(status_file) or os.path.getsize(status_file) == 0:
        return status_map

    with open(status_file, "r", encoding="utf-8", newline="") as file_obj:
        reader = csv.DictReader(file_obj)
        for row in reader:
            profile_url = (row.get("profile_url") or "").strip()
            if not profile_url:
                continue
            status_map[profile_url] = {
                "status": (row.get("status") or "").strip(),
                "detail": (row.get("detail") or "").strip(),
                "updated_at": (row.get("updated_at") or "").strip(),
            }
    return status_map


def write_statuses(status_map):
    status_file = get_active_status_file()
    ensure_parent_dir(status_file)
    with open(status_file, "w", encoding="utf-8", newline="") as file_obj:
        writer = csv.writer(file_obj)
        writer.writerow(STATUS_HEADERS)
        for profile_url in sorted(status_map):
            row = status_map[profile_url]
            writer.writerow(
                [
                    profile_url,
                    row.get("status", ""),
                    row.get("detail", ""),
                    row.get("updated_at", ""),
                ]
            )


def append_status_row(profile_url, status, detail, updated_at):
    status_file = get_active_status_file()
    ensure_csv_header(status_file, STATUS_HEADERS)
    with open(status_file, "a", encoding="utf-8", newline="") as file_obj:
        writer = csv.writer(file_obj)
        writer.writerow([profile_url, status, detail, updated_at])


def record_status(status_map, profile_url, status, detail=""):
    updated_at = datetime.now().isoformat(timespec="seconds")
    status_map[profile_url] = {
        "status": status,
        "detail": detail,
        "updated_at": updated_at,
    }
    append_status_row(profile_url, status, detail, updated_at)


def log_failure(step, target_url, error, profile_url=""):
    fail_log_file = get_active_fail_log_file()
    ensure_parent_dir(fail_log_file)
    file_exists = os.path.exists(fail_log_file) and os.path.getsize(fail_log_file) > 0
    with open(fail_log_file, "a", encoding="utf-8", newline="") as file_obj:
        writer = csv.writer(file_obj)
        if not file_exists:
            writer.writerow(["timestamp", "step", "profile_url", "target_url", "error"])
        writer.writerow(
            [
                datetime.now().isoformat(timespec="seconds"),
                step,
                profile_url,
                target_url,
                str(error),
            ]
        )


def write_detail_rows(
    detail_writer,
    detail_file,
    detail_keys,
    email_sources,
    name,
    pro_link,
    website_final,
    facebook_final,
    new_master_emails,
):
    detail_rows_added = 0

    for email in sorted(email_sources):
        if not is_valid_email_candidate(email):
            continue

        sources = "|".join(sorted(email_sources[email]))
        quality, reason = score_email_quality(
            email,
            business_name=name,
            website=website_final,
            sources=email_sources[email],
        )
        key = (email, pro_link)
        saved_to_master_output = 1 if email in new_master_emails else 0

        if key not in detail_keys:
            detail_writer.writerow(
                [
                    email,
                    name,
                    pro_link,
                    website_final,
                    facebook_final,
                    sources,
                    quality,
                    reason,
                    saved_to_master_output,
                ]
            )
            detail_keys.add(key)
            detail_rows_added += 1

    detail_file.flush()
    return detail_rows_added


def write_master_rows(master_writer, master_file, unique_emails_all, valid_emails):
    master_rows_added = 0
    new_master_emails = set()

    for email in sorted(valid_emails):
        if email in unique_emails_all:
            continue
        unique_emails_all.add(email)
        new_master_emails.add(email)
        master_writer.writerow([email])
        master_rows_added += 1
        print(f"    [SAVED]: {email}")

    master_file.flush()
    return master_rows_added, new_master_emails
