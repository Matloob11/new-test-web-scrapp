import argparse
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.browser_launcher import launch_persistent_browser
from scraper.config import USER_DATA_DIR


async def run(url):
    async with async_playwright() as p:
        print(f"[*] Opening browser with persistent profile in: {USER_DATA_DIR}")
        print("[*] Install/connect your VPN extension, then open BBB.")
        print("[*] Close the browser window when setup is done.")

        context = await launch_persistent_browser(p, headless=False)
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded")

        while len(context.pages) > 0:
            await asyncio.sleep(1)

        print("[*] Browser closed. Session saved.")


def parse_args():
    parser = argparse.ArgumentParser(description="Open persistent browser for manual setup")
    parser.add_argument("--url", default="https://www.bbb.org/", help="URL to open")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run(args.url))
