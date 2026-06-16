import chromadb
from sentence_transformers import SentenceTransformer

DB_PATH = "./chroma_db"
OLD_COLLECTION = "hindu_scriptures"
NEW_COLLECTION = "hindu_scriptures_fixed"

client = chromadb.PersistentClient(path=DB_PATH)
old_col = client.get_collection(name=OLD_COLLECTION)

print(f"Total entries found in SQLite: {old_col.count()}")

new_col = client.get_or_create_collection(name=NEW_COLLECTION)

batch_size = 500
total_count = old_col.count()

for i in range(0, total_count, batch_size):
    batch_data = old_col.get(
        include=['documents', 'metadatas', 'ids'],
        limit=batch_size,
        offset=i
    )
    
    if batch_data['ids']:
        print(f"Re-indexing items {i} to {i + len(batch_data['ids'])}...")
        new_col.add(
            ids=batch_data['ids'],
            documents=batch_data['documents'],
            metadatas=batch_data['metadatas']
        )

print("Sealing the new index...")
client.delete_collection(name=OLD_COLLECTION) 
del client 

print("Done! You now have a matched set of SQLite and Vector files.")