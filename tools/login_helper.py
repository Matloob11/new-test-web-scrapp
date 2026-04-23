import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.config import USER_DATA_DIR
from scraper.browser_launcher import launch_persistent_browser

async def run():
    async with async_playwright() as p:
        # We use a persistent context so that logins are saved
        user_data_dir = USER_DATA_DIR
        
        print(f"[*] Opening browser with persistent profile in: {user_data_dir}")
        print("[*] Please log in to Facebook and any other sites needed.")
        print("[*] CLOSE the browser window manually when you are done.")
        
        context = await launch_persistent_browser(p, headless=False)
        
        page = await context.new_page()
        await page.goto("https://www.facebook.com")
        
        # Keep the script running until the browser is closed
        # We can detect this by checking if the context or pages are still open
        while len(context.pages) > 0:
            await asyncio.sleep(1)
            
        print("[*] Browser closed. Session saved.")

if __name__ == "__main__":
    asyncio.run(run())
