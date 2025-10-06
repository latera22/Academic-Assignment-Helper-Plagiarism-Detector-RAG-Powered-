# backend/analyze.py
import os
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from .auth import get_db
from .models import Assignment, AnalysisResult
from .rag_service import compute_plagiarism_score, embed_text, similarity_search
import json

router = APIRouter(prefix="/analyze", tags=["Analysis"])

class AnalyzePayload(BaseModel):
    assignment_id: int
    extracted_text: str
    word_count: int | None = None

@router.post("/callback")
def analyze_callback(payload: AnalyzePayload, db: Session = Depends(get_db)):
    # Confirm assignment exists
    assignment = db.query(Assignment).filter(Assignment.id == payload.assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    # Update original_text & word_count
    assignment.original_text = payload.extracted_text
    if payload.word_count:
        assignment.word_count = payload.word_count
    db.commit()

    # Compute plagiarism score & flagged sections
    result = compute_plagiarism_score(db, payload.extracted_text)

    # Also prepare suggested_sources = top matches for whole doc (single embedding)
    doc_embedding = embed_text(payload.extracted_text[:2000])  # sample of whole doc or do full
    top_matches = similarity_search(db, doc_embedding, top_k=5)
    suggested_sources = [{
        "source_id": src.id,
        "title": src.title,
        "authors": src.authors,
        "year": src.publication_year,
        "similarity": sim
    } for src, sim in top_matches]

    # Store AnalysisResult
    ar = AnalysisResult(
        assignment_id=assignment.id,
        suggested_sources=json.dumps(suggested_sources),
        plagiarism_score=float(result["plagiarism_score"]),
        flagged_sections=json.dumps(result["flagged_sections"]),
        research_suggestions="",
        citation_recommendations="",
        confidence_score=0.0
    )
    db.add(ar)
    db.commit()
    db.refresh(ar)

    return {"message": "Analysis complete", "analysis_id": ar.id, "plagiarism_score": ar.plagiarism_score}
