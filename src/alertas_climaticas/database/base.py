"""Clase base de la que heredan todos los modelos. Alembic la usa para conocer las tablas."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
