# Web Lead Scraper

Python Playwright scraper for collecting contractor and real-estate related emails from Houzz and BBB.

## Run

```powershell
.\.venv\Scripts\python.exe houzz_pro_scraper.py
```

Or run a source directly:

```powershell
.\.venv\Scripts\python.exe houzz_pro_scraper.py --source houzz --url "HOUZZ_SEARCH_URL"
```

```powershell
.\.venv\Scripts\python.exe houzz_pro_scraper.py --source bbb --url "BBB_SEARCH_URL"
```

## Output

- `houzz_emails.csv` - clean Houzz email list
- `bbb_emails.csv` - clean BBB email list
- `output/csv/*_results_detailed.csv` - detailed rows with quality scoring
- `output/csv/*_scrape_status.csv` - resume/status tracking
- `final/*_high_quality_emails.csv` - final quality-filtered client-ready emails

Scraped emails, logs, browser profiles, and virtualenv files are ignored by Git.

Export final files without scraping:

```powershell
.\.venv\Scripts\python.exe houzz_pro_scraper.py --source bbb --export-final-only
```

Choose quality levels:

```powershell
.\.venv\Scripts\python.exe houzz_pro_scraper.py --source houzz --export-final-only --quality-filter high
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\pip.exe install -r setup\requirements.txt
.\.venv\Scripts\playwright.exe install chromium
```

Manual browser/VPN setup:

```powershell
.\.venv\Scripts\python.exe tools\open_browser.py --url "https://www.bbb.org/"
```
