import asyncio
import random
from urllib.parse import urljoin

from playwright_stealth import Stealth

from scraper.config import REDIRECT_TIMEOUT_MS, RETRY_ATTEMPTS
from scraper.filters.email_filters import extract_mailto_emails, find_emails
from scraper.storage.csv_storage import log_failure
from scraper.utils import decode_houzz_trk_link, normalize_external_url


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
    # Try up to 3 times if we hit "Execution context was destroyed"
    for attempt in range(3):
        try:
            # Short wait for page stabilization
            await asyncio.sleep(0.5 if attempt == 0 else 1.5)
            
            # Wait for network to be somewhat idle if possible
            try:
                await page.wait_for_load_state("networkidle", timeout=3000)
            except:
                pass

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
            exc_str = str(exc)
            if "Execution context was destroyed" in exc_str and attempt < 2:
                print(f"  [retry] Context destroyed during link extraction for {step}, retrying after delay ({attempt+1}/3)...")
                await asyncio.sleep(1.0)
                continue

            if "Execution context was destroyed" not in exc_str:
                log_failure(f"{step}_links", target_url, exc, profile_url)
            
            return [], True
    return [], True


async def extract_page_emails(page, page_url, step, profile_url=""):
    emails = set()
    had_error = False

    # Try up to 3 times if we hit "Execution context was destroyed"
    for attempt in range(3):
        try:
            # Give the page a moment to stabilize if it just finished loading
            # Increased delay for better stability
            await asyncio.sleep(1.0 if attempt == 0 else 2.0)
            
            # Wait for network to be somewhat idle if possible
            try:
                await page.wait_for_load_state("networkidle", timeout=3000)
            except:
                pass

            visible_text = await page.evaluate(
                """() => {
                    try {
                        const bodyText = document.body ? (document.body.innerText || "") : "";
                        const linkText = Array.from(document.querySelectorAll("a[href]"))
                            .map(el => `${el.getAttribute("href") || ""} ${(el.innerText || el.textContent || "").trim()}`)
                            .join("\\n");
                        return `${bodyText}\\n${linkText}`;
                    } catch (e) {
                        return "";
                    }
                }"""
            )
            if visible_text:
                emails.update(find_emails(visible_text))
            
            # mailto link extraction also inside the retry loop
            hrefs = await page.eval_on_selector_all(
                'a[href^="mailto:"]',
                "elements => elements.map(el => el.getAttribute('href')).filter(Boolean)",
            )
            for href in hrefs:
                emails.update(extract_mailto_emails(href))

            # If we got here, evaluate succeeded, break retry loop
            break
        except Exception as exc:
            exc_str = str(exc)
            if "Execution context was destroyed" in exc_str and attempt < 2:
                print(f"  [retry] Context destroyed during extraction for {step}, retrying after delay ({attempt+1}/3)...")
                await asyncio.sleep(1.5)
                continue
            
            if "Execution context was destroyed" not in exc_str:
                had_error = True
                log_failure(f"{step}_text", page_url, exc, profile_url)
            break

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
        # Fallback: Try decoding the URL directly from the tracking link
        decoded_url = decode_houzz_trk_link(full_url)
        if decoded_url:
            print(f"  [~] Redirect failed, but decoded target URL: {decoded_url}")
            return normalize_external_url(decoded_url), False

        log_failure(step, full_url, exc, profile_url)
        print(f"  [!] Redirect failed for {url}: {exc}")
        return normalized_url, True
    finally:
        await page.close()
