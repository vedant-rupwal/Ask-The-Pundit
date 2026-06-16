import argparse
import sys
from pathlib import Path

import chromadb

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

from corpus_utils import clean_text, content_hash, is_quality_document, now_utc_iso, write_jsonl


def export_chroma_corpus(db_path: str, out_path: str):
    client = chromadb.PersistentClient(path=db_path)
    rows = []

    for collection in client.list_collections():
        collection_name = collection.name
        count = collection.count()
        if count == 0:
            continue

        batch = collection.get(
            limit=count,
            include=["documents", "metadatas"],
        )
        documents = batch.get("documents", [])
        metadatas = batch.get("metadatas", [])
        ids = batch.get("ids", [])

        for item_id, document, metadata in zip(ids, documents, metadatas):
            cleaned = clean_text(document or "")
            if not is_quality_document(cleaned, min_chars=20):
                continue
            rows.append(
                {
                    "source": "chroma_db",
                    "source_url": (metadata or {}).get("source_url", ""),
                    "license_status": "project_existing_scripture_corpus",
                    "domain": "local_chroma",
                    "fetch_time": now_utc_iso(),
                    "content_hash": content_hash(cleaned),
                    "collection": collection_name,
                    "item_id": item_id,
                    "metadata": metadata or {},
                    "clean_text": cleaned,
                }
            )

    write_jsonl(out_path, rows)
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Export ChromaDB documents as SLM JSONL corpus.")
    parser.add_argument("--db-path", default="chroma_db")
    parser.add_argument("--out", default="slm/data/processed/scripture_corpus.jsonl")
    args = parser.parse_args()
    count = export_chroma_corpus(args.db_path, args.out)
    print(f"Exported {count} documents to {args.out}")


if __name__ == "__main__":
    main()
