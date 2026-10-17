#!/usr/bin/env python3
"""Compare selected Wayback snapshots of Mistral's news index with local corpus.

Run from repository root: python scripts/wayback_check.py
Requires: requests, beautifulsoup4 (already used by collect.py).
No historical article-body comparisons are performed by this script.
"""
import argparse
import csv
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urljoin, unquote

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = [
    ('2023-09-28', '20230928124436', 'https://mistral.ai/news/'),
    ('2023-12-14', '20231214031455', 'https://mistral.ai/news/'),
    ('2024-03-24', '20240324170625', 'https://mistral.ai/news'),
    ('2024-06-23', '20240623115609', 'https://mistral.ai/news'),
    ('2024-12-16', '20241216160958', 'https://mistral.ai/news'),
    ('2025-03-04', '20250304001446', 'https://mistral.ai/news'),
    ('2025-07-11', '20250711101911', 'https://mistral.ai/news'),
    ('2025-11-22', '20251122025807', 'https://mistral.ai/news'),
    ('2025-12-29', '20251229194809', 'https://mistral.ai/news'),
    ('2026-01-26', '20260126185259', 'https://mistral.ai/news'),
    ('2026-08-02', '20260802054807', 'https://mistral.ai/news/'),
    ('2026-10-16', '20261016075912', 'https://mistral.ai/news/'),
]
FIELDS = ['snapshot_date', 'capture_timestamp', 'requested_url', 'final_url', 'http_status',
          'fetch_status', 'article_links_found', 'possible_pagination', 'notes']
HEADERS = {'User-Agent': 'AcademicResearchBot/0.1 (historical news-index comparison)'}


def canonical_article(value):
    """Return article slug only for a Mistral news article, ignoring tracking/query params."""
    value = unquote(value.strip())
    # Wayback rewrites hrefs as /web/<timestamp>[id_]/https://mistral.ai/news/slug
    value = re.sub(r'^https?://web\.archive\.org', '', value, flags=re.I)
    value = re.sub(r'^/web/\d{1,14}[a-z_]*?/', '', value)
    if value.startswith('//'):
        value = 'https:' + value
    if value.startswith('/news/'):
        value = 'https://mistral.ai' + value
    elif value.startswith('news/'):
        value = 'https://mistral.ai/' + value
    parsed = urlparse(value)
    if parsed.netloc.lower().removeprefix('www.') != 'mistral.ai':
        return None
    parts = [p for p in parsed.path.split('/') if p]
    if len(parts) != 2 or parts[0].lower() != 'news':
        return None
    slug = parts[1].lower()
    if slug in {'rss', 'feed', 'page', 'sitemap.xml'} or '.' in slug:
        return None
    return slug


def links_in_snapshot(html):
    soup = BeautifulSoup(html, 'html.parser')
    # Strip archive toolbar; it includes links unrelated to the captured page.
    for tag in soup.select('#wm-ipp, #wm-ipp-base, #donato, script, style'):
        tag.decompose()
    slugs = set()
    for a in soup.find_all('a', href=True):
        slug = canonical_article(a['href'])
        if slug:
            slugs.add(slug)
    pagination = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if re.search(r'([?&]page=|/page/\d+|[?&](cursor|offset)=)', href, re.I):
            pagination.append(href[:180])
    return sorted(slugs), sorted(set(pagination))[:8]


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh', action='store_true', help='Re-download saved snapshot HTML')
    parser.add_argument('--delay', type=float, default=2.0, help='Delay between Wayback requests (seconds)')
    args = parser.parse_args()
    inventory = ROOT / 'results/corpus_inventory.csv'
    if not inventory.exists():
        parser.error('Missing results/corpus_inventory.csv; run collect.py first')
    with inventory.open(newline='', encoding='utf-8-sig') as f:
        corpus = {row['slug'].lower() for row in csv.DictReader(f) if row.get('slug')}
    folder = ROOT / 'data/wayback/news_index'
    folder.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)
    snapshots, observed = [], defaultdict(set)
    for label, stamp, original in SNAPSHOTS:
        requested = f'https://web.archive.org/web/{stamp}/{original}'
        cached = folder / f'{stamp}.html'
        html, status, final_url, state, note = '', '', '', '', ''
        if cached.exists() and not args.refresh:
            html = cached.read_text(encoding='utf-8')
            state = 'CACHED'
            final_url = '(cached; original response URL not recorded)'
        else:
            try:
                response = session.get(requested, timeout=45)
                status = response.status_code
                final_url = response.url
                response.raise_for_status()
                html = response.text
                # Don't cache Wayback error/challenge pages as successful captures.
                if 'web.archive.org' not in urlparse(final_url).netloc:
                    raise ValueError(f'Unexpected redirect: {final_url}')
                if 'Wayback Machine has not archived that URL' in html:
                    raise ValueError('No archived capture returned')
                cached.write_text(html, encoding='utf-8')
                state = 'FETCHED'
            except (requests.RequestException, ValueError) as exc:
                state = 'FAILED'
                note = str(exc)[:300]
            time.sleep(max(0, args.delay))
        slugs, pagination = links_in_snapshot(html) if html else ([], [])
        if html and not slugs:
            state = 'REVIEW_EMPTY'
            note = 'No article links found; inspect HTML (JS-only listing, blocked page, or capture error).'
        for slug in slugs:
            observed[slug].add(label)
        snapshots.append(dict(snapshot_date=label, capture_timestamp=stamp, requested_url=requested,
                              final_url=final_url, http_status=status, fetch_status=state,
                              article_links_found=len(slugs), possible_pagination=' | '.join(pagination), notes=note))
        print(f'{label}: {state}, {len(slugs)} article links' + (f' — {note}' if note else ''))
    output = ROOT / 'results'
    write_csv(output / 'wayback_snapshots.csv', FIELDS, snapshots)
    comparison = []
    for slug in sorted(corpus | set(observed)):
        dates = sorted(observed.get(slug, set()))
        comparison.append(dict(slug=slug, in_current_corpus='yes' if slug in corpus else 'no',
                               seen_in_snapshots=len(dates), first_seen_snapshot=dates[0] if dates else '',
                               last_seen_snapshot=dates[-1] if dates else '',
                               snapshot_dates='; '.join(dates),
                               review_priority='CHECK_HISTORICAL_ONLY' if dates and slug not in corpus else ''))
    write_csv(output / 'wayback_archive_comparison.csv',
              ['slug', 'in_current_corpus', 'seen_in_snapshots', 'first_seen_snapshot',
               'last_seen_snapshot', 'snapshot_dates', 'review_priority'], comparison)
    missing = [x for x in comparison if x['review_priority']]
    print(f'\nCurrent corpus: {len(corpus)} articles; distinct historical links: {len(observed)}')
    print(f'Historical-only slugs requiring review: {len(missing)}')
    print('Saved results/wayback_snapshots.csv and results/wayback_archive_comparison.csv')
    print('NOTE: Index links alone cannot establish historical archive completeness; check pagination and JS rendering.')


if __name__ == '__main__':
    main()
