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
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as to_markdown

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://mistral.ai'
HEADERS = {'User-Agent': 'AcademicResearchBot/0.1 (polite archival analysis; Python requests)'}
FIELDS = ['url', 'slug', 'title', 'published', 'date_source', 'author', 'language', 'word_count', 'sha256', 'retrieved_at', 'extraction_method', 'status']


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
    # The RSS feed (/news/rss) matches the article URL pattern but is XML.
    if p.path.rstrip('/') == '/news/rss':
        return False
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


def render_article(node):
    """Render one DOM subtree once; never select nested p/li elements independently."""
    fragment = BeautifulSoup(str(node), 'html.parser')
    for tag in fragment.select('nav, footer, header, script, style, noscript, form, aside, button'):
        tag.decompose()
    # Remove repeated site navigation that is sometimes embedded in the main element.
    for tag in fragment.select('[aria-hidden="true"], [hidden]'):
        tag.decompose()
    md = to_markdown(str(fragment), heading_style='ATX', bullets='-', strip=['img']).strip()
    md = re.sub(r'\n{3,}', '\n\n', md)
    # Strip article-toolbar text while retaining title and publication date.
    md = re.sub(r'(?m)^\[Back to Blog\]\([^\n]+\)\n(?:\n|[^\n]*min read\n|Share this post\n|Copy url to clipboardCopied\n)*', '', md)
    md = re.sub(r'(?m)^\s*(?:\d+\s*min read|Share this post|Copy url to clipboardCopied)\s*\n', '', md)
    md = re.sub(r'(?m)\n\s*0%\s*$', '', md).strip()
    # Derive counting text from the SAME rendered representation. Retain link labels,
    # discard URL destinations and Markdown structural punctuation.
    txt = re.sub(r'\[([^\]]+)\]\((?:[^()]|\([^()]*\))*\)', r'\1', md)
    txt = re.sub(r'^\s{0,3}#{1,6}\s+', '', txt, flags=re.M)
    txt = re.sub(r'^\s*(?:[-*+] |\d+\. )', '', txt, flags=re.M)
    txt = re.sub(r'(?<!\w)[*_`~]+|[*_`~]+(?!\w)', '', txt)
    txt = re.sub(r'\n{3,}', '\n\n', txt).strip()
    return txt, md


def normalize_date(value):
    """Return an ISO publication date only for a real, valid calendar date."""
    if not isinstance(value, str) or not value.strip():
        return ''
    value = value.strip()
    try:
        return datetime.strptime(value[:10], '%Y-%m-%d').date().isoformat() if re.match(r'^\d{4}-\d{2}-\d{2}(?:$|[Tt ])', value) else ''
    except ValueError:
        return ''


def visible_header_date(soup):
    """Look for a human-readable date near the article title, not in the body/footer."""
    date_pattern = re.compile(r'^(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}$')
    root = soup.select_one('article') or soup.select_one('main') or soup
    heading = root.find(['h1', 'h2']) or root.find(class_=re.compile(r'text-h[12]'))
    # Only consider the beginning of the article (before its main body).
    # Mistral currently uses <p> elements for both title and header date.
    nodes = heading.parent.parent.find_all(['p', 'time', 'span'], limit=35) if heading and heading.parent and heading.parent.parent else []
    for node in nodes:
        if node.find(['p', 'time', 'span']):
            continue
        label = node.get_text(' ', strip=True)
        if date_pattern.fullmatch(label):
            try:
                return datetime.strptime(label, '%B %d, %Y').date().isoformat()
            except ValueError:
                pass
    return ''


def extract(html):
    soup = BeautifulSoup(html, 'html.parser')
    ld = jsonld_article(soup)
    title = ld.get('headline') or ld.get('name') or meta(soup, 'og:title') or (soup.title.get_text(' ', strip=True) if soup.title else '')
    date_candidates = [
        ('jsonld.datePublished', ld.get('datePublished')),
        ('meta.article:published_time', meta(soup, 'article:published_time')),
        ('meta.date', meta(soup, 'date')),
    ]
    t = soup.find('time', datetime=True)
    if t:
        date_candidates.append(('time.datetime', t.get('datetime')))
    date_candidates.append(('visible_header', visible_header_date(soup)))
    published, date_source = '', 'missing'
    for source, candidate in date_candidates:
        valid = normalize_date(candidate)
        if valid:
            published, date_source = valid, source
            break
    author = ld.get('author', '')
    if isinstance(author, dict):
        author = author.get('name', '')
    elif isinstance(author, list):
        author = ', '.join(x.get('name', '') if isinstance(x, dict) else str(x) for x in author)
    lang = soup.html.get('lang', '') if soup.html else ''
    candidates = [('article', soup.select_one('article')),
                  ('main', soup.select_one('main')),
                  ('[role=main]', soup.select_one('[role=main]'))]
    chosen = next(((name, node) for name, node in candidates if node is not None), None)
    if not chosen:
        return dict(title=title, published=published, date_source=date_source, author=author, language=lang, text='', markdown='', method='NONE')
    method, node = chosen
    text, md = render_article(node)
    return dict(title=title, published=published, date_source=date_source, author=author, language=lang, text=text, markdown=md, method=method)


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
                (processed / f'{slug}.md').write_text(info['markdown'], encoding='utf-8')
                status = 'OK' if len(text.split()) >= 50 else 'REVIEW_SHORT'
                row = dict(url=url, slug=slug, title=info['title'], published=info['published'], date_source=info['date_source'],
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
        print('Saved results/corpus_inventory.csv; inspect sample .txt and .md files before analysis.')


if __name__ == '__main__':
    main()
