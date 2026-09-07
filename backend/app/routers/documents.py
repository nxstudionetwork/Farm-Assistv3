import os
from typing import Optional, List
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database.connection import get_db
from app.models.user import User
from app.models.document import UserDocument
from app.utils.auth import get_current_user, generate_id
from app.integrations.file_storage import FileStorageService
from app.config import settings

router = APIRouter(prefix="/api/v1", tags=["Documents"])

# Valid filter options
VALID_DOCUMENT_TYPES = [
    "Land Documents",
    "Identity Documents",
    "Crop Documents",
    "Farm Documents",
    "Government Documents",
    "Insurance Documents",
    "Loan/Finance Documents",
    "Receipts",
    "Reports",
    "Other"
]

VALID_STATUSES = ["active", "expired", "pending", "verified", "unverified"]

VALID_DATE_RANGES = ["all", "today", "this_week", "this_month", "this_year"]

# Preview-able (inline rendering) extensions
_PREVIEWABLE = {"pdf", "png", "jpg", "jpeg", "gif", "webp", "txt", "csv"}

# file extension -> mime type for secure serving
_EXT_MIME = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp",
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "csv": "text/csv",
    "txt": "text/plain",
}


def _get_owned_doc(document_id: str, db: Session, user: User) -> UserDocument:
    doc = db.query(UserDocument).filter(
        UserDocument.id == document_id,
        UserDocument.user_id == user.id,
        UserDocument.is_deleted == False,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


def _serialize_doc(d: UserDocument) -> dict:
    return {
        "id": d.id,
        "document_id": d.document_id,
        "document_name": d.document_name,
        "document_category": d.document_category,
        "file_type": d.file_type,
        "file_size_bytes": d.file_size_bytes,
        "file_size_mb": round((d.file_size_bytes or 0) / (1024 * 1024), 2),
        "file_url": d.file_url,
        "description": d.description,
        "status": d.status,
        "created_at": str(d.created_at) if d.created_at else None,
        "updated_at": str(d.updated_at) if d.updated_at else None,
        "previewable": (d.file_type or "").lower() in _PREVIEWABLE,
    }


@router.get("/documents")
def list_documents(
    category: Optional[str] = None,
    search: Optional[str] = None,
    doc_type: Optional[str] = None,
    date_range: Optional[str] = None,
    status: Optional[str] = None,
    sort_by: Optional[str] = "newest",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List documents with optional filtering.
    
    Query parameters:
    - category: Legacy parameter, use doc_type instead
    - search: Search by document name or description
    - doc_type: Filter by document type
    - date_range: all, today, this_week, this_month, this_year
    - status: Filter by status (active, expired, pending, etc)
    - sort_by: newest (default), oldest, name_asc, name_desc, updated
    """
    owned_documents = db.query(UserDocument).filter(
        UserDocument.user_id == current_user.id,
        UserDocument.is_deleted == False,
    )
    total_size = sum(d.file_size_bytes or 0 for d in owned_documents.all())
    query = owned_documents
    
    # Category filter (legacy support)
    if category and category != "All":
        query = query.filter(UserDocument.document_category == category)
    
    # Document type filter
    if doc_type and doc_type in VALID_DOCUMENT_TYPES:
        query = query.filter(UserDocument.document_category == doc_type)
    
    # Search filter
    if search and len(search.strip()) > 0:
        search_term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                UserDocument.document_name.ilike(search_term),
                UserDocument.document_category.ilike(search_term),
                UserDocument.description.ilike(search_term),
            )
        )
    
    # Status filter
    if status and status in VALID_STATUSES:
        query = query.filter(UserDocument.status == status)
    
    # Date range filter
    if date_range and date_range in VALID_DATE_RANGES:
        now = datetime.utcnow()
        if date_range == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            query = query.filter(UserDocument.created_at >= start)
        elif date_range == "this_week":
            start = now - timedelta(days=now.weekday())
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
            query = query.filter(UserDocument.created_at >= start)
        elif date_range == "this_month":
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            query = query.filter(UserDocument.created_at >= start)
        elif date_range == "this_year":
            start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            query = query.filter(UserDocument.created_at >= start)
    
    # Sort
    if sort_by == "oldest":
        query = query.order_by(UserDocument.created_at.asc())
    elif sort_by == "name_asc":
        query = query.order_by(UserDocument.document_name.asc())
    elif sort_by == "name_desc":
        query = query.order_by(UserDocument.document_name.desc())
    elif sort_by == "updated":
        query = query.order_by(UserDocument.updated_at.desc())
    else:  # newest (default)
        query = query.order_by(UserDocument.created_at.desc())
    
    docs = query.all()

    items = [_serialize_doc(d) for d in docs]

    return {
        "status": "success",
        "data": {
            "items": items,
            "total": len(items),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
        },
    }


@router.get("/documents/storage/summary")
def storage_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Live storage metrics for the current user's document vault.

    Counts and sizes are computed across ALL of the user's non-deleted
    documents (independent of any list filters), so the Storage Used
    widget always reflects the true vault usage.
    """
    owned = db.query(UserDocument).filter(
        UserDocument.user_id == current_user.id,
        UserDocument.is_deleted == False,
    )

    docs = owned.all()
    total_size = sum(d.file_size_bytes or 0 for d in docs)
    by_category = {}
    for d in docs:
        cat = d.document_category or "Other"
        by_category[cat] = by_category.get(cat, 0) + 1

    return {
        "status": "success",
        "data": {
            "total_documents": len(docs),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "limit_mb": 10240,
            "by_category": by_category,
        },
    }


@router.get("/documents/filter/options")
def get_filter_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get available filter options for the current user's documents."""
    user_docs = db.query(UserDocument).filter(
        UserDocument.user_id == current_user.id,
        UserDocument.is_deleted == False,
    ).all()

    document_types = sorted({doc.document_category for doc in user_docs if doc.document_category})
    statuses = sorted({doc.status for doc in user_docs if doc.status})

    return {
        "status": "success",
        "data": {
            "document_types": document_types,
            "date_ranges": VALID_DATE_RANGES,
            "statuses": statuses,
            "sort_options": ["newest", "oldest", "name_asc", "name_desc", "updated"],
        },
    }


@router.get("/documents/{document_id}")
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = _get_owned_doc(document_id, db, current_user)
    return {
        "status": "success",
        "data": _serialize_doc(doc),
    }


@router.post("/documents/upload", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    document_category: str = Form("Other"),
    description: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Validate the category
    if document_category not in VALID_DOCUMENT_TYPES:
        document_category = "Other"

    # Validate file name
    filename = (file.filename or "").strip()
    if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid file name")

    try:
        # Documents are encrypted at rest + signature validated
        result = await FileStorageService.save_upload(file, "documents", encrypt=True, validate_signature=True)
    except ValueError as e:
        if "File too large" in str(e):
            raise HTTPException(
                status_code=413,
                detail="File is too large. Each document must be 25 MB or smaller.",
            )
        raise HTTPException(status_code=400, detail=str(e))

    doc_id = generate_id("FA-DOC", db, UserDocument)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    doc = UserDocument(
        document_id=doc_id,
        user_id=current_user.id,
        farmer_id=current_user.farmer_id,
        document_name=filename,
        document_category=document_category,
        file_type=ext,
        file_size_bytes=result.get("size_bytes", 0),
        file_url=result.get("url", ""),
        file_path=result.get("path", ""),
        description=description[:2000] or "",
        status="active",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {
        "status": "success",
        "message": "Document uploaded successfully",
        "data": _serialize_doc(doc),
    }


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = _get_owned_doc(document_id, db, current_user)

    if doc.file_path:
        FileStorageService.delete_file(doc.file_path)

    doc.is_deleted = True
    doc.status = "deleted"
    db.commit()

    return {"status": "success", "message": "Document deleted successfully"}


@router.put("/documents/{document_id}/rename")
def rename_document(
    document_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = _get_owned_doc(document_id, db, current_user)

    new_name = (payload.get("document_name") or "").strip()
    if not new_name or len(new_name) > 200:
        raise HTTPException(status_code=400, detail="Document name is required and must be under 200 characters")
    if "/" in new_name or "\\" in new_name or new_name.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid document name")

    doc.document_name = new_name
    doc.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(doc)

    return {"status": "success", "message": "Document renamed successfully", "data": _serialize_doc(doc)}


@router.get("/documents/{document_id}/file")
def get_document_file(
    document_id: str,
    download: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Securely serve a farmer's own document. Decrypts at rest, verifies ownership."""
    doc = _get_owned_doc(document_id, db, current_user)
    if not doc.file_path:
        raise HTTPException(status_code=404, detail="File not found")

    try:
        content = FileStorageService.read_document(doc.file_path)
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=404, detail="File could not be read")

    content_type = _EXT_MIME.get((doc.file_type or "").lower()) or "application/octet-stream"
    headers = {
        "Content-Disposition": ("attachment" if download else "inline")
        + f'; filename="{doc.document_name.replace(chr(34), "")}"'
    }
    return Response(content=content, media_type=content_type, headers=headers)


@router.get("/documents/{document_id}/preview")
def get_document_preview(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return a safe text preview of text/CSV documents (also used as pseudo-OCR)."""
    doc = _get_owned_doc(document_id, db, current_user)
    ext = (doc.file_type or "").lower()

    if ext not in ("txt", "csv"):
        raise HTTPException(status_code=400, detail="Text preview only supports .txt and .csv documents")

    if not doc.file_path:
        raise HTTPException(status_code=404, detail="File not found")

    try:
        content = FileStorageService.read_document(doc.file_path)
    except (ValueError, OSError):
        raise HTTPException(status_code=404, detail="File could not be read")

    text = ""
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:
        pass

    return {
        "status": "success",
        "data": {
            "document_id": doc.id,
            "preview": text[:20000],
            "truncated": len(text) > 20000,
        },
    }


