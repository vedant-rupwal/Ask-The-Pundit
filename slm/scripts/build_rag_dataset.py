import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

from corpus_utils import read_jsonl, write_jsonl


def build_citation(metadata):
    metadata = metadata or {}
    source_ref = metadata.get("source_ref")
    if source_ref:
        return source_ref
    book = metadata.get("book_title", "Unknown Text")
    chapter = metadata.get("chapter_num")
    verse = metadata.get("verse_num")
    if chapter and verse:
        return f"{book} {chapter}.{verse}"
    if verse:
        return f"{book} {verse}"
    return book


def build_rag_dataset(corpus_path: str, out_path: str):
    rows = []
    for row in read_jsonl(corpus_path):
        metadata = row.get("metadata") or {}
        citation = build_citation(metadata)
        text = row.get("clean_text", "")
        if not text:
            continue
        rows.append(
            {
                "instruction": "Answer as a Scripture Scholar using only the retrieved scripture.",
                "input": (
                    "Question: What does this passage teach?\n\n"
                    f"Retrieved scripture:\nCitation: {citation}\nText: {text}"
                ),
                "output": (
                    "This passage should be understood from the retrieved scripture itself. "
                    f"It teaches the point expressed in the cited text.\n\nCitation: {citation}"
                ),
                "citation": citation,
            }
        )
    write_jsonl(out_path, rows)
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Build simple RAG-shaped SFT examples.")
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--out", default="slm/data/processed/rag_sft.jsonl")
    args = parser.parse_args()
    count = build_rag_dataset(args.corpus, args.out)
    print(f"Wrote {count} RAG examples to {args.out}")


if __name__ == "__main__":
    main()
