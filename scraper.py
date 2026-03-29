#!/usr/bin/env python3
"""
WP Scrapper — Lead extractor for ifranchisemalaysia.com
Tries WP REST API first, falls back to HTML scraping.
Outputs timestamped CSV with: name, email, phone, brand_interest, source, date
"""

import csv
import os
import re
import sys
from datetime import datetime

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://ifranchisemalaysia.com"
API_ENDPOINT = f"{BASE_URL}/wp-json/wp/v2/comments"
FALLBACK_URL = f"{BASE_URL}/recent-comments"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; WPScrapper/1.0; +https://github.com/zestmy/wp-scrapper)"
}

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(?:\+?6?0[\s.-]?)?1[\s.-]?\d[\s.-]?\d{3,4}[\s.-]?\d{4}")


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


def scrape_via_api():
    """Fetch comments using WP REST API with pagination."""
    leads = []
    page = 1
    per_page = 100

    print("[API] Attempting WP REST API...")

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

            leads.append({
                "name": c.get("author_name", "").strip(),
                "email": author_email if author_email else email,
                "phone": phone,
                "brand_interest": guess_brand(c.get("post", ""), raw_content),
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

        leads.append({
            "name": author,
            "email": email,
            "phone": phone,
            "brand_interest": guess_brand("", text),
            "comment": text[:200],
            "source": "html",
            "date": datetime.now().strftime("%Y-%m-%d"),
        })

    print(f"[HTML] Collected {len(leads)} comments via HTML scraping.")
    return leads


def guess_brand(post_id, text):
    """Try to identify franchise brand from comment context."""
    # Common franchise brands on the site
    brands = [
        "Tealive", "Secret Recipe", "Domino's", "Marrybrown", "CU", "myNEWS",
        "FamilyMart", "99 Speedmart", "Mr DIY", "KK Mart", "Subway",
        "Baskin Robbins", "Kenny Rogers", "Nando's", "Pizza Hut", "KFC",
    ]
    text_lower = text.lower()
    for brand in brands:
        if brand.lower() in text_lower:
            return brand
    return ""


def save_csv(leads):
    """Write leads to a timestamped CSV file."""
    if not leads:
        print("[SAVE] No leads to save.")
        return

    ensure_output_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(OUTPUT_DIR, f"leads_{timestamp}.csv")

    fieldnames = ["name", "email", "phone", "brand_interest", "comment", "source", "date"]
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
        fieldnames = ["name", "email", "phone", "brand_interest", "comment", "source", "date"]
        with open(all_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(leads)
        print(f"[SAVE] All {len(leads)} comments saved to {all_file}")


if __name__ == "__main__":
    main()
