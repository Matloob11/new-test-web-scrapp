# STONIX Web Lead Scraper (earlier tree)

Playwright scraper for contractor and real-estate emails on **Houzz** and **BBB**, plus a CustomTkinter desktop window titled **STONIX - Web Lead Scraper Pro**.

This is the earlier cousin of [web-lead-scrapper](https://github.com/Matloob11/web-lead-scrapper). It has the same CLI story. It does **not** include the later Qt `desktop_app/`, Supabase device gate, or SMTP outreach page.

## Features

- Source: Houzz or BBB URL
- Max pages / max profiles
- Headless Chromium
- Skip Facebook / Google fallback
- Retry profiles that had no email
- Export a final CSV
- Live log in the GUI (`gui_app.py`)

## Stack

- Python 3.11-class tooling
- Playwright + stealth
- CustomTkinter GUI

No `.env.example`. No access-control module.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\pip.exe install -r setup\requirements.txt
.\.venv\Scripts\playwright.exe install chromium
```

## Run

CLI:

```powershell
.\.venv\Scripts\python.exe houzz_pro_scraper.py --source houzz --url "https://www.houzz.com/..."
```

Useful flags from the script: `--export-final-only`, `--quality-filter high`.

GUI:

```powershell
.\.venv\Scripts\python.exe gui_app.py
```

Respect Houzz/BBB terms of use. This tool is for your own research, not for hammering their sites.

## Layout

```text
houzz_pro_scraper.py
gui_app.py
scraper/
setup/requirements.txt
output/   final/
tests/
```

## License

See the repository.
