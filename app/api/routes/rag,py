from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.db_models import RagChunk
from app.services import rag

router = APIRouter(prefix="/rag", tags=["rag"])

ALLOWED_EXTENSIONS = {".txt", ".md"}


@router.post("/upload")
async def upload_file(file: UploadFile, db: Session = Depends(get_db)):
    """
    Upload a .txt or .md file with notes, strategy guidelines, or any
    context you want the recommendation agent to draw on. Chunked,
    embedded, and stored — used automatically on future recommendations
    when relevant to the stock being asked about.
    """
    filename = file.filename or "unnamed"
    if not any(filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=400, detail=f"Only {ALLOWED_EXTENSIONS} files supported for now.")

    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded text.")

    try:
        chunk_count = rag.ingest_file(db, filename, text)
    except rag.RagError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"filename": filename, "chunks_stored": chunk_count}


@router.get("/documents")
def list_documents(db: Session = Depends(get_db)):
    """List uploaded files and how many chunks each produced."""
    rows = db.query(RagChunk.filename).distinct().all()
    filenames = [r[0] for r in rows]
    return [
        {"filename": fn, "chunk_count": db.query(RagChunk).filter(RagChunk.filename == fn).count()}
        for fn in filenames
    ]


@router.delete("/documents/{filename}")
def delete_document(filename: str, db: Session = Depends(get_db)):
    deleted = db.query(RagChunk).filter(RagChunk.filename == filename).delete()
    db.commit()
    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"No document named '{filename}' found.")
    return {"filename": filename, "chunks_deleted": deleted}