import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.append(str(SERVER_DIR))

from slm_provider import INSUFFICIENT_CONTEXT_RESPONSE, MockSlmProvider, SlmRequest


class MockSlmProviderTests(unittest.TestCase):
    def test_refuses_without_context(self):
        provider = MockSlmProvider()
        answer = provider.generate(
            SlmRequest(
                user_question="What is the soul?",
                visible_screen_text="",
                retrieved_context="No relevant scripture passages were retrieved.",
                citation="",
            )
        )
        self.assertEqual(answer, INSUFFICIENT_CONTEXT_RESPONSE)

    def test_uses_retrieved_context_and_citation(self):
        provider = MockSlmProvider()
        answer = provider.generate(
            SlmRequest(
                user_question="What is the soul?",
                visible_screen_text="",
                retrieved_context="Citation: Bhagavad-gita 2.20\nText: The soul is eternal.",
                citation="Bhagavad-gita 2.20",
            )
        )
        self.assertIn("The soul is eternal.", answer)
        self.assertIn("Citation: Bhagavad-gita 2.20", answer)


if __name__ == "__main__":
    unittest.main()
