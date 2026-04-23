import argparse
import asyncio
import csv
import random

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

from scraper.browser_launcher import launch_persistent_browser
from scraper.sources.bbb_profile import run_bbb_search
from scraper.sources.houzz_profile import process_profile
from scraper.storage.csv_storage import (
    ensure_output_files,
    export_final_emails,
    get_active_detail_output_file,
    get_active_output_file,
    load_existing_detail_keys,
    load_master_emails,
    load_statuses,
    set_active_source,
    write_statuses,
)
from scraper.utils import compact_whitespace, infer_country_from_url, unique_preserve_order


def init_stats():
    return {
        "profiles_attempted": 0,
        "profiles_skipped": 0,
        "processed": 0,
        "failed": 0,
        "no_email": 0,
        "master_saved": 0,
        "detail_saved": 0,
    }


def print_summary(stats):
    print("\n--- Run Summary ---")
    print(f"Profiles attempted: {stats['profiles_attempted']}")
    print(f"Profiles skipped:   {stats['profiles_skipped']}")
    print(f"Processed:          {stats['processed']}")
    print(f"Failed:             {stats['failed']}")
    print(f"No email:           {stats['no_email']}")
    print(f"Master emails:      {stats['master_saved']}")
    print(f"Detail rows:        {stats['detail_saved']}")


async def run_scraper(
    input_url,
    source="houzz",
    max_pages=None,
    max_profiles=None,
    headless=False,
    skip_facebook=False,
    country=None,
    skip_google_fallback=False,
    auto_export_final=True,
    quality_filter=None,
    retry_no_email=False,
):
    async with async_playwright() as p:
        source = normalize_source(source)
        set_active_source(source)
        search_country = compact_whitespace(country) or infer_country_from_url(input_url)
        context = await launch_persistent_browser(p, headless=headless)
        context.set_default_timeout(60000)

        ensure_output_files()

        status_map = load_statuses()
        unique_emails_all = load_master_emails()
        detail_keys = load_existing_detail_keys()
        stats = init_stats()
        output_file = get_active_output_file()
        detail_output_file = get_active_detail_output_file()

        with open(output_file, "a", newline="", encoding="utf-8") as master_file, open(
            detail_output_file, "a", newline="", encoding="utf-8"
        ) as detail_file:
            master_writer = csv.writer(master_file)
            detail_writer = csv.writer(detail_file)

            print(f"\n[*] Starting Search: {input_url}")
            print(f"[*] Source: {source.upper()}")

            if source == "bbb":
                await run_bbb_search(
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
                    max_pages=max_pages,
                    max_profiles=max_profiles,
                    retry_no_email=retry_no_email,
                )
            else:
                print(f"[*] Google FB fallback country: {search_country}")
                await run_houzz_search(
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
                    max_pages=max_pages,
                    max_profiles=max_profiles,
                    skip_facebook=skip_facebook,
                    skip_google_fallback=skip_google_fallback,
                    search_country=search_country,
                    retry_no_email=retry_no_email,
                )

        write_statuses(status_map)
        if auto_export_final:
            export_result = export_final_emails(quality_filter)
            print(f"[DONE] Final clean emails exported to {export_result['final_output_file']}")
            print(f"[DONE] Final detail exported to {export_result['final_detail_file']}")
        await context.close()
        print_summary(stats)
        print(f"\n[DONE] Master data saved to {output_file}")
        print(f"[DONE] Detailed data saved to {detail_output_file}")


def export_final_for_source(source, quality_filter=None):
    source = normalize_source(source)
    set_active_source(source)
    ensure_output_files()
    export_result = export_final_emails(quality_filter)
    print(f"[DONE] Exported {export_result['count']} {source.upper()} emails")
    print(f"[DONE] Final clean emails: {export_result['final_output_file']}")
    print(f"[DONE] Final detail: {export_result['final_detail_file']}")


async def run_houzz_search(
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
    skip_facebook=False,
    skip_google_fallback=False,
    search_country=None,
    retry_no_email=False,
):
    site_cache = {}
    facebook_cache = {}
    google_cache = {}

    main_page = await context.new_page()
    await Stealth().apply_stealth_async(main_page)

    try:
        await main_page.goto(input_url, wait_until="domcontentloaded")

        page_count = 1
        stop_requested = False

        while True:
            print(f"\n--- Houzz Search Page {page_count} ---")
            links = await main_page.eval_on_selector_all("a.hz-pro-ctl", "elements => elements.map(el => el.href)")
            unique_links = unique_preserve_order(links)

            print(f"Found {len(unique_links)} professionals.")

            for pro_link in unique_links:
                existing_status = status_map.get(pro_link, {})
                previous_status = existing_status.get("status")

                if previous_status == "processed" or (previous_status == "no_email" and not retry_no_email):
                    stats["profiles_skipped"] += 1
                    continue

                if max_profiles and stats["profiles_attempted"] >= max_profiles:
                    stop_requested = True
                    break

                if previous_status == "failed":
                    print(f"\n[~] Retrying failed profile: {pro_link}")

                stats["profiles_attempted"] += 1

                result = await process_profile(
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
                    allow_facebook=not skip_facebook,
                    allow_google_fallback=not skip_google_fallback,
                    country=search_country,
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

            next_btn = await main_page.query_selector("a.hz-pagination-link--next")
            if next_btn:
                print("\n[*] Moving to next Houzz search results page...")
                await next_btn.click()
                await main_page.wait_for_load_state("domcontentloaded")
                page_count += 1
                await asyncio.sleep(random.uniform(10, 20))
            else:
                print("\n[*] All pages finished.")
                break
    finally:
        await main_page.close()


def normalize_source(source):
    clean_source = compact_whitespace(source).lower()
    if clean_source in {"1", "houzz", "house", "h"}:
        return "houzz"
    if clean_source in {"2", "bbb", "b"}:
        return "bbb"
    return "houzz"


def prompt_source():
    print("Select website:")
    print("1) Houzz")
    print("2) BBB")
    return normalize_source(input("Enter option 1 or 2: ").strip())


def parse_args():
    parser = argparse.ArgumentParser(description="Houzz/BBB email scraper")
    parser.add_argument("--source", choices=["houzz", "bbb", "1", "2"], help="Website source to scrape")
    parser.add_argument("--url", help="Search results URL for the selected source")
    parser.add_argument("--max-pages", type=int, help="Stop after N result pages")
    parser.add_argument("--max-profiles", type=int, help="Stop after N profiles in this run")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--skip-facebook", action="store_true", help="Do not check Facebook pages")
    parser.add_argument("--country", help="Country name for Google Facebook fallback, e.g. USA")
    parser.add_argument("--skip-google-fallback", action="store_true", help="Do not use Google to find missing Facebook pages")
    parser.add_argument("--retry-no-email", action="store_true", help="Retry profiles previously marked no_email")
    parser.add_argument("--no-final-export", action="store_true", help="Do not export final quality-filtered email CSV after scraping")
    parser.add_argument("--export-final-only", action="store_true", help="Export final quality-filtered email CSV without scraping")
    parser.add_argument(
        "--quality-filter",
        nargs="+",
        choices=["high", "medium", "low"],
        default=["high", "medium"],
        help="Email qualities to include in final export",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    selected_source = normalize_source(args.source) if args.source else prompt_source()
    if args.export_final_only:
        export_final_for_source(selected_source, args.quality_filter)
        raise SystemExit(0)

    default_label = "BBB" if selected_source == "bbb" else "Houzz"
    url_to_scrape = (args.url or input(f"Enter {default_label} Search URL: ").strip()).strip()
    if url_to_scrape:
        asyncio.run(
            run_scraper(
                url_to_scrape,
                source=selected_source,
                max_pages=args.max_pages,
                max_profiles=args.max_profiles,
                headless=args.headless,
                skip_facebook=args.skip_facebook,
                country=args.country,
                skip_google_fallback=args.skip_google_fallback,
                auto_export_final=not args.no_final_export,
                quality_filter=args.quality_filter,
                retry_no_email=args.retry_no_email,
            )
        )
    else:
        print("URL is required.")
