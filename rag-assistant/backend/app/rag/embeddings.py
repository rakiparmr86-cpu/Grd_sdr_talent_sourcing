class EmbeddingModel:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]
