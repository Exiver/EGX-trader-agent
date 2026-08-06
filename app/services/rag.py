"""
RAG pipeline for user-uploaded files. Chunks + embeds text with Gemini,
stores rows in SQLite (embeddings as JSON), and does brute-force cosine
similarity search at query time. See the note at the top of the Phase 5
build guide for why this isn't FAISS/Chroma.
"""
import json

import numpy as np
from google import genai
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.db_models import RagChunk
from app.core.retry import call_with_retry
EMBEDDING_MODEL = "gemini-embedding-001"
CHUNK_SIZE = 800     # characters, not tokens — simple and good enough for notes
CHUNK_OVERLAP = 100


class RagError(Exception):
    pass


def _get_client() -> genai.Client:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise RagError("GEMINI_API_KEY is not set — check your .env file.")
    return genai.Client(api_key=settings.gemini_api_key)


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Simple sliding-window chunker — good enough for personal notes.
    Swap for sentence-aware or semantic chunking later if uploaded docs
    get more complex (you've done that before, so you know the tradeoffs)."""
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts in one API call."""
    if not texts:
        return []
    client = _get_client()
    try:
        response = call_with_retry(client.models.embed_content, model=EMBEDDING_MODEL, contents=texts)
    except Exception as e:
        raise RagError(f"Embedding request failed: {e}") from e
    return [emb.values for emb in response.embeddings]


def ingest_file(db: Session, filename: str, text: str) -> int:
    """Chunk, embed, and store a file's text. Returns the number of chunks stored."""
    chunks = chunk_text(text)
    if not chunks:
        raise RagError("No text content found in file.")

    embeddings = embed_texts(chunks)

    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        db.add(
            RagChunk(
                filename=filename,
                chunk_index=i,
                chunk_text=chunk,
                embedding_json=json.dumps(embedding),
            )
        )
    db.commit()
    return len(chunks)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    a_arr, b_arr = np.array(a), np.array(b)
    denom = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    if denom == 0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / denom)


def retrieve_relevant_chunks(db: Session, query: str, top_k: int = 3) -> list[str]:
    """
    Brute-force similarity search across every stored chunk. Returns the
    top_k most relevant chunk texts, or an empty list if nothing's been
    uploaded yet — that's not an error, RAG context is optional, not
    required, for a recommendation to work.
    """
    all_chunks = db.query(RagChunk).all()
    if not all_chunks:
        return []

    query_embedding = embed_texts([query])[0]

    scored = [
        (chunk.chunk_text, _cosine_similarity(query_embedding, json.loads(chunk.embedding_json)))
        for chunk in all_chunks
    ]
    scored.sort(key=lambda x: x[1], reverse=True)

    return [text for text, _score in scored[:top_k]]