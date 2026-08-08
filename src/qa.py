"""
Phase 6: retrieval, prompt building, and the Claude call.

Takes a question, retrieves the 5 most relevant chunks from the Chroma
store built in Phase 5 (searching across both theory and recipe chunks
together), assembles them into a prompt, and sends it to Claude. Prints
the answer alongside a source list (section, title, page range) for
every chunk actually retrieved, so any answer can be checked against
the real page it came from.

Requires ANTHROPIC_API_KEY to be set, either in the environment or in a
.env file at the project root (see .env.example).

Usage:
  python src/qa.py "What does the book say about salting meat?"
"""

import os
import sys

import anthropic
import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "data/processed/chroma_db"
COLLECTION_NAME = "cookbook"
N_RESULTS = 5
# MODEL = "claude-sonnet-5"
MODEL = "claude-haiku-4-5"
MAX_TOKENS = 1024

SYSTEM_PROMPT = """You are answering questions about the book "Salt, Fat, Acid, Heat" by Samin Nosrat, using only the passages provided below. Your name is 'sAmIn'.

Rules:
- Answer using only the information in the provided passages. Do not use any outside knowledge about cooking, the book, or its author, even if you happen to know it.
- If the passages don't contain enough information to answer the question, say so plainly rather than guessing or filling the gap from general knowledge.
- When you use a passage, cite it by section and page, for example: (Salt, p.29-33).
- Passages are a mix of theory (technique and explanation) and recipe content. Use whichever is relevant to the question, or both, if the question calls for it."""


def get_collection():
    client = chromadb.PersistentClient(path=DB_PATH)
    embedding_function = embedding_functions.DefaultEmbeddingFunction()
    return client.get_collection(COLLECTION_NAME, embedding_function=embedding_function)


def retrieve_chunks(question: str, n_results: int = N_RESULTS) -> list[dict]:
    """
    Retrieves the n_results chunks most similar to the question, across
    both theory and recipe chunks, no type filter applied. Returns a
    plain list of dicts rather than Chroma's raw nested result format,
    easier to work with in build_prompt and easier to print for a check.
    """
    collection = get_collection()
    results = collection.query(query_texts=[question], n_results=n_results)

    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        chunks.append({
            "text": doc,
            "type": meta["type"],
            "section": meta["section"],
            "title": meta["title"],
            "page_start": meta["page_start"],
            "page_end": meta["page_end"],
            "distance": dist,
        })
    return chunks


def format_chunk(chunk: dict) -> str:
    """One retrieved chunk with a metadata header attached, formatted for
    inclusion in the prompt. The header is what lets the model cite its
    sources back to a real section and page range."""
    header = (
        f"[Type: {chunk['type']} | Section: {chunk['section']} | "
        f"Title: {chunk['title']} | Pages: {chunk['page_start']}-{chunk['page_end']}]"
    )
    return f"{header}\n{chunk['text']}"


def build_prompt(question: str, chunks: list[dict]) -> dict:
    """
    Assembles the retrieved chunks and the question into a system prompt
    and user message, ready to hand to the Claude API in the next step.
    Returned as a dict rather than a single string, since the Anthropic
    API takes the system prompt and the user message as separate fields.
    """
    context = "\n\n---\n\n".join(format_chunk(c) for c in chunks)
    user_message = f"Passages from the book:\n\n{context}\n\n---\n\nQuestion: {question}"
    return {"system": SYSTEM_PROMPT, "user": user_message}


def ask_claude(prompt: dict) -> str:
    """
    Sends the assembled system prompt and user message to Claude, returns
    the answer text. This is the one function in the file that actually
    costs anything or touches the network, everything upstream of this
    (retrieval, prompt building) is free and local.
    """
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=prompt["system"],
        messages=[{"role": "user", "content": prompt["user"]}],
    )
    return message.content[0].text


def answer_question(question: str, n_results: int = N_RESULTS) -> dict:
    """
    The full Phase 6 pipeline in one call: retrieve, build the prompt,
    ask Claude, and return both the answer and the sources it was built
    from, so the two can be checked against each other.
    """
    chunks = retrieve_chunks(question, n_results=n_results)
    prompt = build_prompt(question, chunks)
    answer = ask_claude(prompt)
    return {"answer": answer, "sources": chunks}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: python src/qa.py "your question here"')
        sys.exit(1)

    question = sys.argv[1]
    result = answer_question(question)

    print(result["answer"])

    print("References:")
    for c in result["sources"]:
        print(
            f"  [{c['type']}] {c['section']} / {c['title']} "
            f"(pages {c['page_start']}-{c['page_end']}, distance={c['distance']:.3f})"
        )