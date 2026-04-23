import re
from urllib.parse import unquote, urlparse

from scraper.config import TARGET_BUSINESS_KEYWORDS, TARGET_BUSINESS_REJECT_KEYWORDS


def normalize_business_text(value):
    text = unquote(value or "").lower()
    text = re.sub(r"[_+/|-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_target_business_text(*values):
    haystack = normalize_business_text(" ".join(value or "" for value in values))
    if not haystack:
        return False

    if any(keyword in haystack for keyword in TARGET_BUSINESS_REJECT_KEYWORDS):
        return False

    return any(keyword in haystack for keyword in TARGET_BUSINESS_KEYWORDS)


def is_target_profile_url(url, *extra_values):
    parsed = urlparse(url or "")
    return is_target_business_text(parsed.path, parsed.query, *extra_values)
