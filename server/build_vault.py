import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

from chroma_loader import load_chunks_into_db
from vedabase_parser import process_vedabase_page


BATCH_SIZE = 50
REQUEST_DELAY_SECONDS = 1.5
MAX_REQUEST_ATTEMPTS = 3
INITIAL_BACKOFF_SECONDS = 1
CHECKPOINT_PATH = Path("./scraped_verses.json")
VERSE_SPEC_PATTERNS = {
    "bg": re.compile(r"/bg/\d+/(\d+(?:-\d+)?)/?"),
    "sb": re.compile(r"/sb/\d+/\d+/(\d+(?:-\d+)?)/?"),
    "iso": re.compile(r"/iso/(\d+(?:-\d+)?)/?"),
}
LIBRARY_REGISTRY = {
    "bg": {
        "title": "Bhagavad-gita",
        "type": "standard",
        "base_url_pattern": "https://vedabase.io/en/library/bg/{chapter}/{verse}/",
        "index_url_pattern": "https://vedabase.io/en/library/bg/{chapter}/",
        "chapters": {
            1: 47,
            2: 72,
            3: 43,
            4: 42,
            5: 29,
            6: 47,
            7: 30,
            8: 28,
            9: 34,
            10: 42,
            11: 55,
            12: 20,
            13: 35,
            14: 27,
            15: 20,
            16: 24,
            17: 28,
            18: 78,
        },
    },
    "sb": {
        "title": "Srimad-Bhagavatam",
        "type": "hierarchical",
        "base_url_pattern": (
            "https://vedabase.io/en/library/sb/{canto}/{chapter}/{verse}/"
        ),
        "index_url_pattern": "https://vedabase.io/en/library/sb/{canto}/{chapter}/",
        "cantos": {
            1: 19,
            2: 10,
            3: 33,
            4: 31,
            5: 26,
            6: 19,
            7: 15,
            8: 24,
            9: 24,
            10: 90,
            11: 31,
            12: 13,
        },
        "chapter_index_pattern": "https://vedabase.io/en/library/sb/{canto}/{chapter}/",
    },
    "iso": {
        "title": "Sri Isopanisad",
        "type": "flat",
        "base_url_pattern": "https://vedabase.io/en/library/iso/{verse}/",
        "index_url_pattern": "https://vedabase.io/en/library/iso/",
        "verses": 18,
    },
    "tlk": {
        "title": "Teachings of Lord Kapila",
        "type": "chapter-based",
        "base_url_pattern": "https://vedabase.io/en/library/tlk/{chapter}/",
        "chapters": 18,
    },
    "tqk": {
        "title": "Teachings of Queen Kunti",
        "type": "chapter-based",
        "base_url_pattern": "https://vedabase.io/en/library/tqk/{chapter}/",
        "chapters": 26,
    },
    "noi": {
        "title": "Nectar of Instruction",
        "type": "chapter-based",
        "base_url_pattern": "https://vedabase.io/en/library/noi/{chapter}/",
        "chapters": 11,
    },
    "nod": {
        "title": "Nectar of Devotion",
        "type": "chapter-based",
        "base_url_pattern": "https://vedabase.io/en/library/nod/{chapter}/",
        "chapters": 51,
    },
    "tlc": {
        "title": "Teachings of Lord Caitanya",
        "type": "chapter-based",
        "base_url_pattern": "https://vedabase.io/en/library/tlc/{chapter}/",
        "chapters": 32,
    },
     "ssr": {
        "title": "The Science of Self-Realization",
        "type": "chapter-based",
        "base_url_pattern": "https://vedabase.io/en/library/ssr/{chapter}/",
        "chapters": 8,
    },
     "bbd": {
        "title": "Beyond Birth and Death",
        "type": "chapter-based",
        "base_url_pattern": "https://vedabase.io/en/library/bbd/{chapter}/",
        "chapters": 5,
    },
     "bhakti": {
        "title": "Bhakti: The Art of Eternal Love",
        "type": "chapter-based",
        "base_url_pattern": "https://vedabase.io/en/library/bhakti/{chapter}/",
        "chapters": 8,
    },
    "owk": {
        "title": "On the Way to Kṛṣṇa",
        "type": "chapter-based",
        "base_url_pattern": "https://vedabase.io/en/library/owk/{chapter}/",
        "chapters": 5,
    },
    "poy": {
        "title": "The Perfection of Yoga",
        "type": "chapter-based",
        "base_url_pattern": "https://vedabase.io/en/library/poy/{chapter}/",
        "chapters": 8,
    },
    "pqpa": {
        "title": "Perfect Questions, Perfect Answers",
        "type": "chapter-based",
        "base_url_pattern": "https://vedabase.io/en/library/pqpa/{chapter}/",
        "chapters": 8,
    },
     "sc": {
        "title": "A Second Chance",
        "type": "chapter-based",
        "base_url_pattern": "https://vedabase.io/en/library/sc/{chapter}/",
        "chapters": 22,
    },
     "josd": {
        "title": "The Journey of Self-Discovery",
        "type": "chapter-based",
        "base_url_pattern": "https://vedabase.io/en/library/josd/{chapter}/",
        "chapters": 7,
    },
     "rv": {
        "title": "Rāja-vidyā: The King of Knowledge",
        "type": "chapter-based",
        "base_url_pattern": "https://vedabase.io/en/library/rv/{chapter}/",
        "chapters": 8,
    },
     "kb": {
        "title": "Kṛṣṇa, the Supreme Personality of Godhead",
        "type": "chapter-based",
        "base_url_pattern": "https://vedabase.io/en/library/kb/{chapter}/",
        "chapters": 90,
    },
}



def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Scrape Vedabase content and load it into ChromaDB."
    )
    parser.add_argument(
        "--book",
        choices=sorted(LIBRARY_REGISTRY),
        default="bg",
        help="Book slug to scrape.",
    )
    parser.add_argument(
        "--db-path",
        default="../chroma_db",
        help="Persistent ChromaDB path.",
    )
    parser.add_argument(
        "--checkpoint-path",
        default=str(CHECKPOINT_PATH),
        help="Checkpoint file used for resumable scraping.",
    )
    return parser


def make_item_id(book_key, *, canto=None, chapter=None, verse=None):
    if book_key == "bg":
        return f"bg-ch{chapter}-v{verse}"
    if book_key == "sb":
        return f"sb-c{canto}-ch{chapter}-v{verse}"
    if book_key == "iso":
        return f"iso-mantra-{verse}"
    if book_key in {"tlk", "tqk"}:
        return f"{book_key}-ch{chapter}"
    book_config = LIBRARY_REGISTRY.get(book_key)
    if book_config and book_config["type"] == "chapter-based":
        return f"{book_key}-ch{chapter}"
    raise ValueError(f"Unsupported book key '{book_key}'")


def load_checkpoint(checkpoint_path):
    if not checkpoint_path.exists():
        return set()

    try:
        with checkpoint_path.open("r", encoding="utf-8") as checkpoint_file:
            data = json.load(checkpoint_file)
    except (OSError, json.JSONDecodeError) as error:
        print(f"Checkpoint read failed for {checkpoint_path}: {error}")
        return set()

    if not isinstance(data, list):
        print(f"Checkpoint file {checkpoint_path} is not a JSON list. Ignoring it.")
        return set()

    return {item for item in data if isinstance(item, str)}


def save_checkpoint(completed_items, checkpoint_path):
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    with checkpoint_path.open("w", encoding="utf-8") as checkpoint_file:
        json.dump(sorted(completed_items), checkpoint_file, indent=2)


def fetch_with_retries(session, url, timeout=20):
    for attempt in range(1, MAX_REQUEST_ATTEMPTS + 1):
        try:
            response = session.get(url, timeout=timeout, allow_redirects=True)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as error:
            if attempt >= MAX_REQUEST_ATTEMPTS:
                raise

            backoff_seconds = INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1))
            print(
                f"Request attempt {attempt} failed for {url}: {error}. "
                f"Retrying in {backoff_seconds} seconds..."
            )
            time.sleep(backoff_seconds)


def polite_get(session, url, timeout=20):
    try:
        return fetch_with_retries(session, url, timeout=timeout)
    finally:
        time.sleep(REQUEST_DELAY_SECONDS)


def flush_chunks(chunks, item_ids, completed_items, db_path, checkpoint_path, book_title="hindu_scriptures"):
    if not item_ids:
        return

    if chunks:
        load_chunks_into_db(chunks, collection_name=book_title, db_path=db_path)
        print(f"Saved {len(chunks)} chunks to {db_path} under collection '{book_title}'.")

    completed_items.update(item_ids)
    save_checkpoint(completed_items, checkpoint_path)
    print(f"Checkpointed {len(item_ids)} items to {checkpoint_path}.")

    chunks.clear()
    item_ids.clear()


def parse_verse_spec(verse_spec):
    verse_numbers = []

    for part in str(verse_spec).split(","):
        token = part.strip()
        if not token:
            continue

        if "-" in token:
            start_text, end_text = token.split("-", 1)
            start_num = int(start_text)
            end_num = int(end_text)
            verse_numbers.extend(range(start_num, end_num + 1))
        else:
            verse_numbers.append(int(token))

    return verse_numbers


def get_verse_list(actual_verse_spec):
    if actual_verse_spec is None:
        return []

    verse_numbers = parse_verse_spec(actual_verse_spec)
    if not verse_numbers:
        raise ValueError(f"Invalid verse spec '{actual_verse_spec}'")

    return verse_numbers


def extract_verse_spec_from_url(book_key, response_url, default_verse_num):
    pattern = VERSE_SPEC_PATTERNS.get(book_key)
    if not pattern:
        return str(default_verse_num) if default_verse_num is not None else None

    match = pattern.search(response_url)
    if not match:
        return str(default_verse_num) if default_verse_num is not None else None

    return match.group(1)


def resolve_item_ids_for_page(book_key, entry, verse_spec):
    if book_key == "bg":
        return [
            make_item_id(book_key, chapter=int(entry["chapter_num"]), verse=verse_num)
            for verse_num in parse_verse_spec(verse_spec)
        ]

    if book_key == "sb":
        canto_num_text, chapter_num_text = str(entry["chapter_num"]).split(".", 1)
        canto_num = int(canto_num_text)
        chapter_num = int(chapter_num_text)
        return [
            make_item_id(
                book_key,
                canto=canto_num,
                chapter=chapter_num,
                verse=verse_num,
            )
            for verse_num in parse_verse_spec(verse_spec)
        ]

    if book_key == "iso":
        return [
            make_item_id(book_key, verse=verse_num)
            for verse_num in parse_verse_spec(verse_spec)
        ]
    
    book_config = LIBRARY_REGISTRY.get(book_key)
    if book_config and book_config["type"] == "chapter-based":
        return [entry["item_id"]]

    return [entry["item_id"]]


def normalize_verse_page_url(base_url, href):
    if not href:
        return None

    return urljoin(base_url, href)


def find_verse_page_urls(book_key, base_url, html_text):
    pattern = VERSE_SPEC_PATTERNS.get(book_key)
    if not pattern:
        return []

    soup = BeautifulSoup(html_text, "html.parser")
    discovered_urls = set()

    for link in soup.select("a[href]"):
        href = link.get("href", "")
        candidate_url = normalize_verse_page_url(base_url, href)
        if not candidate_url:
            continue

        parsed_path = urlparse(candidate_url).path
        if pattern.search(parsed_path):
            discovered_urls.add(candidate_url)

    return sorted(discovered_urls)


def discover_sb_verse_count(session, canto_num, chapter_num, chapter_index_pattern):
    chapter_url = chapter_index_pattern.format(canto=canto_num, chapter=chapter_num)
    print(f"Discovering verse count from {chapter_url}")
    response = polite_get(session, chapter_url, timeout=20)
    soup = BeautifulSoup(response.text, "html.parser")

    verse_numbers = set()
    verse_link_pattern = re.compile(
        rf"/en/library/sb/{canto_num}/{chapter_num}/(\d+(?:-\d+)?)/?$"
    )

    for link in soup.select("a[href]"):
        href = link.get("href", "")
        match = verse_link_pattern.search(href)
        if match:
            verse_numbers.update(parse_verse_spec(match.group(1)))

    if verse_numbers:
        return max(verse_numbers)

    text_matches = re.findall(r"Text\s+(\d+):", soup.get_text("\n", strip=True))
    if text_matches:
        return max(int(match) for match in text_matches)

    raise ValueError(f"Could not determine verse count for SB {canto_num}.{chapter_num}")


def iter_book_entries(book_key, book_config, session):
    if book_config["type"] == "standard":
        for chapter_num in book_config["chapters"].keys():
            yield {
                "item_id": None,
                "url": book_config["index_url_pattern"].format(chapter=chapter_num),
                "chapter_num": str(chapter_num),
                "verse_num": None,
                "log_label": f"Chapter {chapter_num}",
            }
        return

    if book_config["type"] == "hierarchical":
        for canto_num, total_chapters in book_config["cantos"].items():
            for chapter_num in range(1, total_chapters + 1):
                yield {
                    "item_id": None,
                    "url": book_config["index_url_pattern"].format(
                        canto=canto_num,
                        chapter=chapter_num,
                    ),
                    "chapter_num": f"{canto_num}.{chapter_num}",
                    "verse_num": None,
                    "log_label": f"{canto_num}.{chapter_num}",
                }
        return

    if book_config["type"] == "flat":
        yield {
            "item_id": None,
            "url": book_config["index_url_pattern"],
            "chapter_num": "Mantra",
            "verse_num": None,
            "log_label": "ISO Index",
        }
        return

    if book_config["type"] == "chapter-based":
        for chapter_num in range(1, book_config["chapters"] + 1):
            yield {
                "item_id": make_item_id(book_key, chapter=chapter_num),
                "url": book_config["base_url_pattern"].format(chapter=chapter_num),
                "chapter_num": str(chapter_num),
                "verse_num": None,
                "log_label": f"Chapter {chapter_num}",
            }
        return

    raise ValueError(f"Unsupported book type '{book_config['type']}'")


def build_vault(book_key="bg", db_path="./chroma_db", checkpoint_path=CHECKPOINT_PATH):
    if book_key not in LIBRARY_REGISTRY:
        available_books = ", ".join(sorted(LIBRARY_REGISTRY))
        raise ValueError(
            f"Unknown book '{book_key}'. Available books: {available_books}"
        )

    book_config = LIBRARY_REGISTRY[book_key]
    checkpoint_path = Path(checkpoint_path)
    completed_items = load_checkpoint(checkpoint_path)
    pending_chunks = []
    pending_item_ids = []
    pending_item_id_set = set()
    processed_urls = set()
    items_since_flush = 0
    current_collection_name = None

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (compatible; AskThePanditBot/1.0; +https://localhost)"
            )
        }
    )

    print(f"Loaded {len(completed_items)} completed items from {checkpoint_path}.")
    print(f"Building vault for {book_config['title']} ({book_key})...")

    for entry in iter_book_entries(book_key, book_config, session):
        item_id = entry.get("item_id")

        target_collection_name = "Supplementary Books"
        if book_key == "sb":
            canto_num = int(str(entry["chapter_num"]).split(".", 1)[0])
            target_collection_name = f"Srimad-Bhagavatam Canto {canto_num}"
        elif book_key == "bg":
            target_collection_name = "Bhagavad-gita"

        if current_collection_name is None:
            current_collection_name = target_collection_name
        elif target_collection_name != current_collection_name:
            flush_chunks(
                pending_chunks,
                pending_item_ids,
                completed_items,
                db_path,
                checkpoint_path,
                book_title=current_collection_name,
            )
            pending_item_id_set.clear()
            items_since_flush = 0
            current_collection_name = target_collection_name

        if item_id and (item_id in completed_items or item_id in pending_item_id_set):
            print(f"Skipping already checkpointed item {item_id}.")
            continue

        print(f"Fetching {entry['url']}")

        try:
            response = polite_get(session, entry["url"], timeout=20)
        except requests.exceptions.HTTPError as error:
            status_code = (
                error.response.status_code if error.response is not None else None
            )
            if status_code == 404:
                print(f"Skipping missing page at {entry['url']} (404).")
            else:
                print(f"HTTP error for {entry['url']}: {error}")
            continue
        except requests.exceptions.RequestException as error:
            print(f"Request failed for {entry['url']}: {error}")
            continue

        effective_url = response.url
        if effective_url != entry["url"]:
            print(f"Redirected to {effective_url}")

        if item_id is None:
            verse_page_urls = find_verse_page_urls(book_key, response.url, response.text)
            if not verse_page_urls:
                print(f"No verse URLs found on index page {entry['url']}.")
                continue

            for page_url in verse_page_urls:
                if page_url in processed_urls:
                    print(f"Skipping already processed URL: {page_url}")
                    continue

                try:
                    page_response = polite_get(session, page_url, timeout=20)
                except requests.exceptions.HTTPError as error:
                    status_code = (
                        error.response.status_code if error.response is not None else None
                    )
                    if status_code == 404:
                        print(f"Skipping missing page at {page_url} (404).")
                        continue
                    print(f"HTTP error for {page_url}: {error}")
                    continue
                except requests.exceptions.RequestException as error:
                    print(f"Request failed for {page_url}: {error}")
                    continue

                page_verse_spec = extract_verse_spec_from_url(
                    book_key,
                    page_response.url,
                    None,
                )
                if page_verse_spec is None:
                    print(f"Could not determine verse spec from {page_response.url}. Skipping.")
                    continue

                page_verse_numbers = get_verse_list(page_verse_spec)
                page_item_ids = resolve_item_ids_for_page(
                    book_key,
                    entry,
                    page_verse_spec,
                )

                filtered_item_ids = [
                    resolved_id
                    for resolved_id in page_item_ids
                    if resolved_id not in completed_items
                    and resolved_id not in pending_item_id_set
                ]
                if not filtered_item_ids:
                    print(
                        f"Skipping {page_response.url} because all verses in range "
                        f"{page_verse_spec} are already accounted for."
                    )
                    processed_urls.add(page_response.url)
                    continue

                page_chunks = process_vedabase_page(
                    page_response.text,
                    book_config["title"],
                    entry["chapter_num"],
                    page_verse_numbers,
                )
                pending_chunks.extend(page_chunks)
                pending_item_ids.extend(filtered_item_ids)
                pending_item_id_set.update(filtered_item_ids)
                processed_urls.add(page_response.url)
                items_since_flush += len(filtered_item_ids)

                if items_since_flush >= BATCH_SIZE:
                    flush_chunks(
                        pending_chunks,
                        pending_item_ids,
                        completed_items,
                        db_path,
                        checkpoint_path,
                        book_title=current_collection_name,
                    )
                    pending_item_id_set.clear()
                    items_since_flush = 0

            continue

        page_chunks = process_vedabase_page(
            response.text,
            book_config["title"],
            entry["chapter_num"],
            entry["verse_num"],
        )
        pending_chunks.extend(page_chunks)
        pending_item_ids.append(item_id)
        pending_item_id_set.add(item_id)
        items_since_flush += 1

        if items_since_flush >= BATCH_SIZE:
            flush_chunks(
                pending_chunks,
                pending_item_ids,
                completed_items,
                db_path,
                checkpoint_path,
                book_title=current_collection_name,
            )
            pending_item_id_set.clear()
            items_since_flush = 0

    flush_chunks(
        pending_chunks,
        pending_item_ids,
        completed_items,
        db_path,
        checkpoint_path,
        book_title=current_collection_name,
    )
    pending_item_id_set.clear()
    print(f"Vault build complete for {book_config['title']}.")


if __name__ == "__main__":
    args = build_arg_parser().parse_args()
    build_vault(
        book_key=args.book,
        db_path=args.db_path,
        checkpoint_path=args.checkpoint_path,
    )
