import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

from crawl_mixed_media import crawl_mixed_media, load_seed_urls


def main():
    parser = argparse.ArgumentParser(
        description="Ingest approved sites by crawling same-domain pages and extracting mixed-media text derivatives."
    )
    parser.add_argument("--url-file", required=True)
    parser.add_argument("--out", default="slm/data/raw_web/mixed_media_corpus.jsonl")
    parser.add_argument("--max-depth", type=int, default=1)
    parser.add_argument("--max-pages-per-domain", type=int, default=100)
    parser.add_argument("--request-delay", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--license-status", default="user_approved_source")
    parser.add_argument("--training-status", default="included")
    args = parser.parse_args()

    stats = crawl_mixed_media(
        seed_urls=load_seed_urls(args.url_file),
        out_path=args.out,
        max_depth=args.max_depth,
        max_pages_per_domain=args.max_pages_per_domain,
        request_delay=args.request_delay,
        timeout_seconds=args.timeout_seconds,
        license_status=args.license_status,
        training_status=args.training_status,
    )
    print(
        f"Wrote {stats['documents']} records from {stats['pages_visited']} pages "
        f"to {args.out}"
    )


if __name__ == "__main__":
    main()
