import asyncio
import random

from playwright_stealth import Stealth

from scraper.browser_helpers import extract_page_emails, get_anchor_candidates, goto_with_retry, handle_redirect_url
from scraper.config import DEFAULT_SEARCH_COUNTRY, PROFILE_TIMEOUT_MS
from scraper.filters.business_filters import is_target_business_text
from scraper.filters.email_filters import extract_mailto_emails, is_valid_email_candidate
from scraper.search.google_facebook_search import get_google_facebook_candidates
from scraper.sources.facebook_scraper import get_facebook_emails, normalize_facebook_candidate_url
from scraper.sources.website_scraper import get_site_emails
from scraper.storage.csv_storage import log_failure, record_status, write_detail_rows, write_master_rows
from scraper.utils import merge_email_sources, unique_preserve_order


def score_website_candidate(link):
    href = (link.get("href") or "").strip()
    label = f"{link.get('text', '')} {link.get('aria', '')}".strip().lower()
    href_lower = href.lower()

    if not href or href_lower.startswith("mailto:"):
        return -1
    if any(domain in href_lower for domain in ("facebook", "instagram", "twitter", "linkedin", "pinterest")):
        return -1

    score = 0
    if "website" in label or "visit website" in label or "visit my website" in label:
        score += 7
    if "/trk/" in href_lower:
        score += 6
    if href_lower.startswith("http") and "houzz.com" not in href_lower:
        score += 4
    if href.startswith("/") and "/trk/" in href_lower:
        score += 4
    if "houzz.com" in href_lower and "/trk/" not in href_lower:
        score -= 3
    return score


def score_facebook_candidate(link):
    href = (link.get("href") or "").strip()
    label = f"{link.get('text', '')} {link.get('aria', '')}".strip().lower()
    href_lower = href.lower()

    if not href or href_lower.startswith("mailto:"):
        return -1
    if "facebook.com" in href_lower and not normalize_facebook_candidate_url(href):
        return -1

    score = 0
    if "facebook" in label:
        score += 7
    if "facebook.com" in href_lower:
        score += 7
    if "/trk/" in href_lower and "facebook" in label:
        score += 4
    return score


def pick_best_link(candidates, scorer):
    ranked = []
    for link in candidates:
        score = scorer(link)
        if score > 0:
            ranked.append((score, (link.get("href") or "").strip()))

    if not ranked:
        return ""

    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def extract_profile_links(candidates):
    mailto_emails = set()
    for link in candidates:
        mailto_emails.update(extract_mailto_emails(link.get("href", "")))

    website_url = pick_best_link(candidates, score_website_candidate)
    facebook_url = pick_best_link(candidates, score_facebook_candidate)
    return website_url, facebook_url, mailto_emails


async def process_profile(
    context,
    pro_link,
    master_writer,
    master_file,
    detail_writer,
    detail_file,
    unique_emails_all,
    detail_keys,
    status_map,
    site_cache,
    facebook_cache,
    google_cache,
    allow_facebook=True,
    allow_google_fallback=True,
    country=DEFAULT_SEARCH_COUNTRY,
):
    print(f"\n[+] Professional: {pro_link}")
    pro_page = await context.new_page()
    await Stealth().apply_stealth_async(pro_page)

    try:
        await goto_with_retry(pro_page, pro_link, "profile_page", timeout_ms=PROFILE_TIMEOUT_MS)
        await asyncio.sleep(random.uniform(2.0, 4.0))

        name = ""
        try:
            name_el = await pro_page.query_selector("h1")
            if name_el:
                name = (await name_el.inner_text()).strip()
        except Exception as exc:
            log_failure("profile_name", pro_link, exc, pro_link)

        profile_errors = []
        email_sources = {}

        try:
            profile_text_sample = (await pro_page.locator("body").inner_text(timeout=5000))[:1500]
        except Exception:
            profile_text_sample = ""

        if not is_target_business_text(pro_link, name, profile_text_sample):
            print(f"    [skip] Not contractor/real-estate related: {name}")
            record_status(status_map, pro_link, "no_email", "source=houzz; skipped_non_target_business")
            return {"status": "no_email", "master_saved": 0, "detail_saved": 0}

        profile_candidates, candidate_error = await get_anchor_candidates(pro_page, "profile_page", pro_link, pro_link)
        if candidate_error:
            profile_errors.append("profile_links")

        direct_emails, direct_email_error = await extract_page_emails(pro_page, pro_link, "profile_page", pro_link)
        if direct_email_error:
            profile_errors.append("profile_emails")
        merge_email_sources(email_sources, direct_emails, "profile")

        website_raw, facebook_raw, mailto_emails = extract_profile_links(profile_candidates)
        merge_email_sources(email_sources, mailto_emails, "mailto")

        website_final = ""
        if website_raw:
            website_final, website_redirect_error = await handle_redirect_url(
                context,
                website_raw,
                profile_url=pro_link,
                step="website_redirect",
            )
            if website_redirect_error:
                profile_errors.append("website_redirect")

        facebook_final = ""
        if facebook_raw:
            facebook_final, facebook_redirect_error = await handle_redirect_url(
                context,
                facebook_raw,
                profile_url=pro_link,
                step="facebook_redirect",
            )
            if facebook_redirect_error:
                profile_errors.append("facebook_redirect")

        if facebook_final:
            cleaned_facebook_url = normalize_facebook_candidate_url(facebook_final)
            if cleaned_facebook_url:
                facebook_final = cleaned_facebook_url
            else:
                print(f"    [~] Ignoring generic/non-profile Facebook link: {facebook_final}")
                facebook_final = ""

        print(f"    Name: {name}")
        print(f"    Website: {website_final}")
        print(f"    Facebook: {facebook_final}")
        facebook_checked = False
        google_facebook_checked = False
        google_facebook_candidates = []

        if website_final:
            site_emails, site_error = await get_site_emails(context, website_final, pro_link, site_cache)
            merge_email_sources(email_sources, site_emails, "website")
            if site_error:
                profile_errors.append("website_lookup")

        valid_emails = {email for email in email_sources if is_valid_email_candidate(email)}

        if allow_facebook and allow_google_fallback and name and not facebook_final and not valid_emails:
            google_facebook_checked = True
            google_facebook_candidates, google_error = await get_google_facebook_candidates(
                context,
                name,
                country,
                profile_url=pro_link,
                google_cache=google_cache,
            )
            if google_error:
                profile_errors.append("google_facebook_search")
            if google_facebook_candidates:
                facebook_final = google_facebook_candidates[0]
                print(f"    Google Facebook: {facebook_final}")

        facebook_urls_to_check = []
        if facebook_final:
            facebook_urls_to_check.append(facebook_final)
        facebook_urls_to_check.extend(google_facebook_candidates)

        for facebook_url in unique_preserve_order(facebook_urls_to_check):
            if not allow_facebook or valid_emails:
                break
            facebook_checked = True
            fb_emails, fb_error = await get_facebook_emails(context, facebook_url, pro_link, facebook_cache)
            merge_email_sources(email_sources, fb_emails, "facebook")
            if fb_error:
                profile_errors.append("facebook_lookup")
            facebook_final = facebook_url
            valid_emails = {email for email in email_sources if is_valid_email_candidate(email)}

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
                pro_link,
                website_final,
                facebook_final,
                new_master_emails,
            )

        warning_tags = unique_preserve_order(profile_errors)
        warning_text = f"; warnings={','.join(warning_tags)}" if warning_tags else ""

        if valid_emails:
            record_status(
                status_map,
                pro_link,
                "processed",
                f"emails_found={len(valid_emails)}; master_saved={master_rows_added}; detail_saved={detail_rows_added}{warning_text}",
            )
            return {
                "status": "processed",
                "master_saved": master_rows_added,
                "detail_saved": detail_rows_added,
            }

        if warning_tags:
            record_status(status_map, pro_link, "failed", f"no_email; warnings={','.join(warning_tags)}")
            return {"status": "failed", "master_saved": 0, "detail_saved": 0}

        checked_steps = ["profile", "website"]
        if google_facebook_checked:
            checked_steps.append("google_facebook")
        if facebook_checked:
            checked_steps.append("facebook")
        record_status(status_map, pro_link, "no_email", f"checked_{'_'.join(checked_steps)}")
        return {"status": "no_email", "master_saved": 0, "detail_saved": 0}
    except Exception as exc:
        log_failure("profile_processing", pro_link, exc, pro_link)
        record_status(status_map, pro_link, "failed", str(exc))
        print(f"    [!] Error processing profile: {exc}")
        return {"status": "failed", "master_saved": 0, "detail_saved": 0}
    finally:
        await pro_page.close()
