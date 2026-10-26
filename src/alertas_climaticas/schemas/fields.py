"""Tipos de campo compartidos por los schemas."""

from typing import Annotated

from pydantic import AfterValidator, Field

NAME_MAX_LENGTH = 100


def _reject_null_characters(value: str) -> str:
    # PostgreSQL no guarda el caracter NUL en un texto: sin esto, la base falla y la API responde 500.
    if "\x00" in value:
        raise ValueError("must not contain null characters")
    return value


# Se usa junto a str_strip_whitespace=True: los espacios sobrantes se quitan antes de medir el largo.
Name = Annotated[
    str,
    Field(min_length=1, max_length=NAME_MAX_LENGTH),
    AfterValidator(_reject_null_characters),
]
