import random
from scraper.config import BROWSER_EXECUTABLE_CANDIDATES, USER_DATA_DIR, USER_AGENTS


def find_browser_executable():
    for candidate in BROWSER_EXECUTABLE_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    return None


async def launch_persistent_browser(playwright, headless=False):
    # Pick a random User-Agent for rotation
    selected_ua = random.choice(USER_AGENTS)
    print(f"[*] Rotating User-Agent: {selected_ua[:50]}...")

    launch_options = {
        "headless": headless,
        "viewport": {"width": 1280, "height": 800},
        "user_agent": selected_ua,
        "ignore_https_errors": True,
    }

    executable_path = find_browser_executable()
    if executable_path:
        launch_options["executable_path"] = executable_path
        print(f"[*] Using browser: {executable_path}")
    else:
        print("[*] Using Playwright bundled Chromium")

    return await playwright.chromium.launch_persistent_context(USER_DATA_DIR, **launch_options)
