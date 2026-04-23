import re
from urllib.parse import unquote, urlparse

from scraper.config import COUNTRY_HINTS, DEFAULT_SEARCH_COUNTRY, HOUZZ_DOMAIN_COUNTRIES


def normalize_external_url(url):
    if not url:
        return ""

    cleaned = url.strip()
    if cleaned.startswith("//"):
        return f"https:{cleaned}"
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", cleaned):
        return cleaned
    if cleaned.startswith("/"):
        return cleaned
    if "." in cleaned and " " not in cleaned:
        return f"https://{cleaned.lstrip('/')}"
    return cleaned


def compact_whitespace(value):
    return re.sub(r"\s+", " ", value or "").strip()


def infer_country_from_url(input_url):
    normalized_url = normalize_external_url(input_url)
    parsed = urlparse(normalized_url)
    hostname = (parsed.hostname or parsed.netloc or "").lower()

    domains = sorted(HOUZZ_DOMAIN_COUNTRIES.items(), key=lambda item: len(item[0]), reverse=True)
    for domain, country in domains:
        if hostname == domain or hostname.endswith(f".{domain}"):
            return country

    url_text = unquote(f"{parsed.path} {parsed.query}").lower().replace("_", " ")
    for hint, country in COUNTRY_HINTS.items():
        if hint in url_text:
            return country

    return DEFAULT_SEARCH_COUNTRY


def unique_preserve_order(values):
    return list(dict.fromkeys(values))


def merge_email_sources(source_map, emails, source_name):
    for email in emails:
        clean_email = email.lower().strip()
        source_map.setdefault(clean_email, set()).add(source_name)
