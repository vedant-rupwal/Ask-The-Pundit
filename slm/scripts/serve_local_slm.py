import argparse
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel


INSUFFICIENT_CONTEXT_RESPONSE = "I do not have enough retrieved scripture to answer that."


class GenerateRequest(BaseModel):
    role: str = "Scripture Scholar"
    user_question: str
    visible_screen_text: str = ""
    retrieved_context: str
    citation: str = ""
    rules: list[str] = []


def create_app(checkpoint_path: str | None = None, tokenizer_path: str | None = None) -> FastAPI:
    app = FastAPI(title="Pandit Local SLM")
    app.state.checkpoint_path = checkpoint_path
    app.state.tokenizer_path = tokenizer_path
    app.state.model_ready = False
    app.state.model_error = None

    if checkpoint_path and tokenizer_path:
        try:
            # The tiny smoke checkpoint proves loading, but generation is intentionally
            # conservative until a trained instruction checkpoint exists.
            import torch
            from tokenizers import Tokenizer

            app.state.checkpoint = torch.load(checkpoint_path, map_location="cpu")
            app.state.tokenizer = Tokenizer.from_file(tokenizer_path)
            app.state.model_ready = True
        except Exception as error:
            app.state.model_error = str(error)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "online",
            "model_ready": app.state.model_ready,
            "checkpoint_path": app.state.checkpoint_path,
            "tokenizer_path": app.state.tokenizer_path,
            "model_error": app.state.model_error,
        }

    @app.post("/generate")
    def generate(payload: GenerateRequest) -> dict[str, str]:
        context = payload.retrieved_context.strip()
        if not context or context == "No relevant scripture passages were retrieved.":
            return {"answer": INSUFFICIENT_CONTEXT_RESPONSE}

        answer = (
            "Local Pandit SLM endpoint is wired. A trained instruction checkpoint "
            "is required before neural generation is enabled. Retrieved context was received."
        )
        if payload.citation:
            answer += f"\n\nCitation: {payload.citation}"
        return {"answer": answer}

    return app


def main():
    parser = argparse.ArgumentParser(description="Serve the local Pandit SLM endpoint.")
    parser.add_argument("--checkpoint")
    parser.add_argument("--tokenizer")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7870)
    args = parser.parse_args()

    import uvicorn

    app = create_app(args.checkpoint, args.tokenizer)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
