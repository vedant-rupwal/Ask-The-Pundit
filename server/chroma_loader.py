from functools import lru_cache
from uuid import uuid4
import re

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer


EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"


def sanitize_collection_name(collection_name):
    """
    Sanitize collection name for ChromaDB by:
    - Replacing spaces with underscores
    - Removing commas and special characters
    - Converting to lowercase for consistency
    """
    sanitized = collection_name.replace(" ", "_")
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '', sanitized)
    sanitized = sanitized.lower()
    return sanitized if sanitized else "default_collection"


@lru_cache(maxsize=1)
def _get_embedding_model():
    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def load_chunks_into_db(chunks, collection_name, db_path="./chroma_db"):
    sanitized_name = sanitize_collection_name(collection_name)
    
    client = chromadb.PersistentClient(path=db_path, settings=Settings())
    collection = client.get_or_create_collection(
        name=sanitized_name,
        metadata={"hnsw:space": "cosine"} 
    )

    documents = []
    metadatas = []
    ids = []

    for chunk in chunks:
        page_content = (chunk or {}).get("page_content", "")
        metadata = (chunk or {}).get("metadata", {})

        if not isinstance(page_content, str):
            continue

        page_content = page_content.strip()
        if not page_content:
            continue

        documents.append(page_content)
        metadatas.append(metadata if isinstance(metadata, dict) else {})
        ids.append(str(uuid4()))

    if not documents:
        return collection

    model = _get_embedding_model()
    embeddings = model.encode(documents, convert_to_numpy=True).tolist()

    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings,
    )

    return collection


if __name__ == "__main__":
    sample_chunks = [
        {
            "page_content": (
                "The soul is never born and never dies. It is eternal and cannot be destroyed."
            ),
            "metadata": {
                "book_title": "Bhagavad-gita",
                "chapter_num": 2,
                "verse_num": 20,
                "type": "Core Verse",
            },
        },
        {
            "page_content": (
                "When dharma declines and irreligion rises, the Supreme appears to protect the righteous."
            ),
            "metadata": {
                "book_title": "Bhagavad-gita",
                "chapter_num": 4,
                "verse_num": 7,
                "type": "Core Verse",
            },
        },
        {
            "page_content": (
                "One should elevate oneself by the mind and not degrade oneself, because the mind can be friend or enemy."
            ),
            "metadata": {
                "book_title": "Bhagavad-gita",
                "chapter_num": 6,
                "verse_num": 5,
                "type": "Purport",
                "paragraph": 1,
            },
        },
    ]

    collection = load_chunks_into_db(sample_chunks, collection_name="Bhagavad-gita")

    query_text = "Which verse talks about the eternal nature of the soul?"
    query_embedding = _get_embedding_model().encode(
        [query_text], convert_to_numpy=True
    ).tolist()

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=2,
        include=["documents", "metadatas", "distances"],
    )

    print(f"Collection count: {collection.count()}")
    print(f"Query: {query_text}")
    print("Top matches:")

    for index, document in enumerate(results["documents"][0], start=1):
        metadata = results["metadatas"][0][index - 1]
        distance = results["distances"][0][index - 1]
        print(f"{index}. Distance: {distance:.4f}")
        print(f"   Metadata: {metadata}")
        print(f"   Document: {document}")
