"""Store a menu image on the uploads volume."""

from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

MAX_BYTES = 5 * 1024 * 1024
_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
_PNG = b"\x89PNG\r\n\x1a\n"
_JPEG = b"\xff\xd8\xff"
_IMAGE_ERROR = "La imagen debe ser PNG, JPG o WEBP."


def _matches_signature(extension: str, payload: bytes) -> bool:
    if extension == ".png":
        return payload.startswith(_PNG)
    if extension == ".webp":
        return (
            len(payload) >= 12
            and payload.startswith(b"RIFF")
            and payload[8:12] == b"WEBP"
        )
    return payload.startswith(_JPEG)


def uploads_root() -> Path:
    path = Path(settings.UPLOADS_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


async def read_image(upload: UploadFile) -> tuple[str, bytes]:
    extension = Path(upload.filename or "").suffix.lower()
    content_type = (upload.content_type or "").split(";", 1)[0].strip().lower()
    expected = _TYPES.get(extension)
    if expected is None or content_type != expected:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_IMAGE_ERROR,
        )
    payload = await upload.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La imagen no puede pesar más de 5 MB.",
        )
    if not _matches_signature(extension, payload):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_IMAGE_ERROR,
        )
    return extension, payload


async def save_menu_photo(tenant_id: UUID, upload: UploadFile) -> str:
    extension, payload = await read_image(upload)
    folder = uploads_root() / "menu" / str(tenant_id)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid4()}{extension}"
    (folder / name).write_bytes(payload)
    return f"/uploads/menu/{tenant_id}/{name}"


async def save_tenant_logo(tenant_id: UUID, upload: UploadFile) -> str:
    extension, payload = await read_image(upload)
    folder = uploads_root() / "logos"
    folder.mkdir(parents=True, exist_ok=True)
    for previous in folder.glob(f"{tenant_id}.*"):
        previous.unlink()
    (folder / f"{tenant_id}{extension}").write_bytes(payload)
    return f"/uploads/logos/{tenant_id}{extension}"
