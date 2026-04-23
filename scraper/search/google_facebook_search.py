import asyncio
import random
import re
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

from playwright_stealth import Stealth

from scraper.browser_helpers import get_anchor_candidates, goto_with_retry
from scraper.config import BUSINESS_NAME_STOPWORDS, DEFAULT_SEARCH_COUNTRY, GOOGLE_RESULT_LIMIT, GOOGLE_TIMEOUT_MS
from scraper.sources.facebook_scraper import normalize_facebook_candidate_url
from scraper.storage.csv_storage import log_failure
from scraper.utils import compact_whitespace, normalize_external_url


def build_google_facebook_query(name, country):
    clean_name = compact_whitespace(name)
    clean_country = compact_whitespace(country) or DEFAULT_SEARCH_COUNTRY
    return f'site:facebook.com "{clean_name}" fb in {clean_country}'


def extract_google_target_url(href):
    if not href:
        return ""

    normalized_url = normalize_external_url(href)
    full_url = normalized_url if normalized_url.startswith("http") else urljoin("https://www.google.com", normalized_url)
    parsed = urlparse(full_url)
    hostname = (parsed.hostname or "").lower()

    if "google." in hostname and parsed.path.startswith("/url"):
        query_values = parse_qs(parsed.query)
        target_url = (query_values.get("q") or query_values.get("url") or [""])[0]
        return normalize_external_url(unquote(target_url))

    return full_url


def tokenize_business_name(name):
    tokens = re.findall(r"[a-z0-9]+", (name or "").lower())
    return [
        token
        for token in tokens
        if len(token) >= 2 and token not in BUSINESS_NAME_STOPWORDS
    ]


def score_google_facebook_candidate(url, link, name, country):
    label = f"{link.get('text', '')} {link.get('aria', '')}".strip().lower()
    haystack = f"{url} {label}".lower()
    tokens = tokenize_business_name(name)
    token_hits = sum(1 for token in tokens if token in haystack)

    if tokens and token_hits == 0:
        return -1

    score = 8 + (token_hits * 4)
    if "facebook" in haystack:
        score += 4
    if "fb" in haystack:
        score += 2
    if compact_whitespace(country).lower() in haystack:
        score += 2
    if any(part in url.lower() for part in ("/posts/", "/photos/", "/videos/", "/reel/")):
        score -= 3
    return score


def extract_google_facebook_candidates(links, name, country):
    ranked = []
    seen = set()

    for link in links:
        target_url = extract_google_target_url(link.get("href", ""))
        facebook_url = normalize_facebook_candidate_url(target_url)
        if not facebook_url or facebook_url in seen:
            continue

        score = score_google_facebook_candidate(facebook_url, link, name, country)
        if score <= 0:
            continue

        seen.add(facebook_url)
        ranked.append((score, facebook_url))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [url for _, url in ranked[:GOOGLE_RESULT_LIMIT]]


async def get_google_facebook_candidates(context, name, country, profile_url="", google_cache=None):
    """Use Google as a fallback to discover likely Facebook pages for a pro name."""
    clean_name = compact_whitespace(name)
    clean_country = compact_whitespace(country) or DEFAULT_SEARCH_COUNTRY
    if not clean_name:
        return [], False

    query = build_google_facebook_query(clean_name, clean_country)
    cache_key = query.lower()
    if google_cache is not None and cache_key in google_cache:
        cached_candidates, cached_error = google_cache[cache_key]
        return list(cached_candidates), cached_error

    candidates = []
    had_error = False
    page = await context.new_page()
    await Stealth().apply_stealth_async(page)

    try:
        search_url = f"https://www.google.com/search?q={quote_plus(query)}"
        print(f"  [~] Google FB search: {query}")
        try:
            await goto_with_retry(page, search_url, "google_facebook_search", timeout_ms=GOOGLE_TIMEOUT_MS)
        except Exception as exc:
            had_error = True
            log_failure("google_facebook_search", search_url, exc, profile_url)
            print(f"  [!] Google FB search error ({clean_name}): {exc}")
            return candidates, had_error

        await asyncio.sleep(random.uniform(1.5, 2.5))
        links, link_error = await get_anchor_candidates(page, "google_facebook_search", search_url, profile_url)
        had_error = had_error or link_error
        candidates = extract_google_facebook_candidates(links, clean_name, clean_country)
        if candidates:
            print(f"  [~] Google FB candidate: {candidates[0]}")
    finally:
        await page.close()

    if google_cache is not None:
        google_cache[cache_key] = (list(candidates), had_error)
    return candidates, had_error
