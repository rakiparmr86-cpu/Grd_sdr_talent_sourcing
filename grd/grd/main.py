from __future__ import annotations

from fastapi import FastAPI

from grd import __version__
from grd.api.routes import router
from grd.config import get_settings
from grd.pipeline import Pipeline
from grd.recruiting.api import router as recruiting_router
from grd.recruiting.pipeline import RecruitingPipeline


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=__version__, debug=settings.debug)

    app.state.pipeline = Pipeline(settings)
    app.state.recruiting_pipeline = RecruitingPipeline(settings)

    app.include_router(router, prefix="/api")
    app.include_router(recruiting_router, prefix="/api")

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        pipe = app.state.pipeline
        return {
            "status": "ok",
            "llm": settings.llm_provider,
            "sdr": {
                "agent": settings.agent,
                "spec_loaded": pipe.spec is not None,
                "active_steps": pipe.spec.active_steps() if pipe.spec else [],
                "icp": pipe._default_icp(),
                "capabilities": pipe.research.allowlist,
                "enrichment": settings.provider_list,
            },
            "recruiting": {
                "rubric": settings.rubric,
                "sources": settings.candidate_source_list,
            },
        }

    return app


app = create_app()
