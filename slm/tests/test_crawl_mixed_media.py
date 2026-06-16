import json
import sys
import tempfile
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.append(str(SCRIPT_DIR))

import crawl_mixed_media
from crawl_mixed_media import (
    canonical_domain,
    crawl_mixed_media as run_crawl,
    extract_links,
    extract_mixed_media_records,
    fetch_html,
    is_allowed_url,
    is_forbidden_error,
    is_noise_url,
    mediawiki_api_candidates,
    mediawiki_title_from_url,
    normalize_url,
)


class CrawlMixedMediaTests(unittest.TestCase):
    def test_normalize_url_drops_fragments_and_rejects_non_http(self):
        self.assertEqual(
            normalize_url("/wiki/Page#section", "https://example.org/wiki/Main"),
            "https://example.org/wiki/Page",
        )
        self.assertEqual(
            normalize_url(
                "http://example.org/w/index.php?title=Main_Page&action=edit&section=1"
            ),
            "https://example.org/w/index.php?title=Main_Page",
        )
        self.assertIsNone(normalize_url("mailto:test@example.org"))

    def test_domain_filter_allows_only_seed_domain(self):
        allowed = {canonical_domain("https://vanipedia.org/wiki/Main_Page")}
        self.assertTrue(is_allowed_url("https://vanipedia.org/wiki/Article", allowed))
        self.assertFalse(is_allowed_url("https://example.com/wiki/Article", allowed))
        self.assertFalse(
            is_allowed_url(
                "https://vanipedia.org/w/index.php?title=Main_Page&action=edit",
                allowed,
            )
        )

    def test_noise_url_rejects_admin_and_non_content_pages(self):
        self.assertTrue(is_noise_url("https://vanipedia.org/w/index.php?title=Main_Page&action=edit"))
        self.assertTrue(is_noise_url("https://vanipedia.org/wiki/Special:RecentChanges"))
        self.assertTrue(is_noise_url("https://vanipedia.org/wiki/File:Bookcase.png"))
        self.assertFalse(is_noise_url("https://vanipedia.org/wiki/Main_Page"))

    def test_forbidden_error_detection(self):
        self.assertTrue(is_forbidden_error(RuntimeError("403 Client Error: Forbidden")))
        self.assertFalse(is_forbidden_error(RuntimeError("timeout")))

    def test_extract_links_stays_inside_allowed_domains(self):
        soup = BeautifulSoup(
            """
            <a href="/wiki/Internal">Internal</a>
            <a href="https://other.example/page">External</a>
            """,
            "html.parser",
        )
        allowed = {canonical_domain("https://vanipedia.org/wiki/Main_Page")}
        links = extract_links(soup, "https://vanipedia.org/wiki/Main_Page", allowed)
        self.assertEqual(links, ["https://vanipedia.org/wiki/Internal"])

    def test_mediawiki_helpers_build_expected_api_candidates(self):
        url = "https://vanipedia.org/wiki/Main_Page"
        self.assertEqual(mediawiki_title_from_url(url), "Main_Page")
        self.assertEqual(
            mediawiki_api_candidates(url),
            ["https://vanipedia.org/w/api.php", "https://vanipedia.org/api.php"],
        )

    def test_extract_mixed_media_records_keeps_text_derivatives(self):
        soup = BeautifulSoup(
            """
            <html><body>
              <main><p>This is a long article about devotion, scripture, service, chanting,
              worship, philosophy, practice, discipline, remembrance, knowledge, wisdom,
              compassion, humility, and spiritual life. This extra sentence keeps the
              document above the quality threshold for the crawler.</p></main>
              <figure>
                <img src="/images/krishna.jpg" alt="Krishna playing flute" title="Sacred image" />
                <figcaption>Image caption text</figcaption>
              </figure>
              <video src="/media/talk.mp4" title="Lecture video">
                <track src="/media/talk.vtt" kind="captions" label="English captions" srclang="en" />
              </video>
              <a href="/media/talk-transcript.html">Transcript</a>
            </body></html>
            """,
            "html.parser",
        )
        records = extract_mixed_media_records(
            soup,
            "https://vanimedia.org/wiki/Main_Page",
            "user_approved_source",
            "included",
        )
        media_types = {record["media_type"] for record in records}
        self.assertIn("html_text", media_types)
        self.assertIn("image", media_types)
        self.assertIn("video", media_types)
        self.assertIn("transcript_link", media_types)
        image_record = next(record for record in records if record["media_type"] == "image")
        self.assertIn("Krishna playing flute", image_record["clean_text"])
        self.assertEqual(image_record["metadata"]["ocr_status"], "not_run")

    def test_crawl_respects_depth_and_page_limit_without_network(self):
        pages = {
            "https://example.org/": """
              <html><body>
                <main><p>This page contains enough useful spiritual article text for quality.
                Devotion, practice, scripture, chanting, service, wisdom, knowledge, humility,
                discipline, remembrance, compassion, worship, philosophy, and study are discussed.</p></main>
                <a href="/one">One</a>
                <a href="/two">Two</a>
              </body></html>
            """,
            "https://example.org/one": """
              <html><body><main><p>This second page contains enough text about devotion and
              scripture to pass quality checks. It adds more training material about practice,
              study, humility, service, chanting, worship, remembrance, and wisdom.</p></main></body></html>
            """,
        }
        original_fetch = crawl_mixed_media.fetch_html
        original_sleep = crawl_mixed_media.time.sleep

        def fake_fetch(url, timeout_seconds, user_agent):
            return pages[url]

        try:
            crawl_mixed_media.fetch_html = fake_fetch
            crawl_mixed_media.time.sleep = lambda _seconds: None
            with tempfile.TemporaryDirectory() as temp_dir:
                out_path = Path(temp_dir) / "crawl.jsonl"
                stats = run_crawl(
                    seed_urls=["https://example.org/"],
                    out_path=str(out_path),
                    max_depth=1,
                    max_pages_per_domain=1,
                    request_delay=0,
                    timeout_seconds=1,
                    license_status="user_approved_source",
                    training_status="included",
                )
                rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]
        finally:
            crawl_mixed_media.fetch_html = original_fetch
            crawl_mixed_media.time.sleep = original_sleep

        self.assertEqual(stats["pages_visited"], 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["training_status"], "included")

    def test_fetch_html_uses_mediawiki_api_after_403(self):
        class FakeResponse:
            def __init__(self, status_code, text="", payload=None, headers=None):
                self.status_code = status_code
                self.text = text
                self._payload = payload or {}
                self.headers = headers or {}

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise RuntimeError(f"status {self.status_code}")

            def json(self):
                return self._payload

        calls = []
        original_get = crawl_mixed_media.requests.get

        def fake_get(url, **kwargs):
            calls.append(url)
            if url.endswith("/wiki/Main_Page"):
                return FakeResponse(403)
            return FakeResponse(
                200,
                payload={"parse": {"text": {"*": "<p>API article text</p>"}}},
                headers={"content-type": "application/json"},
            )

        try:
            crawl_mixed_media.requests.get = fake_get
            html = fetch_html("https://vanipedia.org/wiki/Main_Page", 5, "test-agent")
        finally:
            crawl_mixed_media.requests.get = original_get

        self.assertEqual(html, "<p>API article text</p>")
        self.assertIn("https://vanipedia.org/w/api.php", calls)


if __name__ == "__main__":
    unittest.main()
