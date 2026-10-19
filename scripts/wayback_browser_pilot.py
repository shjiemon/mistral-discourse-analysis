#!/usr/bin/env python3
"""Pilot: audit a JS-rendered Wayback news listing and its client-side pagination.

Run from repository root:
    pip install playwright beautifulsoup4
    python -m playwright install chromium
    python scripts/wayback_browser_pilot.py

This does NOT change the corpus or the existing Wayback CSVs.
"""
import argparse
import csv
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, unquote

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = 'https://web.archive.org/web/20250304001446/https://mistral.ai/news'
SLUG = re.compile(r'^[a-z0-9][a-z0-9-]*$', re.I)


def article_slug(href):
    href = unquote(href).replace('\\/', '/')
    # Relative href="news/foo" resolves against the archived URL incorrectly;
    # inspect the literal attribute instead of relying on browser URL resolution.
    if href.startswith('news/'):
        path = '/' + href
    elif href.startswith('/news/'):
        path = href
    else:
        m = re.match(r'https?://web\.archive\.org/web/\d+(?:[a-z]+_)?/(https?://.*)', href)
        if m:
            href = m.group(1)
        p = urlparse(href)
        if p.hostname not in ('mistral.ai', 'www.mistral.ai'):
            return None
        path = p.path
    parts = [x for x in path.split('/') if x]
    if len(parts) != 2 or parts[0].lower() != 'news' or not SLUG.fullmatch(parts[1]):
        return None
    if parts[1].lower() in {'rss', 'feed', 'page', 'sitemap'}:
        return None
    return parts[1].lower()


def extract_tiles(html):
    soup = BeautifulSoup(html, 'html.parser')
    result = {}
    for a in soup.find_all('a', href=True):
        slug = article_slug(a['href'])
        if slug:
            result[slug] = a.get_text(' ', strip=True)[:220]
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--url', default=DEFAULT_URL)
    ap.add_argument('--pages', type=int, default=5)
    ap.add_argument('--headed', action='store_true', help='Show the Chromium browser')
    ap.add_argument('--wait-ms', type=int, default=15000, help='Extra wait after load and clicks (default: 15000 ms)')
    args = ap.parse_args()
    out = ROOT / 'results' / 'wayback_browser_pilot'
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    warnings = []
    capture_match = re.search(r'/web/(\d{8})', args.url)
    capture_date = datetime.strptime(capture_match.group(1), '%Y%m%d').date() if capture_match else None
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        page = browser.new_page(viewport={'width': 1440, 'height': 1100})
        try:
            response = page.goto(args.url, wait_until='domcontentloaded', timeout=60000)
            page.wait_for_timeout(args.wait_ms)
            print('Browser URL:', page.url)
            print('HTTP:', response.status if response else 'unknown')
            if '/web/' not in page.url:
                warnings.append('Navigation did not remain inside Wayback')
            for number in range(1, args.pages + 1):
                if number > 1:
                    # The 2025 snapshot uses <a href="#" role="button">N</a>.
                    # Target the pagination list rather than article or toolbar links.
                    pager = page.locator('ul').filter(has=page.locator('a[role="button"]'))
                    target = pager.locator('a[role="button"]', has_text=re.compile(rf'^\s*{number}\s*$'))
                    if target.count() != 1:
                        warnings.append(f'Page {number}: expected one pagination control, found {target.count()}')
                        print('STOP:', warnings[-1])
                        break
                    try:
                        target.click(timeout=10000)
                        page.wait_for_timeout(args.wait_ms)
                    except PlaywrightTimeout:
                        warnings.append(f'Page {number}: pagination click timed out')
                        break
                html = page.content()
                (out / f'page_{number}.html').write_text(html, encoding='utf-8')
                tiles = extract_tiles(html)
                print(f'Page {number}: {len(tiles)} article slugs; URL {page.url}')
                if not tiles:
                    warnings.append(f'Page {number}: no article links extracted')
                for slug, title in sorted(tiles.items()):
                    # A historical Wayback shell may fetch newer LIVE API data!
                    date_match = re.search(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+20\d{2}\b', title)
                    if date_match and capture_date:
                        published = datetime.strptime(date_match.group(), '%b %d, %Y').date()
                        if published > capture_date:
                            warning = f'ANACHRONISM: {slug} tile dated {published} is later than capture {capture_date}; likely live or later-loaded data'
                            warnings.append(warning)
                            print('WARNING:', warning)
                    rows.append({'page': number, 'slug': slug, 'tile_text': title,
                                 'archive_url': page.url})
                # Screenshot is useful if the archive silently fails to paginate.
                page.screenshot(path=str(out / f'page_{number}.png'), full_page=False)
        finally:
            browser.close()
    with (out / 'article_links.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['page', 'slug', 'tile_text', 'archive_url'])
        writer.writeheader()
        writer.writerows(rows)
    unique = {r['slug'] for r in rows}
    print(f'\nTotal: {len(rows)} page/article occurrences; {len(unique)} unique slugs')
    if warnings:
        print('Warnings:')
        for w in warnings:
            print(' -', w)
    print('Saved:', out / 'article_links.csv')
    print('Note: Check each page screenshot/HTML and verify pagination changed article tiles.')


if __name__ == '__main__':
    main()
