from app.models.schemas import Citation
from app.rag.retriever import Retriever


class RetrievalService:
    def __init__(self) -> None:
        self.retriever = Retriever()

    async def retrieve(self, query: str, knowledge_base_id: str = "default") -> list[Citation]:
        return self.retriever.search(query=query, knowledge_base_id=knowledge_base_id)
