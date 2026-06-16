import subprocess
import os

REPO_ID = "vedantrupwal/vedabase" 

if __name__ == "__main__":
    print("Starting Pandit Server via Uvicorn...")
    subprocess.run(["uvicorn", "pandit_server:app", "--host", "0.0.0.0", "--port", "7860"])