from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import settings
from app.models.schemas import DocumentResponse


class IngestionService:
    async def ingest_upload(self, file: UploadFile) -> DocumentResponse:
        settings.upload_dir.mkdir(parents=True, exist_ok=True)

        document_id = str(uuid4())
        destination = settings.upload_dir / f"{document_id}_{Path(file.filename or 'upload').name}"
        content = await file.read()
        destination.write_bytes(content)

        return DocumentResponse(
            id=document_id,
            filename=file.filename or destination.name,
            status="uploaded",
        )

    async def list_documents(self) -> list[DocumentResponse]:
        if not settings.upload_dir.exists():
            return []

        return [
            DocumentResponse(id=path.stem.split("_", 1)[0], filename=path.name, status="uploaded")
            for path in settings.upload_dir.iterdir()
            if path.is_file()
        ]

    async def delete_document(self, document_id: str) -> None:
        if not settings.upload_dir.exists():
            return

        for path in settings.upload_dir.glob(f"{document_id}_*"):
            if path.is_file():
                path.unlink()
