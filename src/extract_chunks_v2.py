"""
Phase 4, v2: extraction using position-based region boundaries.

Duplicate of extract_chunks.py, kept as a separate file so both versions
can be run and compared side by side, rather than overwriting the
original.

The difference: the original version builds chunk regions between whole
pages, so when a header doesn't start at the very top of a page (about
58% of headers in this book don't), everything above it on that page
gets misattributed, most visibly when several short headers share one
page and all get assigned the entire page's text, producing identical
duplicate content under different titles (e.g. the "Seafood" / "Fat" /
"Eggs" headers all sharing page 42).

This version tracks each header's exact position on the page (page
number AND vertical coordinate), not just the page number, and crops
text between one header's exact position and the next header's exact
position, even when both fall on the same page.

Usage:
  python src/extract_chunks_v2.py data/raw/salt-fat-acid-heat.pdf
"""

import json
import sys
from pathlib import Path

import pdfplumber

# Same top-level sections as the original, unaffected by this change,
# these are still whole-page boundaries confirmed in Phases 1-4.
SECTIONS = [
    ("Salt", 26, 70, "theory"),
    ("Fat", 71, 113, "theory"),
    ("Acid", 114, 142, "theory"),
    ("Heat", 143, 198, "theory"),
    ("What to Cook", 199, 201, "theory"),
    ("Kitchen Basics", 202, 220, "theory"),
    ("Salads", 221, 248, "recipe"),
    ("Dressings", 249, 267, "recipe"),
    ("Vegetables", 268, 286, "recipe"),
    ("Stock and Soups", 287, 298, "recipe"),
    ("Beans, Grains, and Pasta", 299, 325, "recipe"),
    ("Eggs", 326, 334, "recipe"),
    ("Fish", 335, 341, "recipe"),
    ("Thirteen Ways of Looking at a Chicken", 342, 373, "recipe"),
    ("Meat", 374, 391, "recipe"),
    ("Sauces", 392, 426, "recipe"),
    ("Butter-and-Flour Doughs", 427, 442, "recipe"),
    ("Sweets", 443, 471, "recipe"),
    ("Cooking Lessons", 472, 475, "theory"),
    ("Suggested Menus", 476, 479, "theory"),
]

MAX_CHUNK_WORDS = 600
OVERLAP_WORDS = 60


def find_bold_headers(pdf, start_page: int, end_page: int):
    """
    Archer-Bold lines within a page range, now returned as
    (page_num, top, text) instead of (page_num, text). The 'top' value
    (vertical position on the page, in points from the top) is what
    lets regions be sliced within a page, not just between pages.
    """
    headers = []
    for page_num in range(start_page, end_page + 1):
        page = pdf.pages[page_num - 1]
        words = page.extract_words(extra_attrs=["size", "fontname"])
        bold = [w for w in words if "Archer-Bold" in w["fontname"]]
        if not bold:
            continue
        lines = {}
        for w in bold:
            key = round(w["top"])
            lines.setdefault(key, []).append(w)
        for key in sorted(lines):
            line_words = sorted(lines[key], key=lambda w: w["x0"])
            text = " ".join(w["text"] for w in line_words)
            if len(text) >= 3:
                headers.append((page_num, key, text))
    return headers


def extract_region_text(pdf, start_page: int, start_top: float, end_page: int, end_top: float) -> str:
    """
    Extracts text for a region bounded by an exact (page, top) start and
    (page, top) end, instead of whole pages.

    - Single-page region (start_page == end_page): one crop, from
      start_top to end_top on that page.
    - Multi-page region: first page cropped from start_top to the
      bottom of the page, middle pages taken in full, last page cropped
      from the top of the page down to end_top.
    """
    page_texts = []
    for p in range(start_page, end_page + 1):
        page = pdf.pages[p - 1]
        top = start_top if p == start_page else 0
        bottom = end_top if p == end_page else page.height
        if top >= bottom:
            continue  # degenerate slice, nothing real on this page for this region
        cropped = page.crop((0, top, page.width, bottom))
        t = cropped.extract_text()
        if t:
            page_texts.append(t)
    return "\n\n".join(page_texts).strip()


def fix_drop_cap(text: str) -> str:
    """Unchanged from the original, see extract_chunks.py for the full
    explanation of why this exists."""
    lines = text.split("\n")
    for i, line in enumerate(lines[:5]):
        stripped = line.strip()
        if len(stripped) == 1 and stripped.isalpha() and stripped.isupper():
            del lines[i]
            rest = "\n".join(lines).lstrip()
            return stripped + rest
    return text


def split_long_text(text: str, max_words: int = MAX_CHUNK_WORDS, overlap: int = OVERLAP_WORDS):
    """Unchanged from the original."""
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    pieces, current, current_words = [], [], 0

    for para in paragraphs:
        words_in_para = len(para.split())
        if current_words + words_in_para > max_words and current:
            pieces.append("\n\n".join(current))
            tail = " ".join("\n\n".join(current).split()[-overlap:])
            current = [tail, para]
            current_words = len(tail.split()) + words_in_para
        else:
            current.append(para)
            current_words += words_in_para

    if current:
        pieces.append("\n\n".join(current))
    return pieces if pieces else [text]


def extract_chunks(pdf_path: str):
    chunks = []
    with pdfplumber.open(pdf_path) as pdf:
        for section_name, start, end, chunk_type in SECTIONS:
            headers = find_bold_headers(pdf, start, end)
            section_end_top = pdf.pages[end - 1].height

            # regions are now (start_page, start_top, end_page, end_top, title)
            regions = []

            if not headers:
                regions.append((start, 0, end, section_end_top, f"{section_name} (introduction)"))
            else:
                first_page, first_top, _ = headers[0]
                # intro region: whatever's above the first header, often
                # empty (just page margin) when a section starts right at
                # its first header, the emptiness filter below drops those
                regions.append((start, 0, first_page, first_top, f"{section_name} (introduction)"))

                for i, (page_num, top, title) in enumerate(headers):
                    if i + 1 < len(headers):
                        next_page, next_top, _ = headers[i + 1]
                        region_end_page, region_end_top = next_page, next_top
                    else:
                        region_end_page, region_end_top = end, section_end_top
                    regions.append((page_num, top, region_end_page, region_end_top, title))

            for region_index, (rs_page, rs_top, re_page, re_top, title) in enumerate(regions):
                full_text = extract_region_text(pdf, rs_page, rs_top, re_page, re_top)
                full_text = fix_drop_cap(full_text)
                if not full_text:
                    continue  # e.g. an intro region with nothing above the header

                pieces = split_long_text(full_text)
                for j, piece in enumerate(pieces):
                    slug = f"{section_name}-{region_index}-{j}".lower().replace(" ", "_").replace(",", "")
                    chunks.append({
                        "id": slug,
                        "type": chunk_type,
                        "section": section_name,
                        "title": title,
                        "page_start": rs_page,
                        "page_end": re_page,
                        "text": piece.strip(),
                    })
    return chunks


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python src/extract_chunks_v2.py <path-to-pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not Path(pdf_path).exists():
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    chunks = extract_chunks(pdf_path)

    out_path = Path("data/processed/chunks_v2.jsonl")
    with open(out_path, "w") as f:
        for c in chunks:
            f.write(json.dumps(c) + "\n")

    theory = [c for c in chunks if c["type"] == "theory"]
    recipe = [c for c in chunks if c["type"] == "recipe"]
    print(f"Total chunks: {len(chunks)}")
    print(f"  theory: {len(theory)}")
    print(f"  recipe: {len(recipe)}")
    print(f"Saved to {out_path}")
