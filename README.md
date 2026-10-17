# Mistral news discourse — corpus collector (Phase 1–2 starter)

This is an **initial collector**, not yet a validated research corpus. It discovers article URLs from the live news overview and available sitemaps, then saves HTML, extracted article text, and an inventory.

## Install and pilot

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/collect.py --limit 5
```

Inspect `data/processed/*.txt` alongside the corresponding original pages. Check for missing paragraphs, duplicated text, navigation text, correct dates and authors. The `main` or `article` selector is **not guaranteed** to extract the correct article body on every page.

If the pilot works, run:

```bash
python scripts/collect.py
```

The script reuses saved HTML by default. Use `--refresh` to redownload. Use `--delay 2` for slower requests. Stop if the website disallows automated collection, or if it returns rate-limit responses. Respect robots.txt and site terms; avoid aggressive scraping.

## Data

- `results/discovered_urls.txt`: discovered URLs
- `results/corpus_inventory.csv`: metadata, extraction method, word counts, errors
- `data/raw/*.html`: raw retrieved page HTML
- `data/processed/*.txt`: candidate article-body text

## Known limitations / next steps

1. **Discovery may be incomplete** if the site loads articles through client-side JavaScript or paginates without server-rendered links. Compare discovered URLs with archive counts and Wayback captures.
2. **Dates can be absent**: inspect metadata and fall back to page-specific date extraction, rather than silently inventing dates.
3. **Article body extraction is provisional**. Validate a cross-year sample before analysing.
4. **Historical comparison is not implemented yet**. Next build a Wayback capture inventory, retrieve earliest usable captures, compare extracted bodies, and flag differences for human review.
5. **Vocabulary analysis is not implemented yet**. Only build it after validating the corpus.
6. **Current pages may have been edited**. Archive comparisons can establish stability only across available captures.
7. News posts with joint authorship and non-English text need explicit inclusion rules.

## Scope

English-language official Mistral news posts, 2023 through collection date; non-English and joint-authored posts should be flagged for explicit decisions. No conclusions about the whole discourse until coverage is verified.
