import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pathlib import Path

from app.config import settings
from app.models.user import User
from app.utils.auth import get_current_user
from app.integrations.file_storage import FileStorageService

router = APIRouter(prefix="/api/v1", tags=["Storage"])


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
    current_user: User = Depends(get_current_user),
):
    # Prevent path traversal outside the storage root
    storage_root = Path(settings.STORAGE_LOCAL_PATH).resolve()
    full_path = (storage_root / file_path).resolve()
    if not str(full_path).startswith(str(storage_root)):
        raise HTTPException(status_code=400, detail="Invalid file path")
    if full_path.exists() and full_path.is_file():
        return FileResponse(full_path)
    raise HTTPException(status_code=404, detail="File not found")


@router.delete("/storage/{file_path:path}", response_model=dict)
def delete_file(
    file_path: str,
    current_user: User = Depends(get_current_user),
):
    if FileStorageService.delete_file(file_path):
        return {"status": "success", "message": "File deleted"}
    raise HTTPException(status_code=404, detail="File not found")
