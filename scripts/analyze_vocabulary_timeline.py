#!/usr/bin/env python3
"""
Analyze vocabulary development in Mistral's news corpus.

Outputs:
    vocabulary_timeline.csv
    vocabulary_articles.csv
    vocabulary_categories.csv

Aggregation:
    monthly, quarterly (default), yearly

Usage:
    python scripts/analyze_vocabulary_timeline.py
    python scripts/analyze_vocabulary_timeline.py --period monthly
    python scripts/analyze_vocabulary_timeline.py --period yearly
"""

import argparse
import csv
import json
import re

from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


TOKEN_PATTERN = re.compile(
    r"[a-z]+(?:[-'][a-z]+)*",
    flags=re.IGNORECASE
)


def tokenize(text):
    return TOKEN_PATTERN.findall(text.lower())


def normalize_phrase(phrase):
    return tuple(tokenize(phrase))


def period_label(date, aggregation):
    if aggregation == "monthly":
        return date.strftime("%Y-%m")

    if aggregation == "quarterly":
        quarter = (date.month - 1) // 3 + 1
        return f"{date.year}-Q{quarter}"

    if aggregation == "yearly":
        return str(date.year)

    raise ValueError(f"Unknown aggregation: {aggregation}")


def parse_date(value):
    value = str(value).strip()

    if not value:
        raise ValueError("Empty publication date")

    # Handles YYYY-MM-DD and ISO timestamps.
    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError:
        pass

    # Handles dates with additional trailing text.
    match = re.search(r"\d{4}-\d{2}-\d{2}", value)

    if match:
        return datetime.strptime(
            match.group(),
            "%Y-%m-%d"
        )

    raise ValueError(f"Cannot parse date: {value}")


def find_column(fieldnames, candidates):
    lookup = {
        name.lower().strip(): name
        for name in fieldnames
    }

    for candidate in candidates:
        if candidate in lookup:
            return lookup[candidate]

    return None


def load_inventory(path):
    with path.open(
        newline="",
        encoding="utf-8-sig"
    ) as file:
        reader = csv.DictReader(file)

        fields = reader.fieldnames or []

        date_column = find_column(
            fields,
            [
                "published_analysis",
                "published",
                "publication_date",
                "published_date",
                "date",
                "date_published"
            ]
        )

        slug_column = find_column(
            fields,
            [
                "slug",
                "article_slug",
                "filename",
                "file",
                "path",
                "url"
            ]
        )

        if not date_column or not slug_column:
            raise ValueError(
                "Could not identify inventory columns.\n"
                f"Available columns: {fields}\n"
                f"Date column: {date_column}\n"
                f"Article identifier: {slug_column}"
            )

        inventory = {}

        for row in reader:
            identifier = row[slug_column].strip()

            if "/" in identifier:
                identifier = identifier.rstrip("/").split("/")[-1]

            identifier = Path(identifier).stem

            try:
                date = parse_date(row[date_column])
            except ValueError:
                print(
                    f"WARNING: Skipping invalid date "
                    f"for {identifier}"
                )
                continue

            inventory[identifier] = date

    return inventory


def load_dictionary(path):
    with path.open(encoding="utf-8") as file:
        dictionary = json.load(file)

    entries = []

    for group, categories in dictionary.items():
        for category, phrases in categories.items():
            for phrase in phrases:
                entries.append({
                    "group": group,
                    "category": category,
                    "term": phrase,
                    "tokens": normalize_phrase(phrase)
                })

    return entries


def count_phrase(tokens, phrase_tokens):
    """
    Count exact token-sequence matches.

    Overlapping occurrences of the same phrase
    are counted.
    """
    length = len(phrase_tokens)

    if not length:
        return 0

    return sum(
        tokens[i:i + length] == phrase_tokens
        for i in range(len(tokens) - length + 1)
    )


def write_csv(path, rows, columns):
    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with path.open(
        "w",
        newline="",
        encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=columns
        )

        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed")
    )

    parser.add_argument(
        "--inventory",
        type=Path,
        default=Path("results/corpus_inventory.csv")
    )

    parser.add_argument(
        "--dictionary",
        type=Path,
        default=Path("analysis/vocabulary/dictionary.json")
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("analysis/vocabulary")
    )

    parser.add_argument(
        "--period",
        choices=["monthly", "quarterly", "yearly"],
        default="quarterly"
    )
    parser.add_argument(
        "--corpus",
        choices=["news", "expanded", "corporate"],
        default="expanded"
    )

    parser.add_argument(
        "--corporate-input",
        type=Path,
        default=Path("data/corporate/sovereign-ai/processed")
    )

    parser.add_argument(
        "--corporate-inventory",
        type=Path,
        default=Path("data/corporate/sovereign-ai/inventory.csv")
    )

    args = parser.parse_args()

    entries = load_dictionary(args.dictionary)

    documents = []

    if args.corpus in ("news", "expanded"):
        news_inventory = load_inventory(args.inventory)

        for path in sorted(args.input.rglob("*.txt")):
            documents.append({
                "path": path,
                "slug": path.stem,
                "date": news_inventory.get(path.stem),
                "source_type": "news_article"
            })

    if args.corpus in ("corporate", "expanded"):
        corporate_inventory = load_inventory(
            args.corporate_inventory
        )

        for path in sorted(args.corporate_input.rglob("*.txt")):
            documents.append({
                "path": path,
                "slug": path.stem,
                "date": corporate_inventory.get(path.stem),
                "source_type": "corporate_website"
            })

    if not documents:
        raise SystemExit("No documents found")

    # Period-level corpus statistics.
    period_stats = defaultdict(
        lambda: {
            "articles": 0,
            "words": 0
        }
    )

    # Individual term statistics.
    term_stats = defaultdict(
        lambda: {
            "occurrences": 0,
            "articles": 0
        }
    )

    # Category statistics.
    category_stats = defaultdict(
        lambda: {
            "occurrences": 0,
            "articles": 0
        }
    )

    article_rows = []

    processed = 0
    unmatched = []

    for document in documents:
        path = document["path"]
        slug = document["slug"]
        date = document["date"]
        source_type = document["source_type"]

        if date is None:
            unmatched.append(f"{source_type}: {slug}")
            continue

        period = period_label(
            date,
            args.period
        )

        text = path.read_text(
            encoding="utf-8"
        )

        tokens = tokenize(text)
        word_count = len(tokens)

        processed += 1

        period_stats[period]["articles"] += 1
        period_stats[period]["words"] += word_count

        # Track matched token positions per category.
        # This prevents overlapping expressions from
        # inflating category totals.
        category_positions = defaultdict(set)

        for entry in entries:

            phrase = list(entry["tokens"])

            phrase_length = len(phrase)

            occurrences = count_phrase(
                tokens,
                phrase
            )

            term_key = (
                period,
                entry["group"],
                entry["category"],
                entry["term"]
            )

            term_stats[term_key]["occurrences"] += occurrences

            if occurrences:
                term_stats[term_key]["articles"] += 1

            article_rows.append({
                "slug": slug,
                "source_type": source_type,
                "date": date.date().isoformat(),
                "period": period,
                "aggregation": args.period,
                "group": entry["group"],
                "category": entry["category"],
                "term": entry["term"],
                "occurrences": occurrences,
                "word_count": word_count
            })

            # Collect matched positions for category totals.
            for i in range(
                len(tokens) - phrase_length + 1
            ):
                if tokens[i:i + phrase_length] == phrase:
                    key = (
                        entry["group"],
                        entry["category"]
                    )

                    category_positions[key].update(
                        range(i, i + phrase_length)
                    )

        for (group, category), positions in category_positions.items():
            key = (
                period,
                group,
                category
            )

            category_stats[key]["occurrences"] += len(
                positions
            )

            if positions:
                category_stats[key]["articles"] += 1

    # ------------------------------------------
    # Individual term timeline
    # ------------------------------------------

    timeline_rows = []

    for period in sorted(period_stats):
        stats = period_stats[period]

        for entry in entries:
            key = (
                period,
                entry["group"],
                entry["category"],
                entry["term"]
            )

            counts = term_stats[key]

            timeline_rows.append({
                "period": period,
                "aggregation": args.period,
                "group": entry["group"],
                "category": entry["category"],
                "term": entry["term"],
                "occurrences": counts["occurrences"],
                "articles_with_term": counts["articles"],
                "total_articles": stats["articles"],
                "total_words": stats["words"],
                "per_1000_words": round(
                    counts["occurrences"]
                    / stats["words"] * 1000,
                    4
                ) if stats["words"] else 0,
                "article_prevalence_pct": round(
                    counts["articles"]
                    / stats["articles"] * 100,
                    2
                ) if stats["articles"] else 0
            })

    # ------------------------------------------
    # Category timeline
    # ------------------------------------------

    category_rows = []

    categories = sorted({
        (entry["group"], entry["category"])
        for entry in entries
    })

    for period in sorted(period_stats):
        stats = period_stats[period]

        for group, category in categories:
            key = (
                period,
                group,
                category
            )

            counts = category_stats[key]

            category_rows.append({
                "period": period,
                "aggregation": args.period,
                "group": group,
                "category": category,
                "matched_token_positions": counts["occurrences"],
                "articles_with_category": counts["articles"],
                "total_articles": stats["articles"],
                "total_words": stats["words"],
                "per_1000_words": round(
                    counts["occurrences"]
                    / stats["words"] * 1000,
                    4
                ) if stats["words"] else 0,
                "article_prevalence_pct": round(
                    counts["articles"]
                    / stats["articles"] * 100,
                    2
                ) if stats["articles"] else 0
            })

    # ------------------------------------------
    # Write outputs
    # ------------------------------------------

    write_csv(
        args.output / "vocabulary_timeline.csv",
        timeline_rows,
        [
            "period",
            "aggregation",
            "group",
            "category",
            "term",
            "occurrences",
            "articles_with_term",
            "total_articles",
            "total_words",
            "per_1000_words",
            "article_prevalence_pct"
        ]
    )

    write_csv(
        args.output / "vocabulary_articles.csv",
        article_rows,
        [
            "slug",
            "source_type",
            "date",
            "period",
            "aggregation",
            "group",
            "category",
            "term",
            "occurrences",
            "word_count"
        ]
    )

    write_csv(
        args.output / "vocabulary_categories.csv",
        category_rows,
        [
            "period",
            "aggregation",
            "group",
            "category",
            "matched_token_positions",
            "articles_with_category",
            "total_articles",
            "total_words",
            "per_1000_words",
            "article_prevalence_pct"
        ]
    )

    print()
    print("Vocabulary analysis complete")
    print("----------------------------")
    print(f"Aggregation: {args.period}")
    print(f"Corpus: {args.corpus}")
    print(f"Documents processed: {processed}")
    print(f"Unmatched files: {len(unmatched)}")
    print(f"Dictionary entries: {len(entries)}")
    print(f"Periods: {len(period_stats)}")
    print(f"Output directory: {args.output.resolve()}")

    if unmatched:
        print("\nUnmatched article files:")
        for slug in unmatched[:20]:
            print(f"  - {slug}")


if __name__ == "__main__":
    main()
