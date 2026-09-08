from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import admin, chat, documents, knowledge_bases
from app.core.config import settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
    app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])
    app.include_router(
        knowledge_bases.router,
        prefix="/api/v1/knowledge-bases",
        tags=["knowledge-bases"],
    )

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
