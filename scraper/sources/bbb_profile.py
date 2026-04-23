import asyncio
import random
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from playwright_stealth import Stealth

from scraper.browser_helpers import extract_page_emails, get_anchor_candidates, goto_with_retry
from scraper.config import BBB_PROFILE_TIMEOUT_MS, BBB_SEARCH_TIMEOUT_MS, REJECT_WEBSITE_HOST_KEYWORDS
from scraper.filters.business_filters import is_target_business_text, is_target_profile_url
from scraper.filters.email_filters import is_valid_email_candidate
from scraper.sources.website_scraper import get_site_emails
from scraper.storage.csv_storage import log_failure, record_status, write_detail_rows, write_master_rows
from scraper.utils import merge_email_sources, normalize_external_url, unique_preserve_order


def extract_bbb_profile_links(candidates):
    profile_links = []

    for link in candidates:
        href = (link.get("href") or "").strip()
        if not href:
            continue

        absolute_url = normalize_external_url(urljoin("https://www.bbb.org", href))
        parsed = urlparse(absolute_url)
        hostname = (parsed.hostname or "").lower()
        path = parsed.path.lower()

        label = f"{link.get('text', '')} {link.get('aria', '')}".strip()
        if hostname.endswith("bbb.org") and "/profile/" in path and "/us/" in path and is_target_profile_url(absolute_url, label):
            profile_links.append(absolute_url.split("#", 1)[0])

    return unique_preserve_order(profile_links)


def score_bbb_website_link(link):
    href = (link.get("href") or "").strip()
    label = f"{link.get('text', '')} {link.get('aria', '')}".strip().lower()
    href_lower = href.lower()

    if not href or href_lower.startswith(("mailto:", "tel:", "#")):
        return -1

    absolute_url = normalize_external_url(urljoin("https://www.bbb.org", href))
    parsed = urlparse(absolute_url)
    hostname = (parsed.hostname or "").lower()

    if not absolute_url.startswith("http"):
        return -1
    if any(reject_host in hostname for reject_host in REJECT_WEBSITE_HOST_KEYWORDS):
        return -1

    score = 0
    if "visit website" in label:
        score += 20
    elif "website" in label:
        score += 5

    return score


def pick_bbb_website(candidates):
    ranked = []
    for link in candidates:
        score = score_bbb_website_link(link)
        if score > 0:
            absolute_url = normalize_external_url(urljoin("https://www.bbb.org", link.get("href", "")))
            ranked.append((score, absolute_url))

    if not ranked:
        return ""

    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def build_next_bbb_page_url(current_url):
    parsed = urlparse(current_url)
    query = parse_qs(parsed.query)
    current_page = 1

    try:
        current_page = int((query.get("page") or ["1"])[0])
    except ValueError:
        current_page = 1

    query["page"] = [str(current_page + 1)]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


async def get_bbb_business_name(page):
    selectors = (
        ".bpr-header-business-name",
        ".bpr-overview-business-name",
        '[class*="business-name"]',
        '[data-testid*="business-name"]',
    )

    for selector in selectors:
        try:
            element = await page.query_selector(selector)
            if element:
                name = (await element.inner_text()).strip()
                if name:
                    return name
        except Exception:
            continue

    try:
        title = await page.title()
        if "|" in title:
            return title.split("|", 1)[0].strip()
    except Exception:
        pass

    return ""


async def get_bbb_business_category_text(page):
    try:
        header = await page.query_selector(".bpr-header-business-info")
        if header:
            return (await header.inner_text()).strip()
    except Exception:
        pass

    try:
        body_text = await page.locator("body").inner_text(timeout=5000)
        return body_text[:1200]
    except Exception:
        return ""


async def process_bbb_profile(
    context,
    profile_url,
    master_writer,
    master_file,
    detail_writer,
    detail_file,
    unique_emails_all,
    detail_keys,
    status_map,
    site_cache,
):
    print(f"\n[+] BBB Business: {profile_url}")
    page = await context.new_page()
    await Stealth().apply_stealth_async(page)

    try:
        await goto_with_retry(page, profile_url, "bbb_profile", timeout_ms=BBB_PROFILE_TIMEOUT_MS)
        await asyncio.sleep(random.uniform(2.0, 3.5))

        name = ""
        try:
            name = await get_bbb_business_name(page)
        except Exception as exc:
            log_failure("bbb_profile_name", profile_url, exc, profile_url)

        profile_errors = []
        email_sources = {}
        category_text = await get_bbb_business_category_text(page)

        if not is_target_business_text(profile_url, name, category_text):
            print(f"    [skip] Not contractor/real-estate related: {name}")
            record_status(status_map, profile_url, "no_email", "source=bbb; skipped_non_target_business")
            return {"status": "no_email", "master_saved": 0, "detail_saved": 0}

        candidates, candidate_error = await get_anchor_candidates(page, "bbb_profile", profile_url, profile_url)
        if candidate_error:
            profile_errors.append("bbb_profile_links")

        profile_emails, profile_email_error = await extract_page_emails(page, profile_url, "bbb_profile", profile_url)
        if profile_email_error:
            profile_errors.append("bbb_profile_emails")
        merge_email_sources(email_sources, profile_emails, "bbb_profile")

        website_final = pick_bbb_website(candidates)
        print(f"    Name: {name}")
        print(f"    Website: {website_final}")

        if website_final:
            site_emails, site_error = await get_site_emails(context, website_final, profile_url, site_cache)
            merge_email_sources(email_sources, site_emails, "website")
            if site_error:
                profile_errors.append("website_lookup")

        valid_emails = {email for email in email_sources if is_valid_email_candidate(email)}
        detail_rows_added = 0
        master_rows_added = 0

        if valid_emails:
            master_rows_added, new_master_emails = write_master_rows(
                master_writer,
                master_file,
                unique_emails_all,
                valid_emails,
            )
            detail_rows_added = write_detail_rows(
                detail_writer,
                detail_file,
                detail_keys,
                email_sources,
                name,
                profile_url,
                website_final,
                "",
                new_master_emails,
            )

        warning_tags = unique_preserve_order(profile_errors)
        warning_text = f"; warnings={','.join(warning_tags)}" if warning_tags else ""

        if valid_emails:
            record_status(
                status_map,
                profile_url,
                "processed",
                f"source=bbb; emails_found={len(valid_emails)}; master_saved={master_rows_added}; detail_saved={detail_rows_added}{warning_text}",
            )
            return {
                "status": "processed",
                "master_saved": master_rows_added,
                "detail_saved": detail_rows_added,
            }

        if warning_tags and any(tag != "website_lookup" for tag in warning_tags):
            record_status(status_map, profile_url, "failed", f"source=bbb; no_email; warnings={','.join(warning_tags)}")
            return {"status": "failed", "master_saved": 0, "detail_saved": 0}

        warning_text = f"; warnings={','.join(warning_tags)}" if warning_tags else ""
        record_status(status_map, profile_url, "no_email", f"source=bbb; checked_profile_website{warning_text}")
        return {"status": "no_email", "master_saved": 0, "detail_saved": 0}
    except Exception as exc:
        log_failure("bbb_profile_processing", profile_url, exc, profile_url)
        record_status(status_map, profile_url, "failed", f"source=bbb; {exc}")
        print(f"    [!] Error processing BBB profile: {exc}")
        return {"status": "failed", "master_saved": 0, "detail_saved": 0}
    finally:
        await page.close()


async def run_bbb_search(
    context,
    input_url,
    master_writer,
    master_file,
    detail_writer,
    detail_file,
    unique_emails_all,
    detail_keys,
    status_map,
    stats,
    max_pages=None,
    max_profiles=None,
):
    site_cache = {}
    main_page = await context.new_page()
    await Stealth().apply_stealth_async(main_page)

    try:
        page_url = input_url
        page_count = 1
        stop_requested = False

        while True:
            print(f"\n--- BBB Search Page {page_count} ---")
            await goto_with_retry(main_page, page_url, "bbb_search", timeout_ms=BBB_SEARCH_TIMEOUT_MS)
            await asyncio.sleep(random.uniform(3.0, 5.0))

            candidates, candidate_error = await get_anchor_candidates(main_page, "bbb_search", page_url)
            if candidate_error:
                print("  [!] Could not read BBB result links.")

            profile_links = extract_bbb_profile_links(candidates)
            print(f"Found {len(profile_links)} BBB businesses.")

            if not profile_links:
                break

            for profile_url in profile_links:
                existing_status = status_map.get(profile_url, {})
                previous_status = existing_status.get("status")

                if previous_status in {"processed", "no_email"}:
                    stats["profiles_skipped"] += 1
                    continue

                if max_profiles and stats["profiles_attempted"] >= max_profiles:
                    stop_requested = True
                    break

                if previous_status == "failed":
                    print(f"\n[~] Retrying failed BBB profile: {profile_url}")

                stats["profiles_attempted"] += 1
                result = await process_bbb_profile(
                    context,
                    profile_url,
                    master_writer,
                    master_file,
                    detail_writer,
                    detail_file,
                    unique_emails_all,
                    detail_keys,
                    status_map,
                    site_cache,
                )

                stats[result["status"]] += 1
                stats["master_saved"] += result["master_saved"]
                stats["detail_saved"] += result["detail_saved"]

            if stop_requested:
                print("\n[*] Reached max profile limit.")
                break

            if max_pages and page_count >= max_pages:
                print("\n[*] Reached max page limit.")
                break

            page_count += 1
            page_url = build_next_bbb_page_url(page_url)
    finally:
        await main_page.close()
