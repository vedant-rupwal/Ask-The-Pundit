import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

from corpus_utils import read_jsonl


def train_tokenizer(input_path: str, out_path: str, vocab_size: int):
    try:
        from tokenizers import Tokenizer
        from tokenizers.models import BPE
        from tokenizers.pre_tokenizers import ByteLevel
        from tokenizers.trainers import BpeTrainer
    except ImportError as error:
        raise SystemExit(
            "Missing optional dependency 'tokenizers'. Install requirements before training."
        ) from error

    def iterator():
        for row in read_jsonl(input_path):
            yield row["clean_text"]

    tokenizer = Tokenizer(BPE(unk_token="<unk>"))
    tokenizer.pre_tokenizer = ByteLevel(add_prefix_space=False)
    trainer = BpeTrainer(
        vocab_size=vocab_size,
        special_tokens=["<pad>", "<unk>", "<bos>", "<eos>"],
    )
    tokenizer.train_from_iterator(iterator(), trainer=trainer)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    tokenizer.save(out_path)
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Train a custom BPE tokenizer.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", default="slm/models/tokenizer.json")
    parser.add_argument("--vocab-size", type=int, default=8000)
    args = parser.parse_args()
    train_tokenizer(args.input, args.out, args.vocab_size)
    print(f"Saved tokenizer to {args.out}")


if __name__ == "__main__":
    main()
