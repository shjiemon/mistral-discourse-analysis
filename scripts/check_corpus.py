#!/usr/bin/env python3
"""Audit collected Mistral news corpus without network access.

Run from project root: python scripts/check_corpus.py
"""
import argparse
import csv
import hashlib
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / 'results' / 'corpus_inventory.csv'
PROCESSED = ROOT / 'data' / 'processed'
RAW = ROOT / 'data' / 'raw'


def parse_date(value):
    if not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace('Z', '+00:00')).date()
    except ValueError:
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--short', type=int, default=150,
                        help='Flag documents shorter than this many words (default: 150)')
    parser.add_argument('--cutoff', default='2026-10-17',
                        help='Last publication date eligible for study (YYYY-MM-DD)')
    args = parser.parse_args()
    cutoff = date.fromisoformat(args.cutoff)
    if not INVENTORY.exists():
        parser.error(
            f'Inventory not found: {INVENTORY}. Run the collector first.')
    with INVENTORY.open(newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    flags = []
    year_counts = Counter()
    statuses = Counter()
    dates = []
    hashes = defaultdict(list)
    urls = defaultdict(list)
    slugs = set()
    words = []

    def flag(row, code, detail):
        flags.append({'slug': row.get('slug', ''), 'issue': code,
                     'detail': str(detail), 'url': row.get('url', '')})

    for row in rows:
        slug = row.get('slug', '').strip()
        slugs.add(slug)
        url = row.get('url', '').strip()
        urls[url].append(slug)
        status = row.get('status', '').strip()
        statuses[status] += 1
        if status != 'OK':
            flag(row, 'STATUS', status or '(empty)')
        if not url or urlparse(url).hostname not in ('mistral.ai', 'www.mistral.ai'):
            flag(row, 'URL', 'missing or unexpected hostname')
        if urlparse(url).path.rstrip('/') == '/news/rss':
            flag(row, 'RSS_ENDPOINT', 'not an article')
        if not row.get('title', '').strip():
            flag(row, 'MISSING_TITLE', 'empty title')
        lang = row.get('language', '').strip().lower()
        if lang not in ('en', 'en-us', 'en-gb'):
            flag(row, 'LANGUAGE', lang or '(missing)')
        published = row.get('published', '').strip()
        d = parse_date(published)
        if not d:
            flag(row, 'MISSING_OR_INVALID_DATE', published or '(missing)')
        else:
            year_counts[d.year] += 1
            dates.append(d)
            if d > cutoff:
                flag(row, 'AFTER_CUTOFF', d.isoformat())
            if d.year < 2023:
                flag(row, 'EARLY_DATE', d.isoformat())
        text_path = PROCESSED / f'{slug}.txt'
        md_path = PROCESSED / f'{slug}.md'
        raw_path = RAW / f'{slug}.html'
        for path, label in ((raw_path, 'HTML'), (text_path, 'TXT'), (md_path, 'MD')):
            if not path.exists():
                flag(row, f'MISSING_{label}', str(path.relative_to(ROOT)))
            elif path.stat().st_size == 0:
                flag(row, f'EMPTY_{label}', str(path.relative_to(ROOT)))
        if text_path.exists():
            content = text_path.read_text(encoding='utf-8')
            count = len(content.split())
            words.append(count)
            if count < args.short:
                flag(row, 'SHORT_TEXT', f'{count} words (< {args.short})')
            declared = row.get('word_count', '').strip()
            if declared and declared.isdigit() and int(declared) != count:
                flag(row, 'WORD_COUNT_MISMATCH',
                     f'CSV {declared}; actual {count}')
            digest = hashlib.sha256(content.encode('utf-8')).hexdigest()
            hashes[digest].append(slug)
            recorded = row.get('sha256', '').strip()
            if recorded and recorded != digest:
                flag(row, 'HASH_MISMATCH',
                     'processed text differs from inventory SHA-256')
            lines = [line.strip()
                     for line in content.splitlines() if line.strip()]
            adjacent = [(i + 1, line[:90]) for i, (line, nxt) in enumerate(
                zip(lines, lines[1:])) if line == nxt and len(line) >= 35]
            if adjacent:
                flag(row, 'ADJACENT_DUPLICATE_LINES',
                     f'{len(adjacent)} instances; first: {adjacent[0]}')
    for url, group in urls.items():
        if len(group) > 1:
            flag({'slug': ', '.join(group), 'url': url},
                 'DUPLICATE_URL', len(group))
    for digest, group in hashes.items():
        if len(group) > 1:
            flag({'slug': ', '.join(group)}, 'IDENTICAL_TEXT',
                 f'{len(group)} files share SHA-256 {digest[:12]}')
    for ext in ('txt', 'md'):
        for path in sorted(PROCESSED.glob(f'*.{ext}')):
            if path.stem not in slugs:
                flag({'slug': path.stem}, 'ORPHAN_FILE',
                     str(path.relative_to(ROOT)))

    out = ROOT / 'results' / 'corpus_quality_flags.csv'
    with out.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(
            f, fieldnames=['slug', 'issue', 'detail', 'url'])
        writer.writeheader()
        writer.writerows(flags)

    print(f'Inventory records: {len(rows)}')
    print('Statuses: ' +
          (', '.join(f'{k or "(empty)"}={v}' for k, v in sorted(statuses.items())) or '(none)'))
    print('Publication years: ' +
          (', '.join(f'{y}={n}' for y, n in sorted(year_counts.items())) or '(none)'))
    if dates:
        print(f'Publication date range: {min(dates)} to {max(dates)}')
    if words:
        print(
            f'Words per article: min={min(words)}, median={sorted(words)[len(words)//2]}, max={max(words)}')
        print(
            f'Total words (all existing .txt files in inventory): {sum(words):,}')
    counts = Counter(x['issue'] for x in flags)
    print('Flags: ' + (', '.join(f'{k}={v}' for k,
          v in sorted(counts.items())) or 'none'))
    print(f'Detailed flags: {out.relative_to(ROOT)}')
    if flags:
        print('\nFirst 15 flags:')
        for item in flags[:15]:
            print(f"  {item['slug']}: {item['issue']} — {item['detail']}")
    print('\nNote: This is an automated screening, not proof of archive completeness or extraction fidelity.')


if __name__ == '__main__':
    main()
