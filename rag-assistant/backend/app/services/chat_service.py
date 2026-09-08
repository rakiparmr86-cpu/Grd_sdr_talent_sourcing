from app.models.schemas import ChatRequest, ChatResponse
from app.rag.llm import OllamaClient
from app.services.citation_service import CitationService
from app.services.retrieval_service import RetrievalService


class ChatService:
    def __init__(self) -> None:
        self.retrieval = RetrievalService()
        self.citations = CitationService()
        self.llm = OllamaClient()

    async def chat(self, request: ChatRequest) -> ChatResponse:
        context = await self.retrieval.retrieve(request.message, request.knowledge_base_id)
        answer = await self.llm.generate(request.message, context)
        return ChatResponse(answer=answer, citations=self.citations.format(context))

    async def stream_chat(self, request: ChatRequest):
        response = await self.chat(request)
        for token in response.answer.split():
            yield token + " "
