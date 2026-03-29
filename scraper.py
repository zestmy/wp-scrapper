#!/usr/bin/env python3
"""
WP Scrapper — Lead extractor for ifranchisemalaysia.com
Tries WP REST API first, falls back to HTML scraping.
Outputs timestamped CSV with: name, email, phone, brand_interest, category, source, date
"""

import csv
import os
import re
import sys
from datetime import datetime
from html import unescape

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://ifranchisemalaysia.com"
API_ENDPOINT = f"{BASE_URL}/wp-json/wp/v2/comments"
POSTS_ENDPOINT = f"{BASE_URL}/wp-json/wp/v2/posts"
CATEGORIES_ENDPOINT = f"{BASE_URL}/wp-json/wp/v2/categories"
FALLBACK_URL = f"{BASE_URL}/recent-comments"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; WPScrapper/1.0; +https://github.com/zestmy/wp-scrapper)"
}

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(?:\+?6?0[\s.-]?)?1[\s.-]?\d[\s.-]?\d{3,4}[\s.-]?\d{4}")

# Caches to avoid repeated API calls
_post_cache = {}   # post_id -> {"title": str, "slug": str, "categories": [int]}
_cat_cache = {}    # cat_id -> cat_name


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def extract_fields(text):
    """Extract email and phone from comment text."""
    email = EMAIL_RE.search(text)
    phone = PHONE_RE.search(text)
    return (
        email.group(0) if email else "",
        phone.group(0) if phone else "",
    )


def fetch_categories():
    """Fetch all WP categories and cache them."""
    if _cat_cache:
        return
    print("[API] Fetching categories...")
    try:
        resp = requests.get(
            CATEGORIES_ENDPOINT,
            params={"per_page": 100},
            headers=HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        for cat in resp.json():
            _cat_cache[cat["id"]] = unescape(cat["name"])
        print(f"[API] Cached {len(_cat_cache)} categories.")
    except requests.RequestException as e:
        print(f"[API] Failed to fetch categories: {e}")


def fetch_post_info(post_id):
    """Fetch post title, slug, and categories. Results are cached."""
    if post_id in _post_cache:
        return _post_cache[post_id]

    try:
        resp = requests.get(
            f"{POSTS_ENDPOINT}/{post_id}",
            params={"_fields": "id,slug,title,categories"},
            headers=HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        # Clean brand name from post title — strip suffixes like "Franchise Business Opportunity"
        raw_title = unescape(data.get("title", {}).get("rendered", ""))
        brand = re.sub(
            r"\s*[-–—|:,]?\s*\b(franchise|business|opportunit(y|ies)|malaysia|in malaysia)\b.*$",
            "", raw_title, flags=re.IGNORECASE
        ).strip()

        # Resolve category names (skip parent "Franchise Opportunities" id=10)
        cat_ids = [cid for cid in data.get("categories", []) if cid != 10]
        category = _cat_cache.get(cat_ids[0], "") if cat_ids else ""

        info = {"brand": brand, "category": category}
        _post_cache[post_id] = info
        return info
    except requests.RequestException:
        info = {"brand": "", "category": ""}
        _post_cache[post_id] = info
        return info


def scrape_via_api():
    """Fetch comments using WP REST API with pagination."""
    leads = []
    page = 1
    per_page = 100

    print("[API] Attempting WP REST API...")
    fetch_categories()

    while True:
        try:
            resp = requests.get(
                API_ENDPOINT,
                params={"per_page": per_page, "page": page, "orderby": "date", "order": "desc"},
                headers=HEADERS,
                timeout=30,
            )
            if resp.status_code == 400 or resp.status_code == 404:
                print(f"[API] Endpoint returned {resp.status_code}, API not available.")
                return None
            resp.raise_for_status()
        except requests.RequestException as e:
            if page == 1:
                print(f"[API] Request failed: {e}")
                return None
            break

        comments = resp.json()
        if not comments:
            break

        for c in comments:
            raw_content = BeautifulSoup(c.get("content", {}).get("rendered", ""), "html.parser").get_text()
            email, phone = extract_fields(raw_content)
            author_email = c.get("author_email", "") or ""

            post_id = c.get("post", 0)
            post_info = fetch_post_info(post_id) if post_id else {"brand": "", "category": ""}

            leads.append({
                "name": c.get("author_name", "").strip(),
                "email": author_email if author_email else email,
                "phone": phone,
                "brand_interest": post_info["brand"],
                "category": post_info["category"],
                "comment": raw_content.strip()[:200],
                "source": "api",
                "date": c.get("date", ""),
            })

        total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
        if page >= total_pages:
            break
        page += 1

    print(f"[API] Collected {len(leads)} comments via REST API.")
    return leads


def scrape_via_html():
    """Fallback: scrape the recent-comments HTML page."""
    leads = []
    print("[HTML] Falling back to HTML scraping...")

    try:
        resp = requests.get(FALLBACK_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[HTML] Failed to fetch page: {e}")
        return leads

    soup = BeautifulSoup(resp.text, "html.parser")

    # Try common WordPress comment selectors
    comment_blocks = soup.select(".comment-body, .comment-content, li.comment, .recentcomments li")

    for block in comment_blocks:
        text = block.get_text(separator=" ", strip=True)
        author_el = block.select_one(".comment-author, .fn, .url, cite")
        author = author_el.get_text(strip=True) if author_el else ""

        email, phone = extract_fields(text)

        # Try to extract brand from link href slug
        brand = ""
        link_el = block.select_one("a[href]")
        if link_el:
            href = link_el.get("href", "")
            slug_match = re.search(r"ifranchisemalaysia\.com/([^/]+?)(?:\.html|/)", href)
            if slug_match:
                brand = slug_match.group(1).replace("-", " ").title()
                brand = re.sub(
                    r"\s*(Franchise|Business|Opportunity|Malaysia).*$",
                    "", brand, flags=re.IGNORECASE
                ).strip()

        leads.append({
            "name": author,
            "email": email,
            "phone": phone,
            "brand_interest": brand,
            "category": "",
            "comment": text[:200],
            "source": "html",
            "date": datetime.now().strftime("%Y-%m-%d"),
        })

    print(f"[HTML] Collected {len(leads)} comments via HTML scraping.")
    return leads


def save_csv(leads):
    """Write leads to a timestamped CSV file."""
    if not leads:
        print("[SAVE] No leads to save.")
        return

    ensure_output_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(OUTPUT_DIR, f"leads_{timestamp}.csv")

    fieldnames = ["name", "email", "phone", "brand_interest", "category", "comment", "source", "date"]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(leads)

    print(f"[SAVE] {len(leads)} leads saved to {filename}")
    return filename


def main():
    print(f"=== WP Scrapper — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    print(f"Target: {BASE_URL}")

    # Try API first
    leads = scrape_via_api()

    # Fallback to HTML if API unavailable
    if leads is None:
        leads = scrape_via_html()

    # Filter leads that have at least an email or phone
    qualified = [l for l in leads if l["email"] or l["phone"]]
    print(f"[FILTER] {len(qualified)} qualified leads (have email or phone) out of {len(leads)} total.")

    save_csv(qualified)

    # Also save all comments (including those without contact info)
    if len(leads) > len(qualified):
        ensure_output_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        all_file = os.path.join(OUTPUT_DIR, f"all_comments_{timestamp}.csv")
        fieldnames = ["name", "email", "phone", "brand_interest", "category", "comment", "source", "date"]
        with open(all_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(leads)
        print(f"[SAVE] All {len(leads)} comments saved to {all_file}")

    # Summary by category
    if qualified:
        from collections import Counter
        cat_counts = Counter(l["category"] or "Uncategorized" for l in qualified)
        print(f"\n[SUMMARY] Leads by category:")
        for cat, count in cat_counts.most_common():
            print(f"  {cat}: {count}")


if __name__ == "__main__":
    main()
