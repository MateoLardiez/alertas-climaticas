FROM python:3.12-slim

# uv (el gestor de dependencias) se copia de su imagen oficial, fijando la version.
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

# Primero solo las dependencias: esta capa se reutiliza mientras no cambien pyproject.toml ni uv.lock.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Despues el codigo (cambia seguido) y el proyecto en si.
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
RUN uv sync --frozen --no-dev

# Sin root: si alguien vulnera la app, no tiene permisos de administrador en el contenedor.
RUN useradd --system --no-create-home app
USER app

EXPOSE 8000

# Forma shell (sh -c) para que ${HOST} y ${PORT} se expandan; exec deja a uvicorn como proceso principal.
CMD ["sh", "-c", "exec uvicorn alertas_climaticas.main:app --host ${HOST} --port ${PORT}"]
