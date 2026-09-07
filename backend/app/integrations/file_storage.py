import os
import uuid
import base64
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from fastapi import UploadFile
from cryptography.fernet import Fernet, InvalidToken
import base64 as _b64
import hashlib as _hashlib

from app.config import settings

logger = logging.getLogger(__name__)

# Signature-based detection for common document/image types.
# Each entry: (extension, magic bytes prefix or list, mime type)
_MAGIC_SIGNATURES = [
    ("pdf", b"%PDF-", "application/pdf"),
    ("png", b"\x89PNG\r\n\x1a\n", "image/png"),
    ("jpg", b"\xff\xd8\xff", "image/jpeg"),
    ("jpeg", b"\xff\xd8\xff", "image/jpeg"),
    ("gif", (b"GIF87a", b"GIF89a"), "image/gif"),
    ("webp", b"RIFF", "image/webp"),
    ("zip", b"PK\x03\x04", "application/zip"),  # docx / xlsx are zip containers
]

# file extension -> mime type map used to cross check internet media types
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


class FileStorageService:
    @staticmethod
    def _fernet() -> Fernet:
        # Derive a stable 32-byte key from the app secret so documents can be
        # decrypted across restarts without persisting a separate key.
        digest = _hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
        key = _b64.urlsafe_b64encode(digest)
        return Fernet(key)

    @staticmethod
    def encrypt_bytes(content: bytes) -> bytes:
        return FileStorageService._fernet().encrypt(content)

    @staticmethod
    def decrypt_bytes(content: bytes) -> bytes:
        try:
            return FileStorageService._fernet().decrypt(content)
        except (InvalidToken, ValueError) as e:
            logger.error("Failed to decrypt file content: %s", e)
            raise ValueError("Invalid or corrupted encrypted file")

    @staticmethod
    def get_storage_path(subdir: str = "") -> Path:
        base = Path(settings.STORAGE_LOCAL_PATH)
        path = base / subdir
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _safe_subdir(subdir: str) -> str:
        """Validate a user-supplied subdir so it cannot escape the storage root."""
        subdir = (subdir or "").strip().strip("/").strip("\\")
        subdir = subdir.replace("\\", "/")
        parts = [p for p in subdir.split("/") if p not in ("", ".", "..")]
        clean = "/".join(parts)
        for part in parts:
            if part == ".." or ":" in part:
                raise ValueError("Invalid storage sub-directory")
        return clean

    @staticmethod
    def detect_mime(content: bytes) -> Optional[str]:
        """Detect MIME type from file signatures, ignoring the extension."""
        for ext, sig, mime in _MAGIC_SIGNATURES:
            if isinstance(sig, bytes):
                if content.startswith(sig):
                    return mime
            else:
                if content.startswith(sig[0]) or content.startswith(sig[1]):
                    return mime
        # Fallback: common text types by printable check
        try:
            content.decode("utf-8")
            return "text/plain"
        except Exception:
            return None

    @staticmethod
    def validate_file(filename: str, content_type: str, content: Optional[bytes] = None) -> Tuple[bool, str]:
        allowed_exts = [ext.strip().lower() for ext in settings.STORAGE_ALLOWED_EXTENSIONS.split(",")]
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if not ext:
            return False, "File must have a valid extension"
        if ext not in allowed_exts:
            return False, f"File type .{ext} is not allowed. Allowed: {', '.join(allowed_exts)}"

        # Validate filename does not attempt path traversal or obscure naming
        if "/" in filename or "\\" in filename or filename.startswith("."):
            return False, "Invalid file name"

        if content is None:
            return True, ""

        detected = FileStorageService.detect_mime(content)

        # Signature check against the declared extension/mime
        if detected is not None:
            expected_for_ext = _EXT_MIME.get(ext)
            declared_mime = (content_type or "").lower()
            # For office documents (zip containers) we accept generic zip signature
            if expected_for_ext and detected != expected_for_ext:
                if not (detected == "application/zip" and ext in ("docx", "xlsx")):
                    return False, f"File content does not match the .{ext} type (detected: {detected})"
            if declared_mime and declared_mime not in ("application/octet-stream",) and declared_mime != detected:
                if not (detected == "application/zip" and ext in ("docx", "xlsx")):
                    return False, f"File MIME type {declared_mime} does not match its actual content ({detected})"

        return True, ""

    @staticmethod
    async def save_upload(file: UploadFile, subdir: str = "uploads", encrypt: bool = False, validate_signature: bool = True) -> dict:
        content = await file.read()
        content_type = file.content_type or ""

        valid, error = FileStorageService.validate_file(
            file.filename or "unknown", content_type, content if validate_signature else None
        )
        if not valid:
            raise ValueError(error)

        if len(content) > settings.STORAGE_MAX_FILE_SIZE_MB * 1024 * 1024:
            raise ValueError(f"File too large. Max size: {settings.STORAGE_MAX_FILE_SIZE_MB}MB")

        file_hash = hashlib.md5(content).hexdigest()
        ext = (file.filename or "file").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "bin"
        unique_name = f"{uuid.uuid4().hex}.{ext}"
        year_month = datetime.utcnow().strftime("%Y/%m")
        safe_subdir = FileStorageService._safe_subdir(subdir)
        save_dir = FileStorageService.get_storage_path(f"{safe_subdir}/{year_month}")
        file_path = save_dir / unique_name

        # Optionally encrypt content at rest (Fernet symmetric AES)
        to_write = FileStorageService.encrypt_bytes(content) if encrypt else content

        with open(file_path, "wb") as f:
            f.write(to_write)

        return {
            "file_name": file.filename,
            "stored_name": unique_name,
            "path": f"{subdir}/{year_month}/{unique_name}",
            "size_bytes": len(content),
            "size_mb": round(len(content) / (1024 * 1024), 2),
            "content_type": content_type,
            "file_hash": file_hash,
        }

    @staticmethod
    def read_file(file_path: str) -> bytes:
        """Read a stored file back as raw bytes (path-traversal safe)."""
        storage_root = Path(settings.STORAGE_LOCAL_PATH).resolve()
        full_path = (storage_root / file_path).resolve()
        if str(full_path) != str(storage_root) and not str(full_path).startswith(str(storage_root) + os.sep):
            raise ValueError("Invalid file path")
        with open(full_path, "rb") as f:
            return f.read()

    @staticmethod
    def read_document(file_path: str) -> bytes:
        """Read + decrypt a stored document (documents are encrypted at rest)."""
        return FileStorageService.decrypt_bytes(FileStorageService.read_file(file_path))

    @staticmethod
    def save_base64_image(data_uri: str, subdir: str = "images") -> dict:
        if "," in data_uri:
            header, data = data_uri.split(",", 1)
            content_type = header.split(";")[0].replace("data:", "")
        else:
            data = data_uri
            content_type = "image/png"

        try:
            content = base64.b64decode(data, validate=True)
        except Exception:
            raise ValueError("Invalid base64 image data")

        ext = content_type.split("/")[-1] if "/" in content_type else "png"
        if ext == "jpeg":
            ext = "jpg"
        allowed_img = {"png", "jpg", "jpeg", "gif", "webp"}
        if ext not in allowed_img:
            raise ValueError(f"Image type .{ext} is not allowed")

        # Validate the decoded payload matches the declared image type
        detected = FileStorageService.detect_mime(content)
        expected = _EXT_MIME.get(ext)
        if detected is not None and expected and detected != expected:
            raise ValueError(f"Image content does not match the .{ext} type (detected: {detected})")
        if detected is None:
            raise ValueError("Could not verify image content signature")

        if len(content) > settings.STORAGE_MAX_FILE_SIZE_MB * 1024 * 1024:
            raise ValueError(f"File too large. Max size: {settings.STORAGE_MAX_FILE_SIZE_MB}MB")

        file_hash = hashlib.md5(content).hexdigest()
        unique_name = f"{uuid.uuid4().hex}.{ext}"
        year_month = datetime.utcnow().strftime("%Y/%m")
        safe_subdir = FileStorageService._safe_subdir(subdir)
        save_dir = FileStorageService.get_storage_path(f"{safe_subdir}/{year_month}")
        file_path = save_dir / unique_name

        with open(file_path, "wb") as f:
            f.write(content)

        return {
            "stored_name": unique_name,
            "path": f"{safe_subdir}/{year_month}/{unique_name}",
            "size_bytes": len(content),
            "size_kb": round(len(content) / 1024, 1),
            "content_type": content_type,
            "file_hash": file_hash,
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
