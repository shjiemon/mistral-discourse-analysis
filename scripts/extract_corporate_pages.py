from pathlib import Path
from bs4 import BeautifulSoup
import re


# Project directories
ROOT = Path(__file__).resolve().parents[1]

SOURCE_DIR = ROOT / "data/corporate/sovereign-ai/raw"
OUTPUT_DIR = ROOT / "data/corporate/sovereign-ai/processed"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


FILES = [
    "sovereign-ai.html",
    "products.html",
    "our-method.html",
    "use-cases.html",
]


def extract_text(html):
    soup = BeautifulSoup(html, "html.parser")

    # Remove non-content elements.
    for element in soup(
        ["script", "style", "noscript", "svg", "template"]
    ):
        element.decompose()

    # Prefer the page's main content.
    main = soup.find("main")

    if main is None:
        raise ValueError(
            "No <main> element found. "
            "Inspect the HTML before extracting."
        )

    # Remove navigation and other interface elements
    # contained within <main>.
    for element in main(
        ["nav", "footer", "header", "button"]
    ):
        element.decompose()

    # Extract text, preserving block boundaries.
    text = main.get_text(separator="\n", strip=True)

    # Normalize whitespace.
    lines = []

    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()

        if not line:
            continue

        # Remove consecutive identical lines.
        if lines and line == lines[-1]:
            continue

        lines.append(line)

    return "\n".join(lines)


def main():
    for filename in FILES:
        source = SOURCE_DIR / filename
        destination = OUTPUT_DIR / filename.replace(
            ".html", ".txt"
        )

        if not source.exists():
            print(f"MISSING: {source}")
            continue

        html = source.read_text(encoding="utf-8")

        try:
            text = extract_text(html)
        except ValueError as error:
            print(f"ERROR: {filename}: {error}")
            continue

        destination.write_text(
            text,
            encoding="utf-8"
        )

        print(
            f"{filename}: "
            f"{len(text.split())} words "
            f"-> {destination.name}"
        )


if __name__ == "__main__":
    main()