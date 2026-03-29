# WP Scrapper

Lead extractor for [ifranchisemalaysia.com](https://ifranchisemalaysia.com) — scrapes WordPress comments to find potential franchise leads with contact info.

## How It Works

1. **WP REST API** (`/wp-json/wp/v2/comments`) — tried first for structured data
2. **HTML Fallback** (`/recent-comments`) — used when API is unavailable
3. Extracts: name, email, phone, brand interest
4. Outputs timestamped CSV files to `output/`

## Quick Start

```bash
# Local
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python scraper.py

# DigitalOcean (one-liner)
curl -sSL https://raw.githubusercontent.com/zestmy/wp-scrapper/main/setup.sh | bash
```

## Deployment

- **Server:** DigitalOcean Droplet
- **Install dir:** `/opt/ifranchise-scraper`
- **Schedule:** Daily at 8AM via cron
- **Logs:** `/opt/ifranchise-scraper/scraper.log`

## Output

CSV files in `output/` with columns:
- `name` — comment author
- `email` — extracted email address
- `phone` — extracted Malaysian phone number
- `brand_interest` — detected franchise brand
- `comment` — first 200 chars of comment
- `source` — `api` or `html`
- `date` — comment date

## Files

| File | Purpose |
|------|---------|
| `scraper.py` | Main scraper script |
| `setup.sh` | Server install + cron setup |
| `requirements.txt` | Python dependencies |
| `.gitignore` | Excludes output/venv/logs |
