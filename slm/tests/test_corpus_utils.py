import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.append(str(SCRIPT_DIR))

from corpus_utils import clean_text, content_hash, is_probably_english, is_quality_document


class CorpusUtilsTests(unittest.TestCase):
    def test_clean_text_removes_navigation_lines(self):
        text = "Real paragraph about scripture.\nPrivacy Policy\nAnother useful paragraph."
        self.assertNotIn("Privacy Policy", clean_text(text))

    def test_hash_normalizes_whitespace(self):
        self.assertEqual(content_hash("one   two"), content_hash("one two"))

    def test_language_filter_accepts_english(self):
        self.assertTrue(is_probably_english("Krishna speaks about devotion and wisdom."))

    def test_quality_rejects_tiny_text(self):
        self.assertFalse(is_quality_document("too short"))

    def test_quality_can_accept_short_scripture_records(self):
        text = "The soul is eternal and full of knowledge."
        self.assertTrue(is_quality_document(text, min_chars=20))


if __name__ == "__main__":
    unittest.main()
