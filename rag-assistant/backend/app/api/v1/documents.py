from fastapi import APIRouter, Depends, File, UploadFile

from app.core.security import require_api_key
from app.models.schemas import DocumentResponse
from app.services.ingestion_service import IngestionService

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(file: UploadFile = File(...)) -> DocumentResponse:
    return await IngestionService().ingest_upload(file)


@router.get("", response_model=list[DocumentResponse])
async def list_documents() -> list[DocumentResponse]:
    return await IngestionService().list_documents()


@router.delete("/{document_id}")
async def delete_document(document_id: str) -> dict[str, str]:
    await IngestionService().delete_document(document_id)
    return {"status": "deleted", "document_id": document_id}
