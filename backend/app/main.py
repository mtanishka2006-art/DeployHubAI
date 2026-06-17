"""FastAPI application entrypoint.

Wires the API layer, configures CORS, creates tables on startup (for zero-config
dev/demo runs; production uses Alembic migrations), seeds demo data, and
initializes Kafka subscribers that drive the processing layer.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.api.routes import (
    auth,
    connectors,
    deployments,
    dr,
    incidents,
    memory,
    metrics,
    mission_control,
    overview,
    pipelines,
    simulation,
)

configure_logging("DEBUG" if settings.DEBUG else "INFO")
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables for zero-config runs. (Alembic owns schema in production.)
    Base.metadata.create_all(bind=engine)
    if os.getenv("SEED_ON_STARTUP", "true").lower() == "true":
        from app.seed.seed_data import run_all

        db = SessionLocal()
        try:
            run_all(db)
        except Exception:  # noqa: BLE001
            logger.exception("seeding failed (continuing)")
        finally:
            db.close()
    # Start the App Connector Hub background poller.
    from app.ingestion.poller import start_poller, stop_poller

    await start_poller()
    logger.info("%s API ready (env=%s)", settings.APP_NAME, settings.ENVIRONMENT)
    yield
    await stop_poller()


app = FastAPI(
    title=f"{settings.APP_NAME} API",
    version="1.0.0",
    description=(
        "AI-Powered Infrastructure Observability, Incident Intelligence, and "
        "Disaster Recovery Platform."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API = settings.API_PREFIX
for module in (
    auth,
    overview,
    metrics,
    incidents,
    deployments,
    dr,
    memory,
    mission_control,
    simulation,
    connectors,
    pipelines,
):
    app.include_router(module.router, prefix=API)


@app.get("/health", tags=["system"])
def health():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "kafka": "enabled" if settings.kafka_enabled else "in-memory",
        "llm": "enabled" if settings.llm_enabled else "heuristic",
    }


@app.get("/", tags=["system"])
def root():
    return {"name": settings.APP_NAME, "docs": "/docs", "health": "/health"}
