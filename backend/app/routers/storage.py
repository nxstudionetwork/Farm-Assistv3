import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pathlib import Path

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User
from app.utils.auth import get_current_user, get_optional_user
from app.database.connection import get_db
from app.integrations.file_storage import FileStorageService
from app.models.messages import Message, MessageAttachment, ConversationParticipant

router = APIRouter(prefix="/api/v1", tags=["Storage"])

# Directories served publicly via GET so they can be used directly in <img>/<video>
# src attributes (browsers cannot attach Authorization headers). Private content
# (messages/, documents/) stays protected behind the existing per-user checks.
PUBLIC_STORAGE_DIRS = {
    "farmbuzz",
    "profile-pictures",
    "marketplace",
    "images",
    "uploads",
    "posts",
    "shorts",
    "stories",
    "avatars",
    "crops",
    "weather",
    "learning",
    "experts",
    "services",
    "schemes",
    "news",
}


def _authorize_storage_access(file_path: str, current_user: User, db: Session) -> None:
    """Enforce per-directory access rules so no user can read/delete private files.

    - messages/: only the sender or a participant of the owning conversation.
    - documents/: never served via this generic route (use /documents/{id}/file).
    - everything else (farmbuzz, profile-pictures, marketplace, images): public.
    """
    norm = file_path.replace("\\", "/").lstrip("/")
    parts = norm.split("/")
    if not parts:
        raise HTTPException(status_code=400, detail="Invalid file path")
    top = parts[0].lower()

    if top in ("documents", "loan-documents"):
        raise HTTPException(status_code=404, detail="File not found")

    if top == "messages":
        if not current_user:
            raise HTTPException(status_code=404, detail="File not found")
        target = norm.split("/", 1)[1] if "/" in norm else norm
        att = (
            db.query(MessageAttachment)
            .filter(MessageAttachment.file_url.like(f"%/messages/{target}"))
            .first()
        )
        if not att:
            raise HTTPException(status_code=404, detail="File not found")
        if not att.message_id or att.message_id == "":
            return
        msg = db.query(Message).filter(Message.id == att.message_id).first()
        if not msg:
            return
        if msg.sender_id == current_user.id:
            return
        participant = (
            db.query(ConversationParticipant)
            .filter(
                ConversationParticipant.conversation_id == msg.conversation_id,
                ConversationParticipant.user_id == current_user.id,
            )
            .first()
        )
        if not participant:
            raise HTTPException(status_code=404, detail="File not found")


@router.post("/storage/upload", response_model=dict)
async def upload_file(
    file: UploadFile = File(...),
    subdir: str = "uploads",
    current_user: User = Depends(get_current_user),
):
    try:
        result = await FileStorageService.save_upload(file, subdir)
        result["url"] = FileStorageService.get_file_url(result["path"])
        return {"status": "success", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/storage/upload-base64", response_model=dict)
def upload_base64(
    payload: dict,
    current_user: User = Depends(get_current_user),
):
    image_data = payload.get("image_data", "")
    subdir = payload.get("subdir", "images")
    if not image_data:
        raise HTTPException(status_code=400, detail="No image data provided")
    try:
        result = FileStorageService.save_base64_image(image_data, subdir)
        result["url"] = FileStorageService.get_file_url(result["path"])
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/storage/{file_path:path}")
async def serve_file(
    file_path: str,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    # Prevent path traversal outside the storage root
    storage_root = Path(settings.STORAGE_LOCAL_PATH).resolve()
    full_path = (storage_root / file_path).resolve()
    if not str(full_path).startswith(str(storage_root)):
        raise HTTPException(status_code=400, detail="Invalid file path")
    _authorize_storage_access(file_path, current_user, db)
    if full_path.exists() and full_path.is_file():
        return FileResponse(full_path, headers={"Cache-Control": "public, max-age=86400"})
    raise HTTPException(status_code=404, detail="File not found")


@router.delete("/storage/{file_path:path}", response_model=dict)
def delete_file(
    file_path: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Prevent path traversal outside the storage root
    storage_root = Path(settings.STORAGE_LOCAL_PATH).resolve()
    full_path = (storage_root / file_path).resolve()
    if not str(full_path).startswith(str(storage_root)):
        raise HTTPException(status_code=400, detail="Invalid file path")
    _authorize_storage_access(file_path, current_user, db)
    if FileStorageService.delete_file(file_path):
        return {"status": "success", "message": "File deleted"}
    raise HTTPException(status_code=404, detail="File not found")
