import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))


def evaluate(checkpoint_path: str, tokenizer_path: str):
    try:
        import torch
        from tokenizers import Tokenizer
    except ImportError as error:
        raise SystemExit(
            "Missing optional training dependencies. Install torch and tokenizers first."
        ) from error

    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    tokenizer = Tokenizer.from_file(tokenizer_path)
    prompt = "Question: What is the nature of the soul?\nRetrieved scripture:"
    encoded = tokenizer.encode(prompt).ids
    if not encoded:
        raise SystemExit("Tokenizer produced no tokens for the smoke prompt.")
    if "model_state" not in checkpoint:
        raise SystemExit("Checkpoint does not contain model_state.")
    print("Smoke evaluation passed: checkpoint and tokenizer load successfully.")


def main():
    parser = argparse.ArgumentParser(description="Validate tiny checkpoint/tokenizer artifacts.")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--tokenizer", required=True)
    args = parser.parse_args()
    evaluate(args.checkpoint, args.tokenizer)


if __name__ == "__main__":
    main()
