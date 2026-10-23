# Mistral AI — Discourse and Infrastructure Research

Research repository for *Mistral AI: Rethinking Technological Autonomy through Infrastructural Dependence*.

The project investigates how Mistral AI's proposition of technological autonomy has evolved since its founding, and how that proposition relates to its own infrastructural dependencies.

The research adopts a **technographic approach**, complemented by an exploratory vocabulary analysis of Mistral's public communications.

For research design, corpus construction, analytical procedures, and limitations, see [METHODOLOGY.md](METHODOLOGY.md).

## Repository contents

| Directory | Contents |
|---|---|
| `data/raw/` | Retrieved HTML of Mistral news articles |
| `data/processed/` | Extracted news articles in Markdown and plain text |
| `data/corporate/sovereign-ai/` | Four supplementary corporate webpages |
| `data/wayback/` | Historical material collected through the Wayback Machine |
| `analysis/vocabulary/` | Dictionary, vocabulary results, and visualization |
| `scripts/` | Collection, extraction, analysis, and visualization scripts |
| `results/` | Corpus inventories and intermediate collection results |

The primary corpus contains **89 English-language Mistral news articles** (September 2023–October 2026), supplemented by four corporate webpages captured in October 2026.

## Setup

Requires Python 3.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Reproduce the vocabulary analysis

Run the analysis using the preserved corpus:

```bash
python scripts/analyze_vocabulary_timeline.py --corpus news --output analysis/vocabulary/news

python scripts/analyze_vocabulary_timeline.py --corpus corporate --output analysis/vocabulary/corporate

python scripts/analyze_vocabulary_timeline.py --corpus expanded --output analysis/vocabulary/expanded
```

The three configurations analyze news articles, corporate webpages, or both combined.

Generate the historical vocabulary visualization:

```bash
python scripts/plot_vocabulary_timeline.py
```

The resulting figure is saved to:

`analysis/vocabulary/news/autonomy_vocabulary_v1.png`

## Collection and supplementary scripts

The news collector can be run using:

```bash
python scripts/collect.py
```

To test collection on a small sample:

```bash
python scripts/collect.py --limit 5
```

**Note:** Recollecting live webpages may produce different results. Use the preserved corpus to reproduce the existing analysis.

Extract text from the preserved corporate HTML captures:

```bash
python scripts/extract_corporate_pages.py
```

The repository also includes scripts for corpus checks, exploratory vocabulary analysis, and Wayback investigations.

Browser-based Wayback investigations require Playwright's Chromium browser:

```bash
python -m playwright install chromium
```

## Research status

The news corpus, supplementary corporate-page collection, and exploratory vocabulary analysis have been assembled.

The broader technographic investigation of Mistral's technical offerings, partnerships, and infrastructural dependencies is ongoing.

The vocabulary analysis identifies changes in corporate discourse; it does not independently establish changes in technological autonomy.

See [METHODOLOGY.md](METHODOLOGY.md) for methodological qualifications.
