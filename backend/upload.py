import os, requests, uuid
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from .models import Assignment
from .auth import get_db
from .auth import create_access_token  # reuse JWT if needed for workflow

router = APIRouter(prefix="/assignments", tags=["Assignments"])

UPLOAD_DIR = "/app/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "http://n8n:5678/webhook/assignment")

@router.post("/upload")
def upload_assignment(
    file: UploadFile = File(...),
    topic: str = Form("Unknown"),
    academic_level: str = Form("Undergraduate"),
    student_id: int = Form(...),
    db: Session = Depends(get_db)
):
    try:
        filename = f"{uuid.uuid4()}_{file.filename}"
        filepath = os.path.join(UPLOAD_DIR, filename)

        # Save file locally
        with open(filepath, "wb") as f:
            f.write(file.file.read())

        # Create DB record
        new_assignment = Assignment(
            student_id=student_id,
            filename=filename,
            topic=topic,
            academic_level=academic_level,
            word_count=0,  # can be updated later after analysis
            uploaded_at=datetime.utcnow()
        )
        db.add(new_assignment)
        db.commit()
        db.refresh(new_assignment)

        # Notify n8n workflow
        data = {"assignment_id": new_assignment.id, "filename": filename, "topic": topic}
        try:
            response = requests.post(N8N_WEBHOOK_URL, json=data, timeout=10)
            response.raise_for_status()
        except Exception as e:
            print(f"Warning: Failed to trigger n8n webhook — {e}")

        return {"message": "Assignment uploaded successfully", "assignment_id": new_assignment.id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
