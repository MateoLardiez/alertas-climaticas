"""Errores de dominio. Los services los lanzan sin saber de HTTP; main.py los traduce a respuestas."""

import uuid


class NotFoundError(Exception):
    """Un recurso referenciado no existe."""

    def __init__(self, resource: str, resource_id: uuid.UUID) -> None:
        self.resource = resource
        self.resource_id = resource_id
        super().__init__(f"{resource} {resource_id} not found")
