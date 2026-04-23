import asyncio
import random
from urllib.parse import urljoin

from playwright_stealth import Stealth

from scraper.config import REDIRECT_TIMEOUT_MS, RETRY_ATTEMPTS
from scraper.filters.email_filters import extract_mailto_emails, find_emails
from scraper.storage.csv_storage import log_failure
from scraper.utils import normalize_external_url


async def goto_with_retry(page, url, step, timeout_ms, retries=RETRY_ATTEMPTS):
    last_error = None
    total_attempts = retries + 1

    for attempt in range(1, total_attempts + 1):
        try:
            return await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        except Exception as exc:
            last_error = exc
            if attempt >= total_attempts:
                raise
            print(f"  [retry] {step} attempt {attempt}/{total_attempts} failed: {exc}")
            await asyncio.sleep(random.uniform(1.5, 3.0))

    raise last_error


async def get_anchor_candidates(page, step, target_url, profile_url=""):
    try:
        links = await page.eval_on_selector_all(
            "a[href]",
            """elements => elements.map(el => ({
                href: el.getAttribute('href') || '',
                text: (el.innerText || el.textContent || '').trim(),
                aria: el.getAttribute('aria-label') || ''
            }))""",
        )
        return links, False
    except Exception as exc:
        log_failure(f"{step}_links", target_url, exc, profile_url)
        return [], True


async def extract_page_emails(page, page_url, step, profile_url=""):
    emails = set()
    had_error = False

    try:
        visible_text = await page.evaluate(
            """() => {
                const bodyText = document.body ? (document.body.innerText || "") : "";
                const linkText = Array.from(document.querySelectorAll("a[href]"))
                    .map(el => `${el.getAttribute("href") || ""} ${(el.innerText || el.textContent || "").trim()}`)
                    .join("\\n");
                return `${bodyText}\\n${linkText}`;
            }"""
        )
        emails.update(find_emails(visible_text))
    except Exception as exc:
        had_error = True
        log_failure(f"{step}_text", page_url, exc, profile_url)

    try:
        hrefs = await page.eval_on_selector_all(
            'a[href^="mailto:"]',
            "elements => elements.map(el => el.getAttribute('href')).filter(Boolean)",
        )
        for href in hrefs:
            emails.update(extract_mailto_emails(href))
    except Exception as exc:
        had_error = True
        log_failure(f"{step}_mailto", page_url, exc, profile_url)

    return emails, had_error


async def handle_redirect_url(context, url, profile_url="", step="redirect"):
    """Follow Houzz redirect links and return final target URL."""
    normalized_url = normalize_external_url(url)
    if not normalized_url:
        return "", False

    url_lower = normalized_url.lower()
    needs_redirect = normalized_url.startswith("/") or "/trk/" in url_lower or "houzz.com" in url_lower
    if not needs_redirect:
        return normalized_url, False

    full_url = normalized_url if normalized_url.startswith("http") else urljoin("https://www.houzz.com", normalized_url)
    page = await context.new_page()
    await Stealth().apply_stealth_async(page)

    try:
        await goto_with_retry(page, full_url, step, timeout_ms=REDIRECT_TIMEOUT_MS)
        return normalize_external_url(page.url), False
    except Exception as exc:
        log_failure(step, full_url, exc, profile_url)
        print(f"  [!] Redirect failed for {url}: {exc}")
        return normalized_url, True
    finally:
        await page.close()
