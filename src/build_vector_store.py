"""
Phase 5: vector store.

Loads data/processed/chunks.jsonl into a persistent Chroma collection,
so the chunks can be searched by similarity and filtered by their
metadata (type, section, title, page range).

Persistent means the store is written to disk (data/processed/chroma_db)
rather than rebuilt in memory every run. Re-running this script clears
and rebuilds the collection from the current chunks.jsonl, so it's safe
to run again any time the extraction step changes.

Embeddings come from Chroma's default embedding function
(all-MiniLM-L6-v2, downloaded automatically on first run, then cached
locally). This needs real internet access the first time it runs, the
model can't be fetched in a network-restricted environment.

Usage:
  python src/build_vector_store.py
"""

import json
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

CHUNKS_PATH = Path("data/processed/chunks_v2.jsonl")
DB_PATH = "data/processed/chroma_db"
COLLECTION_NAME = "cookbook"


def load_chunks():
    with open(CHUNKS_PATH) as f:
        return [json.loads(line) for line in f]


def build_store():
    chunks = load_chunks()

    # Chroma's default embedding function: all-MiniLM-L6-v2, a small
    # neural model run locally via sentence-transformers. Downloaded
    # once on first use, then cached, no need to fit anything ourselves
    # the way the TF-IDF version required.
    embedding_function = embedding_functions.DefaultEmbeddingFunction()

    client = chromadb.PersistentClient(path=DB_PATH)

    # start clean each run, so the store always matches the current
    # chunks.jsonl rather than accumulating stale entries from earlier
    # extraction attempts
    existing = [c.name for c in client.list_collections()]
    if COLLECTION_NAME in existing:
        client.delete_collection(COLLECTION_NAME)
    collection = client.create_collection(
        COLLECTION_NAME, embedding_function=embedding_function
    )

    # Chroma's add() takes parallel lists, not a list of records, so the
    # chunk dicts get split into ids / documents / metadatas here
    ids = [c["id"] for c in chunks]
    documents = [c["text"] for c in chunks]
    metadatas = [
        {
            "type": c["type"],
            "section": c["section"],
            "title": c["title"],
            "page_start": c["page_start"],
            "page_end": c["page_end"],
        }
        for c in chunks
    ]

    # batched, since Chroma (and most vector DBs) cap how many records
    # a single add() call accepts
    batch_size = 100
    for i in range(0, len(ids), batch_size):
        collection.add(
            ids=ids[i:i + batch_size],
            documents=documents[i:i + batch_size],
            metadatas=metadatas[i:i + batch_size],
        )

    return collection


if __name__ == "__main__":
    collection = build_store()
    print(f"Collection '{COLLECTION_NAME}' now holds {collection.count()} chunks")
    print(f"Stored on disk at {DB_PATH}")
