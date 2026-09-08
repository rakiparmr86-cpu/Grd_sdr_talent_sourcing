from fastapi import APIRouter, Depends

from app.core.security import require_api_key
from app.models.schemas import KnowledgeBaseResponse

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases() -> list[KnowledgeBaseResponse]:
    return [KnowledgeBaseResponse(id="default", name="Default", document_count=0)]
