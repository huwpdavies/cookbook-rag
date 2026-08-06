"""
Phase 4: extraction.

Turns the raw PDF into tagged, stored chunks using what Phases 1-3 found:

- Chunk boundaries come from Archer-Bold lines (the book's real header/
  title font), not the all-caps guess from Phase 1. Font-based detection
  catches recipe titles (title-case, missed by the all-caps rule) and
  skips the two false positives (a footnote marker, an epigraph
  attribution) on its own.
- Every top-level section (Salt, Fat, Salads, Dressings, ...) is tagged
  theory or recipe using the page ranges confirmed in Phase 3, refined
  here with exact recipe-category boundaries.
- One chunking method is used across the whole book, not a separate
  recipe-specific splitter. Recipe titles and in-recipe sub-headings
  (e.g. the variations inside "Avocado Salad Matrix") share the same
  font and size, so there's no reliable signal to tell them apart.
  Treating each as its own chunk is a fine outcome here anyway: a
  variation like "Avocado" is still a complete, retrievable unit for
  ingredient search.
- Long sections get a secondary paragraph-based split with overlap, so
  no single chunk runs too long for retrieval to be precise.
- A drop-cap fix reassembles the stray first letter that PDF extraction
  splits off the top of each chapter's opening paragraph.

Usage:
  python src/extract_chunks.py data/raw/salt-fat-acid-heat.pdf
"""

import json
import re
import sys
from pathlib import Path

import pdfplumber

# Top-level sections, confirmed in Phases 1-3 and refined here with exact
# recipe-category page numbers pulled from the font-based scan.
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

MAX_CHUNK_WORDS = 600  # long sections get split further, with overlap
OVERLAP_WORDS = 60


def find_bold_headers(pdf, start_page: int, end_page: int):
    """Archer-Bold lines within a page range: the chunk-boundary signal."""
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
            if len(text) >= 3:  # drop stray single-character bold fragments
                headers.append((page_num, text))
    return headers


def fix_drop_cap(text: str) -> str:
    """
    Reassembles the drop-capped first letter of a chapter's opening
    paragraph. The glyph is oversized and spans several normal text
    lines, so PDF extraction places it on its own line near the top of
    the text, not necessarily the very first line, and the real opening
    word is left missing that letter (e.g. 'rowing up' instead of
    'Growing up'). Search the first few lines for a lone capital letter,
    remove it from wherever it landed, and prepend it to the text.
    """
    lines = text.split("\n")
    for i, line in enumerate(lines[:5]):
        stripped = line.strip()
        if len(stripped) == 1 and stripped.isalpha() and stripped.isupper():
            del lines[i]
            rest = "\n".join(lines).lstrip()
            return stripped + rest
    return text


def split_long_text(text: str, max_words: int = MAX_CHUNK_WORDS, overlap: int = OVERLAP_WORDS):
    """Paragraph-based split for sections too long for one chunk, with a
    small word overlap at each seam so an idea crossing the boundary
    isn't lost entirely on either side."""
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

            # region list: (region_start, region_end, title) built entirely
            # within this section, so nothing bleeds across a section
            # boundary and lead-in prose before the first header isn't lost
            regions = []
            if not headers or headers[0][0] > start:
                first_header_page = headers[0][0] if headers else end + 1
                regions.append((start, min(first_header_page - 1, end), f"{section_name} (introduction)"))
            for i, (page_num, title) in enumerate(headers):
                region_end = headers[i + 1][0] - 1 if i + 1 < len(headers) else end
                region_end = max(region_end, page_num)
                regions.append((page_num, region_end, title))

            for region_start, region_end, title in regions:
                page_texts = []
                for p in range(region_start, region_end + 1):
                    t = pdf.pages[p - 1].extract_text()
                    if t:
                        page_texts.append(t)
                full_text = "\n\n".join(page_texts).strip()
                full_text = fix_drop_cap(full_text)
                if not full_text:
                    continue

                pieces = split_long_text(full_text)
                for j, piece in enumerate(pieces):
                    slug = f"{section_name}-{region_start}-{j}".lower().replace(" ", "_").replace(",", "")
                    chunks.append({
                        "id": slug,
                        "type": chunk_type,
                        "section": section_name,
                        "title": title,
                        "page_start": region_start,
                        "page_end": region_end,
                        "text": piece.strip(),
                    })
    return chunks


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python src/extract_chunks.py <path-to-pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not Path(pdf_path).exists():
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    chunks = extract_chunks(pdf_path)

    out_path = Path("data/processed/chunks.jsonl")
    with open(out_path, "w") as f:
        for c in chunks:
            f.write(json.dumps(c) + "\n")

    theory = [c for c in chunks if c["type"] == "theory"]
    recipe = [c for c in chunks if c["type"] == "recipe"]
    print(f"Total chunks: {len(chunks)}")
    print(f"  theory: {len(theory)}")
    print(f"  recipe: {len(recipe)}")
    print(f"Saved to {out_path}")
