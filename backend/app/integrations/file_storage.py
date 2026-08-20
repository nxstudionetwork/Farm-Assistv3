import os
import uuid
import base64
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from fastapi import UploadFile
from app.config import settings

logger = logging.getLogger(__name__)


class FileStorageService:
    @staticmethod
    def get_storage_path(subdir: str = "") -> Path:
        base = Path(settings.STORAGE_LOCAL_PATH)
        path = base / subdir
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def validate_file(filename: str, content_type: str) -> Tuple[bool, str]:
        allowed_exts = [ext.strip().lower() for ext in settings.STORAGE_ALLOWED_EXTENSIONS.split(",")]
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in allowed_exts:
            return False, f"File type .{ext} is not allowed. Allowed: {', '.join(allowed_exts)}"

        allowed_types = {
            "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "gif": "image/gif", "pdf": "application/pdf",
            "doc": "application/msword", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "csv": "text/csv", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
        if ext in allowed_types and content_type and content_type != allowed_types[ext]:
            if not content_type.startswith("image/") or not ext in ["jpg", "jpeg", "png", "gif"]:
                pass

        return True, ""

    @staticmethod
    async def save_upload(file: UploadFile, subdir: str = "uploads") -> dict:
        valid, error = FileStorageService.validate_file(file.filename or "unknown", file.content_type or "")
        if not valid:
            raise ValueError(error)

        content = await file.read()
        if len(content) > settings.STORAGE_MAX_FILE_SIZE_MB * 1024 * 1024:
            raise ValueError(f"File too large. Max size: {settings.STORAGE_MAX_FILE_SIZE_MB}MB")

        file_hash = hashlib.md5(content).hexdigest()
        ext = (file.filename or "file").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "bin"
        unique_name = f"{uuid.uuid4().hex}.{ext}"
        year_month = datetime.utcnow().strftime("%Y/%m")
        save_dir = FileStorageService.get_storage_path(f"{subdir}/{year_month}")
        file_path = save_dir / unique_name

        with open(file_path, "wb") as f:
            f.write(content)

        return {
            "file_name": file.filename,
            "stored_name": unique_name,
            "path": f"{subdir}/{year_month}/{unique_name}",
            "size_bytes": len(content),
            "size_mb": round(len(content) / (1024 * 1024), 2),
            "content_type": file.content_type,
            "file_hash": file_hash,
        }

    @staticmethod
    def save_base64_image(data_uri: str, subdir: str = "images") -> dict:
        if "," in data_uri:
            header, data = data_uri.split(",", 1)
            content_type = header.split(";")[0].replace("data:", "")
        else:
            data = data_uri
            content_type = "image/png"

        ext = content_type.split("/")[-1] if "/" in content_type else "png"
        if ext == "jpeg":
            ext = "jpg"

        content = base64.b64decode(data)
        file_hash = hashlib.md5(content).hexdigest()
        unique_name = f"{uuid.uuid4().hex}.{ext}"
        year_month = datetime.utcnow().strftime("%Y/%m")
        save_dir = FileStorageService.get_storage_path(f"{subdir}/{year_month}")
        file_path = save_dir / unique_name

        with open(file_path, "wb") as f:
            f.write(content)

        return {
            "stored_name": unique_name,
            "path": f"{subdir}/{year_month}/{unique_name}",
            "size_bytes": len(content),
            "size_kb": round(len(content) / 1024, 1),
            "content_type": content_type,
        }

    @staticmethod
    def delete_file(file_path: str) -> bool:
        storage_root = Path(settings.STORAGE_LOCAL_PATH).resolve()
        full_path = (storage_root / file_path).resolve()
        # Prevent path traversal outside the storage root
        if str(full_path) != str(storage_root) and not str(full_path).startswith(str(storage_root) + os.sep):
            logger.error(f"Blocked path traversal attempt for {file_path}")
            return False
        try:
            if full_path.exists() and full_path.is_file():
                full_path.unlink()
                return True
        except Exception as e:
            logger.error(f"Failed to delete file {file_path}: {e}")
        return False

    @staticmethod
    def get_file_url(file_path: str) -> str:
        return f"/api/v1/storage/{file_path}"
