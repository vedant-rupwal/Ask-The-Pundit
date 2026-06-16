import argparse
import sys
import time
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import parse_qs, unquote, urldefrag, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

from corpus_utils import (
    clean_text,
    content_hash,
    domain_from_url,
    is_quality_document,
    now_utc_iso,
    write_jsonl,
)


MEDIA_EXTENSIONS = {
    "image": (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp"),
    "audio": (".mp3", ".m4a", ".wav", ".ogg", ".flac", ".aac"),
    "video": (".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v"),
}
TRANSCRIPT_HINTS = ("transcript", "caption", "subtitles", "lyrics")
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def load_seed_urls(url_file: str):
    return [
        line.strip()
        for line in Path(url_file).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def normalize_url(url: str, base_url: str | None = None) -> str | None:
    absolute_url = urljoin(base_url or "", url or "")
    absolute_url, _fragment = urldefrag(absolute_url)
    parsed = urlparse(absolute_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    scheme = "https" if parsed.scheme == "http" else parsed.scheme
    path = parsed.path or "/"
    query = normalize_query(parsed.query)
    normalized = parsed._replace(
        scheme=scheme,
        path=path,
        params="",
        query=query,
        fragment="",
    )
    return normalized.geturl()


def normalize_query(query: str) -> str:
    if not query:
        return ""
    allowed_keys = {"title"}
    parsed_query = parse_qs(query, keep_blank_values=False)
    kept = []
    for key in sorted(allowed_keys):
        for value in parsed_query.get(key, []):
            kept.append((key, value))
    return urlencode(kept)


def canonical_domain(url: str) -> str:
    domain = domain_from_url(url)
    return domain[4:] if domain.startswith("www.") else domain


def is_allowed_url(url: str, allowed_domains: set[str]) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if canonical_domain(url) not in allowed_domains:
        return False
    return not is_noise_url(url)


def is_noise_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    query = parse_qs(parsed.query)
    title = " ".join(query.get("title", [])).lower()
    action = query.get("action", [""])[0].lower()

    if action and action not in {"view"}:
        return True
    if any(
        blocked in path
        for blocked in (
            "special:",
            "/wiki/help:",
            "/wiki/file:",
            "/wiki/image:",
            "/wiki/template:",
            "/wiki/template_talk:",
            "/wiki/user:",
            "/wiki/user_talk:",
            "/wiki/talk:",
        )
    ):
        return True
    if any(
        blocked in title
        for blocked in (
            "special:",
            "help:",
            "file:",
            "image:",
            "template:",
            "user:",
            "talk:",
        )
    ):
        return True
    return False


def fetch_html(url: str, timeout_seconds: int, user_agent: str) -> str:
    response = requests.get(
        url,
        timeout=timeout_seconds,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
        },
    )
    if response.status_code == 403 and mediawiki_title_from_url(url):
        return fetch_mediawiki_html(url, timeout_seconds, user_agent)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type.lower():
        raise ValueError(f"not an HTML page: {content_type}")
    return response.text


def mediawiki_title_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    prefix = "/wiki/"
    if not parsed.path.startswith(prefix):
        return None
    title = unquote(parsed.path[len(prefix) :])
    return title or "Main_Page"


def mediawiki_api_candidates(url: str):
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    return [f"{base}/w/api.php", f"{base}/api.php"]


def fetch_mediawiki_html(url: str, timeout_seconds: int, user_agent: str) -> str:
    title = mediawiki_title_from_url(url)
    if not title:
        raise ValueError("not a MediaWiki /wiki/ page")

    params = {
        "action": "parse",
        "page": title,
        "prop": "text",
        "format": "json",
        "redirects": "1",
    }
    headers = {
        "User-Agent": user_agent,
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    }
    errors = []

    for endpoint in mediawiki_api_candidates(url):
        try:
            response = requests.get(
                endpoint,
                params=params,
                timeout=timeout_seconds,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            parsed_text = data.get("parse", {}).get("text", {})
            html = parsed_text.get("*")
            if html:
                return html
            errors.append(f"{endpoint}: no parse.text returned")
        except Exception as error:
            errors.append(f"{endpoint}: {error}")

    raise ValueError("MediaWiki API fallback failed: " + " | ".join(errors))


def extract_main_text(soup: BeautifulSoup) -> str:
    working = BeautifulSoup(str(soup), "html.parser")
    for tag in working(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()
    main = working.find("main") or working.find("article") or working.body or working
    return clean_text(main.get_text("\n"))


def extract_links(soup: BeautifulSoup, page_url: str, allowed_domains: set[str]):
    links = []
    for anchor in soup.find_all("a", href=True):
        href = normalize_url(anchor.get("href"), page_url)
        if href and is_allowed_url(href, allowed_domains):
            links.append(href)
    return links


def extract_mixed_media_records(
    soup: BeautifulSoup,
    page_url: str,
    license_status: str,
    training_status: str,
):
    rows = []
    page_text = extract_main_text(soup)
    if is_quality_document(page_text, min_chars=200):
        rows.append(
            build_record(
                source_url=page_url,
                media_url="",
                media_type="html_text",
                clean_text_value=page_text,
                license_status=license_status,
                training_status=training_status,
                metadata={},
            )
        )

    for image in soup.find_all("img"):
        media_url = normalize_url(
            image.get("src")
            or image.get("data-src")
            or image.get("data-original")
            or image.get("data-lazy-src"),
            page_url,
        )
        caption = find_nearby_caption(image)
        derivative_text = clean_text(
            "\n".join(
                value
                for value in [
                    image.get("alt", ""),
                    image.get("title", ""),
                    caption,
                ]
                if value
            )
        )
        rows.append(
            build_record(
                source_url=page_url,
                media_url=media_url or "",
                media_type="image",
                clean_text_value=derivative_text,
                license_status=license_status,
                training_status=training_status,
                metadata={
                    "alt": image.get("alt", ""),
                    "title": image.get("title", ""),
                    "caption": caption,
                    "ocr_status": "not_run",
                },
            )
        )

    for tag_name in ("audio", "video"):
        for media in soup.find_all(tag_name):
            sources = [media.get("src")] + [source.get("src") for source in media.find_all("source")]
            tracks = [
                {
                    "src": normalize_url(track.get("src"), page_url) or "",
                    "kind": track.get("kind", ""),
                    "label": track.get("label", ""),
                    "srclang": track.get("srclang", ""),
                }
                for track in media.find_all("track")
            ]
            caption = find_nearby_caption(media)
            derivative_text = clean_text(
                "\n".join(
                    value
                    for value in [
                        media.get("title", ""),
                        media.get("aria-label", ""),
                        caption,
                        " ".join(track["label"] for track in tracks if track["label"]),
                    ]
                    if value
                )
            )
            for raw_source in sources:
                media_url = normalize_url(raw_source, page_url)
                if not media_url:
                    continue
                rows.append(
                    build_record(
                        source_url=page_url,
                        media_url=media_url,
                        media_type=tag_name,
                        clean_text_value=derivative_text,
                        license_status=license_status,
                        training_status=training_status,
                        metadata={
                            "caption": caption,
                            "tracks": tracks,
                            "transcription_status": "not_run",
                        },
                    )
                )

    rows.extend(
        extract_media_and_transcript_links(
            soup,
            page_url,
            license_status,
            training_status,
        )
    )
    return rows


def extract_media_and_transcript_links(
    soup: BeautifulSoup,
    page_url: str,
    license_status: str,
    training_status: str,
):
    rows = []
    for anchor in soup.find_all("a", href=True):
        media_url = normalize_url(anchor.get("href"), page_url)
        if not media_url:
            continue
        lower_url = media_url.lower()
        link_text = clean_text(anchor.get_text(" "))
        media_type = media_type_from_url(lower_url)
        if media_type:
            rows.append(
                build_record(
                    source_url=page_url,
                    media_url=media_url,
                    media_type=media_type,
                    clean_text_value=link_text,
                    license_status=license_status,
                    training_status=training_status,
                    metadata={
                        "link_text": link_text,
                        "ocr_status": "not_run" if media_type == "image" else "",
                        "transcription_status": "not_run" if media_type in {"audio", "video"} else "",
                    },
                )
            )
            continue

        if any(hint in lower_url or hint in link_text.lower() for hint in TRANSCRIPT_HINTS):
            rows.append(
                build_record(
                    source_url=page_url,
                    media_url=media_url,
                    media_type="transcript_link",
                    clean_text_value=link_text,
                    license_status=license_status,
                    training_status=training_status,
                    metadata={"link_text": link_text, "transcript_status": "linked_not_fetched"},
                )
            )
    return rows


def media_type_from_url(url: str) -> str | None:
    for media_type, extensions in MEDIA_EXTENSIONS.items():
        if url.lower().endswith(extensions):
            return media_type
    return None


def find_nearby_caption(tag) -> str:
    figure = tag.find_parent("figure")
    if figure:
        caption = figure.find("figcaption")
        if caption:
            return clean_text(caption.get_text(" "))

    next_caption = tag.find_next(["figcaption", "caption"])
    if next_caption:
        return clean_text(next_caption.get_text(" "))
    return ""


def build_record(
    source_url: str,
    media_url: str,
    media_type: str,
    clean_text_value: str,
    license_status: str,
    training_status: str,
    metadata: dict,
):
    text_for_hash = clean_text_value or f"{source_url} {media_url} {media_type}"
    return {
        "source": "mixed_media_crawl",
        "source_url": source_url,
        "media_url": media_url,
        "media_type": media_type,
        "license_status": license_status,
        "training_status": training_status,
        "domain": domain_from_url(source_url),
        "fetch_time": now_utc_iso(),
        "content_hash": content_hash(text_for_hash),
        "clean_text": clean_text_value,
        "metadata": metadata,
    }


def crawl_mixed_media(
    seed_urls,
    out_path: str,
    max_depth: int,
    max_pages_per_domain: int,
    request_delay: float,
    timeout_seconds: int,
    license_status: str,
    training_status: str,
    user_agent: str = DEFAULT_USER_AGENT,
):
    normalized_seeds = [normalize_url(seed) for seed in seed_urls]
    normalized_seeds = [seed for seed in normalized_seeds if seed]
    allowed_domains = {canonical_domain(seed) for seed in normalized_seeds}
    queue = deque((seed, 0) for seed in normalized_seeds)
    visited_urls = set()
    pages_per_domain = defaultdict(int)
    blocked_domains = set()
    seen_record_hashes = set()
    rows = []

    while queue:
        page_url, depth = queue.popleft()
        if page_url in visited_urls:
            continue
        if not is_allowed_url(page_url, allowed_domains):
            continue

        domain = canonical_domain(page_url)
        if domain in blocked_domains:
            continue
        if pages_per_domain[domain] >= max_pages_per_domain:
            continue

        visited_urls.add(page_url)
        pages_per_domain[domain] += 1

        try:
            html = fetch_html(page_url, timeout_seconds, user_agent)
        except Exception as error:
            print(f"SKIP {page_url}: {error}")
            if is_forbidden_error(error):
                blocked_domains.add(domain)
                print(f"BLOCKED DOMAIN {domain}: skipping remaining queued URLs for this domain.")
            continue

        soup = BeautifulSoup(html, "html.parser")
        for row in extract_mixed_media_records(
            soup,
            page_url,
            license_status,
            training_status,
        ):
            record_key = row["content_hash"]
            if record_key in seen_record_hashes:
                continue
            seen_record_hashes.add(record_key)
            rows.append(row)

        if depth < max_depth:
            for link in extract_links(soup, page_url, allowed_domains):
                if link not in visited_urls:
                    queue.append((link, depth + 1))

        if request_delay > 0:
            time.sleep(request_delay)

    write_jsonl(out_path, rows)
    return {
        "documents": len(rows),
        "pages_visited": len(visited_urls),
        "domains": dict(pages_per_domain),
        "blocked_domains": sorted(blocked_domains),
    }


def is_forbidden_error(error: Exception) -> bool:
    return "403" in str(error) or "Forbidden" in str(error)


def main():
    parser = argparse.ArgumentParser(description="Crawl approved sites and extract text derivatives from mixed media.")
    parser.add_argument("--url-file", required=True)
    parser.add_argument("--out", default="slm/data/raw_web/mixed_media_corpus.jsonl")
    parser.add_argument("--max-depth", type=int, default=1)
    parser.add_argument("--max-pages-per-domain", type=int, default=100)
    parser.add_argument("--request-delay", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--license-status", default="user_approved_source")
    parser.add_argument("--training-status", default="included")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
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
        user_agent=args.user_agent,
    )
    print(
        f"Wrote {stats['documents']} records from {stats['pages_visited']} pages "
        f"to {args.out}"
    )


if __name__ == "__main__":
    main()
