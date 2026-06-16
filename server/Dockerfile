FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y git-lfs && git lfs install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/chroma_db && chmod 777 /app/chroma_db
EXPOSE 7860
CMD ["python", "app.py"]