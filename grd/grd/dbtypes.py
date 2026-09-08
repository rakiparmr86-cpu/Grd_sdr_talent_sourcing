"""Portable column types. Same models run on SQLite (dev/tests) and Postgres."""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.types import TypeDecorator

EMBED_DIM = 384  # sentence-transformers/all-MiniLM-L6-v2; bump if you swap models


class Embedding(TypeDecorator):
    """`vector(N)` on Postgres (with pgvector), plain JSON list everywhere else.

    Lets the RAG tables (doc_chunks) live in the same schema on either backend.
    On SQLite an embedding is just a JSON array - fine for small corpora and
    tests; real similarity search needs Postgres + pgvector.
    """

    impl = JSON
    cache_ok = True

    def __init__(self, dim: int = EMBED_DIM) -> None:
        self.dim = dim
        super().__init__()

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            try:
                from pgvector.sqlalchemy import Vector

                return dialect.type_descriptor(Vector(self.dim))
            except ImportError:  # pgvector not installed - degrade to JSON
                return dialect.type_descriptor(JSON())
        return dialect.type_descriptor(JSON())
