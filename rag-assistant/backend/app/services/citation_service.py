from app.models.schemas import Citation


class CitationService:
    def format(self, citations: list[Citation]) -> list[Citation]:
        return citations
