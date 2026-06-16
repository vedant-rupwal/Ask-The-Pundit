# Pandit SLM Workspace

This workspace is the first from-scratch SLM milestone for Ask the Pandit.
It does not assume GPU access. The local target is a tiny smoke-test model;
the production target is a later 100M-300M parameter training run.

## Pipeline

1. Export scripture text from ChromaDB.
2. Crawl approved same-domain web pages into a tracked mixed-media raw corpus.
3. Clean, deduplicate, and normalize all documents.
4. Train a custom tokenizer.
5. Run a tiny transformer pretraining smoke test.
6. Build RAG-shaped supervised examples.
7. Evaluate checkpoint loading and simple inference.

## Suggested Commands

Run from the repo root:

```powershell
python slm/scripts/export_chroma_corpus.py --db-path chroma_db --out slm/data/processed/scripture_corpus.jsonl
python slm/scripts/crawl_mixed_media.py --url-file slm/data/web_urls.txt --out slm/data/raw_web/mixed_media_corpus.jsonl --max-depth 1 --max-pages-per-domain 20 --license-status user_approved_source
python slm/scripts/clean_corpus.py --input slm/data/processed/scripture_corpus.jsonl --input slm/data/raw_web/mixed_media_corpus.jsonl --out slm/data/processed/clean_corpus.jsonl
python slm/scripts/train_tokenizer.py --input slm/data/processed/clean_corpus.jsonl --out slm/models/tokenizer.json --vocab-size 8000
python slm/scripts/train_tiny_transformer.py --config slm/configs/tiny_smoke.json
python slm/scripts/build_rag_dataset.py --corpus slm/data/processed/scripture_corpus.jsonl --out slm/data/processed/rag_sft.jsonl
python slm/scripts/evaluate_smoke.py --checkpoint slm/models/tiny_smoke.pt --tokenizer slm/models/tokenizer.json
python slm/scripts/serve_local_slm.py --checkpoint slm/models/tiny_smoke.pt --tokenizer slm/models/tokenizer.json --port 7870
```

The training scripts require optional dependencies listed in `server/requirements.txt`.

For a larger crawl, increase limits gradually:

```powershell
python slm/scripts/crawl_mixed_media.py --url-file slm/data/web_urls.txt --out slm/data/raw_web/mixed_media_corpus.jsonl --max-depth 2 --max-pages-per-domain 500 --request-delay 1.0 --license-status user_approved_source
```

Mixed-media records are text-only derivatives for SLM training. Images store alt text,
titles, captions, and OCR status. Audio/video store captions, track metadata, transcript
links, and transcription status. Raw media files are not downloaded by this pipeline.

To route the current backend through the local endpoint:

```powershell
$env:SLM_PROVIDER="local_slm"
$env:LOCAL_SLM_ENDPOINT="http://127.0.0.1:7870/generate"
python server/app.py
```
