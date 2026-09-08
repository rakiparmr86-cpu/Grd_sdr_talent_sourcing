from app.models.schemas import Citation
from app.rag.vector_store import ChromaVectorStore


class Retriever:
    def __init__(self) -> None:
        self.vector_store = ChromaVectorStore()

    def search(self, query: str, knowledge_base_id: str = "default") -> list[Citation]:
        return self.vector_store.similarity_search(query=query, k=5)
