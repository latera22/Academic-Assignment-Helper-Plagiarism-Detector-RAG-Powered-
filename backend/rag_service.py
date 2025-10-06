# backend/rag_service.py
import os
import openai
from typing import List, Tuple, Dict
from sqlalchemy import text
from sqlalchemy.orm import Session
from .models import AcademicSource
import numpy as np

# Load settings from env
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", 1536))

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY must be set in environment")

openai.api_key = OPENAI_API_KEY

# -------------------------
# Embedding helpers
# -------------------------
def embed_text(text: str) -> List[float]:
    """
    Create an embedding vector for `text` using OpenAI.
    Returns a list[float] of length EMBEDDING_DIM.
    """
    # Keep a single call - adapt if using new client libraries or rate-limits
    resp = openai.Embedding.create(model=EMBEDDING_MODEL, input=text)
    vec = resp["data"][0]["embedding"]
    if len(vec) != EMBEDDING_DIM:
        # pad or trim if needed (better to set correct EMBEDDING_DIM)
        vec = (vec + [0.0] * EMBEDDING_DIM)[:EMBEDDING_DIM]
    return vec

# -------------------------
# Database helpers
# -------------------------
def upsert_academic_source(db: Session, title: str, authors: str, year: int, abstract: str, full_text: str, source_type: str = "paper") -> AcademicSource:
    """
    Insert or update an academic source and its embedding.
    """
    # compute embedding
    embedding = embed_text(full_text or abstract or title)
    # Try to find an existing record by title (or create new)
    src = db.query(AcademicSource).filter(AcademicSource.title == title).first()
    if not src:
        src = AcademicSource(title=title, authors=authors, publication_year=year, abstract=abstract, full_text=full_text, source_type=source_type, embedding=embedding)
        db.add(src)
    else:
        src.authors = authors
        src.publication_year = year
        src.abstract = abstract
        src.full_text = full_text
        src.source_type = source_type
        src.embedding = embedding
    db.commit()
    db.refresh(src)
    return src

def similarity_search(db: Session, query_embedding: List[float], top_k: int = 5) -> List[Tuple[AcademicSource, float]]:
    """
    Return top_k AcademicSource matched with similarity score (cosine similarity).
    Uses PG vector cosine distance ordering (1 - cosine sim) if vector_cosine_ops is available.
    """
    # Use raw SQL for pgvector cosine similarity (assuming vector column name `embedding`)
    # This returns distance; convert to similarity = 1 - distance for cosine distance
    sql = text(f"""
        SELECT id, title, authors, publication_year, abstract, full_text, source_type, embedding,
               1 - (embedding <#> :q) AS similarity
        FROM academic_sources
        ORDER BY embedding <#> :q
        LIMIT :k
    """)
    # :q needs to be array format accepted by SQLAlchemy/postgres. We'll pass list -> composite via psycopg2
    res = db.execute(sql, {"q": query_embedding, "k": top_k})
    results = []
    for row in res:
        # fetch object by id to return ORM object (or construct lightweight dict)
        src = db.query(AcademicSource).get(row["id"])
        sim = float(row["similarity"])
        results.append((src, sim))
    return results

# -------------------------
# Plagiarism scoring
# -------------------------
def compute_plagiarism_score(db: Session, text_to_check: str, chunk_size: int = 512, overlap: int = 64, top_k: int = 3) -> Dict:
    """
    1. Split `text_to_check` into chunks
    2. Create embeddings for each chunk
    3. Run similarity_search for each chunk
    4. Aggregate a plagiarism score and return flagged sections with matches
    """
    # naive text splitter
    tokens = text_to_check.split()
    chunks = []
    i = 0
    while i < len(tokens):
        chunk_tokens = tokens[i:i+chunk_size]
        chunks.append(" ".join(chunk_tokens))
        i += chunk_size - overlap

    flagged = []
    total_score = 0.0
    counted = 0

    for idx, chunk in enumerate(chunks):
        emb = embed_text(chunk)
        matches = similarity_search(db, emb, top_k=top_k)
        # take best match similarity
        best_sim = 0.0
        best_src = None
        for src, sim in matches:
            if sim > best_sim:
                best_sim = sim
                best_src = src
        # if above threshold, flag
        threshold = float(os.getenv("PLAGIARISM_SIMILARITY_THRESHOLD", 0.80))
        if best_sim >= threshold:
            flagged.append({
                "chunk_index": idx,
                "chunk_text_snippet": chunk[:400],
                "similarity": best_sim,
                "source_id": best_src.id if best_src else None,
                "source_title": best_src.title if best_src else None
            })
        total_score += best_sim
        counted += 1

    avg_score = (total_score / counted) if counted else 0.0
    # normalize to 0..1 (already cosine similarity)
    return {
        "plagiarism_score": avg_score,
        "flagged_sections": flagged,
        "chunks_count": len(chunks)
    }
