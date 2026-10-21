"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from eb import __version__
from eb.config import get_settings
from eb.db import close_pool, get_pool

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_pool()
    yield
    close_pool()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="Engineering Brain", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from eb.chat.router import router as chat_router
    from eb.documents.router import router as documents_router
    from eb.retrieval.router import router as search_router

    app.include_router(documents_router)
    app.include_router(search_router)
    app.include_router(chat_router)

    # Optional modules register their routers when present.
    for modname in ("eb.wiki.router", "eb.compliance.router", "eb.specs.router"):
        try:
            mod = __import__(modname, fromlist=["router"])
        except ImportError:
            continue
        app.include_router(mod.router)

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        with get_pool().connection() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
