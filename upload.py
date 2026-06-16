import os
from huggingface_hub import HfApi

HF_TOKEN = os.getenv("HF_TOKEN")

if not HF_TOKEN:
    raise RuntimeError("HF_TOKEN is not set. Create a write-scoped token and set it as an environment variable.")

api = HfApi(token=HF_TOKEN)

print("Starting upload to Hugging Face...")

api.upload_folder(
    folder_path="./chroma_db",             # The local folder you want to upload
    repo_id="vedantrupwal/vedabase",       # Your dataset repo
    repo_type="dataset",                   # Specifying it's a dataset
    path_in_repo=""               # The folder name it will have on HF
)

print("✅ Upload Complete! The Pandit is ready.")
