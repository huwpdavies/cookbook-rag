# Project Plan: Salt, Fat, Acid, Heat RAG

A running log of building a RAG pipeline over *Salt, Fat, Acid, Heat* by Samin Nosrat.

## Phase 1: Setup

*Set up the project environment so extraction, storage, and
retrieval have a consistent place to read from and write to.*

Built the project folder (`data/raw`, `data/processed`, `src`), a
`requirements.txt`, and an `.env` template for the API key. Nothing
book-specific here, this is the same scaffold any RAG project starts
from.

## Phase 2: Inspect the book

*Check the raw source for extraction quality and structure
before writing any processing logic that depends on it.*

**What we ran:** `pdfinfo`, `pdffonts`, and a custom scan across all 530
pages, sampling text from the front, middle, and back, then flagging
short all-caps lines as candidate section headers.

**What we found:**

- Text layer is usable throughout. The two blank pages are cover art
  and a flyleaf, not a scanning problem.
- The header scan found 54 candidate lines, 52 of them real section
  titles that line up with the book's actual structure, giving
  page-numbered boundaries the book's own contents page doesn't have.
  The other 2 are false positives (footnote markers, an epigraph
  attribution), filtered by excluding short lines that start with
  punctuation.
- The four element-divider pages are images with no extractable text,
  a handful of pages hardcoded rather than detected. Drop caps also
  scramble the first letter of each chapter's opening paragraph, needs
  reassembly in code.
- The index, bibliography, and acknowledgements (pages 480-530) extract
  fine but are noise, excluded from the pipeline entirely.

**Result:** a page-numbered structural map of the whole book, built from
what's actually on the page rather than assumed from the book's genre or
table of contents.

## Phase 3: Chunking strategy

*Decide how to split the source into retrievable units,
since retrieval quality depends more on this than any other single step.*

**The format that drives this decision:** the book splits cleanly into
two kinds of content. Part One is continuous prose organized under real
subheadings, an argument that unfolds across a section. Part Two is a
large set of self-contained recipes, each with a title, an ingredient
list, and a method. These need different handling, since what makes a
chunk "correct" is different for each.

**Decision: hybrid chunking, one method per content type.**

- **Theory content (Salt, Fat, Acid, Heat, plus Kitchen Basics, Cooking
  Lessons, and Suggested Menus): structure-based chunking.**
  Cut along the subheadings found in Phase 2 (`WHAT IS SALT?`, `HOW SALT
  WORKS`, and so on), so each chunk is one complete unit of the book's
  own argument. Where a subsection runs long (Salt's subsections span 44
  pages), apply a secondary paragraph-based split inside it, with a
  little overlap at the seams so an idea that crosses a chunk boundary
  doesn't lose its thread.
- **Recipes (Salads through Sweets): content-aware chunking.** One
  recipe, one chunk, regardless of length. A recipe is a single unit,
  title, ingredients, and method belong together, and cutting one in
  half to fit a size rule would break the exact thing that makes it
  useful to retrieve.

Both paths write to the same schema (text, type tag, section, page
number), so everything downstream, storage, retrieval, Q&A, doesn't need
to know which method produced a given chunk.

**Other approaches considered, and why they don't fit here:**

| Approach | What it does | Why not used |
|---|---|---|
| Fixed-size chunking | Cuts every N characters, with overlap | Doesn't respect sentence or argument boundaries, would cut both theory explanations and recipes in arbitrary places |
| Sentence/paragraph chunking | Cuts on natural language boundaries | Better than fixed-size, but uneven chunk sizes, and doesn't understand that a recipe needs to stay whole |
| Semantic chunking | Uses embeddings to detect topic shifts | Built for books with weak or inconsistent structure. This book already has real, explicit headers, a more reliable signal than an embedding-based guess |

**Decisions:**

1. Kitchen Basics (pages 202-220, tools/ingredients/how-tos): tagged
   **theory**. Reference and technique content, not self-contained
   recipes.
2. Cooking Lessons and Suggested Menus (pages 472-479, after the
   recipe section): tagged **theory**. Cooking Lessons walks through
   technique rather than standalone recipes, and Suggested Menus is a
   list of recommendations, not recipes itself.

Both decisions keep the tag schema to two types, theory and recipe,
rather than adding a third category for a small amount of content.

---

---

## Phase 4: Extraction script

*Turn the chosen chunking strategy into working code that produces the
actual stored chunks.*

**What we ran:** checked a real recipe page's raw text and font metadata
before writing any recipe-specific splitting logic, following the same
"look before coding" rule from Phase 1.

**What we found:**

- Recipe titles are title-case (`Avocado Salad Matrix`), not all-caps,
  so the Phase 1/2 all-caps rule would have missed every recipe title
  entirely. The book's actual header/title font is `Archer-Bold`, used
  consistently for theory subheadings and recipe titles alike, and it
  also skips the two Phase 2 false positives on its own (they weren't
  set in that font).
- Recipes are written in prose, not a title/ingredients-list/method
  layout. Ingredient quantities are marked inline with a distinct font
  (`IdealSansPro-Medium`) inside flowing paragraphs, not a separate
  bullet list.
- In-recipe sub-variations (e.g. the "Avocado", "Beetroots", and
  "Citrus" options inside "Avocado Salad Matrix") use the exact same
  font and size as a true top-level recipe title. No reliable signal
  distinguishes the two.
- Re-scanning with the font-based signal gave exact page numbers for
  every recipe category, correcting the rough estimates from Phase 3,
  and surfaced a category Phase 3 missed entirely: "Thirteen Ways of
  Looking at a Chicken" (pages 342-373) sits between Fish and Meat and
  was being silently folded into Fish.
- First run of the script silently dropped the prose introduction
  before each section's first bold header (Salt's personal-essay
  opening, pages 26-28, the same pages the drop-cap quirk was found on
  in Phase 1). Fixed by building chunk regions per section rather than
  globally, so lead-in text before the first header becomes its own
  chunk instead of being lost.
- The drop-cap fix itself needed a second pass: the oversized drop-cap
  glyph lands on its own line a few lines into the text, not on line
  one as first assumed, so the original fix reinserted the letter in
  the wrong place ("nowhere G else" instead of "Growing"). Fixed by
  searching the first few lines for the stray letter instead of
  assuming its position.

**Decision:** one chunking method across the whole book, using
`Archer-Bold` lines as the boundary signal everywhere, rather than a
separate structure-based method for theory and a separate content-aware
method for recipes as planned in Phase 3. The two methods collapsed
into one once real inspection showed there's no way to tell a top-level
recipe title apart from an in-recipe sub-variation, and no separate
ingredient-list structure to split on either. A sub-variation becoming
its own chunk isn't a real loss: something like "Avocado" is still a
complete, useful unit for ingredient-based search on its own. Long
sections still get the planned secondary paragraph split with overlap.

**Result:** 496 chunks (242 theory, 254 recipe), saved to
`data/processed/chunks.jsonl`. Every chunk carries type, section, title,
and page range, and every section's boundaries were spot-checked by eye
against the actual page, not assumed from the earlier estimate.

---

## Reference: page boundaries used by the extraction script

Refined in Phase 4 with exact page numbers from the font-based scan,
replacing the rough estimate from Phase 2.

| Section | Pages | Type |
|---|---|---|
| Salt | 26-70 | theory |
| Fat | 71-113 | theory |
| Acid | 114-142 | theory |
| Heat | 143-198 | theory |
| What to Cook | 199-201 | theory |
| Kitchen Basics | 202-220 | theory |
| Salads | 221-248 | recipe |
| Dressings | 249-267 | recipe |
| Vegetables | 268-286 | recipe |
| Stock and Soups | 287-298 | recipe |
| Beans, Grains, and Pasta | 299-325 | recipe |
| Eggs | 326-334 | recipe |
| Fish | 335-341 | recipe |
| Thirteen Ways of Looking at a Chicken | 342-373 | recipe |
| Meat | 374-391 | recipe |
| Sauces | 392-426 | recipe |
| Butter-and-Flour Doughs | 427-442 | recipe |
| Sweets | 443-471 | recipe |
| Cooking Lessons | 472-475 | theory |
| Suggested Menus | 476-479 | theory |
| Tips / Acknowledgements / Bibliography / Index | 480-530 | excluded (noise) |

## Reference: known extraction quirks to handle in code

- Drop-cap reassembly on each chapter's opening paragraph
- Filter header candidates that start with punctuation (removes the
  footnote-marker and epigraph false positives from Phase 2)
- Skip empty-text pages (the image-only element dividers) rather than
  treating them as missing data
- Exclude index, bibliography, and acknowledgements sections entirely
