# Cookbook RAG: Salt, Fat, Acid, Heat

RAG pipeline over *Salt, Fat, Acid, Heat* by Samin Nosrat: a
theory-heavy cookbook (technique and explanation in Part One) with a
large recipe section (Part Two). Built to search both parts, tagged
separately, and to eventually link a recipe back to the technique the
book explains for it.

For the full decision log, what was tried, what was found, and why
each choice was made, see [`PROJECT_PLAN.md`](PROJECT_PLAN.md). This
file is just setup and how to run each script.

## Phases

- [x] Phase 1: setup (this folder, dependencies, `.env`)
- [x] Phase 2: inspect the book (`src/inspect_pdf.py`)
- [x] Phase 3: decide the chunking strategy
- [x] Phase 4: extraction script (`src/extract_chunks.py`)
- [x] Phase 5: vector store (`src/build_vector_store.py`)
- [ ] Phase 6: basic Q&A over the store
- [ ] Phase 7: cross-reference recipes to the technique sections
- [ ] Phase 8: front end

## Setup

```bash
cd cookbook-rag
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # then paste your Anthropic API key in
```

Drop the book PDF into `data/raw/` before running anything below.

## Phase 2: inspect the book

```bash
python src/inspect_pdf.py data/raw/salt-fat-acid-heat.pdf
```

Prints page count, whether the text layer is usable, text samples from
the front/middle/back, and a rough list of header candidates. Check
this output by eye before trusting any extraction step downstream,
it's what caught the book's image-only chapter dividers and drop-cap
quirk in the first place.

## Phase 4: extract and chunk

```bash
python src/extract_chunks.py data/raw/salt-fat-acid-heat.pdf
```

Writes `data/processed/chunks.jsonl`, one JSON object per chunk, each
tagged with type (`theory` / `recipe`), section, title, and page range.
Section boundaries and the chunking approach are hardcoded based on
what Phases 2-4 found by inspecting the actual book, see
`PROJECT_PLAN.md` for why.

## Phase 5: build the vector store

```bash
python src/build_vector_store.py
```

Loads `chunks.jsonl` into a persistent Chroma collection at
`data/processed/chroma_db`, using Chroma's default embedding function
(`all-MiniLM-L6-v2`). This downloads the model on first run, real
internet access is required, this step will fail in a network-
restricted environment. Re-running the script rebuilds the collection
from scratch each time, so it's always in sync with the current
`chunks.jsonl`.

## Next

Phase 6 wires retrieval up to an LLM call: take a question, pull the
relevant chunks from Chroma, and have the model produce an answer
grounded in what was actually retrieved.
