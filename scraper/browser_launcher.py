from scraper.config import BROWSER_EXECUTABLE_CANDIDATES, USER_DATA_DIR


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def find_browser_executable():
    for candidate in BROWSER_EXECUTABLE_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    return None


async def launch_persistent_browser(playwright, headless=False):
    launch_options = {
        "headless": headless,
        "viewport": {"width": 1280, "height": 800},
        "user_agent": USER_AGENT,
    }

    executable_path = find_browser_executable()
    if executable_path:
        launch_options["executable_path"] = executable_path
        print(f"[*] Using browser: {executable_path}")
    else:
        print("[*] Using Playwright bundled Chromium")

    return await playwright.chromium.launch_persistent_context(USER_DATA_DIR, **launch_options)
