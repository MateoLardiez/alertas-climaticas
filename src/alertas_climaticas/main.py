"""Punto de entrada de la API: crea la app FastAPI, registra los routers y traduce errores."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from alertas_climaticas.config import get_settings
from alertas_climaticas.exceptions import AlreadyExistsError, NotFoundError
from alertas_climaticas.jobs.alert_evaluation import create_scheduler
from alertas_climaticas.routers import alerts, events, farms, notifications, regions, users


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Arranca el scheduler del job de alertas junto con la app y lo detiene al apagarla."""
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    scheduler = create_scheduler(settings) if settings.evaluation_job_enabled else None
    if scheduler is not None:
        scheduler.start()
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown()


app = FastAPI(title="Alertas Climaticas", lifespan=lifespan)

app.include_router(users.router)
app.include_router(regions.router)
app.include_router(events.router)
app.include_router(farms.router)
app.include_router(alerts.router)
app.include_router(notifications.router)


@app.exception_handler(NotFoundError)
async def handle_not_found(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})


@app.exception_handler(AlreadyExistsError)
async def handle_already_exists(request: Request, exc: AlreadyExistsError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})
