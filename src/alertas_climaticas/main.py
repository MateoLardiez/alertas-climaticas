"""Punto de entrada de la API: crea la app FastAPI, registra los routers y traduce errores."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from alertas_climaticas.exceptions import AlreadyExistsError, NotFoundError
from alertas_climaticas.routers import alerts, events, farms, regions, users

app = FastAPI(title="Alertas Climaticas")

app.include_router(users.router)
app.include_router(regions.router)
app.include_router(events.router)
app.include_router(farms.router)
app.include_router(alerts.router)


@app.exception_handler(NotFoundError)
async def handle_not_found(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})


@app.exception_handler(AlreadyExistsError)
async def handle_already_exists(request: Request, exc: AlreadyExistsError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})
