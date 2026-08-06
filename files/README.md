# Cookbook RAG

RAG project over a theory-heavy cookbook: mostly technique and explanation,
with a recipe section near the end. Built to search both parts and to link
a recipe back to the technique the book explains for it.

## Phases

- [ ] Phase 0: setup (this folder, dependencies, `.env`)
- [ ] Phase 1: inspect the book (`src/inspect_pdf.py`)
- [ ] Phase 2: extract and split into theory chunks and recipe chunks
- [ ] Phase 3: load into Chroma, tagged `theory` / `recipe`
- [ ] Phase 4: basic Q&A over the store
- [ ] Phase 5: cross-reference recipes to the technique sections
- [ ] Phase 6: Streamlit front end

## Setup

```bash
cd cookbook-rag
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # then paste your Anthropic API key in
```

## Phase 1: inspect the book

Drop the PDF into `data/raw/`, then run:

```bash
python src/inspect_pdf.py data/raw/your-book.pdf
```

This prints:
- page count and whether the text layer is usable (garbled or empty means
  the book may need OCR)
- text samples from the front, middle, and back of the book
- a rough list of header candidates, to check whether the book's
  structure is regular enough to chunk on headers directly, or whether
  it needs manual section boundaries

Look at the output before writing any extraction code. If the header
guesses are close to the real chapter/section titles, header-based
chunking will work well. If they're noisy, the table of contents (first
few pages) is usually a more reliable source of section boundaries than
guessing from formatting.

## Next

Once Phase 1's output is checked by eye, Phase 2 builds two extraction
paths: one for the prose chapters (chunk by section), one for the recipe
pages at the back (chunk one recipe per entry).
