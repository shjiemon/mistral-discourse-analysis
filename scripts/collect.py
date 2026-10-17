#!/usr/bin/env python3
"""Discover Mistral news articles and save their HTML, extracted text, and metadata.

Usage: python scripts/collect.py --limit 5
       python scripts/collect.py
"""
import argparse
import csv
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://mistral.ai'
HEADERS = {'User-Agent': 'AcademicResearchBot/0.1 (polite archival analysis; Python requests)'}
FIELDS = ['url', 'slug', 'title', 'published', 'author', 'language', 'word_count', 'sha256', 'retrieved_at', 'extraction_method', 'status']


def get(session, url, retries=3):
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def news_url(url):
    p = urlparse(url)
    return p.hostname in {'mistral.ai', 'www.mistral.ai'} and re.match(r'^/news/[^/?#]+/?$', p.path) is not None


def discover(session):
    """Discover via archive links; supplement with sitemap URLs where available."""
    found = set()
    response = get(session, BASE + '/news/')
    soup = BeautifulSoup(response.text, 'html.parser')
    for a in soup.select('a[href]'):
        url = urljoin(response.url, a['href']).split('#')[0].split('?')[0].rstrip('/')
        if news_url(url):
            found.add(url)
    print(f'Archive HTML: {len(found)} article links')
    try:
        xml = get(session, BASE + '/sitemap.xml').text
        sitemap = BeautifulSoup(xml, 'xml')
        candidates = [x.get_text(strip=True) for x in sitemap.find_all('loc')]
        nested = [x for x in candidates if x.endswith('.xml')]
        for sm in nested[:50]:
            try:
                candidates += [x.get_text(strip=True) for x in BeautifulSoup(get(session, sm).text, 'xml').find_all('loc')]
            except requests.RequestException as exc:
                print(f'Warning: cannot read sitemap {sm}: {exc}', file=sys.stderr)
        for url in candidates:
            if news_url(url):
                found.add(url.rstrip('/'))
        print(f'After sitemap: {len(found)} article links')
    except (requests.RequestException, Exception) as exc:
        print(f'Warning: sitemap unavailable ({exc}); using archive links only', file=sys.stderr)
    return sorted(found)


def meta(soup, key):
    tag = soup.find('meta', attrs={'property': key}) or soup.find('meta', attrs={'name': key})
    return tag.get('content', '').strip() if tag else ''


def jsonld_article(soup):
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            obj = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue
        nodes = obj if isinstance(obj, list) else [obj]
        for node in nodes:
            if isinstance(node, dict) and '@graph' in node:
                nodes.extend(node['@graph'])
            if isinstance(node, dict) and any(x in str(node.get('@type', '')) for x in ['Article', 'BlogPosting', 'NewsArticle']):
                return node
    return {}


def extract(html):
    soup = BeautifulSoup(html, 'html.parser')
    ld = jsonld_article(soup)
    title = ld.get('headline') or meta(soup, 'og:title') or (soup.title.get_text(' ', strip=True) if soup.title else '')
    published = ld.get('datePublished') or meta(soup, 'article:published_time') or meta(soup, 'date')
    if not published:
        t = soup.find('time', datetime=True)
        published = t.get('datetime', '') if t else ''
    author = ld.get('author', '')
    if isinstance(author, dict):
        author = author.get('name', '')
    elif isinstance(author, list):
        author = ', '.join(x.get('name', '') if isinstance(x, dict) else str(x) for x in author)
    lang = soup.html.get('lang', '') if soup.html else ''
    # Inspect these selectors against downloaded samples before trusting the corpus.
    candidates = [('article', soup.select_one('article')),
                  ('main', soup.select_one('main')),
                  ('[role=main]', soup.select_one('[role=main]'))]
    chosen = next(((name, node) for name, node in candidates if node is not None), None)
    if not chosen:
        return dict(title=title, published=published, author=author, language=lang, text='', method='NONE')
    method, node = chosen
    fragment = BeautifulSoup(str(node), 'html.parser')
    for tag in fragment.select('nav, footer, header, script, style, noscript, form, aside, button'):
        tag.decompose()
    blocks = fragment.select('h1, h2, h3, h4, p, li, blockquote')
    text = '\n\n'.join(x.get_text(' ', strip=True) for x in blocks if x.get_text(' ', strip=True))
    if len(text.split()) < 50:
        text = fragment.get_text(' ', strip=True)
        method += ':fallback'
    return dict(title=title, published=published, author=author, language=lang, text=text, method=method)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=0, help='Limit downloads for pilot; 0=all')
    parser.add_argument('--delay', type=float, default=1.0, help='Seconds between requests')
    parser.add_argument('--refresh', action='store_true', help='Redownload existing files')
    args = parser.parse_args()
    raw = ROOT / 'data/raw'
    processed = ROOT / 'data/processed'
    raw.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    (ROOT / 'results').mkdir(exist_ok=True)
    with requests.Session() as session:
        session.headers.update(HEADERS)
        urls = discover(session)
        (ROOT / 'results/discovered_urls.txt').write_text('\n'.join(urls) + '\n', encoding='utf-8')
        if args.limit:
            urls = urls[:args.limit]
        rows = []
        for i, url in enumerate(urls, 1):
            slug = urlparse(url).path.rstrip('/').split('/')[-1]
            path = raw / f'{slug}.html'
            try:
                if not path.exists() or args.refresh:
                    response = get(session, url)
                    path.write_text(response.text, encoding='utf-8')
                    time.sleep(args.delay)
                html = path.read_text(encoding='utf-8')
                info = extract(html)
                text = info['text']
                (processed / f'{slug}.txt').write_text(text, encoding='utf-8')
                status = 'OK' if len(text.split()) >= 50 else 'REVIEW_SHORT'
                row = dict(url=url, slug=slug, title=info['title'], published=info['published'],
                           author=info['author'], language=info['language'], word_count=len(text.split()),
                           sha256=hashlib.sha256(text.encode()).hexdigest(),
                           retrieved_at=datetime.now(timezone.utc).isoformat(),
                           extraction_method=info['method'], status=status)
            except Exception as exc:
                row = dict.fromkeys(FIELDS, '')
                row.update(url=url, slug=slug, status=f'ERROR: {exc}')
            rows.append(row)
            print(f'[{i}/{len(urls)}] {slug}: {row["status"]} ({row["word_count"]} words)')
        with (ROOT / 'results/corpus_inventory.csv').open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        print('Saved results/corpus_inventory.csv; inspect sample .txt files before analysis.')


if __name__ == '__main__':
    main()
