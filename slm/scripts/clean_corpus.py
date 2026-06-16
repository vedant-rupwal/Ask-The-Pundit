import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

from corpus_utils import clean_text, content_hash, is_quality_document, read_jsonl, write_jsonl


def clean_corpus(input_paths, out_path: str):
    rows = []
    seen_hashes = set()

    for input_path in input_paths:
        for row in read_jsonl(input_path):
            cleaned = clean_text(row.get("clean_text") or row.get("text") or "")
            min_chars = 20 if row.get("source") == "chroma_db" else 200
            if not is_quality_document(cleaned, min_chars=min_chars):
                continue
            doc_hash = content_hash(cleaned)
            if doc_hash in seen_hashes:
                continue
            seen_hashes.add(doc_hash)
            row["clean_text"] = cleaned
            row["content_hash"] = doc_hash
            rows.append(row)

    write_jsonl(out_path, rows)
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Clean and deduplicate one or more JSONL corpora.")
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--out", default="slm/data/processed/clean_corpus.jsonl")
    args = parser.parse_args()
    count = clean_corpus(args.input, args.out)
    print(f"Wrote {count} cleaned documents to {args.out}")


if __name__ == "__main__":
    main()
