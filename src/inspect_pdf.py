"""
Phase 1: inspect the book.

Run this before writing any chunking code. It tells you:
  - how many pages, and whether the text layer is usable
  - a text sample from an early page and a late page (recipes are usually
    near the end, theory near the front, so this shows both)
  - a rough guess at where headers/chapter breaks are, based on short,
    capitalized, standalone lines

Usage:
  python src/inspect_pdf.py data/raw/your-book.pdf
"""

import sys
from pathlib import Path

import pdfplumber


def sample_pages(pdf_path: str, page_numbers: list[int]) -> None:
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        print()
        print("=" * 60)
        print(f"TEXT SAMPLES (book has {total} pages)")
        print("=" * 60)
        for n in page_numbers:
            if n < 1 or n > total:
                continue
            text = pdf.pages[n - 1].extract_text() or "(no extractable text on this page)"
            print(f"\n--- page {n} ---")
            print(text[:800])


def guess_headers(pdf_path: str, max_pages: int = 40) -> None:
    """
    Rough pass at finding section/chapter headers: short lines, often
    capitalized, that stand alone. Not meant to be exact, just enough to
    tell you whether header-based chunking is realistic for this book,
    and to give you real candidate strings to check by eye.
    """
    print()
    print("=" * 60)
    print(f"HEADER CANDIDATES (scanned first {max_pages} pages)")
    print("=" * 60)
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages[:max_pages], start=1):
            text = page.extract_text() or ""
            for line in text.split("\n"):
                stripped = line.strip()
                if 3 <= len(stripped) <= 60 and (
                    stripped.isupper() or stripped.istitle()
                ):
                    print(f"page {i}: {stripped}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python src/inspect_pdf.py <path-to-pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not Path(pdf_path).exists():
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
    sample_pages(pdf_path, page_numbers=[1, 5, max(1, total - 10)])

    guess_headers(pdf_path)