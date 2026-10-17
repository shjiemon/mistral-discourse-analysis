#!/usr/bin/env python3
"""Audit selected archived Mistral news indexes against the current corpus.

Run from repository root: python scripts/wayback_check.py
Dependencies: requests, beautifulsoup4. No article-body comparison is performed.

Archived index pages can be partial, JS-rendered, or redirected to another capture.
This script records those limitations rather than treating missing links as evidence
of missing articles. It follows *explicit* pagination links only, with a page cap.
"""
import argparse
import csv
import json
import re
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse, urlunparse

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
HEADERS = {'User-Agent': 'AcademicResearchBot/0.2 (historical news-index comparison)'}
# Strictly accept only article URLs from mistral.ai; exclude /news/page/N and RSS.
WAYBACK = re.compile(r'^(?:https?://web\.archive\.org)?/web/(\d{6,14})(?:[a-z]{2,5}_)?/(.+)$', re.I)
ARTICLE_URL = re.compile(r'(?:https?:\\?/\\?/|https?://|/)?(?:www\.)?mistral\.ai(?:\\?/|/)+news(?:\\?/|/)+([a-z0-9][a-z0-9-]*)', re.I)
RELATIVE_ARTICLE = re.compile(r'(?<![a-z0-9])(?:\\?/|/)news(?:\\?/|/)([a-z0-9][a-z0-9-]*)', re.I)
EXCLUDE = {'rss', 'feed', 'page', 'sitemap', 'sitemap.xml'}
SNAPSHOT_FIELDS = ['snapshot_date', 'capture_timestamp', 'requested_url', 'final_url', 'actual_capture_timestamp',
                   'http_status', 'fetch_status', 'first_page_anchor_links', 'first_page_embedded_links',
                   'article_links_found', 'pages_examined', 'pagination_discovered', 'pagination_attempted',
                   'pagination_failed', 'coverage_warning', 'notes']
PAGE_FIELDS = ['snapshot_date', 'page_number', 'requested_url', 'final_url', 'actual_capture_timestamp',
               'http_status', 'fetch_status', 'anchor_links', 'embedded_links', 'pagination_links', 'notes']


def unwrap_wayback(value):
    """Return (original URL, capture timestamp) for a replay URL, if applicable."""
    value = unquote(value.strip()).replace('\\/', '/')
    match = WAYBACK.match(value)
    if match:
        return match.group(2), match.group(1)
    return value, ''


def normalize_target(value):
    """Normalize Mistral news-index/page URLs, discarding tracking parameters."""
    original, _ = unwrap_wayback(value)
    if original.startswith('//'):
        original = 'https:' + original
    if original.startswith('/news'):
        original = 'https://mistral.ai' + original
    parsed = urlparse(original)
    if parsed.netloc.lower().removeprefix('www.') != 'mistral.ai':
        return None
    path = re.sub(r'/+', '/', parsed.path).rstrip('/') or '/'
    match = re.fullmatch(r'/news(?:/page/(\d+))?', path, re.I)
    page_num = int(match.group(1) or 1) if match else None
    if page_num is None:
        # Some news indexes use ?page=2, but ignore arbitrary query parameters.
        if path != '/news':
            return None
    query = parse_qs(parsed.query)
    if 'page' in query:
        try:
            page_num = int(query['page'][0])
        except (ValueError, IndexError):
            return None
    if not page_num or page_num < 1:
        return None
    return page_num, f'https://mistral.ai/news/page/{page_num}/' if page_num > 1 else 'https://mistral.ai/news/'


def canonical_article(value):
    original, _ = unwrap_wayback(value)
    if original.startswith('//'):
        original = 'https:' + original
    if original.startswith('/news/'):
        original = 'https://mistral.ai' + original
    parsed = urlparse(original)
    if parsed.netloc.lower().removeprefix('www.') != 'mistral.ai':
        return None
    parts = [p for p in parsed.path.split('/') if p]
    if len(parts) != 2 or parts[0].lower() != 'news':
        return None
    slug = parts[1].lower()
    if slug in EXCLUDE or '.' in slug or not re.fullmatch(r'[a-z0-9][a-z0-9-]*', slug):
        return None
    return slug


def extract_index(html):
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup.select('#wm-ipp, #wm-ipp-base, #donato'):
        tag.decompose()
    anchors = set()
    pagination = {}
    for a in soup.find_all('a', href=True):
        href = a['href']
        slug = canonical_article(href)
        if slug:
            anchors.add(slug)
        target = normalize_target(href)
        if target and target[0] > 1:
            pagination[target[0]] = target[1]
    # Next.js hydration JSON, JSON-LD, and embedded application state sometimes
    # contain article URLs even when there are no server-rendered <a> tags.
    # Only count recognizable /news/<slug> paths, not arbitrary words.
    embedded = set()
    raw = html.replace('\\/', '/')
    for regex in (ARTICLE_URL, RELATIVE_ARTICLE):
        for match in regex.finditer(raw):
            slug = match.group(1).lower()
            if slug not in EXCLUDE and re.fullmatch(r'[a-z0-9][a-z0-9-]*', slug):
                embedded.add(slug)
    # Look for structured href/url values that may have been HTML-escaped.
    for script in soup.find_all('script'):
        if script.get('type') == 'application/ld+json':
            try:
                data = json.loads(script.string or script.get_text())
                candidates = []
                def walk(obj):
                    if isinstance(obj, dict):
                        for key, val in obj.items():
                            if key in ('url', '@id', 'href') and isinstance(val, str):
                                candidates.append(val)
                            walk(val)
                    elif isinstance(obj, list):
                        for x in obj:
                            walk(x)
                walk(data)
                for item in candidates:
                    slug = canonical_article(item)
                    if slug:
                        embedded.add(slug)
            except (ValueError, TypeError):
                pass
    return anchors, embedded, pagination


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def fetch(session, url, cache_path, refresh, delay):
    """Return HTML and retrieval metadata. Store sidecar for provenance."""
    sidecar = cache_path.with_suffix('.json')
    if cache_path.exists() and not refresh:
        html = cache_path.read_text(encoding='utf-8')
        metadata = json.loads(sidecar.read_text(encoding='utf-8')) if sidecar.exists() else {}
        return html, {'requested_url': url, 'final_url': metadata.get('final_url', ''),
                      'actual_capture_timestamp': metadata.get('actual_capture_timestamp', ''),
                      'http_status': metadata.get('http_status', ''), 'fetch_status': 'CACHED',
                      'notes': 'Cached HTML; capture provenance unknown' if not metadata else ''}
    result = {'requested_url': url, 'final_url': '', 'actual_capture_timestamp': '',
              'http_status': '', 'fetch_status': 'FAILED', 'notes': ''}
    try:
        response = session.get(url, timeout=45)
        result['http_status'] = response.status_code
        result['final_url'] = response.url
        response.raise_for_status()
        parsed = urlparse(response.url)
        if parsed.netloc.lower() != 'web.archive.org':
            raise ValueError('Unexpected redirect outside web.archive.org')
        _, actual = unwrap_wayback(response.url)
        result['actual_capture_timestamp'] = actual
        if not actual:
            raise ValueError('Response did not resolve to a dated Wayback capture')
        html = response.text
        if 'Wayback Machine has not archived that URL' in html:
            raise ValueError('No archived capture returned')
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(html, encoding='utf-8')
        result['fetch_status'] = 'FETCHED'
        sidecar.write_text(json.dumps(result, indent=2), encoding='utf-8')
        return html, result
    except (requests.RequestException, ValueError) as exc:
        result['notes'] = str(exc)[:250]
        return '', result
    finally:
        time.sleep(max(0, delay))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true', help='Re-download all snapshot HTML')
    parser.add_argument('--delay', type=float, default=2, help='Seconds between Wayback requests')
    parser.add_argument('--max-pages', type=int, default=5, help='Max pages per snapshot, including index (default 5)')
    args = parser.parse_args()
    if args.max_pages < 1:
        parser.error('--max-pages must be >= 1')
    inventory = ROOT / 'results/corpus_inventory.csv'
    if not inventory.exists():
        parser.error('Missing results/corpus_inventory.csv; run collect.py first')
    with inventory.open(newline='', encoding='utf-8-sig') as handle:
        corpus = {r['slug'].lower() for r in csv.DictReader(handle) if r.get('slug')}
    folder = ROOT / 'data/wayback/news_index'
    folder.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)
    snapshots, pages, observed = [], [], defaultdict(set)
    for label, stamp, original in SNAPSHOTS:
        requested = f'https://web.archive.org/web/{stamp}/{original}'
        pending = [(1, requested)]
        visited = set()
        all_slugs = set()
        first_meta = None
        first_anchor = first_embedded = 0
        pagination_discovered = set()
        pagination_attempted = 0
        pagination_failed = 0
        warnings = []
        while pending and len(visited) < args.max_pages:
            page_num, url = pending.pop(0)
            if page_num in visited:
                continue
            visited.add(page_num)
            # Preserve previous version's cached index filename; extra pages use suffix.
            cached = folder / (f'{stamp}.html' if page_num == 1 else f'{stamp}_page_{page_num}.html')
            html, meta = fetch(session, url, cached, args.refresh, args.delay)
            if first_meta is None:
                first_meta = meta
            if page_num > 1:
                pagination_attempted += 1
            anchor, embedded, pagination = extract_index(html) if html else (set(), set(), {})
            all_slugs.update(anchor | embedded)
            if page_num == 1:
                first_anchor, first_embedded = len(anchor), len(embedded)
            if not html or (not anchor and not embedded):
                if page_num > 1:
                    pagination_failed += 1
                warnings.append(f'page {page_num}: no extractable article links')
            if html and not anchor and embedded:
                warnings.append(f'page {page_num}: embedded URLs only; verify manually')
            if html and not anchor and not embedded:
                meta['fetch_status'] = 'REVIEW_EMPTY'
            actual = meta.get('actual_capture_timestamp', '')
            if actual and actual[:8] != stamp[:8]:
                warnings.append(f'page {page_num}: redirected to capture {actual} (requested {stamp})')
            pages.append(dict(snapshot_date=label, page_number=page_num, **meta,
                              anchor_links=len(anchor), embedded_links=len(embedded),
                              pagination_links='; '.join(str(n) for n in sorted(pagination))))
            for number, target in pagination.items():
                pagination_discovered.add(number)
                if number not in visited and number not in [n for n, _ in pending]:
                    # Timestamp-bound replay URL. Redirects to other captures are flagged.
                    pending.append((number, f'https://web.archive.org/web/{stamp}/{target}'))
            if page_num > 1 and len(anchor | embedded) == 0:
                # Prevent wandering through an archive with unusable pagination.
                pass
        if pending:
            warnings.append(f'pagination truncated at --max-pages={args.max_pages}')
        for slug in all_slugs:
            observed[slug].add(label)
        state = first_meta['fetch_status'] if first_meta else 'FAILED'
        if not all_slugs and state in ('CACHED', 'FETCHED'):
            state = 'REVIEW_EMPTY'
        if warnings and state not in ('FAILED', 'REVIEW_EMPTY'):
            state = 'REVIEW_PARTIAL'
        row = dict(snapshot_date=label, capture_timestamp=stamp,
                   requested_url=requested, final_url=(first_meta or {}).get('final_url', ''),
                   actual_capture_timestamp=(first_meta or {}).get('actual_capture_timestamp', ''),
                   http_status=(first_meta or {}).get('http_status', ''), fetch_status=state,
                   first_page_anchor_links=first_anchor, first_page_embedded_links=first_embedded,
                   article_links_found=len(all_slugs), pages_examined=len(visited),
                   pagination_discovered='; '.join(map(str, sorted(pagination_discovered))),
                   pagination_attempted=pagination_attempted, pagination_failed=pagination_failed,
                   coverage_warning='yes' if warnings else 'no', notes=' | '.join(warnings))
        snapshots.append(row)
        print(f'{label}: {state}, {len(all_slugs)} unique articles, {len(visited)} page(s)'
              + (f' — {row["notes"]}' if warnings else ''))
    output = ROOT / 'results'
    write_csv(output / 'wayback_snapshots.csv', SNAPSHOT_FIELDS, snapshots)
    write_csv(output / 'wayback_pages.csv', PAGE_FIELDS, pages)
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
    missing = [r for r in comparison if r['review_priority']]
    print(f'\nCurrent corpus: {len(corpus)}; distinct historical slugs: {len(observed)}')
    print(f'Historical-only slugs requiring review: {len(missing)}')
    print('Saved results/wayback_snapshots.csv, results/wayback_pages.csv, '
          'results/wayback_archive_comparison.csv')
    print('CAUTION: A saved page may omit JS-loaded or paginated articles. '
          'Wayback coverage cannot prove archive completeness.')


if __name__ == '__main__':
    main()
