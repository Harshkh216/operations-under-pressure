"""FastAPI application factory and lifespan."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import auth_router, outbox_router, teams_router, work_items_router
from app.core.config import settings
from app.db.session import get_db
from app.services.outbox import start_outbox_processor, stop_outbox_processor

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting operations backend database=%s cors_origins=%s", "sqlite" if settings.is_sqlite else "postgresql", settings.cors_origins)
    start_outbox_processor()
    try:
        yield
    finally:
        stop_outbox_processor()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Operations Under Pressure",
        version="1.0.0",
        description="Backend for the Newtonite Software Engineering Challenge.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router)
    app.include_router(teams_router)
    app.include_router(work_items_router)
    app.include_router(outbox_router)

    @app.get("/health", tags=["meta"])
    def health(db: Session = Depends(get_db)) -> dict[str, str]:
        try:
            db.execute(text("SELECT 1"))
        except Exception as exc:
            logger.exception("Health check database query failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database unavailable",
            ) from exc
        return {"status": "ok", "database": "ok"}

    return app


app = create_app()
