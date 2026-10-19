#!/usr/bin/env python3
"""Explore vocabulary in Mistral's news announcement corpus."""

import argparse
import csv
import re
from collections import Counter
from pathlib import Path

STOPWORDS = set("""
a an and are as at be been being but by can could did do does for
from had has have having he her here hers him his how i if in into
is it its itself may me might more most must my no nor not of on
or our ours out over she should so some such than that the their
theirs them themselves there these they this those through to too
under until up us very was we were what when where which while who
whom why will with would you your yours
""".split())

VOCABULARY = {
    "openness": [
        "open", "openness", "openly",
        "open-source", "open-weight", "open-weights",
    ],
    "choice": [
        "choice", "choices", "choose", "choosing",
        "freedom", "flexibility", "flexible",
    ],
    "control": [
        "control", "controls", "controlled", "controlling",
        "ownership", "own",
    ],
    "independence_autonomy": [
        "independent", "independence", "independently",
        "autonomy", "autonomous",
        "self-host", "self-hosted", "self-hosting",
    ],
    "sovereignty": [
        "sovereign", "sovereignty",
    ],
}

TOKEN_PATTERN = re.compile(
    r"[a-z]+(?:[-'][a-z]+)*",
    flags=re.IGNORECASE,
)


def tokenize(text):
    return TOKEN_PATTERN.findall(text.lower())


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed"),
        help="Directory containing processed articles",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("analysis/vocabulary"),
        help="Output directory",
    )
    args = parser.parse_args()

    files = sorted(
        path for path in args.input.rglob("*.txt")
        if path.is_file()
    )

    if not files:
        raise SystemExit(
            f"No .txt files found in {args.input}. "
            "Check the directory and file extensions."
        )

    word_counts = Counter()
    word_documents = Counter()

    bigram_counts = Counter()
    bigram_documents = Counter()

    vocabulary_counts = Counter()
    vocabulary_documents = Counter()

    vocabulary_lookup = {
        term: category
        for category, terms in VOCABULARY.items()
        for term in terms
    }

    for path in files:
        text = path.read_text(encoding="utf-8")
        tokens = tokenize(text)

        # Remove stopwords for exploratory word frequencies.
        words = [
            token for token in tokens
            if token not in STOPWORDS
        ]

        word_counts.update(words)
        word_documents.update(set(words))

        # Keep adjacent meaningful words for exploratory bigrams.
        bigrams = [
            f"{left} {right}"
            for left, right in zip(tokens, tokens[1:])
            if left not in STOPWORDS
            and right not in STOPWORDS
        ]

        bigram_counts.update(bigrams)
        bigram_documents.update(set(bigrams))

        # Vocabulary matching uses the original token sequence.
        matched_terms = [
            token for token in tokens
            if token in vocabulary_lookup
        ]

        vocabulary_counts.update(matched_terms)
        vocabulary_documents.update(set(matched_terms))

    word_rows = [
        {
            "word": word,
            "total_occurrences": count,
            "document_frequency": word_documents[word],
        }
        for word, count in word_counts.most_common(200)
    ]

    bigram_rows = [
        {
            "bigram": bigram,
            "total_occurrences": count,
            "document_frequency": bigram_documents[bigram],
        }
        for bigram, count in bigram_counts.most_common(100)
    ]

    vocabulary_rows = [
        {
            "category": category,
            "term": term,
            "total_occurrences": vocabulary_counts[term],
            "document_frequency": vocabulary_documents[term],
        }
        for category, terms in VOCABULARY.items()
        for term in terms
    ]

    write_csv(
        args.output / "word_frequencies.csv",
        word_rows,
        ["word", "total_occurrences", "document_frequency"],
    )

    write_csv(
        args.output / "bigram_frequencies.csv",
        bigram_rows,
        ["bigram", "total_occurrences", "document_frequency"],
    )

    write_csv(
        args.output / "autonomy_vocabulary.csv",
        vocabulary_rows,
        [
            "category",
            "term",
            "total_occurrences",
            "document_frequency",
        ],
    )

    print(f"Processed {len(files)} articles.")
    print(f"Results saved to: {args.output.resolve()}")


if __name__ == "__main__":
    main()