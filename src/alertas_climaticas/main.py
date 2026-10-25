"""Punto de entrada de la API: crea la app FastAPI, registra los routers y traduce errores."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from alertas_climaticas.exceptions import NotFoundError
from alertas_climaticas.routers import farms, regions, users

app = FastAPI(title="Alertas Climaticas")

app.include_router(users.router)
app.include_router(regions.router)
app.include_router(farms.router)


@app.exception_handler(NotFoundError)
async def handle_not_found(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})
