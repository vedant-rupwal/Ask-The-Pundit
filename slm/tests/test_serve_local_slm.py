import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.append(str(SCRIPT_DIR))

from serve_local_slm import INSUFFICIENT_CONTEXT_RESPONSE, GenerateRequest, create_app


class ServeLocalSlmTests(unittest.TestCase):
    def test_health_without_checkpoint(self):
        app = create_app()
        self.assertFalse(app.state.model_ready)

    def test_request_model_refuses_empty_context_shape(self):
        payload = GenerateRequest(
            user_question="What is the soul?",
            retrieved_context="No relevant scripture passages were retrieved.",
        )
        self.assertEqual(payload.retrieved_context, "No relevant scripture passages were retrieved.")
        self.assertEqual(INSUFFICIENT_CONTEXT_RESPONSE, "I do not have enough retrieved scripture to answer that.")


if __name__ == "__main__":
    unittest.main()
