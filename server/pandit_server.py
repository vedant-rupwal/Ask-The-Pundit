import os
import subprocess
from huggingface_hub import snapshot_download, hf_hub_download
from typing import List, Dict, Any

os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "true"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1" 
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from contextlib import asynccontextmanager
import httpx
import json
import chromadb
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel
from sentence_transformers import CrossEncoder, SentenceTransformer
import re

from slm_provider import SlmRequest, get_slm_provider, stream_text

COLLECTIONS_REGISTRY = [
    "Bhagavad-gita",
    "Srimad-Bhagavatam Canto 1",
    "Srimad-Bhagavatam Canto 2",
    "Srimad-Bhagavatam Canto 3",
    "Srimad-Bhagavatam Canto 4",
    "Srimad-Bhagavatam Canto 5",
    "Srimad-Bhagavatam Canto 6",
    "Srimad-Bhagavatam Canto 7",
    "Srimad-Bhagavatam Canto 8",
    "Srimad-Bhagavatam Canto 9",
    "Srimad-Bhagavatam Canto 10",
    "Srimad-Bhagavatam Canto 11",
    "Srimad-Bhagavatam Canto 12",
    "Supplementary Books",
]

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
OPENAI_MODEL = "Qwen/Qwen2.5-7B-Instruct"
SLM_PROVIDER = os.getenv("SLM_PROVIDER", "hf_router").strip()
TOP_K_RESULTS = 10
FINAL_TOP_RESULTS = 3
MAX_CONTEXT_CHARS = 7000

CHROMA_DB_PATH = os.path.abspath("./chroma_db")
REPO_ID = "vedantrupwal/vedabase"
HF_TOKEN = os.getenv("HF_TOKEN")
last_query = {}

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

def determine_collections_to_search(app, tool_book_filter):
    """
    Determine which collections to search based on the tool_book_filter.
    If no filter or empty filter, return all registered collections.
    Otherwise, map requested books to the hybrid collection layout.
    """
    if not tool_book_filter:
        return [(name, app.state.collections.get(name), None) for name in app.state.collections]

    collections = []
    for requested_book in tool_book_filter:
        if requested_book == "Bhagavad-gita":
            collections.append(("Bhagavad-gita", app.state.collections.get("Bhagavad-gita"), None))
        elif requested_book == "Srimad-Bhagavatam":
            for canto_num in range(1, 13):
                canto_name = f"Srimad-Bhagavatam Canto {canto_num}"
                collections.append((canto_name, app.state.collections.get(canto_name), None))
        else:
            collections.append(("Supplementary Books", app.state.collections.get("Supplementary Books"), {"book_title": requested_book}))

    return collections

def sync_database():
    if not HF_TOKEN:
        print("--- ERROR: HF_TOKEN NOT FOUND ---")
        return
    
    try:
        print(f"--- STARTING DEEP SYNC FROM {REPO_ID} ---")
        snapshot_download(
            repo_id=REPO_ID,
            repo_type="dataset",
            local_dir=CHROMA_DB_PATH,
            token=HF_TOKEN,
            force_download=True,
            local_dir_use_symlinks=False
        )
        
        db_file = os.path.join(CHROMA_DB_PATH, "chroma.sqlite3")
        if os.path.exists(db_file):
            size = os.path.getsize(db_file) / (1024*1024)
            print(f"--- SYNC SUCCESSFUL. DB SIZE: {size:.2f} MB ---")
        else:
            print(f"--- SYNC WARNING: {db_file} not found. Checking current dir... ---")
            print(f"Directory Contents: {os.listdir('.')}")
    except Exception as e:
        print(f"--- SYNC ERROR: {e} ---")

@asynccontextmanager
async def lifespan(app: FastAPI):
    sync_database()

    print("Loading Models...")
    app.state.model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    app.state.reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

    print(f"Connecting to ChromaDB at {CHROMA_DB_PATH}...")
    db_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

    app.state.collections = {}
    total_verses = 0
    
    for book_name in COLLECTIONS_REGISTRY:
        sanitized_name = sanitize_collection_name(book_name)
        try:
            collection = db_client.get_collection(name=sanitized_name)
            app.state.collections[book_name] = collection
            collection_count = collection.count()
            total_verses += collection_count
            print(f"   Loaded '{book_name}' ({sanitized_name}): {collection_count} verses")
        except Exception as e:
            print(f"    Collection '{book_name}' ({sanitized_name}) not found: {e}")
    
    print(f"---  DATABASE CONNECTED. TOTAL VERSES: {total_verses} ---")
    print(f"--- Active Collections: {len(app.state.collections)} ---")
    yield

app = FastAPI(title="Ask the Pandit API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    user_question: str
    visible_screen_text: str
    book_filter: str | None = None
    history: List[Dict[str, Any]] = []  


SYSTEM_PROMPT_INSTRUCTIONS = (
    "You are a theological expert on {expertise_area} "
    "STRICT RULE: You must respond ONLY in English. Do not use Chinese characters. "
    "The user is reading this text on their screen: "
    "{visible_screen_text}. "
    "They are asking this question: "
    "{user_question}. "
    "Answer their question concisely by applying the wisdom from these "
    "retrieved scriptures: "
    "{chroma_results}. "
    "Do not hallucinate scriptures outside of what is provided."
)


def get_openai_client():
    if not HF_TOKEN:
        raise RuntimeError("HF_TOKEN is not set.")

    return OpenAI(
        base_url="https://router.huggingface.co/v1",
        api_key=HF_TOKEN,
        timeout=30.0,
    )


def format_chroma_results(documents, metadatas):
    formatted_results = []
    seen_texts = set()

    for document, metadata in zip(documents, metadatas):
        if document in seen_texts:
            print(f"Skipping duplicate text.")
            continue
        
        seen_texts.add(document)
        safe_metadata = metadata or {}
        citation = build_citation(safe_metadata)
        content_type = safe_metadata.get("type", "Passage")
        paragraph = safe_metadata.get("paragraph")

        reference = citation
        if paragraph:
            reference += f", paragraph {paragraph}"

        formatted_results.append(f"Citation: {reference} ({content_type})\nText: {document}")

    if not formatted_results:
        return "No relevant scripture passages were retrieved."

    return "\n\n".join(formatted_results)


def build_citation(metadata):
    safe_metadata = metadata or {}
    source_ref = safe_metadata.get("source_ref")
    if source_ref:
        return source_ref

    book_title = safe_metadata.get("book_title", "Unknown Text")
    chapter_num = safe_metadata.get("chapter_num")
    verse_num = safe_metadata.get("verse_num")

    if chapter_num and verse_num:
        if str(chapter_num).lower() == "mantra":
            return f"{book_title} Mantra {verse_num}"
        return f"{book_title} {chapter_num}.{verse_num}"
    if verse_num:
        return f"{book_title} {verse_num}"
    if chapter_num:
        return f"{book_title} Chapter {chapter_num}"
    return book_title


def rerank_results(user_question, documents, metadatas, reranker, top_n):
    if not documents:
        return [], []

    query_document_pairs = [[user_question, document] for document in documents]
    scores = reranker.predict(query_document_pairs)

    ranked_items = sorted(
        zip(documents, metadatas, scores),
        key=lambda item: item[2],
        reverse=True,
    )
    top_ranked_items = ranked_items[:top_n]

    reranked_documents = [item[0] for item in top_ranked_items]
    reranked_metadatas = [item[1] for item in top_ranked_items]
    return reranked_documents, reranked_metadatas


def truncate_text(text, max_length):
    if max_length <= 0:
        return ""

    if len(text) <= max_length:
        return text

    marker = "[...]"
    if max_length <= len(marker):
        return marker[:max_length]

    return text[: max_length - len(marker)] + marker


def parse_books_filter(raw_filter):
    if not raw_filter or raw_filter.lower() in ["all", "all books"]:
        return "Vedic scriptures", []

    books_list = [book.strip() for book in raw_filter.split(",") if book.strip()]
    if len(books_list) == 1:
        expertise_area = books_list[0]
    elif len(books_list) == 2:
        expertise_area = f"{books_list[0]} and {books_list[1]}"
    else:
        expertise_area = ", ".join(books_list[:-1]) + f", and {books_list[-1]}"

    return expertise_area, books_list


def retrieve_scripture_context(
    request: Request,
    query_text: str,
    visible_screen_text: str,
    books_list: List[str],
):
    model = request.app.state.model
    reranker = request.app.state.reranker
    hybrid_query = query_text
    if visible_screen_text:
        hybrid_query = f"{query_text}\n\n{visible_screen_text[:300]}"

    query_embedding = model.encode([hybrid_query], convert_to_numpy=True).tolist()
    collections_to_search = determine_collections_to_search(request.app, books_list)
    batch_retrieved_documents = []
    batch_retrieved_metadatas = []

    for collection_name, collection, base_where in collections_to_search:
        if collection is None:
            continue

        target_n_results = 50 if collection_name == "Supplementary Books" else 10
        query_kwargs = {
            "query_embeddings": query_embedding,
            "n_results": target_n_results,
            "include": ["documents", "metadatas"],
        }
        if base_where:
            query_kwargs["where"] = base_where

        try:
            query_results = collection.query(**query_kwargs)
            docs = query_results.get("documents", [[]])[0]
            metas = query_results.get("metadatas", [[]])[0]
            batch_retrieved_documents.extend(docs)
            batch_retrieved_metadatas.extend(metas)
            filter_message = f" with filter={base_where}" if base_where else ""
            print(f"  Local SLM search in '{collection_name}'{filter_message}: {len(docs)} results")
        except Exception as e:
            print(f"  Error searching '{collection_name}': {e}")

    reranked_docs, reranked_metas = rerank_results(
        query_text,
        batch_retrieved_documents,
        batch_retrieved_metadatas,
        reranker,
        FINAL_TOP_RESULTS,
    )
    if not reranked_docs and batch_retrieved_documents:
        reranked_docs = batch_retrieved_documents[:FINAL_TOP_RESULTS]
        reranked_metas = batch_retrieved_metadatas[:FINAL_TOP_RESULTS]

    raw_chroma_results = format_chroma_results(reranked_docs, reranked_metas)
    citations = [build_citation(metadata) for metadata in reranked_metas]
    final_citation = ", ".join(list(dict.fromkeys(citations)))
    return hybrid_query, raw_chroma_results, final_citation


@app.get("/last-query-log")
async def get_last_query_log():
    global last_query 
    return last_query

@app.get("/debug-db")
async def debug_db():
    try:
        collection = app.state.db
        count = collection.count()
        peek = collection.peek(limit=2)
        sample_id = peek['ids'][0] if peek['ids'] else "none"
        
        return {
            "status": "Diagnostic Complete",
            "count_in_db": count,
            "sample_ids": peek['ids'],
            "sample_metadata": peek['metadatas'],
            "embedding_model_used_on_server": EMBEDDING_MODEL_NAME,
            "can_read_sqlite": len(peek['ids']) > 0
        }
    except Exception as e:
        return {"diagnostic_error": str(e)}

@app.get("/")
def health_check():
    import os
    import chromadb
    try:
        temp_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        collections = temp_client.list_collections()
        col_names = [c.name for c in collections]
        count = 0
        if col_names:
            col = temp_client.get_collection(name=col_names[0])
            count = col.count()
    except Exception as e:
        col_names = []
        count = f"Error: {str(e)}"

    return {
        "status": "online",
        "slm_provider": SLM_PROVIDER,
        "found_collections": col_names,
        "first_col_count": count,
        "database_path": CHROMA_DB_PATH,
        "files_found": os.listdir(CHROMA_DB_PATH) if os.path.exists(CHROMA_DB_PATH) else []
    }

@app.post("/ask-the-pandit")
async def ask_the_pandit(request: Request, payload: QueryRequest):
    global last_query
    user_question = payload.user_question.strip()
    visible_screen_text = payload.visible_screen_text.strip()
    raw_filter = (payload.book_filter or "").strip()

    if not user_question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        expertise_area, books_list = parse_books_filter(raw_filter)

        if SLM_PROVIDER != "hf_router":
            hybrid_query, raw_chroma_results, final_citation = retrieve_scripture_context(
                request,
                user_question,
                visible_screen_text,
                books_list,
            )
            provider = get_slm_provider(SLM_PROVIDER)
            direct_answer = provider.generate(
                SlmRequest(
                    user_question=user_question,
                    visible_screen_text=visible_screen_text,
                    retrieved_context=raw_chroma_results,
                    citation=final_citation,
                )
            )
            last_query["hybrid_query"] = hybrid_query
            last_query["raw_chroma_results"] = raw_chroma_results
            last_query["system_prompt"] = (
                f"Provider: {provider.name}. "
                "Direct RAG path used; retrieved scripture was passed to the local SLM provider."
            )
            return StreamingResponse(
                stream_text(direct_answer),
                media_type="text/plain; charset=utf-8",
            )

        model = request.app.state.model
        reranker = request.app.state.reranker
        client = get_openai_client()

        search_tool = {
            "type": "function",
            "function": {
                "name": "search_scriptures",
                "description": "Search the Vedic scriptures database for relevant passages based on a query and optional book filter.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "queries": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            },
                            "description": "A list of search queries. CRITICAL: If the user asks to compare two concepts or books, you MUST break them into separate, distinct search queries (e.g., ['Sri Isopanisad main theme', 'Nectar of Instruction main theme']). NEVER put two different books in the same query string."
                        },
                        "book_filter": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [
                                    "Bhagavad-gita", 
                                    "Srimad-Bhagavatam", 
                                    "Sri Isopanisad", 
                                    "Teachings of Lord Kapila", 
                                    "Teachings of Queen Kunti",
                                    "Nectar of Instruction", 
                                    "Nectar of Devotion",    
                                    "Teachings of Lord Caitanya",
                                    "The Science of Self-Realization",
                                    "Beyond Birth and Death",
                                    "Bhakti: The Art of Eternal Love",
                                    "On the Way to Kṛṣṇa",
                                    "The Perfection of Yoga",
                                    "Perfect Questions, Perfect Answers",
                                    "A Second Chance",
                                    "The Journey of Self-Discovery",
                                    "Rāja-vidyā: The King of Knowledge",
                                    "Kṛṣṇa, the Supreme Personality of Godhead"
                                ]
                            },
                            "description": "Optional list of book titles to filter the search. If empty, search all books."
                        }
                        ,
                        "verse_filter": {
                            "type": "string",
                            "description": "Optional exact verse or mantra number to filter by (e.g., '1', '2.13', '15'). Only use this if the user asks for a specific verse number."
                        }
                    },
                    "required": ["queries"] 
                }
            }
        }
       
        messages = [
            {
                "role": "system",
                "content": f"You are a theological expert on {expertise_area}. The user is reading this text on their screen: '{visible_screen_text}'. CRITICAL INSTRUCTION: You MUST use the search_scriptures tool if the user provides a topic, name (e.g., 'Krishna'), or question. ONLY bypass the tool if the user is saying a casual greeting like 'Hello' or 'Thank you'. Provide concise answers in English only."
            }
        ]

        if hasattr(payload, 'history') and payload.history:
            recent_history = payload.history[-6:]
            for past_msg in recent_history:
                if past_msg.get("role") in ["user", "assistant"] and past_msg.get("text"):
                    messages.append({
                        "role": past_msg["role"],
                        "content": past_msg["text"]
                    })

        messages.append({
            "role": "user", 
            "content": f"{user_question}\n\n[SYSTEM ENFORCEMENT: If the text above is a theological concept, name, or question, you MUST trigger the search_scriptures tool immediately. Do not answer directly from memory. ONLY answer directly if the text is a standard greeting like 'Hello'.]"
        })

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            tools=[search_tool],
            tool_choice="auto",
            max_tokens=500,
            temperature=0.7
        )

        tool_calls = response.choices[0].message.tool_calls
        final_citation = ""
        direct_answer = ""
        
        if tool_calls:
            tool_call = tool_calls[0]
            args = json.loads(tool_call.function.arguments)
            
            search_queries = args.get("queries", [user_question])
            if isinstance(search_queries, str):
                search_queries = [search_queries]

            tool_book_filter = args.get("book_filter", [])
            raw_verse = args.get("verse_filter")
            tool_verse_filter = str(raw_verse).strip() if raw_verse is not None else None

            # STRICT OVERRIDE: If the user selected specific books in the UI frontend,
            # force the AI to respect only those books.
            if books_list:
                tool_book_filter = books_list

            all_reranked_docs = []
            all_reranked_metas = []

            for single_query in search_queries:
                hybrid_query = single_query
                if visible_screen_text:
                    hybrid_query = f"{single_query}\n\n{visible_screen_text[:300]}"

                query_embedding = model.encode([hybrid_query], convert_to_numpy=True).tolist()

                collections_to_search = determine_collections_to_search(request.app, tool_book_filter)

                if not collections_to_search:
                    print(f"No collections found for filter: {tool_book_filter}")
                    continue

                batch_retrieved_documents = []
                batch_retrieved_metadatas = []

                for collection_name, collection, base_where in collections_to_search:
                    if collection is None:
                        continue
                    final_where = None

                    if base_where and tool_verse_filter:
                        final_where = {"$and": [base_where, {"verse_num": tool_verse_filter}]}
                    elif tool_verse_filter:
                        final_where = {"verse_num": tool_verse_filter}
                    elif base_where:
                        final_where = base_where
                    target_n_results = 50 if collection_name == "Supplementary Books" else 10

                    query_kwargs = {
                        "query_embeddings": query_embedding,
                        "n_results": target_n_results,
                        "include": ["documents", "metadatas"],
                    }
                    if final_where:
                        query_kwargs["where"] = final_where

                    try:
                        query_results = collection.query(**query_kwargs)
                        docs = query_results.get("documents", [[]])[0]
                        metas = query_results.get("metadatas", [[]])[0]

                        batch_retrieved_documents.extend(docs)
                        batch_retrieved_metadatas.extend(metas)

                        filter_message = f" with filter={final_where}" if final_where else ""
                        print(f"  Search in '{collection_name}'{filter_message}: {len(docs)} results")
                    except Exception as e:
                        print(f"  Error searching '{collection_name}': {e}")
                
                reranked_docs, reranked_metas = rerank_results(
                    single_query,
                    batch_retrieved_documents,
                    batch_retrieved_metadatas,
                    reranker,
                    FINAL_TOP_RESULTS,
                )

                if not reranked_docs and batch_retrieved_documents:
                    reranked_docs = batch_retrieved_documents[:3]
                    reranked_metas = batch_retrieved_metadatas[:3]
                
                all_reranked_docs.extend(reranked_docs)
                all_reranked_metas.extend(reranked_metas)

            raw_chroma_results = format_chroma_results(all_reranked_docs, all_reranked_metas)
            citations = [build_citation(m) for m in all_reranked_metas]
            final_citation = ", ".join(list(dict.fromkeys(citations)))

            messages.append(response.choices[0].message)
            messages.append({
                "role": "tool",
                "content": raw_chroma_results,
                "tool_call_id": tool_call.id
            })
            
            if raw_chroma_results == "No relevant scripture passages were retrieved.":
                messages.append({
                    "role": "system",
                    "content": "CRITICAL INSTRUCTION: The database search returned zero results. You are FORBIDDEN from answering the question. You MUST reply EXACTLY with this phrase and absolutely nothing else: 'I do not have enough retrieved scripture to answer that.' Do not add any introductory words."
                })
            else:
                messages.append({
                    "role": "system",
                    "content": "You are a faithful messenger. Answer the user's question using ONLY the retrieved scripture text provided above. You are explicitly allowed to use reading comprehension to connect pronouns to their subjects, and you may interpret similes or metaphors. IF the user's question is based on a false premise that is directly contradicted by the text, you must use the text to correct them. However, if the text does NOT contain the answer or does not address the core topic, you must reply with: 'I do not have enough retrieved scripture to answer that.' Do not use outside knowledge."})
            last_query["hybrid_query"] = " | ".join(search_queries)
            last_query["raw_chroma_results"] = raw_chroma_results
            last_query["system_prompt"] = f"Tool used: search_scriptures with queries={search_queries}, book_filter={tool_book_filter}"

        else:
            direct_answer = response.choices[0].message.content
            
            last_query["hybrid_query"] = "No search performed (Direct Answer)"
            last_query["raw_chroma_results"] = "N/A"
            last_query["system_prompt"] = "The AI agent chose to answer directly without using the database."
            
    except Exception as error:
        print(f"Server Error: {error}")
        raise HTTPException(status_code=500, detail=f"Query Failed: {error}")

    def stream_answer():
        try:
            if tool_calls:
                response = client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=messages,
                    stream=True,
                    max_tokens=500,
                    temperature=0.7
                )
                
                emitted_content = False
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        emitted_content = True
                        yield chunk.choices[0].delta.content
                
                if emitted_content:
                    yield f"\n\nCitation: {final_citation}"
                else:
                    yield "The Pandit is silent today."
            else:
                yield direct_answer or "The Pandit has no direct answer."

        except Exception as e:
            print(f"DEBUG ERROR: {str(e)}")
            yield "The Pandit encountered a network disturbance."

    try:
        collections_count = sum(col.count() for col in request.app.state.collections.values() if col)
        print(f"--- Querying Multi-Collection DB: {len(request.app.state.collections)} collections, {collections_count} total items ---")
    except Exception as e:
        print(f"--- State Access Error: {e} ---")

    return StreamingResponse(stream_answer(), media_type="text/plain; charset=utf-8")
