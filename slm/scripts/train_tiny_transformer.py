import argparse
import json
import math
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

from corpus_utils import read_jsonl


def require_training_deps():
    try:
        import torch
        from tokenizers import Tokenizer
    except ImportError as error:
        raise SystemExit(
            "Missing optional training dependencies. Install torch and tokenizers first."
        ) from error
    return torch, Tokenizer


def load_tokens(torch, tokenizer, corpus_path: str):
    ids = []
    for row in read_jsonl(corpus_path):
        ids.extend(tokenizer.encode(row["clean_text"]).ids)
        ids.append(tokenizer.token_to_id("<eos>") or 3)
    if len(ids) < 256:
        raise SystemExit("Corpus is too small for even the tiny smoke test.")
    return torch.tensor(ids, dtype=torch.long)


class TinyCausalTransformer:
    @staticmethod
    def build(torch, vocab_size, block_size, n_layer, n_head, n_embd, dropout):
        nn = torch.nn

        class Model(nn.Module):
            def __init__(self):
                super().__init__()
                self.block_size = block_size
                self.token = nn.Embedding(vocab_size, n_embd)
                self.position = nn.Embedding(block_size, n_embd)
                layer = nn.TransformerEncoderLayer(
                    d_model=n_embd,
                    nhead=n_head,
                    dim_feedforward=4 * n_embd,
                    dropout=dropout,
                    batch_first=True,
                    activation="gelu",
                )
                self.layers = nn.TransformerEncoder(layer, num_layers=n_layer)
                self.norm = nn.LayerNorm(n_embd)
                self.head = nn.Linear(n_embd, vocab_size, bias=False)

            def forward(self, idx, targets=None):
                batch, length = idx.shape
                positions = torch.arange(length, device=idx.device)
                x = self.token(idx) + self.position(positions)[None, :, :]
                mask = torch.triu(
                    torch.ones(length, length, device=idx.device) * float("-inf"),
                    diagonal=1,
                )
                x = self.layers(x, mask=mask)
                logits = self.head(self.norm(x))
                loss = None
                if targets is not None:
                    loss = nn.functional.cross_entropy(
                        logits.reshape(batch * length, -1),
                        targets.reshape(batch * length),
                    )
                return logits, loss

        return Model()


def get_batch(torch, tokens, batch_size, block_size):
    max_start = len(tokens) - block_size - 1
    starts = torch.randint(0, max_start, (batch_size,))
    x = torch.stack([tokens[start : start + block_size] for start in starts])
    y = torch.stack([tokens[start + 1 : start + block_size + 1] for start in starts])
    return x, y


def train_from_config(config_path: str):
    torch, Tokenizer = require_training_deps()
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    tokenizer = Tokenizer.from_file(config["tokenizer"])
    tokens = load_tokens(torch, tokenizer, config["train_corpus"])

    model_config = config["model"]
    vocab_size = max(model_config["vocab_size"], tokenizer.get_vocab_size())
    model = TinyCausalTransformer.build(
        torch,
        vocab_size=vocab_size,
        block_size=config["block_size"],
        n_layer=model_config["n_layer"],
        n_head=model_config["n_head"],
        n_embd=model_config["n_embd"],
        dropout=model_config["dropout"],
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=config["learning_rate"])
    model.train()

    for step in range(config["max_steps"]):
        x, y = get_batch(torch, tokens, config["batch_size"], config["block_size"])
        _, loss = model(x, y)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        if step == 0 or (step + 1) == config["max_steps"]:
            print(f"step={step + 1} loss={loss.item():.4f} ppl={math.exp(min(loss.item(), 20)):.2f}")

    out_path = Path(config["checkpoint_out"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"model_state": model.state_dict(), "config": config}, out_path)
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Run a tiny CPU-safe transformer smoke test.")
    parser.add_argument("--config", default="slm/configs/tiny_smoke.json")
    args = parser.parse_args()
    out_path = train_from_config(args.config)
    print(f"Saved checkpoint to {out_path}")


if __name__ == "__main__":
    main()
