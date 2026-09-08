from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    id: str
    filename: str
    status: str


class KnowledgeBaseResponse(BaseModel):
    id: str
    name: str
    document_count: int


class Citation(BaseModel):
    document_id: str
    filename: str
    page: int | None = None
    text: str
    score: float | None = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    knowledge_base_id: str = "default"


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
