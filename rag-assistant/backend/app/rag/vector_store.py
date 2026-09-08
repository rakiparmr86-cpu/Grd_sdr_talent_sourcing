from app.models.schemas import Citation


class ChromaVectorStore:
    def add_texts(self, texts: list[str], metadatas: list[dict] | None = None) -> None:
        return None

    def similarity_search(self, query: str, k: int = 5) -> list[Citation]:
        return []
